from scripts.serve import service_host


def test_service_host_binds_loopback_unless_lan_is_explicit() -> None:
    # Given: the developer CLI defaults and its explicit LAN option.
    # When: each mode resolves a bind host.
    # Then: only LAN chooses all IPv4 interfaces.
    assert service_host(lan=False) == "127.0.0.1"
    assert service_host(lan=True) == "0.0.0.0"
