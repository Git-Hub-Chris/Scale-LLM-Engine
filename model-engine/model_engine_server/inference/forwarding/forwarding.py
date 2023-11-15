import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, List, Optional, Sequence, Tuple

import requests
import sseclient
import yaml
from fastapi.responses import JSONResponse
from model_engine_server.common.dtos.tasks import EndpointPredictV1Request
from model_engine_server.core.loggers import logger_name, make_logger
from model_engine_server.inference.common import get_endpoint_config
from model_engine_server.inference.infra.gateways.datadog_inference_monitoring_metrics_gateway import (
    DatadogInferenceMonitoringMetricsGateway,
)
from model_engine_server.inference.post_inference_hooks import PostInferenceHooksHandler

__all__: Sequence[str] = (
    "Forwarder",
    "LoadForwarder",
    "LoadStreamingForwarder",
    "StreamingForwarder",
)

logger = make_logger(logger_name())

KEY_SERIALIZE_RESULTS_AS_STRING: str = "serialize_results_as_string"

ENV_SERIALIZE_RESULTS_AS_STRING: str = "SERIALIZE_RESULTS_AS_STRING"

DEFAULT_PORT: int = 5005


class ModelEngineSerializationMixin:
    """Mixin class for optionally wrapping Model Engine requests."""

    model_engine_unwrap: bool
    serialize_results_as_string: bool

    def _get_serialize_results_as_string_value(
        self,
        serialize_results_as_string: Optional[bool],
        json_payload: Any,
    ) -> Optional[bool]:
        if serialize_results_as_string is not None:
            return serialize_results_as_string

        elif KEY_SERIALIZE_RESULTS_AS_STRING in json_payload:
            serialize_results_as_string = bool(json_payload[KEY_SERIALIZE_RESULTS_AS_STRING])
            logger.warning(
                f"Found '{KEY_SERIALIZE_RESULTS_AS_STRING}' in payload! "
                f"Overriding {self.serialize_results_as_string=} with "
                f"{serialize_results_as_string=}"
            )

            if not isinstance(serialize_results_as_string, bool):
                logger.error(
                    f"Found {type(serialize_results_as_string)=} but expecting True/False. "
                    f"Ignoring '{KEY_SERIALIZE_RESULTS_AS_STRING} value and using default "
                    f"({self.serialize_results_as_string=})'"
                )
                serialize_results_as_string = self.serialize_results_as_string

            return serialize_results_as_string

        return None

    def unwrap_json_payload(self, json_payload: Any) -> Tuple[Any, bool]:
        # TODO: eventually delete
        serialize_results_as_string: Optional[bool] = None
        # IF we get a feature update in model_engine where it's able to allow a user to
        # request this from the API, then we can determine that here.
        # (NOTE: This is _potential_ future behavior)
        serialize_results_as_string = self._get_serialize_results_as_string_value(
            serialize_results_as_string,
            json_payload,  # type: ignore
        )

        if self.model_engine_unwrap:
            logger.info(f"Unwrapping {json_payload.keys()=}")
            json_payload = json_payload.get("args", json_payload)
            serialize_results_as_string = self._get_serialize_results_as_string_value(
                serialize_results_as_string,
                json_payload,  # type: ignore
            )

        if serialize_results_as_string is None:
            using_serialize_results_as_string: bool = self.serialize_results_as_string
        else:
            using_serialize_results_as_string = serialize_results_as_string

        return json_payload, using_serialize_results_as_string

    @staticmethod
    def get_response_payload(using_serialize_results_as_string: bool, response: Any):
        # Model Engine expects a JSON object with a "result" key.
        if using_serialize_results_as_string:
            response_as_string: str = json.dumps(response)
            return {"result": response_as_string}

        return {"result": response}


