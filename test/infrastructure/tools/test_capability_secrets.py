from pathlib import Path

from infrastructure.tools import ToolCapabilitySecretAdapter


def test_secret_adapter_keeps_plaintext_outside_configuration(tmp_path: Path):
    path = tmp_path / "auth.env"
    adapter = ToolCapabilitySecretAdapter(path)

    reference = adapter.set_web_search_secret("local-only-key")

    assert reference == "ELFIE_WEB_SEARCH_API_KEY"
    assert adapter.has_secret(reference) is True
    assert "local-only-key" in path.read_text(encoding="utf-8")

    adapter.set_web_search_secret("")
    assert adapter.has_secret(reference) is False
