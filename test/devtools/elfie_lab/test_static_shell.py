from devtools.elfie_lab.app import create_app


def test_elfie_lab_serves_the_shared_vite_react_shell(tmp_path, client_for) -> None:
    # Given
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

    # When
    response = client.get("/")

    # Then
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert 'window.__ELFIENEST_LAB__ = "elfie"' in response.text
    assert 'src="/ui/assets/' in response.text
    assert client.get("/elfie/experiment").status_code == 200
    assert client.get("/elfie/evaluations").status_code == 200
    assert client.get("/static/app.js").status_code == 404