@dataclass
class Forwarder(ModelEngineSerializationMixin):
    """Forwards inference requests to another service via HTTP POST.

    Expects this user-defined inference service to be running on localhost. However,
    it is configurable to hit _any_ prediction endpoint via the `predict_endpoint` field.

    Example use in a Python shell:

      >>>> forward = Forwarder("http://localhost:5005/predict", True, False)
      >>>> request = {"your": "custom", "request": "format"}
      >>>> response = forward(request)
      >>>> print(f"Received forwarded response: {response}") # JSON-like result
    """

    predict_endpoint: str
    model_engine_unwrap: bool
    serialize_results_as_string: bool
    post_inference_hooks_handler: PostInferenceHooksHandler
    wrap_response: bool
    forward_http_status: bool

    def __call__(self, json_payload: Any) -> Any:
        request_obj = EndpointPredictV1Request.parse_obj(json_payload)
        json_payload, using_serialize_results_as_string = self.unwrap_json_payload(json_payload)
        json_payload_repr = json_payload.keys() if hasattr(json_payload, "keys") else json_payload

        logger.info(f"Accepted request, forwarding {json_payload_repr=}")

        try:
            response_raw: Any = requests.post(
                self.predict_endpoint,
                json=json_payload,
                headers={
                    "Content-Type": "application/json",
                },
            )
            response = response_raw.json()
        except Exception:
            logger.exception(
                f"Failed to get response for request ({json_payload_repr}) "
                "from user-defined inference service."
            )
            raise
        if isinstance(response, dict):
            logger.info(
                f"Got response from user-defined service: {response.keys()=}, {response_raw.status_code=}"
            )
        elif isinstance(response, list):
            logger.info(
                f"Got response from user-defined service: {len(response)=}, {response_raw.status_code=}"
            )
        else:
            logger.info(
                f"Got response from user-defined service: {response=}, {response_raw.status_code=}"
            )

        if self.wrap_response:
            response = self.get_response_payload(using_serialize_results_as_string, response)

        # TODO: we actually want to do this after we've returned the response.
        self.post_inference_hooks_handler.handle(request_obj, response)
        if self.forward_http_status:
            return JSONResponse(content=response, status_code=response_raw.status_code)
        else:
            return response


@dataclass(frozen=True)
class LoadForwarder:
    """Loader for any user-defined service Forwarder. Default values are suitable for production use.

    NOTE: Currently only implements support for /predict endpoints.
    NOTE: Currently unsupported features that are planned for a later release:
          /batch prediction
          /healthcheck
          GRPC connections to user-defined services
          non-localhost user-defined service address
    """

    user_port: int = DEFAULT_PORT
    user_hostname: str = "localhost"
    use_grpc: bool = False
    predict_route: str = "/predict"
    healthcheck_route: str = "/readyz"
    batch_route: Optional[str] = None
    model_engine_unwrap: bool = True
    serialize_results_as_string: bool = True
    wrap_response: bool = True
    forward_http_status: bool = False

    def load(self, resources: Path, cache: Any) -> Forwarder:
        if self.use_grpc:
            raise NotImplementedError(
                "User-defined service **MUST** use HTTP at the moment. "
                "GRPC support is not implemented yet."
            )

        if self.batch_route is not None:
            raise NotImplementedError(
                "Batch inference support for user-defined services is not currently implemented! "
                "Support is only for single inference requests."
            )

        if len(self.healthcheck_route) == 0:
            raise ValueError("healthcheck route must be non-empty!")

        if len(self.predict_route) == 0:
            raise ValueError("predict route must be non-empty!")

        if not self.healthcheck_route.startswith("/"):
            raise ValueError(f"healthcheck route must start with /: {self.healthcheck_route=}")

        if not self.predict_route.startswith("/"):
            raise ValueError(f"predict route must start with /: {self.predict_route=}")

        if not (1 <= self.user_port <= 65535):
            raise ValueError(f"Invalid port value: {self.user_port=}")

        if len(self.user_hostname) == 0:
            raise ValueError("hostname must be non-empty!")

        if self.user_hostname != "localhost":
            raise NotImplementedError(
                "Currently only localhost-based user-code services are supported with forwarders! "
                f"Cannot handle {self.user_hostname=}"
            )

        def endpoint(route: str) -> str:
            return f"http://{self.user_hostname}:{self.user_port}{route}"

        pred: str = endpoint(self.predict_route)
        hc: str = endpoint(self.healthcheck_route)

        logger.info(f"Forwarding to user-defined service at: {self.user_hostname}:{self.user_port}")
        logger.info(f"Prediction endpoint:  {pred}")
        logger.info(f"Healthcheck endpoint: {hc}")

        while True:
            try:
                if requests.get(hc).status_code == 200:
                    break
            except requests.exceptions.ConnectionError:
                pass

            logger.info(f"Waiting for user-defined service to be ready at {hc}...")
            time.sleep(1)

        logger.info(f"Unwrapping model engine payload formatting?: {self.model_engine_unwrap}")

        logger.info(f"Serializing result as string?: {self.serialize_results_as_string}")
        if ENV_SERIALIZE_RESULTS_AS_STRING in os.environ:
            x = os.environ[ENV_SERIALIZE_RESULTS_AS_STRING].strip().lower()
            if x == "true":
                serialize_results_as_string: bool = True
            elif x == "false":
                serialize_results_as_string = False
            else:
                raise ValueError(
                    f"Unrecognized value for env var '{ENV_SERIALIZE_RESULTS_AS_STRING}': "
                    f"expecting a boolean ('true'/'false') but got '{x}'"
                )
            logger.warning(
                f"Found '{x}' for env var '{ENV_SERIALIZE_RESULTS_AS_STRING}: "
                f"OVERRIDING to new setting {serialize_results_as_string=}"
            )
        else:
            serialize_results_as_string = self.serialize_results_as_string

        endpoint_config = get_endpoint_config()
        handler = PostInferenceHooksHandler(
            endpoint_name=endpoint_config.endpoint_name,
            bundle_name=endpoint_config.bundle_name,
            post_inference_hooks=endpoint_config.post_inference_hooks,
            user_id=endpoint_config.user_id,
            billing_queue=endpoint_config.billing_queue,
            billing_tags=endpoint_config.billing_tags,
            default_callback_url=endpoint_config.default_callback_url,
            default_callback_auth=endpoint_config.default_callback_auth,
            monitoring_metrics_gateway=DatadogInferenceMonitoringMetricsGateway(),
        )

        return Forwarder(
            predict_endpoint=pred,
            model_engine_unwrap=self.model_engine_unwrap,
            serialize_results_as_string=serialize_results_as_string,
            post_inference_hooks_handler=handler,
            wrap_response=self.wrap_response,
            forward_http_status=self.forward_http_status,
        )


