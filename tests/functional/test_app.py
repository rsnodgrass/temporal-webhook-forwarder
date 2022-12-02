def test_healthcheck(test_client):
    """
    GIVEN a Flask application configured for testing
    with no LIVE dependencies (e.g. Temporal instance)
    WHEN the '/' page is requested (GET)
    THEN check that the response is valid
    """
    response = test_client.get("/")
    assert response.status_code == 200
    assert b"OK" in response.data


def test_deep_healthcheck(test_client):
    """
    FOR NOW DO NOT TEST for now, since a deep healthcheck
    confirms that the underlying Temporal instances are
    all alive and ready to have Durable Executions started.
    """
    pass
