import pytest

from infrastructure.tools.local_files import LocalFileAccessError, LocalFileAccessPlugin


def test_local_file_access_reads_and_lists_only_inside_root(tmp_path):
    (tmp_path / "probe.txt").write_text("hello", encoding="utf-8")
    plugin = LocalFileAccessPlugin(tmp_path)

    assert plugin.read_text("probe.txt") == "hello"
    assert plugin.list_files() == ["probe.txt"]

    with pytest.raises(LocalFileAccessError):
        plugin.read_text("../outside.txt")
