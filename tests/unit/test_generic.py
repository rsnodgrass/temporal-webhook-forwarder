from temporal.webhooks.generic import GenericWebhook

NO_CONFIG = None
NO_FORWARDER = None

class MockRequest:
    def __init__(self, headers={}):
        self.headers = headers

def test_headers_are_filtered():
    """
    Ensure all request headers are passed unfiltered, there is no
    advanced filtering that occurs within GenericWebhooks (though
    for security reasons, there may be a need to add blocking of
    some headers in future).
    """
    original_headers = { "X-Hello": "World" }

    request = MockRequest(headers=original_headers)
    webhook = GenericWebhook(NO_CONFIG, request, NO_FORWARDER)

    assert webhook.headers.len() == request.headers.len()
    assert webhook.headers == request.headers


def test_request_id():
    """
    Test pseudo-standard X-Request-ID headers are automatically
    attached to any request.
    """
    id = "fc6f8d28-2962-48a7-9e3c-16de4f03c1c0"
    request = MockRequest(headers={ "X-Request-ID": id })
    webhook = GenericWebhook(NO_CONFIG, request, NO_FORWARDER)

    assert request.id == id

