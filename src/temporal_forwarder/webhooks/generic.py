# Generic forwarding of webhooks to Temporal without any validation of
# the data being passed. This should probably NOT be used on a production
# server that is open to all traffic since it does not verify any data
# and always enqueues data from any HTTP GET/POST request.

import logging
import uuid

from flask import Request

from .. import TemporalDestination, WebhookCall, WebhookForwarder

DEFAULT_TEMPORAL_WORKFLOW = "GenericWebhook"
DEFAULT_TASK_QUEUE = "generic_webhooks"

LOG = logging.getLogger()


class GenericForwarder(WebhookForwarder):
    def __init__(self, config):
        super().__init__(config)

    def destinations(self, filter: WebhookCall = None) -> list[TemporalDestination]:
        """
        Which Temporal destinations webhooks should be enqueued
        """
        return [
            TemporalDestination(
                self._config.temporal_endpoint,
                self._config.temporal_namespace,
                DEFAULT_TEMPORAL_WORKFLOW,
                DEFAULT_TASK_QUEUE,
            )
        ]

    def new_webhook_call(self, request: Request) -> WebhookCall:
        """
        Factory method creating a new WebhookCall
        """
        forwarder = self
        return GenericWebhook(self._config, request, forwarder)


class GenericWebhook(WebhookCall):
    def __init__(self, config, request, forwarder):
        super().__init__(config, request)
        self._forwarder = forwarder
        self._id = None

        # if a "standard" request id header exists, use that as the id
        for header in ["X-Request-ID"]:
            id = request.headers.get(header)
            if id:
                self._id = id
                LOG.debug("Using %s id %s", header, id)
                break

        # if no id from the caller in webhook request, generate a random ID
        if not self._id:
            self._id = str(uuid.uuid4())

    @property
    def id(self) -> str:
        return self._id

    def verify(self) -> bool:
        return True

    def destination(self) -> TemporalDestination:
        return self._forwarder.destinations()[0]

    def headers(self) -> dict:
        """
        For Generic webhooks, just include all HTTP headers when forwarding.
        """
        headers = {}
        for key, value in self._request.headers.items():
            headers[key] = value
        return headers
