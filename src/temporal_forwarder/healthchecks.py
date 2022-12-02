"""
Health check Flask routes
"""

import logging
from http import HTTPStatus

from flask import Response, abort
from flask import current_app as app

LOG = logging.getLogger()

from app import (  # FIXME: bind to the temporal client(s) configured
    TEMPORAL_CLIENT,
    WEBHOOK_FORWARDERS,
)


@app.route("/")
@app.route("/health")
async def healthcheck():
    return ("OK", HTTPStatus.OK)  # 200


@app.route("/health/temporal")
async def deep_healthcheck():
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
            abort(Response("FAILED", HTTPStatus.SERVICE_UNAVAILABLE))  # 503

    return ("OK", HTTPStatus.OK)  # 200
