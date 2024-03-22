"""
DTOs for LLM APIs.
"""

from typing import Any, Dict, List, Optional

from model_engine_server.common.dtos.model_endpoints import (
    CpuSpecificationType,
    GetModelEndpointV1Response,
    GpuType,
    ModelEndpointType,
    StorageSpecificationType,
)
from model_engine_server.domain.entities import (
    BatchJobStatus,
    CallbackAuth,
    FineTuneHparamValueType,
    LLMFineTuneEvent,
    LLMInferenceFramework,
    LLMSource,
    ModelEndpointStatus,
    Quantization,
)
from pydantic import BaseModel, Field, HttpUrl


class CreateLLMModelEndpointV1Request(BaseModel):
    name: str

    # LLM specific fields
    model_name: str
    source: LLMSource = LLMSource.HUGGING_FACE
    inference_framework: LLMInferenceFramework = LLMInferenceFramework.VLLM
    inference_framework_image_tag: str = "latest"
    num_shards: int = 1
    """
    Number of shards to distribute the model onto GPUs.
    """

    quantize: Optional[Quantization] = None
    """
    Whether to quantize the model.
    """

    checkpoint_path: Optional[str] = None
    """
    Path to the checkpoint to load the model from.
    """

    # General endpoint fields
    metadata: Dict[str, Any]  # TODO: JSON type
    post_inference_hooks: Optional[List[str]]
    endpoint_type: ModelEndpointType = ModelEndpointType.SYNC
    cpus: CpuSpecificationType
    gpus: int
    memory: StorageSpecificationType
    gpu_type: GpuType
    storage: Optional[StorageSpecificationType]
    optimize_costs: Optional[bool]
    min_workers: int
    max_workers: int
    per_worker: int
    labels: Dict[str, str]
    prewarm: Optional[bool]
    high_priority: Optional[bool]
    billing_tags: Optional[Dict[str, Any]]
    default_callback_url: Optional[HttpUrl]
    default_callback_auth: Optional[CallbackAuth]
    public_inference: Optional[bool] = True  # LLM endpoints are public by default.


class CreateLLMModelEndpointV1Response(BaseModel):
    endpoint_creation_task_id: str


class GetLLMModelEndpointV1Response(BaseModel):
    id: str
    """
    The autogenerated ID of the Launch endpoint.
    """

    name: str
    model_name: str
    source: LLMSource
    status: ModelEndpointStatus
    inference_framework: LLMInferenceFramework
    inference_framework_image_tag: Optional[str] = None
    num_shards: Optional[int] = None
    quantize: Optional[Quantization] = None
    checkpoint_path: Optional[str] = None
    spec: Optional[GetModelEndpointV1Response] = None


class ListLLMModelEndpointsV1Response(BaseModel):
    model_endpoints: List[GetLLMModelEndpointV1Response]


class UpdateLLMModelEndpointV1Request(BaseModel):
    # LLM specific fields
    model_name: Optional[str]
    source: Optional[LLMSource]
    inference_framework_image_tag: Optional[str]
    num_shards: Optional[int]
    """
    Number of shards to distribute the model onto GPUs.
    """

    quantize: Optional[Quantization]
    """
    Whether to quantize the model.
    """

    checkpoint_path: Optional[str]
    """
    Path to the checkpoint to load the model from.
    """

    # General endpoint fields
    metadata: Optional[Dict[str, Any]]
    post_inference_hooks: Optional[List[str]]
    cpus: Optional[CpuSpecificationType]
    gpus: Optional[int]
    memory: Optional[StorageSpecificationType]
    gpu_type: Optional[GpuType]
    storage: Optional[StorageSpecificationType]
    optimize_costs: Optional[bool]
    min_workers: Optional[int]
    max_workers: Optional[int]
    per_worker: Optional[int]
    labels: Optional[Dict[str, str]]
    prewarm: Optional[bool]
    high_priority: Optional[bool]
    billing_tags: Optional[Dict[str, Any]]
    default_callback_url: Optional[HttpUrl]
    default_callback_auth: Optional[CallbackAuth]
    public_inference: Optional[bool]


class UpdateLLMModelEndpointV1Response(BaseModel):
    endpoint_creation_task_id: str


# Delete uses the default Launch endpoint APIs.


class CompletionSyncV1Request(BaseModel):
    """
    Request object for a synchronous prompt completion task.
    """

    prompt: str
    max_new_tokens: int
    temperature: float = Field(ge=0.0, le=1.0)
    """
    Temperature of the sampling. Setting to 0 equals to greedy sampling.
    """
    stop_sequences: Optional[List[str]] = None
    """
    List of sequences to stop the completion at.
    """
    return_token_log_probs: Optional[bool] = False
    """
    Whether to return the log probabilities of the tokens.
    """
    presence_penalty: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    """
    Only supported in vllm, lightllm
    Penalize new tokens based on whether they appear in the text so far. 0.0 means no penalty
    """
    frequency_penalty: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    """
    Only supported in vllm, lightllm
    Penalize new tokens based on their existing frequency in the text so far. 0.0 means no penalty
    """
    top_k: Optional[int] = Field(default=None, ge=-1)
    """
    Controls the number of top tokens to consider. -1 means consider all tokens.
    """
    top_p: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    """
    Controls the cumulative probability of the top tokens to consider. 1.0 means consider all tokens.
    """
    include_stop_str_in_output: Optional[bool] = None
    """
    Whether to include the stop strings in output text.
    """
    guided_json: Optional[Dict[str, Any]] = None
    """
    JSON schema for guided decoding.
    """
    guided_regex: Optional[str] = None
    """
    Regex for guided decoding.
    """
    guided_choice: Optional[List[str]] = None
    """
    Choices for guided decoding.
    """


