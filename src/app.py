#!/usr/bin/env python3

import logging
import argparse
import asyncio
import os
import sys

import uvloop

from temporal_forwarder import *
from temporal_forwarder.plugins import WEBHOOK_FORWARDERS, register_plugins

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOG = logging.getLogger()


def env_help():
    """
    Create help string showing env variables used by this app (and any configured forwarder plugins).
    This extends what argparse displays beyond just direct command line arguments.
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


# async def main(cfg: DictConfig):
async def main():
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

    # app must be created first so that env vars for configured forwarders can be displayed in help
    app = create_app(Config)
    register_plugins(Config)

    # display help for any environment variables needed by forwarding plugins
    if args.help_env_vars:
        print(env_help())
        sys.exit(1)

    # run Flask app until complete
    await app.run(
        host=args.host,
        port=args.port,
        debug=True,
        ssl_context=(Config.ssl_cert, Config.ssl_key),
    )


if __name__ == "__main__":
    # use high-performance uvloop event loop
    if sys.version_info >= (3, 11):
        with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
            runner.run(main())
    else:
        uvloop.install()
        asyncio.run(main())
