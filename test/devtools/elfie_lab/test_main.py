import argparse

import pytest

from devtools.elfie_lab.__main__ import loopback_host


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost"])
def test_loopback_host_accepts_only_local_addresses(host: str) -> None:
    assert loopback_host(host) == host


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.test"])
def test_loopback_host_rejects_remote_bindings(host: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="本地回环"):
        loopback_host(host)
