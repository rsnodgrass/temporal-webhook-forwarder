#!/usr/bin/env python3

import logging
import argparse
import asyncio
import dataclasses
import importlib
import os
import pkgutil
import sys
from dataclasses import dataclass
from http import HTTPStatus

# import hydra
# from omegaconf import DictConfig, OmegaConf
import temporalio
import uvloop
from flask import Flask, Response, abort, json, request
from temporalio.client import Client

from temporal_forwarder import *
from temporal_forwarder.codec import EncryptionCodec

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOG = logging.getLogger()

app = Flask(__name__)

TEMPORAL_CLIENT = None

WEBHOOK_FORWARDERS = {}
#    "generic": temporal_forwarder.webhooks.forwarder_generic.GenericForwarder
#    "shopify": temporal_forwarder.webhooks.forwarder_shopify.ShopifyForwarder
#    'shippo': temporal_forwarder.webhooks.forwarder_shippo.ShippoForwarder
#    'shipstation': temporal_forwarder.webhooks.forwarder_shipstation.ShipstationForwarder

# dumb configuration mechanism, really should use hydra, Dynaconf or dotenv
@dataclass
class Config:
    temporal_endpoint: str = DEFAULT_TEMPORAL_ENDPOINT
    temporal_namespace: str = "default"
    validate_hmac: bool = True
    global_task_queue: bool = True
    ssl_cert: str = "fullchain.pem"
    ssl_key: str = "privkey.pem"
    fail_on_fatal: bool = True
    encoding: str = "utf-8"


@app.route("/")
@app.route("/temporal")
async def healthcheck():
    # If all Temporal endpoints are alive and accepting workflows, the
    # forwarder is considered healthy. However, if even ONE endpoint
    # fails (even if others are alive) this still reports unhealthy.
    temporal_endpoints = {"default": TEMPORAL_CLIENT}

    # add all Temporal endpoints in use by the forwarders to the healthcheck list
    for slug, forwarder in WEBHOOK_FORWARDERS.items():
        for dest in forwarder.destinations():
            temporal_endpoints[slug] = dest.endpoint

    checked_endpoints = {}
    for slug, endpoint in temporal_endpoints.items():
        try:
            # only check each physical Temporal endpoint once (e.g. multiple
            # forwarders can share the same Temporal instance)
            if not endpoint in checked_endpoints:
                # FIXME: do some sort of keep-alive check against the client for this endpoint
                checked_endpoints[endpoint] = [slug]
            else:
                checked_endpoints[endpoint].append(slug)
        except Exception as e:
            LOG.warning(f"Temporal {endpoint} for {slug} failed health check", e)
            return ("FAILED", HTTPStatus.SERVICE_UNAVAILABLE)  # 503

    return ("OK", HTTPStatus.OK)  # 200


# Example: https://temporal-webhook.mydomain.com:5000/temporal/shopify
@app.route("/temporal/<forwarder_slug>", methods=["POST", "GET"])
async def forward_webhook(forwarder_slug):
    forwarder = WEBHOOK_FORWARDERS.get(forwarder_slug)
    if not forwarder:
        LOG.debug("Ignoring request for unknown forwarder {forwarder_slug}")
        return ("", HTTPStatus.NOT_IMPLEMENTED)  # 501

    # create a new webhook object for the request
    webhook = forwarder.new_webhook_call(request)

    # inject additional meta-data useful for debugging in workflow/activities
    headers = webhook.headers()
    headers |= {
        "X-Webhook-Route": forwarder_slug,
        "X-Webhook-Method": request.method,
        #'X-Webhook-Time': now
    }

    # verify the webhook request is valid
    if webhook.verify():
        headers["X-Webhook-Verified"] = "True"
    else:
        msg = f"Webhook {forwarder_slug} {webhook.id} failed verification"
        if Config.validate_hmac:
            msg += " – DROPPING EVENT"
            LOG.error(msg)
            abort(Response(msg, HTTPStatus.UNAUTHORIZED))
        else:
            msg + " – PROCESSING ANYWAY!!!"
            LOG.warning(msg)

    # if there is absolutely no data to provide, skip enqueuing the webhook
    data = webhook.data()
    if not data or data == "{}":
        LOG.warning(f"No data for webhook {forwarder_slug} {webhook.id} - SKIPPING")
        return ("", HTTPStatus.BAD_REQUEST)

    # create the JSON webhook payload that will be passed to execution
    temporal_payload = json.dumps({"headers": headers, "data": data})
    LOG.debug(f"Webhook {webhook.id}: %s", temporal_payload)

    # start_workflow ONLY returns if durable execution actually started
    await start_workflow(webhook, temporal_payload)

    # include the webhook.id used to enqueue to Temporal in the response
    return (webhook.id, HTTPStatus.OK)


