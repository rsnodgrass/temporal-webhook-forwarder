import logging
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

# dumb configuration mechanism, really should use hydra/OmegaConf, Dynaconf or dotenv
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
