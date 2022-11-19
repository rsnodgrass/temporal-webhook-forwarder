import logging
import base64
import json
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass

from flask import Request

LOG = logging.getLogger()

DEFAULT_TEMPORAL_ENDPOINT = "localhost:7233"


@dataclass
class TemporalDestination:
    endpoint: str = DEFAULT_TEMPORAL_ENDPOINT
    namespace: str = "default"
    workflow_type: str = None
    task_queue: str = "temporal_webhook_gateway"


# environment variable description for documentation/auto-configuration
@dataclass
class EnvVar:
    var: str = None
    help: str = None
    required: bool = False
    default: str = None


class WebhookCall(metaclass=ABCMeta):
    def __init__(self, config, request: Request):
        self._config = config
        self._request = request

    @property
    @abstractmethod
    def id(self) -> str:
        """
        Identifier used for the workflow instance (ideally idempotency id)
        """
        raise NotImplementedError

    @property
    def request(self):
        return self._request

    @abstractmethod
    def verify(self) -> bool:
        """
        Verify the webhook request is valid and sent from a trusted source.
        """
        raise NotImplementedError

    def headers(self) -> dict:
        """
        Headers from the incoming webhook request that should be passed along to
        the Durable Execution workflow.
        """
        return {"Content-Type": self._request.headers.get("Content-Type")}

    @abstractmethod
    def destination(self) -> TemporalDestination:
        """
        The exact Temporal destination this specific webhook instance should be routed
        """
        return NotImplementedError

    def data(self) -> str:
        """
        The data top be passed to the Temporal destination (can be overridden).
        By default this includes the entire POST body or GET query params.
        """
        request = self._request
        encoding = self._config.encoding

        data = None
        if request.method == "POST":
            # pass JSON natively, but Base64 encode all other data content types
            content_type = request.headers.get("Content-Type")
            LOG.debug("Webhook %s content type %s", self.id, content_type)
            data = request.get_data()

            if content_type in ["application/json"]:
                text = data.decode(encoding)
                data = json.loads(text)
            else:
                # re-encode the date with Base64
                data = base64.b64encode(data).decode(encoding)

        else:
            # convert Flask's MultiDict request params to JSON as the data
            # ... may need to be UTF-8 decoded (Config.encoding)
            LOG.info(request.args)
            data = request.args.to_dict(flat=True)

        return data


class WebhookForwarder(metaclass=ABCMeta):
    """
    Base class definition for all webhook forwarder implementations.
    """

    def __init__(self, config):
        self._config = config

    def env_vars(self) -> list[EnvVar]:
        """
        Return environment vars used by this adapter (for command line help)
        """
        return []

    def destinations(self, filter: WebhookCall = None) -> list[TemporalDestination]:
        """
        The Temporal destinations this forwarder routes requests to, which can be
        filtered to a smaller set given a specific webhook call.
        This is also used during healthchecks.
        """
        return []

    @abstractmethod
    def new_webhook_call(self, request: Request) -> WebhookCall:
        """
        Factory method creating a new WebhookCall specific to a forwarder implementation
        """
        raise NotImplementedError
