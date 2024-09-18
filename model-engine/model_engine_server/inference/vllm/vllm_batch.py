import argparse
import asyncio
import json
import os
import subprocess
from typing import Any, AsyncGenerator, AsyncIterator, Coroutine, Dict, List, Optional, Union

import smart_open
from model_engine_server.common.dtos.llms import (
    BatchCompletionContent,
    BatchCompletionsModelConfig,
    CompletionResponse,
    CompletionV1Output,
    CreateBatchCompletionsEngineRequest,
    CreateBatchCompletionsV1RequestContent,
    TokenOutput,
)
from model_engine_server.inference.infra.gateways.datadog_inference_monitoring_metrics_gateway import (
    DatadogInferenceMonitoringMetricsGateway,
)
from model_engine_server.inference.utils import (
    await_coroutines,
    check_unknown_startup_memory_usage,
    get_cpu_cores_in_container,
    random_uuid,
)
from pydantic import TypeAdapter
from tqdm import tqdm
from typing_extensions import TypeAlias, assert_never
from vllm import AsyncEngineArgs, AsyncLLMEngine, RequestOutput, SamplingParams
from vllm.engine.protocol import AsyncEngineClient
from vllm.entrypoints.openai.protocol import ChatCompletionRequest, CompletionRequest, ErrorResponse
from vllm.entrypoints.openai.serving_chat import OpenAIServingChat
from vllm.entrypoints.openai.serving_completion import OpenAIServingCompletion
from vllm.utils import merge_async_iterators

CONFIG_FILE = os.getenv("CONFIG_FILE")
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
MODEL_WEIGHTS_FOLDER = os.getenv("MODEL_WEIGHTS_FOLDER", "./model_weights")

SKIP_AWS_PROFILE_SET = os.getenv("SKIP_AWS_PROFILE_SET", "false").lower() == "true"
if not SKIP_AWS_PROFILE_SET:
    os.environ["AWS_PROFILE"] = os.getenv("S3_WRITE_AWS_PROFILE", "default")


openai_serving_chat: OpenAIServingChat
openai_serving_completion: OpenAIServingCompletion

CPU_COUNT = get_cpu_cores_in_container()

_BatchCompletionContent: TypeAlias = Union[
    CreateBatchCompletionsV1RequestContent,
    List[CompletionRequest],
    List[ChatCompletionRequest],
]


