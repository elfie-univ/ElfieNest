"""Object image associations cross the catalog endpoint without model edits."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from devtools.asset_design.app import create_app
from devtools.asset_design.catalog import Catalog


def test_catalog_serves_explicit_image_owners_and_image_selection_module(tmp_path):
    association = {
        "path": "reference.png",
        "objects": ["layout:central:1"],
        "title": "Ground floor",
        "kind": "reference",
    }
    (tmp_path / "reference.png").write_bytes(b"local reference")
    (tmp_path / "catalog.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "id": "image",
                        "category": "central",
                        "title": "Reference",
                        "files": [
                            {
                                "path": "reference.png",
                                "name": "reference.png",
                                "kind": "image",
                                "bytes": 15,
                            }
                        ],
                    }
                ],
                "imageReferences": [association],
            }
        )
    )
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        response = client.get("/assets/design/catalog.json")
        assert response.status_code == 200
        assert response.json()["imageReferences"] == [{**association, "version": None}]
        assert client.get("/assets/design/content-images.mjs").status_code == 200
    assert not (tmp_path / "adoptions.json").exists()


def test_catalog_rejects_image_owners_without_a_supported_kind():
    with pytest.raises(ValidationError):
        Catalog.model_validate(
            {
                "imageReferences": [
                    {
                        "path": "reference.png",
                        "objects": ["layout:central:1"],
                        "title": "Reference",
                        "kind": "model-version",
                    }
                ]
            }
        )
