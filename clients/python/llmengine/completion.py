from typing import AsyncIterable, Iterator, Union

from llmengine.api_engine import APIEngine
from llmengine.data_types import (
    CompletionStreamV1Request,
    CompletionStreamV1Response,
    CompletionSyncV1Request,
    CompletionSyncV1Response,
)


class Completion(APIEngine):
    """
    Completion API. This API is used to generate text completions. The Completions API can be run either
    synchronous or asynchronously (via Python `asyncio`); for each of these modes, you can also choose to
    stream token responses or not.
    """

    @classmethod
    async def acreate(
        cls,
        model_name: str,
        prompt: str,
        max_new_tokens: int = 20,
        temperature: float = 0.2,
        timeout: int = 10,
        stream: bool = False,
    ) -> Union[CompletionSyncV1Response, AsyncIterable[CompletionStreamV1Response]]:
        """
        Create a completion task asynchronously.

        Example without token streaming:
            ```python
            import asyncio
            from llmengine import Completion

            async def main():
                response = await Completion.acreate(
                    model_name="llama-7b",
                    prompt="Hello, my name is",
                    max_new_tokens=10,
                    temperature=0.2,
                )
                print(response.json())

            asyncio.run(main())
            ```

        JSON response:
            ```json
            {
                "status": "SUCCESS",
                "outputs":
                [
                    {
                        "text": "_______, and I am a _____",
                        "num_prompt_tokens": null,
                        "num_completion_tokens": 10
                    }
                ],
                "traceback": null
            }
            ```

        Example with token streaming:
            ```python
            import asyncio
            from llmengine import Completion

            async def main():
                stream = await Completion.acreate(
                    model_name="llama-7b",
                    prompt="why is the sky blue?",
                    max_new_tokens=5,
                    temperature=0.2,
                    stream=True,
                )

                async for response in stream:
                    if response.output:
                        print(response.json())

            asyncio.run(main())
            ```

        JSON responses:
            ```json
            {"status": "SUCCESS", "output": {"text": "\\n", "finished": false, "num_prompt_tokens": null, "num_completion_tokens": 1}, "traceback": null}
            {"status": "SUCCESS", "output": {"text": "I", "finished": false, "num_prompt_tokens": null, "num_completion_tokens": 2}, "traceback": null}
            {"status": "SUCCESS", "output": {"text": " think", "finished": false, "num_prompt_tokens": null, "num_completion_tokens": 3}, "traceback": null}
            {"status": "SUCCESS", "output": {"text": " the", "finished": false, "num_prompt_tokens": null, "num_completion_tokens": 4}, "traceback": null}
            {"status": "SUCCESS", "output": {"text": " sky", "finished": true, "num_prompt_tokens": null, "num_completion_tokens": 5}, "traceback": null}
            ```


        Args:
            model_name (str):
                Model name to use for inference
            prompt (str):
                Input text
            max_new_tokens (int):
                Maximum number of generated tokens
            temperature (float):
                The value used to module the logits distribution.
            timeout (int):
                Timeout in seconds
            stream (bool):
                Whether to stream the response. If true, the return type is an
                `Iterator[CompletionStreamV1Response]`.

        Returns:
            response (Union[CompletionSyncV1Response, AsyncIterable[CompletionStreamV1Response]]): generated response or iterator of response chunks
        """
        if stream:

            async def _acreate_stream(
                **kwargs,
            ) -> AsyncIterable[CompletionStreamV1Response]:
                data = CompletionStreamV1Request(**kwargs).dict()
                response = cls.apost_stream(
                    resource_name=f"v1/llm/completions-stream?model_endpoint_name={model_name}",
                    data=data,
                    timeout=timeout,
                )
                async for chunk in response:
                    yield CompletionStreamV1Response.parse_obj(chunk)

            return _acreate_stream(
                model_name=model_name,
                prompt=prompt,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                timeout=timeout,
            )

        else:

            async def _acreate_sync(**kwargs) -> CompletionSyncV1Response:
                data = CompletionSyncV1Request(**kwargs).dict()
                response = await cls.apost_sync(
                    resource_name=f"v1/llm/completions-sync?model_endpoint_name={model_name}",
                    data=data,
                    timeout=timeout,
                )
                return CompletionSyncV1Response.parse_obj(response)

            return await _acreate_sync(
                prompts=[prompt], max_new_tokens=max_new_tokens, temperature=temperature
            )

    @classmethod
    def create(
        cls,
        model_name: str,
        prompt: str,
        max_new_tokens: int = 20,
        temperature: float = 0.2,
        timeout: int = 10,
        stream: bool = False,
    ) -> Union[CompletionSyncV1Response, Iterator[CompletionStreamV1Response]]:
        """
        Create a completion task synchronously.

        Example request without token streaming:
            ```python
            from llmengine import Completion

            response = Completion.create(
                model_name="llama-7b",
                prompt="Hello, my name is",
                max_new_tokens=10,
                temperature=0.2,
            )
            print(response.json())
            ```

        JSON Response:
            ```json
            {
                "status": "SUCCESS",
                "outputs":
                [
                    {
                        "text": "_______ and I am a _______",
                        "num_prompt_tokens": null,
                        "num_completion_tokens": 10
                    }
                ],
                "traceback": null
            }
            ```

        Example request with token streaming:
            ```python
            from llmengine import Completion

            stream = Completion.create(
                model_name="llama-7b",
                prompt="why is the sky blue?",
                max_new_tokens=5,
                temperature=0.2,
                stream=True,
            )

            for response in stream:
                if response.output:
                    print(response.json())
            ```

        JSON responses:
            ```json
            {"status": "SUCCESS", "output": {"text": "\\n", "finished": false, "num_prompt_tokens": null, "num_completion_tokens": 1 }, "traceback": null }
            {"status": "SUCCESS", "output": {"text": "I", "finished": false, "num_prompt_tokens": null, "num_completion_tokens": 2 }, "traceback": null }
            {"status": "SUCCESS", "output": {"text": " don", "finished": false, "num_prompt_tokens": null, "num_completion_tokens": 3 }, "traceback": null }
            {"status": "SUCCESS", "output": {"text": "’", "finished": false, "num_prompt_tokens": null, "num_completion_tokens": 4 }, "traceback": null }
            {"status": "SUCCESS", "output": {"text": "t", "finished": true, "num_prompt_tokens": null, "num_completion_tokens": 5 }, "traceback": null }
            ```

        Args:
            model_name (str):
                Model name to use for inference
            prompt (str):
                Input text
            max_new_tokens (int):
                Maximum number of generated tokens
            temperature (float):
                The value used to module the logits distribution.
            timeout (int):
                Timeout in seconds
            stream (bool):
                Whether to stream the response. If true, the return type is an `Iterator`.

        Returns:
            response (Union[CompletionSyncV1Response, Iterator[CompletionStreamV1Response]]): generated response or iterator of response chunks
        """
        if stream:

            def _create_stream(**kwargs):
                data_stream = CompletionStreamV1Request(**kwargs).dict()
                response_stream = cls.post_stream(
                    resource_name=f"v1/llm/completions-stream?model_endpoint_name={model_name}",
                    data=data_stream,
                    timeout=timeout,
                )
                for chunk in response_stream:
                    yield CompletionStreamV1Response.parse_obj(chunk)

            return _create_stream(
                prompt=prompt, max_new_tokens=max_new_tokens, temperature=temperature
            )

        else:
            data = CompletionSyncV1Request(
                prompts=[prompt], max_new_tokens=max_new_tokens, temperature=temperature
            ).dict()
            response = cls.post_sync(
                resource_name=f"v1/llm/completions-sync?model_endpoint_name={model_name}",
                data=data,
                timeout=timeout,
            )
            return CompletionSyncV1Response.parse_obj(response)
