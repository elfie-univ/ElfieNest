from _pytest.capture import CaptureFixture

from app.interfaces.cli.tui import setup_app


def test_run_setup_wizard_redirects_to_the_single_web_setup(
    capsys: CaptureFixture[str],
) -> None:
    setup_app.run_setup_wizard()

    output = capsys.readouterr().out
    assert "CLI TUI Setup 已废弃" in output
    assert "./elfienest.sh serve" in output
    assert "Web Setup" in output