# NOTE: Temporal task queues should typically be configured to allow only ONE
# instance of a workflow_id active at a time
async def start_workflow(webhook: WebhookCall, payload):
    for dest in [webhook.destination()]:
        try:
            # NOTE: this really should start on as many destinations as possible and
            # then abort if any error occured (to give a chance of success to later
            # destinations in the list.
            LOG.info(
                f"Starting {dest.workflow_type} {webhook.id} on queue {dest.task_queue}"
            )
            handle = await TEMPORAL_CLIENT.start_workflow(
                dest.workflow_type,
                payload,
                # namespace=destination.namespace, # NOT SUPPORTED
                task_queue=dest.task_queue,
                id=webhook.id,
            )
            return handle

        except Exception as e:
            msg = f"Failed starting workflow {webhook.id} on queue {dest.task_queue} (exception {e})"
            LOG.error(msg)
            abort(Response(msg, HTTPStatus.FAILED_DEPENDENCY))


async def start_temporal_forwarder(host: str, port: int):
    # use Temporal's unencrypted default data converter (unless overridden later)
    data_converter = temporalio.converter.default()

    # if AES_KEY env var is specified, enable payload encryption
    aes_key = os.environ.get("AES_KEY")
    if aes_key:
        # enable payload encryption codec for the existing data converter
        data_converter = dataclasses.replace(
            temporalio.converter.default(),
            payload_codec=EncryptionCodec(
                key_id=os.environ.get("AES_KEY_ID", "unnamed-key"),
                key=bytes.fromhex(aes_key),
            ),
        )
    else:
        LOG.warning("Payload encryption is NOT enabled (set AES_KEY env var)")

    LOG.info(
        f"Using Temporal endpoint {Config.temporal_endpoint} (namespace {Config.temporal_namespace})"
    )
    global TEMPORAL_CLIENT
    TEMPORAL_CLIENT = await Client.connect(
        Config.temporal_endpoint, data_converter=data_converter
    )

    # run Flask app until complete
    await app.run(
        host=host, port=port, debug=True, ssl_context=(Config.ssl_cert, Config.ssl_key)
    )


def discover_webhook_forwarders():
    """
    Forwarders use the naming convention forwarder_{plugin_name} by convention and will auto-load
    any of the modules discovered based on this. However, these are ONLY ACTIVATED when the
    correct configuration is added that enables routing/temporal/<slug> to a forwarder.
    """
    plugin_dir = os.getcwd() + "/temporal_forwarder/webhooks"
    LOG.debug(f"Searching for forwarder plugins in {plugin_dir}")

    discovered_plugins = {
        name: importlib.import_module("temporal_forwarder.webhooks." + name)
        for finder, name, ispkg in pkgutil.iter_modules(path=[plugin_dir])
        if name.startswith("webhook_")
    }
    print(f"Discovered forwarder plugins: {discovered_plugins}")


def register_webhook_forwarder(
    forwarder_route: str, module_class_name: str, config: Config
):
    """
    Register an WebhookForwarder to a specific externally exposed webhook route
    """
    try:
        module_name, class_name = module_class_name.rsplit(".", 1)
        forwarder_class = getattr(importlib.import_module(module_name), class_name)
        WEBHOOK_FORWARDERS[forwarder_route] = forwarder_class(config)
    except Exception as e:
        LOG.fatal(f"Could not register route {forwarder_route} {class_name}: {e}")
        if Config.fail_on_fatal:
            sys.exit(1)