class TokenOutput(BaseModel):
    token: str
    log_prob: float


class CompletionOutput(BaseModel):
    text: str
    num_prompt_tokens: int
    num_completion_tokens: int
    tokens: Optional[List[TokenOutput]] = None


class CompletionSyncV1Response(BaseModel):
    """
    Response object for a synchronous prompt completion task.
    """

    request_id: Optional[str]
    output: Optional[CompletionOutput] = None


class CompletionStreamV1Request(BaseModel):
    """
    Request object for a stream prompt completion task.
    """

    prompt: str
    max_new_tokens: int
    temperature: float = Field(ge=0.0, le=1.0)
    """
    Temperature of the sampling. Setting to 0 equals to greedy sampling.
    """
    stop_sequences: Optional[List[str]] = None
    """
    List of sequences to stop the completion at.
    """
    return_token_log_probs: Optional[bool] = False
    """
    Whether to return the log probabilities of the tokens.
    """
    presence_penalty: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    """
    Only supported in vllm, lightllm
    Penalize new tokens based on whether they appear in the text so far. 0.0 means no penalty
    """
    frequency_penalty: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    """
    Only supported in vllm, lightllm
    Penalize new tokens based on their existing frequency in the text so far. 0.0 means no penalty
    """
    top_k: Optional[int] = Field(default=None, ge=-1)
    """
    Controls the number of top tokens to consider. -1 means consider all tokens.
    """
    top_p: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    """
    Controls the cumulative probability of the top tokens to consider. 1.0 means consider all tokens.
    """
    include_stop_str_in_output: Optional[bool] = None
    """
    Whether to include the stop strings in output text.
    """
    guided_json: Optional[Dict[str, Any]] = None
    """
    JSON schema for guided decoding. Only supported in vllm.
    """
    guided_regex: Optional[str] = None
    """
    Regex for guided decoding. Only supported in vllm.
    """
    guided_choice: Optional[List[str]] = None
    """
    Choices for guided decoding. Only supported in vllm.
    """


class CompletionStreamOutput(BaseModel):
    text: str
    finished: bool
    num_prompt_tokens: Optional[int] = None
    num_completion_tokens: Optional[int] = None
    token: Optional[TokenOutput] = None


class StreamErrorContent(BaseModel):
    error: str
    """Error message."""
    timestamp: str
    """Timestamp of the error."""


class StreamError(BaseModel):
    """
    Error object for a stream prompt completion task.
    """

    status_code: int
    """The HTTP status code of the error."""
    content: StreamErrorContent
    """The error content."""


class CompletionStreamV1Response(BaseModel):
    """
    Response object for a stream prompt completion task.
    """

    request_id: Optional[str]
    output: Optional[CompletionStreamOutput] = None
    error: Optional[StreamError] = None
    """Error of the response (if any)."""


class TokenUsage(BaseModel):
    """
    Token usage for a prompt completion task.
    """

    num_prompt_tokens: Optional[int] = 0
    num_completion_tokens: Optional[int] = 0
    total_duration: Optional[float] = None
    """Includes time spent waiting for the model to be ready."""

    time_to_first_token: Optional[float] = None  # Only for streaming requests

    @property
    def num_total_tokens(self) -> int:
        return (self.num_prompt_tokens or 0) + (self.num_completion_tokens or 0)

    @property
    def total_tokens_per_second(self) -> float:
        return (
            self.num_total_tokens / self.total_duration
            if self.total_duration and self.total_duration > 0
            else 0.0
        )

    @property
    def inter_token_latency(self) -> Optional[float]:  # Only for streaming requests
        if (
            self.time_to_first_token is None
            or self.num_completion_tokens is None
            or self.total_duration is None
        ):
            return None
        if self.num_completion_tokens < 2:
            return 0.0
        return (self.total_duration - self.time_to_first_token) / (self.num_completion_tokens - 1)


class CreateFineTuneRequest(BaseModel):
    model: str
    training_file: str
    validation_file: Optional[str] = None
    # fine_tuning_method: str  # TODO enum + uncomment when we support multiple methods
    hyperparameters: Dict[str, FineTuneHparamValueType]  # validated somewhere else
    suffix: Optional[str] = None
    wandb_config: Optional[Dict[str, Any]] = None
    """
    Config to pass to wandb for init. See https://docs.wandb.ai/ref/python/init
    Must include `api_key` field which is the wandb API key.
    """