@dataclass
class StreamingForwarder(ModelEngineSerializationMixin):
    """Forwards inference requests to another service via HTTP POST.

    Expects this user-defined inference service to be running on localhost. However,
    it is configurable to hit _any_ prediction endpoint via the `predict_endpoint` field.

    Example use in a Python shell:

      >>>> forward = StreamingForwarder("http://localhost:5005/predict", True, False)
      >>>> request = {"your": "custom", "request": "format"}
      >>>> response = forward(request)
      >>>> for r in response:
      >>>>     print(f"Received forwarded response: {r}") # JSON-like result
    """

    predict_endpoint: str
    model_engine_unwrap: bool
    serialize_results_as_string: bool
    post_inference_hooks_handler: PostInferenceHooksHandler  # unused for now

    def __call__(self, json_payload: Any) -> Iterator[Any]:
        json_payload, using_serialize_results_as_string = self.unwrap_json_payload(json_payload)
        json_payload_repr = json_payload.keys() if hasattr(json_payload, "keys") else json_payload

        logger.info(f"Accepted request, forwarding {json_payload_repr=}")

        try:
            response = requests.post(
                self.predict_endpoint,
                json=json_payload,
                headers={
                    "Content-Type": "application/json",
                },
                stream=True,
            )
        except Exception:
            logger.exception(
                f"Failed to get response for request ({json_payload_repr}) "
                "from user-defined inference service."
            )
            raise

        client = sseclient.SSEClient(response)
        for event in client.events():
            yield self.get_response_payload(
                using_serialize_results_as_string, json.loads(event.data)
            )


