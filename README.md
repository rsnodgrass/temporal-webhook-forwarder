# temporal-webhook-forwarder

Forward webhook calls to Temporal for Durable Execution

[![stability-alpha](https://img.shields.io/badge/stability-alpha-f4d03f.svg)](https://github.com/mkenney/software-guides/blob/master/STABILITY-BADGES.md#alpha)
[![MIT license](http://img.shields.io/badge/license-MIT-brightgreen.svg)](http://opensource.org/licenses/MIT)

## Overview

This is a proof-of-concept to better understand how [Temporal](https://temporal.io) works.
I manage an old Shopify shop which had legacy integrations doing manual batch processing
and figured it was a perfect time to move some of them over to webhooks.

The forwarder starts a Temporal Durable Execution workflow with data passed via
webhook POST/GET requests (notably for Shopify). If the creation of the Durable
Execution workflow fails, this returns the appropriate status code to the
webhook caller so that they may retry per their SLA/policy. The webhook data
is verified as valid before enqueuing to Temporal by checking digest
signatures (and/or client certificates).

## Encryption (Optional)

This uses Temporal AES GCM as defined in Temporal samples to KISS and ensure this
forwarder can be inserted between Shopify and workflows/activities implemented in
any language easily. Initially a custom codec was considered, but quickly this
made little given sense given:

* AES GCM is secure enough for most use cases;
* Temporal has examples of using this codec in multiple languages (no need to write docs);
* can leverage existing '[codec_server](https://github.com/temporalio/samples-python/blob/main/encryption/codec_server.py)' to decrypt data using 'tctl';
* sample codec allows passing encrypted data or plaintext (useful for expediting testing);
* additional metadata can be passed as needed in future

To enable encryption define 'AES_KEY' environment variable with the hex
representation of the key. Additionally, 'AES_KEY_ID' can be defined with a
logical name/id for the key to inform worker activities which key they
should use to decrypt the payload (if workers implement this).

## Performance Consideration

For efficiency at large scale where fleet cost matters this "Proof of Concept"
should really be re-written in a compiled language like Rust or Go, instead of Python.
This was originally created to explore integrating Shopify webhooks with Temporal
for a Shop with very low transaction rates (e.g. call volume rates measured in
several per hour)...and dev implementation time was significantly more
important (hence Python).

## Webhook Forwarder Plugins

### Shopify Webhook

#### Requirements

* valid SSL fullchain.pem and privkey.pem certificates for server's DNS name (e.g. webhook.yourdomain.com) - **required by Shopify**
* 'SHOPIFY_WEBHOOKS_KEY' env variable defined (value from Shopify)

#### Setup Shopify Webhook Notifications

Add webhooks to the `Setting > Notifications > Webhooks` admin dashboard for the Shopify store under https://yourstore.myshopify.com/admin/settings/notifications:

[](docs/shopify_webhook_admin.png)

Each webhook callback should point to `https://host:port/temporal/shopify` where your forwarder is being hosted. For example: `https://webhook.yourdomain.com:5555/temporal/shopify`

#### Features

* task queue routing based on a single global task queue per forwarder (e.g. ShopifyWebhooks)
* payload verification using Shopify webhook HMAC signatures

#### Warnings

* Shopify does not provide a HMAC digest of `X-Shopify-*` header values (so technically they could be tampered with by MITM)

#### Skipped By Design

* routing based on `X-Shopify-API-Version` (KISS, this is passed via the data into the Temporal workflow)
* routing or dropping of events based on `X-Shopify-Stage` (production, test) – could also map these to Temporal namespaces
* dropping/filtering events based on `X-Shopify-*` header values
* automatic creation of webhook subscriptions within Shopify itself using the admin API (this should be a separate general purpose tool, unrelated to this forwarder...one may already exist)
* support for multiple SHOPIFY_WEBHOOK_KEY to enable multi-tenant forwarding for multiple Shopify stores
* dynamically routing based on Shopify API advertised webhooks (see https://help.shopify.com/en/manual/orders/notifications/webhooks) – just route all valid signed to task queues

### Generic Webhook

Blindly enqueues to Temporal Durable Execution whatever data is submitted as POST or GET, along with some headers. This should probably NOT be used on a production server that is open to all traffic since it does not verify the data or caller.


## Running

This leverages https://github.com/smallwat3r/docker-nginx-gunicorn-flask-letsencrypt
to run Nginx + Gunicorn + Flask + auto-refreshed LetsEncrypt certificates using docker-compose.

Of course, this package can be used in a variety of deployment models and cloud services. Follow the host setup, configuration, operations, scaling, and tuning guidelines provided by the above packages (including how to use alternative certificates to LetsEncrypt).

### Notes for Running Manually

Running the forwarder manually:

```console
pip3 install -r src/requirements.txt
python3 app.py
```

Generating a dev environment LetsEncrypt cert:

```console
mkdir ~/lets-encrypt
certbot certonly --preferred-challenges=dns --manual --config-dir ~/lets-encrypt --work-dir ~/lets-encrypt --logs-dir ~/lets-encrypt
```

#### Command Line

```console
usage: forwarder [-h] [--host HOST] [--port PORT] [--cert CERT] [--key KEY] [--endpoint ENDPOINT]
                 [--global-queue | --no-global-queue] [--validate-hmac | --no-validate-hmac]
                 [--help-env-vars HELP_ENV_VARS] [-d]

options:
  -h, --help            show this help message and exit
  --host HOST           listener host (default: 0.0.0.0)
  --port PORT           listener port (default: 5000)
  --cert CERT           SSL cert (default: fullchain.pem)
  --key KEY             SSL key (default: privkey.pem)
  --endpoint ENDPOINT   Temporal endpoint (default: localhost:7233)
  --global-queue, --no-global-queue
                        global task queue for all webhooks vs unique queue per webhook topic
                        (default: True)
  --validate-hmac, --no-validate-hmac
                        validate webhook data with Shopify SHA256 HMAC (default: True)
  --help-env-vars HELP_ENV_VARS
                        display environment vars used by configured plugins (default: False)
  -d, --debug           verbose logging (default: False)

Environment variables:
AES_KEY - hex string for AES key used to encerypt payloads passed into Temporal (recommended)
AES_KEY_ID - name/id passed to workers to select correct key to decrypt (recommended)
TEMPORAL_ENDPOINT - Temporal endpoint messages should be routed (overrides localhost:7233)
TEMPORAL_NAMESPACE - Temporal namespace to use (overrides default)

Configured forwarder env vars:
SHOPIFY_WEBHOOKS_KEY - Shopify provided API secret key to validate webhook data (REQUIRED)
```

## Features

* (optional) 256-bit AES symmetric encryption of workflow payloads passed into Temporal

### Unsupported

#### Not Yet Implemented

* advanced config mechanism (in addition to command line and ENV vars .. hydra or dynaconf)
* support for plugging in other relevent webhooks (Shippo, Shipstation, Klarna, ShipBob, etc) **[partially implemented]**

#### Left to the Reader

* Temporal TLS authentication **(skipped since my Temporal instance was running within same internal network)**
* support/testing of certificates issued by a CA other than Let's Encrypt
* routing to task_queues based on X-Shopify-Topic headers **(not needed)**
* multi-tenant task routing based on Shopify Shop domain to Temporal task queues (`X-Shopify-Shop-Domain`)

#### Skipped By Design

* routing to multiple different Temporal endpoints based on headers or payload – unnecessary complexity when it is probably easier to spin up separate instances of the forwarder
* one to many delivery (e.g. multiple Temporal instances/queues/etc for a single inbound webhook)
* tranformations of the webhook data

## Support

* This is provided as an "example" only.
* Pull Requests **may** be reviewed and accepted (no guarantees).
* Feel free to fork.

### See Also

* [Temporal Community Forum](https://community.temporal.io/)
* [Hookdeck](https://hookdeck.com/) is an alternative mechanism for queuing/managing webhooks
