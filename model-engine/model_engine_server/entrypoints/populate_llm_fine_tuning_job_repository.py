"""
This script initializes the file backing the LLMFineTuneRepository and adds a test template to it

FOR TESTING:
To get the bundle id, print the result of calling
`get_or_create_docker_image_batch_job_bundle(CREATE_FINE_TUNE_DI_BATCH_JOB_BUNDLE_REQUEST, users[0])`
from e2e_test_v1.py

FOR ACTUAL CREATION:
You will need a docker image from the fine-tuning repo. Refer to llm/finetune_pipeline/README.md for instructions.

"""

import argparse
import asyncio

import requests
from model_engine_server.common.config import hmi_config
from model_engine_server.domain.entities.llm_fine_tune_entity import LLMFineTuneTemplate
from model_engine_server.infra.repositories import (
    ABSFileLLMFineTuneRepository,
    S3FileLLMFineTuneRepository,
)

FT_IMAGE_TAG = "00f0edae308d9cd5d9fc24fbd4ee0180e8edc738"

BUNDLE_NAME_BY_MODEL = {
    "7b_or_13b": "fine-tune-upload-safetensors",
    "llama_2_34b": "fine-tune-upload-safetensors-34b",
    "llama_2_70b": "fine-tune-upload-safetensors-70b",
}

DEFAULT_7B_MODEL_CONFIG = {
    "source": "hugging_face",
    "inference_framework": "vllm",
    "inference_framework_image_tag": "latest",
    "num_shards": 1,
    "quantize": None,
    "cpus": 8,
    "memory": "24Gi",
    "storage": "40Gi",
    "gpus": 1,
    "gpu_type": "nvidia-ampere-a10",
    "min_workers": 0,
    "max_workers": 1,
    "per_worker": 10,
    "endpoint_type": "streaming",
}

DEFAULT_13B_MODEL_CONFIG = {
    "source": "hugging_face",
    "inference_framework": "vllm",
    "inference_framework_image_tag": "latest",
    "num_shards": 2,
    "quantize": None,
    "cpus": 16,
    "memory": "48Gi",
    "storage": "80Gi",
    "gpus": 2,
    "gpu_type": "nvidia-ampere-a10",
    "min_workers": 0,
    "max_workers": 1,
    "per_worker": 10,
    "endpoint_type": "streaming",
}

# DEFAULT_34B_MODEL_CONFIG defined below because it depends on cloud_provider

DEFAULT_70B_MODEL_CONFIG = {
    "source": "hugging_face",
    "inference_framework": "vllm",
    "inference_framework_image_tag": "latest",
    "num_shards": 2,
    "quantize": None,
    "cpus": 20,
    "memory": "160Gi",
    "storage": "200Gi",
    "gpus": 2,
    "gpu_type": "nvidia-ampere-a100e",
    "min_workers": 0,
    "max_workers": 1,
    "per_worker": 30,
    "endpoint_type": "streaming",
}


def create_model_bundle(cloud_provider, url, user, model_type, image_tag):
    RESOURCE_REQUESTS_BY_MODEL = {
        "7b_or_13b": {
            "cpus": 40,
            "memory": "160Gi",
            "storage": "94Gi",
            "gpus": 2 if cloud_provider == "azure" else 4,
            "gpu_type": "nvidia-ampere-a10",
        },
        "llama_2_34b": {
            "cpus": 60,
            "memory": "400Gi",
            "storage": "300Gi",
            "gpus": 4,
            "gpu_type": "nvidia-ampere-a100e",
        },
        "llama_2_70b": {
            "cpus": 80,
            "memory": "1000Gi",
            "storage": "500Gi",
            "gpus": 8,
            "gpu_type": "nvidia-ampere-a100e",
        },
    }

    name = BUNDLE_NAME_BY_MODEL[model_type]
    resource_requests = RESOURCE_REQUESTS_BY_MODEL[model_type]

    response = requests.post(
        f"{url}/v1/docker-image-batch-job-bundles",
        json={
            "name": name,
            "image_repository": "spellbook-finetune",
            "image_tag": image_tag,
            "command": [
                "dumb-init",
                "--",
                "ddtrace-run",
                "python",
                "llm/finetune_pipeline/docker_image_fine_tuning_entrypoint.py",
                "--config-file",
                "/launch_reserved/config_file.json",
            ],
            "mount_location": "/launch_reserved/config_file.json",
            "resource_requests": resource_requests,
            "public": True,
        },
        headers={"Content-Type": "application/json"},
        auth=requests.auth.HTTPBasicAuth(user, ""),
    ).json()
    return response["docker_image_batch_job_bundle_id"]


