"""Compact catalog storage preserves version ownership and file metadata."""

import json

from devtools.asset_design.deletion import write_json


def test_catalog_file_records_use_one_line_without_changing_values(tmp_path):
    shared = {"path": "shared.bin", "name": "共享.bin", "kind": "data", "bytes": 3}
    changed = {**shared, "kind": "source", "bytes": 5}
    data = {
        "assets": [
            {"id": "old", "files": [shared], "designVersion": {"revision": 1}},
            {"id": "new", "files": [shared, changed]},
            {"id": "empty", "files": []},
            {"id": "no-files", "description": '引号 " 和换行\n原样保留'},
        ],
        "imageReferences": [],
        "stats": {"files": 1},
    }
    path = tmp_path / "catalog.json"
    write_json(path, data)
    saved = path.read_text()
    assert json.loads(saved) == data
    assert len([line for line in saved.splitlines() if '"path"' in line]) == 3
    assert all('"bytes"' in line for line in saved.splitlines() if '"path"' in line)
    assert saved.endswith("\n")
    write_json(path, json.loads(saved))
    assert path.read_text() == saved


def test_other_json_files_keep_existing_formatting(tmp_path):
    data = {"assets": [{"files": [{"path": "source.glb", "bytes": 3}]}]}
    path = tmp_path / "version.json"
    write_json(path, data)
    assert path.read_text() == json.dumps(data, ensure_ascii=False, indent=2) + "\n"
