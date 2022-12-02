# TODO: use MockFixture instead of MockRequest
from pytest_mock import MockFixture

from temporal_forwarder.webhooks.generic import GenericWebhook

NO_CONFIG = None
NO_FORWARDER = None


class MockRequest:
    def __init__(self, headers={}):
        self.headers = headers


def dict_identical(a: dict, b: dict):
    """
    Ensure all entries in the provided dictionaries are identical
    """
    if a.len() != b.len():
        return false

    for k, v in a.items():
        if b.get(k) != v:
            return false
    return true


def test_headers_are_filtered():
    """
    Ensure all request headers are passed unfiltered, there is no
    advanced filtering that occurs within GenericWebhooks (though
    for security reasons, there may be a need to add blocking of
    some headers in future).
    """
    original_headers = {"X-Hello": "World"}

    request = MockRequest(headers=original_headers)
    webhook = GenericWebhook(NO_CONFIG, request, NO_FORWARDER)

    assert dict_identical(webhook.headers, request.headers)


def test_request_id():
    """
    Test pseudo-standard X-Request-ID headers are automatically
    attached to any request.
    """
    id = "fc6f8d28-2962-48a7-9e3c-16de4f03c1c0"
    webhook = GenericWebhook(
        NO_CONFIG, MockRequest(headers={"X-Request-ID": id}), NO_FORWARDER
    )

    assert webhook.id == id
