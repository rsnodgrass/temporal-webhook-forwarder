# Shopify specific webhook logic, including any validation of signatures
# or client authentication.
#
# See:
# https://hookdeck.com/webhooks/platforms/shopify-webhooks-features-and-best-practices-guide
#
# NOTE:
# * If an incoming webhook notification is not responded to within Shopify's five-second
#   window, it times out

import logging
import base64
import hashlib
import hmac
import os
from http import HTTPStatus

from flask import Request, Response, abort

from temporal_forwarder import EnvVar, TemporalDestination
from temporal_forwarder.webhook import WebhookCall, WebhookForwarder


X_SHOPIFY_API_VERSION = "X-Shopify-API-Version"
X_SHOPIFY_HMAC_SHA256 = "X-Shopify-Hmac-SHA256"
X_SHOPIFY_SHOP_DOMAIN = "X-Shopify-Shop-Domain"
X_SHOPIFY_STAGE = "X-Shopify-Stage"
X_SHOPIFY_TEST = "X-Shopify-Test"
X_SHOPIFY_TOPIC = "X-Shopify-Topic"
X_SHOPIFY_WEBHOOK_ID = "X-Shopify-Webhook-Id"

DEFAULT_SHOPIFY_TEMPORAL_WORKFLOW = "ShopifyWebhook"
DEFAULT_SHOPIFY_TASK_QUEUE = "shopify_webhooks"

LOG = logging.getLogger()


class ShopifyForwarder(WebhookForwarder):
    def __init__(self, config):
        super().__init__(config)

        self._secret_key = os.environ.get("SHOPIFY_WEBHOOKS_KEY")
        if not self._secret_key:  # FIXME: unless validate_hmac disabled
            raise Exception(
                "Must define SHOPIFY_WEBHOOKS_KEY env var "
                + "to verify Shopify data signatures"
            )

    def env_vars(self) -> list[EnvVar]:
        """
        Return environment vars used by this forwarder (for command line help)
        """
        return [
            EnvVar(
                var="SHOPIFY_WEBHOOKS_KEY",
                help="Shopify provided key to validate webhook data HMAC",
                required=True,
            )
        ]

    def destinations(self, filter: WebhookCall = None) -> list[TemporalDestination]:
        """
        Which Temporal destinations this Shopify webhook should be added to (currently
        only supports a SINGLE destination)
        """
        return [
            TemporalDestination(
                self._config.temporal_endpoint,
                self._config.temporal_namespace,
                DEFAULT_SHOPIFY_TEMPORAL_WORKFLOW,
                DEFAULT_SHOPIFY_TASK_QUEUE,
            )
        ]

    def new_webhook_call(self, request: Request) -> WebhookCall:
        """
        Factory method creating a new WebhookCall specific to Shopify
        """
        forwarder = self
        return ShopifyWebhook(self._config, request, forwarder)


class ShopifyWebhook(WebhookCall):
    def __init__(self, config, request, forwarder):
        super().__init__(config, request)
        self._forwarder = forwarder

        if request.method != "POST":
            LOG.error(f"Only Shopify POST webhooks supported")
            abort(Response("FAILED", HTTPStatus.BAD_REQUEST))

        # Assign the Temporal workflow_id = X-Shopify-Webhook-Id used by Shopify
        # to indicate duplicate attempts of the same instance of a webhook
        # being retried.
        #
        # NOTE: Configure the Temporal service to only allow a single active
        # workflow_id per task queue to ensure identical events sent from Shopify
        # aren't unnecessarily processed multiple times.
        self._id = request.headers.get(X_SHOPIFY_WEBHOOK_ID)
        if not self._id:
            msg = (
                f"Missing {X_SHOPIFY_WEBHOOK_ID} header for {request.base_url} – DROPPING"
            )
            LOG.error(msg)
            abort(Response(msg, HTTPStatus.BAD_REQUEST))

    @property
    def id(self) -> str:
        return self._id

    def verify(self) -> bool:
        """
        Verify the request data is untampered and actually from Shopify for
        the specified Store.

        See https://shopify.dev/apps/webhooks/configuration/https#step-5-verify-the-webhook
        (NOTE: Shopify provides no way to verify headers are untampered with)
        """
        request = self._request
        hmac_header = request.headers.get(X_SHOPIFY_HMAC_SHA256)
        if not hmac_header:
            msg = f"Missing {X_SHOPIFY_HMAC_SHA256} header for {request.base_url} – DROPPING (id={webhook.id})"
            LOG.error(msg)
            abort(Response(msg, HTTPStatus.BAD_REQUEST))

        key = self._forwarder._secret_key.encode("utf-8")
        digest = hmac.new(key, request.get_data(), digestmod=hashlib.sha256).digest()
        computed_hmac = base64.b64encode(digest)
        return hmac.compare_digest(computed_hmac, hmac_header.encode("utf-8"))

    def headers(self) -> str:
        """
        Include all the X-Shopify-* HTTP headers along in the payload
        so Temporal workers can access them (for example to re-verify
        the data signature via the HMAC).
        """
        headers = super().headers()
        for header, value in self.request.headers.items():
            if header.startswith("X-Shopify-"):
                headers[header] = value
        return headers

    def destination(self) -> TemporalDestination:
        return TemporalDestination(
            self._config.temporal_endpoint,
            self._config.temporal_namespace,
            DEFAULT_SHOPIFY_TEMPORAL_WORKFLOW,
            DEFAULT_SHOPIFY_TASK_QUEUE,
        )
