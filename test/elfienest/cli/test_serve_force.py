from __future__ import annotations

from scripts.e2e_dashboard_check import find_distinct_free_ports
from scripts.serve import remaining_occupied_ports


def test_force_cleanup_reports_ports_still_occupied() -> None:
    # Given
    occupied = ((8000, "HTTP"), (8766, "WebSocket"), (8767, "音频服务器"))

    # When
    remaining = remaining_occupied_ports(
        occupied,
        lambda port: port in {8766, 8767},
    )

    # Then
    assert remaining == [(8766, "WebSocket"), (8767, "音频服务器")]


def test_dashboard_e2e_uses_distinct_service_ports() -> None:
    ports = find_distinct_free_ports(4)

    assert len(ports) == 4
    assert len(set(ports)) == 4
