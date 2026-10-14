"""Default verification is offline; real-provider tests are explicitly marked."""
import pytest
import requests


@pytest.fixture(autouse=True)
def block_unplanned_network(request, monkeypatch):
    if request.node.get_closest_marker('live'):
        return

    def blocked(*args, **kwargs):
        raise AssertionError('Offline tests must mock external requests')

    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)
