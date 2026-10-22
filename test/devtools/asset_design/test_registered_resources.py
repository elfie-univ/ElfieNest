"""Resource authorization caches registrations without scanning asset payloads."""

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from devtools.asset_design.catalog import load_catalog, registered_file


def write_catalog(root, paths):
    row = {
        "id": "part_shared",
        "category": "part",
        "title": "Shared resources",
        "files": [
            {"path": path, "name": Path(path).name, "kind": "data", "bytes": 1}
            for path in paths
        ],
    }
    (root / "catalog.json").write_text(json.dumps({"assets": [row]}))


def test_file_requests_parse_once_without_scanning_other_payloads(
    tmp_path, monkeypatch
):
    for name in ("first.bin", "other.bin"):
        (tmp_path / name).write_bytes(b"x")
    write_catalog(tmp_path, ["first.bin", "other.bin"])
    original_read = Path.read_bytes
    original_stat = Path.stat
    reads = []
    stats = []

    def read(path, *args, **kwargs):
        reads.append(path)
        return original_read(path, *args, **kwargs)

    def stat(path, *args, **kwargs):
        stats.append(path)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(Path, "stat", stat)
    for _ in range(3):
        assert registered_file(tmp_path, "first.bin") == tmp_path / "first.bin"
    assert reads == [tmp_path / "catalog.json"]
    assert tmp_path / "other.bin" not in stats


def test_same_size_catalog_rewrite_with_restored_mtime_invalidates_index(tmp_path):
    for name in ("first.bin", "other.bin"):
        (tmp_path / name).write_bytes(b"x")
    write_catalog(tmp_path, ["first.bin"])
    index = tmp_path / "catalog.json"
    previous = index.stat()
    assert registered_file(tmp_path, "first.bin")
    assert registered_file(tmp_path, "other.bin") is None
    write_catalog(tmp_path, ["other.bin"])
    assert index.stat().st_size == previous.st_size
    os.utime(index, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    assert registered_file(tmp_path, "first.bin") is None
    assert registered_file(tmp_path, "other.bin") == tmp_path / "other.bin"


def test_registration_change_is_visible_without_restarting(tmp_path):
    (tmp_path / "first.bin").write_bytes(b"x")
    write_catalog(tmp_path, [])
    assert registered_file(tmp_path, "first.bin") is None
    write_catalog(tmp_path, ["first.bin"])
    assert registered_file(tmp_path, "first.bin")
    (tmp_path / "catalog.json").unlink()
    assert registered_file(tmp_path, "first.bin") is None


def test_symlink_escape_is_checked_for_every_request(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    payload = root / "shared.bin"
    payload.write_bytes(b"x")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"y")
    write_catalog(root, ["shared.bin"])
    assert registered_file(root, "shared.bin") == payload
    payload.unlink()
    payload.symlink_to(outside)
    assert registered_file(root, "shared.bin") is None


@pytest.mark.parametrize("name", ["blocked.js", "blocked.py", "blocked.html"])
def test_executable_resources_stay_blocked(tmp_path, name):
    (tmp_path / name).write_bytes(b"x")
    write_catalog(tmp_path, [name])
    assert registered_file(tmp_path, name) is None


def test_registration_index_still_validates_catalog_schema(tmp_path):
    (tmp_path / "catalog.json").write_text('{"assets":[{"files":[]}]}')
    with pytest.raises(ValidationError):
        registered_file(tmp_path, "anything.bin")


def test_catalog_stats_inspect_repeated_shared_payload_once(tmp_path, monkeypatch):
    payload = tmp_path / "resources/shared.bin"
    payload.parent.mkdir()
    payload.write_bytes(b"shared")
    write_catalog(tmp_path, ["resources/shared.bin"] * 3)
    original_stat = Path.stat
    inspections = []

    def stat(path, *args, **kwargs):
        if path == payload:
            inspections.append(path)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    catalog = load_catalog(tmp_path)
    assert catalog.stats["bytes"] == len(b"shared")
    assert all(entry.bytes == len(b"shared") for entry in catalog.assets[0].files)
    assert len(inspections) <= 2