@dataclass(frozen=True)
class LoadStreamingForwarder:
    """Loader for any user-defined service Forwarder. Default values are suitable for production use.

    NOTE: Currently only implements support for /stream endpoints.
    NOTE: Currently unsupported features that are planned for a later release:
          /batch prediction
          /healthcheck
          GRPC connections to user-defined services
          non-localhost user-defined service address
    """

    user_port: int = DEFAULT_PORT
    user_hostname: str = "localhost"
    use_grpc: bool = False
    predict_route: str = "/predict"
    healthcheck_route: str = "/readyz"
    batch_route: Optional[str] = None
    model_engine_unwrap: bool = True
    serialize_results_as_string: bool = False

    def load(self, resources: Path, cache: Any) -> StreamingForwarder:
        if self.use_grpc:
            raise NotImplementedError(
                "User-defined service **MUST** use HTTP at the moment. "
                "GRPC support is not implemented yet."
            )

        if self.batch_route is not None:
            raise NotImplementedError(
                "Batch inference support for user-defined services is not currently implemented! "
                "Support is only for single inference requests."
            )

        if len(self.healthcheck_route) == 0:
            raise ValueError("healthcheck route must be non-empty!")

        if len(self.predict_route) == 0:
            raise ValueError("predict route must be non-empty!")

        if not self.healthcheck_route.startswith("/"):
            raise ValueError(f"healthcheck route must start with /: {self.healthcheck_route=}")

        if not self.predict_route.startswith("/"):
            raise ValueError(f"predict route must start with /: {self.predict_route=}")

        if not (1 <= self.user_port <= 65535):
            raise ValueError(f"Invalid port value: {self.user_port=}")

        if len(self.user_hostname) == 0:
            raise ValueError("hostname must be non-empty!")

        if self.user_hostname != "localhost":
            raise NotImplementedError(
                "Currently only localhost-based user-code services are supported with forwarders! "
                f"Cannot handle {self.user_hostname=}"
            )

        def endpoint(route: str) -> str:
            return f"http://{self.user_hostname}:{self.user_port}{route}"

        pred: str = endpoint(self.predict_route)
        hc: str = endpoint(self.healthcheck_route)

        logger.info(f"Forwarding to user-defined service at: {self.user_hostname}:{self.user_port}")
        logger.info(f"Prediction endpoint:  {pred}")
        logger.info(f"Healthcheck endpoint: {hc}")

        while True:
            try:
                if requests.get(hc).status_code == 200:
                    break
            except requests.exceptions.ConnectionError:
                pass

            logger.info(f"Waiting for user-defined service to be ready at {hc}...")
            time.sleep(1)

        logger.info(f"Unwrapping model engine payload formatting?: {self.model_engine_unwrap}")

        logger.info(f"Serializing result as string?: {self.serialize_results_as_string}")
        if ENV_SERIALIZE_RESULTS_AS_STRING in os.environ:
            x = os.environ[ENV_SERIALIZE_RESULTS_AS_STRING].strip().lower()
            if x == "true":
                serialize_results_as_string: bool = True
            elif x == "false":
                serialize_results_as_string = False
            else:
                raise ValueError(
                    f"Unrecognized value for env var '{ENV_SERIALIZE_RESULTS_AS_STRING}': "
                    f"expecting a boolean ('true'/'false') but got '{x}'"
                )
            logger.warning(
                f"Found '{x}' for env var '{ENV_SERIALIZE_RESULTS_AS_STRING}: "
                f"OVERRIDING to new setting {serialize_results_as_string=}"
            )
        else:
            serialize_results_as_string = self.serialize_results_as_string

        endpoint_config = get_endpoint_config()
        handler = PostInferenceHooksHandler(
            endpoint_name=endpoint_config.endpoint_name,
            bundle_name=endpoint_config.bundle_name,
            post_inference_hooks=endpoint_config.post_inference_hooks,
            user_id=endpoint_config.user_id,
            billing_queue=endpoint_config.billing_queue,
            billing_tags=endpoint_config.billing_tags,
            default_callback_url=endpoint_config.default_callback_url,
            default_callback_auth=endpoint_config.default_callback_auth,
            monitoring_metrics_gateway=DatadogInferenceMonitoringMetricsGateway(),
        )

        return StreamingForwarder(
            predict_endpoint=pred,
            model_engine_unwrap=self.model_engine_unwrap,
            serialize_results_as_string=serialize_results_as_string,
            post_inference_hooks_handler=handler,
        )


def load_named_config(config_uri, config_overrides=None):
    with open(config_uri, "rt") as rt:
        if config_uri.endswith(".json"):
            return json.load(rt)
        else:
            c = yaml.safe_load(rt)
            if config_overrides:
                _substitute_config_overrides(c, config_overrides)
            if len(c) == 1:
                name = list(c.keys())[0]
                c = c[name]
                if "name" not in c:
                    c["name"] = name
            return c


def _substitute_config_overrides(config: dict, config_overrides: List[str]) -> None:
    """
    Modifies config based on config_overrides.

    config_overrides should be a list of strings of the form `key=value`,
    where `key` can be of the form `key1.key2` to denote a substitution for config[key1][key2]
    (nesting can be arbitrarily deep).
    """
    for override in config_overrides:
        split = override.split("=")
        if len(split) != 2:
            raise ValueError(f"Config override {override} must contain exactly one =")
        key_path, value = split
        try:
            _set_value(config, key_path.split("."), value)
        except Exception as e:
            raise ValueError(f"Error setting {key_path} to {value} in {config}") from e


def _set_value(config: dict, key_path: List[str], value: Any) -> None:
    """
    Modifies config by setting the value at config[key_path[0]][key_path[1]]... to be `value`.
    """
    key = key_path[0]
    if len(key_path) == 1:
        config[key] = value if not value.isdigit() else int(value)
    else:
        if key not in config:
            config[key] = dict()
        _set_value(config[key], key_path[1:], value)
