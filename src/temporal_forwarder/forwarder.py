"""
Routes specific to forwarding to webhook plugins
"""

import logging
from http import HTTPStatus

from flask import Response, abort
from flask import current_app as app
from flask import json, request

from app import (  # FIXME: bind to the temporal client(s) configured
    TEMPORAL_CLIENT,
    WEBHOOK_FORWARDERS,
    Config,
)

from temporal_forwarder.webhook import WebhookCall

LOG = logging.getLogger()

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
        headers["X-Webhook-Verified"] = "False"
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
