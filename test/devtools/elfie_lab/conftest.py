from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_for():
    with ExitStack() as stack:

        def open_client(app):
            return stack.enter_context(TestClient(app))

        yield open_client
