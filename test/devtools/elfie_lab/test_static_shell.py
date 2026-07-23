from pathlib import Path

from devtools.elfie_lab.app import create_app


def test_static_shell_has_three_columns_without_top_navigation(tmp_path, client_for):
    runtime_dir = tmp_path / "runtime"
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    response = client.get("/")

    assert response.status_code == 200
    assert 'class="elfie-panel"' in response.text
    assert 'class="timeline-panel"' in response.text
    assert 'class="detail-panel"' in response.text
    assert 'id="detailTitle">当前状态' in response.text
    assert 'id="foodSelect"' in response.text
    assert 'id="foodSetupList"' in response.text
    assert 'id="appearanceFrame"' in response.text
    assert 'id="personalityRadar"' in response.text
    assert 'id="relationGraph"' in response.text
    assert 'id="createSpecies"' in response.text
    assert 'id="createAnatomy"' not in response.text
    assert 'id="runtimeMode"' not in response.text
    assert "<nav" not in response.text
    assert client.get("/static/app.js").status_code == 200
    foods_script = client.get("/static/foods.js")
    assert foods_script.status_code == 200
    assert "完整 Runtime Lab" in foods_script.text
    assert client.get("/static/styles.css").status_code == 200
    tokens = client.get("/static/tokens.css")
    assert tokens.status_code == 200
    assert "color-scheme: light" in tokens.text

    runtime = client.get("/api/runtime/status")
    assert runtime.status_code == 200
    assert runtime.json()["scope"] == "override"
    assert runtime.json()["config_dir"] == str(runtime_dir)


def test_static_frontend_uses_small_native_modules(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

    shell = client.get("/")
    assert '<script type="module" src="/static/app.js"></script>' in shell.text

    javascript_modules = (
        "api.js",
        "store.js",
        "dom.js",
        "portrait.js",
        "profile.js",
        "profile-projections.js",
        "personality-editor.js",
        "preview-protocol.js",
        "foods.js",
        "elfie-menu.js",
        "timeline.js",
        "detail.js",
        "detail-format.js",
        "detail-preview.js",
        "composer.js",
        "create-elfie.js",
    )
    app_source = client.get("/static/app.js").text
    assert len(app_source.splitlines()) <= 150
    module_sources = {}
    for filename in javascript_modules:
        response = client.get(f"/static/{filename}")
        assert response.status_code == 200
        assert len(response.text.splitlines()) <= 250
        assert ".innerHTML" not in response.text
        module_sources[filename] = response.text
    frontend_source = app_source + "\n" + "\n".join(module_sources.values())
    for filename in javascript_modules:
        assert f'from "./{filename}"' in frontend_source or filename in app_source

    stylesheet_modules = (
        "tokens.css",
        "base.css",
        "layout.css",
        "components.css",
        "personality.css",
        "detail.css",
        "responsive.css",
    )
    stylesheet_entry = client.get("/static/styles.css").text
    for filename in stylesheet_modules:
        assert f'@import url("./{filename}")' in stylesheet_entry
        response = client.get(f"/static/{filename}")
        assert response.status_code == 200
        assert len(response.text.splitlines()) <= 250

    app_path = Path(__file__).parents[3] / "devtools" / "elfie_lab" / "app.py"
    pure_lines = [
        line
        for line in app_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(pure_lines) <= 250


def test_godot_web_runtime_disables_browser_cache(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

    response = client.head("/godot-web/elfienest.pck")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_lab_static_modules_disable_browser_cache(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

    response = client.get("/static/profile.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
