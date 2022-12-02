import logging
import base64
import json
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass

from flask import Flask

LOG = logging.getLogger()

DEFAULT_TEMPORAL_ENDPOINT = "localhost:7233"

def create_app(config):
    """
    Create the Flask app (also used for functional tests)
    """
    app = Flask(__name__)

    with app.app_context():

        # import various routes
        from temporal_forwarder import forwarder, healthchecks

        # FUTURE: register Blueprints
        # app.register_blueprint(auth.auth_bp)

        return app



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