class CreateFineTuneResponse(BaseModel):
    id: str


class GetFineTuneResponse(BaseModel):
    id: str = Field(..., description="Unique ID of the fine tune")
    fine_tuned_model: Optional[str] = Field(
        default=None,
        description="Name of the resulting fine-tuned model. This can be plugged into the "
        "Completion API ones the fine-tune is complete",
    )
    status: BatchJobStatus = Field(..., description="Status of the requested fine tune.")


class ListFineTunesResponse(BaseModel):
    jobs: List[GetFineTuneResponse]


class CancelFineTuneResponse(BaseModel):
    success: bool


class GetFineTuneEventsResponse(BaseModel):
    # LLMFineTuneEvent is entity layer technically, but it's really simple
    events: List[LLMFineTuneEvent]


class ModelDownloadRequest(BaseModel):
    model_name: str = Field(..., description="Name of the fine tuned model")
    download_format: Optional[str] = Field(
        default="hugging_face",
        description="Format that you want the downloaded urls to be compatible with. Currently only supports hugging_face",
    )


class ModelDownloadResponse(BaseModel):
    urls: Dict[str, str] = Field(
        ..., description="Dictionary of (file_name, url) pairs to download the model from."
    )


class DeleteLLMEndpointResponse(BaseModel):
    deleted: bool


class CreateBatchCompletionsRequestContent(BaseModel):
    prompts: List[str]
    max_new_tokens: int
    temperature: float = Field(ge=0.0, le=1.0)
    """
    Temperature of the sampling. Setting to 0 equals to greedy sampling.
    """
    stop_sequences: Optional[List[str]] = None
    """
    List of sequences to stop the completion at.
    """
    return_token_log_probs: Optional[bool] = False
    """
    Whether to return the log probabilities of the tokens.
    """
    presence_penalty: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    """
    Only supported in vllm, lightllm
    Penalize new tokens based on whether they appear in the text so far. 0.0 means no penalty
    """
    frequency_penalty: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    """
    Only supported in vllm, lightllm
    Penalize new tokens based on their existing frequency in the text so far. 0.0 means no penalty
    """
    top_k: Optional[int] = Field(default=None, ge=-1)
    """
    Controls the number of top tokens to consider. -1 means consider all tokens.
    """
    top_p: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    """
    Controls the cumulative probability of the top tokens to consider. 1.0 means consider all tokens.
    """


class CreateBatchCompletionsModelConfig(BaseModel):
    model: str
    checkpoint_path: Optional[str] = None
    """
    Path to the checkpoint to load the model from.
    """
    labels: Dict[str, str]
    """
    Labels to attach to the batch inference job.
    """
    num_shards: Optional[int] = 1
    """
    Suggested number of shards to distribute the model. When not specified, will infer the number of shards based on model config.
    System may decide to use a different number than the given value.
    """
    quantize: Optional[Quantization] = None
    """
    Whether to quantize the model.
    """
    seed: Optional[int] = None
    """
    Random seed for the model.
    """


class ToolConfig(BaseModel):
    """
    Configuration for tool use.
    NOTE: this config is highly experimental and signature will change significantly in future iterations.
    """

    name: str
    """
    Name of the tool to use for the batch inference.
    """
    max_iterations: Optional[int] = 10
    """
    Maximum number of iterations to run the tool.
    """
    execution_timeout_seconds: Optional[int] = 60
    """
    Maximum runtime of the tool in seconds.
    """
    should_retry_on_error: Optional[bool] = True
    """
    Whether to retry the tool on error.
    """


class CreateBatchCompletionsRequest(BaseModel):
    """
    Request object for batch completions.
    """

    input_data_path: Optional[str]
    output_data_path: str
    """
    Path to the output file. The output file will be a JSON file of type List[CompletionOutput].
    """
    content: Optional[CreateBatchCompletionsRequestContent] = None
    """
    Either `input_data_path` or `content` needs to be provided.
    When input_data_path is provided, the input file should be a JSON file of type BatchCompletionsRequestContent.
    """
    model_config: CreateBatchCompletionsModelConfig
    """
    Model configuration for the batch inference. Hardware configurations are inferred.
    """
    data_parallelism: Optional[int] = Field(default=1, ge=1, le=64)
    """
    Number of replicas to run the batch inference. More replicas are slower to schedule but faster to inference.
    """
    max_runtime_sec: Optional[int] = Field(default=24 * 3600, ge=1, le=2 * 24 * 3600)
    """
    Maximum runtime of the batch inference in seconds. Default to one day.
    """
    tool_config: Optional[ToolConfig] = None
    """
    Configuration for tool use.
    NOTE: this config is highly experimental and signature will change significantly in future iterations.
    """


class CreateBatchCompletionsResponse(BaseModel):
    job_id: str


class GetBatchCompletionsResponse(BaseModel):
    progress: float
    """
    Progress of the batch inference in percentage from 0 to 100.
    """
    finished: bool
