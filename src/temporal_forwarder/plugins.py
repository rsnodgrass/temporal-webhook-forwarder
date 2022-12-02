import logging
import importlib
import os
import pkgutil
import sys

from flask import current_app as app

from . import Config

LOG = logging.getLogger()

WEBHOOK_FORWARDERS = {}
#    "generic": temporal_forwarder.webhooks.forwarder_generic.GenericForwarder
#    "shopify": temporal_forwarder.webhooks.forwarder_shopify.ShopifyForwarder
#    'shippo': temporal_forwarder.webhooks.forwarder_shippo.ShippoForwarder
#    'shipstation': temporal_forwarder.webhooks.forwarder_shipstation.ShipstationForwarder


def register_plugins(config):
    # FIXME: poor mans plugin (use config to determine which forwarders to include)
    register_webhook_forwarder(
        "shopify", "temporal_forwarder.webhooks.shopify.ShopifyForwarder", config
    )
    # register_webhook_forwarder(
    #    "generic", "temporal_forwarder.webhooks.generic.GenericForwarder", onfig
    # )


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
