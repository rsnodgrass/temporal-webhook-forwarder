# TODO: use MockFixture instead of MockRequest
from pytest_mock import MockFixture

from temporal_forwarder.webhooks.shopify import ShopifyWebhook

NO_CONFIG = None
NO_FORWARDER = None

REQUEST_ID = "fc6f8d28-2962-48a7-9e3c-16de4f03c1c0"


class MockRequest:
    def __init__(self, headers={}):
        self.headers = headers
        # always inject required Webhook-Id header
        self.headers |= {"X-Shopify-Webhook-Id": REQUEST_ID}

        self.method = "POST"
        self.base_url = "/test"


def test_headers_are_filtered():
    """
    Ensure X-Shopify-* headers are the passed, but others ignored.
    """
    original_headers = {"X-Hello": "World", "X-Shopify-Test": "True"}

    request = MockRequest(headers=original_headers)
    webhook = ShopifyWebhook(NO_CONFIG, request, NO_FORWARDER)

    assert "X-Shopify-Test" in webhook.headers()
    assert not "X-Hello" in webhook.headers()


def test_request_id():
    """
    Test pseudo-standard X-Request-ID headers are overwritten by the
    X-Shopify-Webhook-Id.
    """
    webhook = ShopifyWebhook(
        NO_CONFIG, MockRequest(headers={"X-Request-ID": "test"}), NO_FORWARDER
    )

    assert webhook.id != "test"
    assert webhook.id == REQUEST_ID
