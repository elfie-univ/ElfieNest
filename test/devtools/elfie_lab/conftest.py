from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_for():
    with ExitStack() as stack:

        def open_client(app):
            return stack.enter_context(TestClient(app, base_url="http://127.0.0.1"))

        yield open_client
