from fastapi.testclient import TestClient

from devtools.nest_lab.app import create_app


def test_nest_lab_serves_the_shared_vite_react_shell(tmp_path) -> None:
    # Given
    client = TestClient(create_app(tmp_path), base_url="http://127.0.0.1")

    # When
    response = client.get("/")

    # Then
    assert response.status_code == 200
    assert 'window.__ELFIENEST_LAB__ = "nest"' in response.text
    assert 'src="/ui/assets/' in response.text
    assert client.get("/nest/experiment").status_code == 200
    assert client.get("/static/app.js").status_code == 404