async def download_model(checkpoint_path: str, target_dir: str) -> None:
    s5cmd = f"./s5cmd --numworkers 512 sync --concurrency 10 --include '*.model' --include '*.json' --include '*.bin' --include '*.safetensors' --exclude 'optimizer*' --exclude 'train*' {os.path.join(checkpoint_path, '*')} {target_dir}"
    env = os.environ.copy()
    env["AWS_PROFILE"] = os.getenv("S3_WRITE_AWS_PROFILE", "default")
    # Need to override these env vars so s5cmd uses AWS_PROFILE
    env["AWS_ROLE_ARN"] = ""
    env["AWS_WEB_IDENTITY_TOKEN_FILE"] = ""
    process = subprocess.Popen(
        s5cmd,
        shell=True,  # nosemgrep
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    if process.stdout:
        for line in process.stdout:
            print(line, flush=True)

    process.wait()

    if process.returncode != 0 and process.stderr:
        stderr_lines = []
        for line in iter(process.stderr.readline, ""):
            stderr_lines.append(line.strip())

        print(f"Error downloading model weights: {stderr_lines}", flush=True)


async def generate_v1_completions(
    engine: AsyncEngineClient,
    content: CreateBatchCompletionsV1RequestContent,
) -> List[Optional[CompletionV1Output]]:
    prompts = content.prompts
    bar = tqdm(total=len(prompts), desc="Processed prompts")
    sampling_params = SamplingParams(
        max_tokens=content.max_new_tokens,
        temperature=content.temperature,
        stop=content.stop_sequences,
        logprobs=1 if content.return_token_log_probs else None,
        presence_penalty=content.presence_penalty or 0.0,
        frequency_penalty=content.frequency_penalty or 0.0,
        top_k=content.top_k or -1,
        top_p=content.top_p or 1.0,
        skip_special_tokens=(
            content.skip_special_tokens if content.skip_special_tokens is not None else True
        ),
    )

    results_generators: List[AsyncIterator[RequestOutput]] = []
    for prompt in prompts:
        request_id = random_uuid()
        results_generator = engine.generate(
            prompt,
            sampling_params=sampling_params,
            request_id=request_id,
        )
        results_generators.append(results_generator)

    return_token_log_probs = True

    generator = merge_async_iterators(*results_generators)
    outputs: List[Optional[CompletionV1Output]] = [None] * len(prompts)
    tokens: List[List[TokenOutput]] = [list() for _ in prompts]
    async for i, res in generator:
        # There should only be one output
        output = res.outputs[-1]

        if return_token_log_probs and output.logprobs is not None:
            # Sometime the logprobs are not present in the output
            logprobs = output.logprobs[-1]
            for token_id in logprobs.keys():
                tokens[i].append(
                    TokenOutput(
                        token=logprobs[token_id].decoded_token,
                        log_prob=logprobs[token_id].logprob,
                    )
                )

        if res.finished:
            outputs[i] = CompletionV1Output(
                text=output.text,
                num_prompt_tokens=len(res.prompt_token_ids),
                num_completion_tokens=len(output.token_ids),
                tokens=[
                    token.model_dump() for token in tokens[i]
                ],  # Not sure why, but pydantic doesn't like when I pass it TokenOutput directly but works when I encode it as a dict...
            )
            bar.update(1)

    return outputs


async def generate_v2_completions(
    engine: AsyncEngineClient,
    requests: Union[List[CompletionRequest], List[ChatCompletionRequest]],
) -> List[Union[CompletionResponse, ErrorResponse, None]]:
    bar = tqdm(total=len(requests), desc="Processed requests")
    results_generators: List[
        Coroutine[
            Any,
            Any,
            Union[ErrorResponse, AsyncGenerator[str, None], CompletionResponse],
        ]
    ] = []
    for request in requests:
        if isinstance(request, CompletionRequest):
            results_generators.append(openai_serving_completion.create_completion(request))
        elif isinstance(request, ChatCompletionRequest):
            results_generators.append(openai_serving_chat.create_chat_completion(request))
        else:
            assert_never(request)

    results_generator = await_coroutines(*results_generators)
    outputs: List[Optional[CompletionResponse]] = [None] * len(requests)

    async for i, res in results_generator:
        if isinstance(res, AsyncGenerator):
            continue
        outputs[i] = res
        bar.update(1)
    return outputs


async def generate_completions(
    engine: AsyncEngineClient, request: _BatchCompletionContent
) -> Union[List[Optional[CompletionV1Output]], List[Optional[CompletionResponse]]]:
    if isinstance(request, CreateBatchCompletionsV1RequestContent):
        return await generate_v1_completions(engine, request)
    elif isinstance(request, List):
        return await generate_v2_completions(engine, request)
    else:
        assert_never(request)


async def init_engine(
    model: str,
    request: CreateBatchCompletionsEngineRequest,
) -> AsyncEngineClient:
    global openai_serving_chat
    global openai_serving_completion

    if request.attention_backend is not None:
        os.environ["ATTENTION_BACKEND"] = request.attention_backend

    engine_args = AsyncEngineArgs(
        model=model,
        tensor_parallel_size=request.model_cfg.num_shards,
        seed=request.model_cfg.seed or 0,
        disable_log_requests=True,
        gpu_memory_utilization=request.max_gpu_memory_utilization or 0.9,
        max_model_len=request.model_cfg.max_context_length,
    )

    async_engine_client = AsyncLLMEngine.from_engine_args(engine_args)
    model_config = await async_engine_client.get_model_config()
    served_model_names = [model]

    openai_serving_chat = OpenAIServingChat(
        async_engine_client,
        model_config,
        served_model_names,
        response_role=request.model_cfg.response_role or "assistant",
        lora_modules=None,
        prompt_adapters=None,
        request_logger=None,
        chat_template=None,
    )

    openai_serving_completion = OpenAIServingCompletion(
        async_engine_client,
        model_config,
        served_model_names,
        lora_modules=None,
        prompt_adapters=None,
        request_logger=None,
    )

    return async_engine_client


def overwrite_request(request: Dict[str, Any], model: str) -> Dict[str, Any]:
    request["model"] = model
    request["stream"] = False
    return request


def load_batch_content(
    request: CreateBatchCompletionsEngineRequest,
) -> _BatchCompletionContent:
    content = request.content
    if content is None:
        with smart_open.open(request.input_data_path, "r") as f:
            data = json.load(f)
            content = TypeAdapter(BatchCompletionContent).validate_python(data)

    # Recast the content to vLLMs schema
    if isinstance(content, List) and len(content) > 0:
        model = get_model_name(request.model_cfg)
        return TypeAdapter(
            Union[List[CompletionRequest], List[ChatCompletionRequest]]
        ).validate_python(
            [overwrite_request(req.model_dump(exclude_none=True), model) for req in content]
        )

    return content


def get_model_name(model_config: BatchCompletionsModelConfig) -> str:
    return MODEL_WEIGHTS_FOLDER if model_config.checkpoint_path else model_config.model


async def handle_batch_job(request: CreateBatchCompletionsEngineRequest) -> None:
    metrics_gateway = DatadogInferenceMonitoringMetricsGateway()

    model = get_model_name(request.model_cfg)

    if request.model_cfg.checkpoint_path:
        await download_model(
            checkpoint_path=request.model_cfg.checkpoint_path,
            target_dir=MODEL_WEIGHTS_FOLDER,
        )

    content = load_batch_content(request)
    engine = await init_engine(
        model,
        request=request,
    )

    outputs = await generate_completions(engine, content)
    with smart_open.open(request.output_data_path, "w") as f:
        f.write(json.dumps([output.model_dump() if output else None for output in outputs]))

    metrics_gateway.emit_batch_completions_metric(
        model,
        use_tool=False,
        num_prompt_tokens=0,
        num_completion_tokens=0,
        is_finetuned=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config-file-data",
        "--config_file_data",
        type=str,
        default=None,
        help="Optional override for the config file data, as a json string",
    )

    args = parser.parse_args()

    check_unknown_startup_memory_usage()

    config_file_data = args.config_file_data
    if config_file_data is None:
        if CONFIG_FILE is None or not os.path.exists(CONFIG_FILE):
            raise FileNotFoundError(f"Config file {CONFIG_FILE} not found")
        with open(CONFIG_FILE, "r") as f:
            config_file_data = f.read()

    request = CreateBatchCompletionsEngineRequest.model_validate_json(config_file_data)

    asyncio.run(handle_batch_job(request))