def env_help():
    """
    Create help string showing env variables used by this application. This extends what argparse
    displays beyond just direct command line arguments.
    """
    help = ""
    for route, forwarder in WEBHOOK_FORWARDERS.items():
        env_vars = forwarder.env_vars()
        if env_vars:
            help += f"{route} env vars:\n"
            for v in env_vars:
                help += f" {v.var} = {v.help}"

                # add any details to the help printout (required / default values)
                details = {}
                if v.required:
                    details["required"] = True
                if v.default:
                    details["default"] = v.default
                if details:
                    help += " (" + "; ".join(details) + ")"
                help += "\n"


# @hydra.main(config_path=".", config_name="config")
# async def main(cfg: DictConfig):
async def main():
    # FIXME: load all the webhooks so we can display any env variables in help

    p = argparse.ArgumentParser(
        description="Shopify webhook callbacks to Temporal workflow forwarder",
        epilog=(
            "Environment variables:\n"
            + f"AES_KEY - hex string for AES key used to encerypt payloads passed into Temporal (recommended)\n"
            + f"AES_KEY_ID - name/id passed to workers to select correct key to decrypt (recommended)\n"
            + f"TEMPORAL_ENDPOINT - Temporal endpoint  messages should be routed (overrides {Config.temporal_endpoint})\n"
            + f"TEMPORAL_NAMESPACE - Temporal namespace to use (overrides {Config.temporal_namespace})\n"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--host", help=f"listener host", default="0.0.0.0")
    p.add_argument("--port", help=f"listener port ", type=int, default=5000)
    p.add_argument("--cert", help=f"SSL cert", default=Config.ssl_cert)
    p.add_argument("--key", help=f"SSL key", default=Config.ssl_key)

    p.add_argument("--endpoint", help=f"Temporal endpoint", default="localhost:7233")

    p.add_argument(
        "--global-queue",
        dest="global_queue",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="global task queue for all webhooks vs unique queue per webhook topic",
    )
    p.add_argument(
        "--validate-hmac",
        dest="validate_hmac",
        default=Config.validate_hmac,
        action=argparse.BooleanOptionalAction,
        help=f"validate webhook data with Shopify SHA256 HMAC",
    )

    p.add_argument(
        "--help-env-vars",
        dest="help_env_vars",
        help="display environment vars used by configured plugins",
        default=False,
    )
    p.add_argument("-d", "--debug", action="store_true", help="verbose logging")
    args = p.parse_args()

    if args.debug:
        logging.getLogger().setLevel(level=logging.DEBUG)

    Config.ssl_cert = args.cert
    Config.ssl_key = args.key

    Config.temporal_endpoint = os.environ.get("TEMPORAL_ENDPOINT", args.endpoint)
    Config.temporal_namespace = os.environ.get(
        "TEMPORAL_NAMESPACE", Config.temporal_namespace
    )

    Config.global_task_queue = args.global_queue
    Config.validate_hmac = args.validate_hmac

    # FIXME: poor mans plugin (use config in future)
    register_webhook_forwarder(
        "shopify", "temporal_forwarder.webhooks.shopify.ShopifyForwarder", Config
    )
    # register_webhook_forwarder(
    #    "generic", "temporal_forwarder.webhooks.generic.GenericForwarder", Config
    # )

    # display help for any environment variables needed by adapters
    if args.help_env_vars:
        print(env_help())
        sys.exit(1)

    # start the Temporal webhook forwarder (blocking)
    await start_temporal_forwarder(args.host, args.port)


if __name__ == "__main__":
    # use high-performance uvloop event loop
    if sys.version_info >= (3, 11):
        with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
            runner.run(main())
    else:
        uvloop.install()
        asyncio.run(main())
