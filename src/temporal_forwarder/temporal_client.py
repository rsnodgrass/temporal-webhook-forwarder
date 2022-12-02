import logging
import dataclasses
import os

import temporalio
from temporalio.client import Client

from temporal_forwarder.codec import EncryptionCodec

from . import Config

LOG = logging.getLogger()

TEMPORAL_CLIENT = None

async def get_temporal_client(config=None):
    global TEMPORAL_CLIENT
    if not TEMPORAL_CLIENT:
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
        
        TEMPORAL_CLIENT = await Client.connect(
            Config.temporal_endpoint, data_converter=data_converter
        )
    return TEMPORAL_CLIENT

async def start_temporal_forwarder(app, host: str, port: int):
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

    # run Flask app until complete
    await app.run(
        host=host, port=port, debug=True, ssl_context=(Config.ssl_cert, Config.ssl_key)
    )