async def main(args):
    cloud_provider = args.cloud_provider
    url = args.url or f"http://model-engine.{hmi_config.gateway_namespace}.svc.cluster.local"
    repository = args.repository or hmi_config.cloud_file_llm_fine_tune_repository
    user = args.user or "test-user"
    initialize_repository = args.initialize_repository

    if repository.startswith("s3://"):
        repo = S3FileLLMFineTuneRepository(file_path=repository)
    elif repository.startswith("azure://") or "blob.core.windows.net" in repository:
        repo = ABSFileLLMFineTuneRepository(file_path=repository)
    else:
        raise ValueError(f"LLM fine-tune repository must be S3 or ABS file; got {repository}")

    # Clears the file. Needed the first time we're populating data
    if initialize_repository:
        await repo.initialize_data()

    lora_7b_or_13b_bun = create_model_bundle(cloud_provider, url, user, "7b_or_13b", FT_IMAGE_TAG)
    print(f"lora_7b_or_13b bundle id: {lora_7b_or_13b_bun}")

    lora_llama_2_34b_bun = create_model_bundle(
        cloud_provider, url, user, "llama_2_34b", FT_IMAGE_TAG
    )
    print(f"lora_34b_bun bundle id: {lora_llama_2_34b_bun}")

    lora_llama_2_70b_bun = create_model_bundle(
        cloud_provider, url, user, "llama_2_70b", FT_IMAGE_TAG
    )
    print(f"llama_2_70b bundle id: {lora_llama_2_70b_bun}")

    await repo.write_job_template_for_model(
        "mpt-7b",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_7B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "mosaicml/mpt-7b",
                "_BASE_MODEL_SHORT": "mpt-7b",
            },
            required_params=[],
        ),
    )
    print("Wrote mpt-7b with lora")

    await repo.write_job_template_for_model(
        "mpt-7b-instruct",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_7B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "mosaicml/mpt-7b-instruct",
                "_BASE_MODEL_SHORT": "mpt-7b-instruct",
            },
            required_params=[],
        ),
    )
    print("Wrote mpt-7b-instruct with lora")

    await repo.write_job_template_for_model(
        "llama-7b",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_7B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "hf-llama-7b",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "llama-7b",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote llama-7b with lora")

    await repo.write_job_template_for_model(
        "llama-2-7b",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_7B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "hf-llama-2-7b",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "llama-2-7b",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote llama-2-7b with lora")

    await repo.write_job_template_for_model(
        "llama-2-7b-chat",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_7B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "hf-llama-2-7b-chat",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "llama-2-7b-chat",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote llama-2-7b-chat with lora")

    await repo.write_job_template_for_model(
        "llama-2-13b",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_13B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "hf-llama-2-13b",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "llama-2-13b",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote llama-2-13b with lora")

    await repo.write_job_template_for_model(
        "llama-2-13b-chat",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_13B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "hf-llama-2-13b-chat",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "llama-2-13b-chat",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote llama-2-13b-chat with lora")

    await repo.write_job_template_for_model(
        "llama-2-70b",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_llama_2_70b_bun,
            launch_endpoint_config=DEFAULT_70B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "hf-llama-2-70b",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "llama-2-70b",  # == create llm endpoint request's model_name
                "max_length": 1024,  # To prevent OOM on 8xA100e
            },
            required_params=[],
        ),
    )
    print("Wrote llama-2-70b with lora")

    await repo.write_job_template_for_model(
        "mistral-7b",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_7B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "mistralai/mistral-7b-v0.1",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "mistral-7b",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote mistral-7b with lora")

    await repo.write_job_template_for_model(
        "mistral-7b-instruct",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_7B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "mistralai/mistral-7b-instruct-v0.1",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "mistral-7b-instruct",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote mistral-7b-instruct with lora")
    await repo.write_job_template_for_model(
        "codellama-7b",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_7B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "codellama-7b",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "codellama-7b",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote codellama-7b with lora")

    await repo.write_job_template_for_model(
        "codellama-7b-instruct",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_7B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "codellama-7b-instruct",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "codellama-7b-instruct",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote codellama-7b-instruct with lora")

    await repo.write_job_template_for_model(
        "codellama-13b",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_13B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "codellama-13b",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "codellama-13b",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote codellama-13b with lora")

    await repo.write_job_template_for_model(
        "codellama-13b-instruct",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_7b_or_13b_bun,
            launch_endpoint_config=DEFAULT_13B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "codellama-13b-instruct",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "codellama-13b-instruct",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote codellama-13b-instruct with lora")

    DEFAULT_34B_MODEL_CONFIG = {
        "source": "hugging_face",
        "inference_framework": "vllm",
        "inference_framework_image_tag": "latest",
        "num_shards": 2 if cloud_provider == "azure" else 4,
        "quantize": None,
        "cpus": 32,
        "memory": "80Gi",
        "storage": "100Gi",
        "gpus": 2 if cloud_provider == "azure" else 4,
        "gpu_type": "nvidia-ampere-a10",
        "min_workers": 0,
        "max_workers": 1,
        "per_worker": 10,
        "endpoint_type": "streaming",
    }

    await repo.write_job_template_for_model(
        "codellama-34b",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_llama_2_34b_bun,
            launch_endpoint_config=DEFAULT_34B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "codellama-34b",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "codellama-34b",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote codellama-34b with lora")

    await repo.write_job_template_for_model(
        "codellama-34b-instruct",
        "lora",
        LLMFineTuneTemplate(
            docker_image_batch_job_bundle_id=lora_llama_2_34b_bun,
            launch_endpoint_config=DEFAULT_34B_MODEL_CONFIG,
            default_hparams={
                "_BASE_MODEL": "codellama-34b-instruct",  # == model_name inside of training script
                "_BASE_MODEL_SHORT": "codellama-34b-instruct",  # == create llm endpoint request's model_name
            },
            required_params=[],
        ),
    )
    print("Wrote codellama-34b-instruct with lora")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process command line arguments.")
    parser.add_argument(
        "--cloud-provider",
        choices=["aws", "azure"],
        help="Cloud provider",
        required=False,
        default="aws",
    )
    parser.add_argument("--url", help="Url to the model-engine gateway", required=False)
    parser.add_argument(
        "--repository", help="Url to the LLM fine-tuning job repository", required=False
    )
    parser.add_argument(
        "--user", help="User ID to create Docker image batch job bundles with", required=False
    )
    parser.add_argument(
        "--initialize-repository", action="store_true", required=False, default=False
    )
    args = parser.parse_args()
    asyncio.run(main(args))
