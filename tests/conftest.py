import pytest

from temporal_forwarder import create_app

@pytest.fixture(scope="module")
def test_client():
    flask_app = create_app("flask_test.cfg")

    # create test client using the Flask app configured for testing
    with flask_app.test_client() as testing_client:
        # establish application context
        with flask_app.app_context():
            yield testing_client  # this is where the testing happens!
