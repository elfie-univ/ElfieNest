from __future__ import annotations

from pathlib import Path

from elfie.brain.memory.node_types import MemoryNode
from elfie.profile import create_visual_profile
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.elfie_workspace.elfies import (
    SQLiteElfiesProjectionAdapter,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.nest_db.store import get_db, init_db
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


def _database(tmp_path: Path) -> str:
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users(id,account_id,role,password_hash) "
            "VALUES (1,'alice','owner','hash'),(2,'bob','user','hash')"
        )
        connection.execute(
            """INSERT INTO elfies(
                   elfie_id,name,owner_user_id,species,adopted_at,status,summary
               ) VALUES
                   ('00000001','小狐',1,'fox','2026-08-01T00:00:00Z','offline','好奇探索'),
                   ('00000002','小犬',2,'dog','2026-08-02T00:00:00Z','offline','安静温顺')"""
        )
        connection.commit()
    return db_path


def test_directory_reads_only_elfies_owned_projection(tmp_path: Path) -> None:
    db_path = _database(tmp_path)
    adapter = SQLiteElfiesProjectionAdapter(db_path)

    records = adapter.list_directory(owner_user_id=1, species_id="fox")

    assert len(records) == 1
    assert records[0].elfie_id == "00000001"
    assert records[0].owner_account_id == "alice"
    assert records[0].summary == "好奇探索"
    assert not hasattr(records[0], "bed_number")
    assert not hasattr(records[0], "main_food_id")
    assert not hasattr(records[0], "status")


def test_profile_reader_consumes_the_public_profile_authority(tmp_path: Path) -> None:
    db_path = _database(tmp_path)
    layout = final_root_layout(tmp_path).elfie("00000001")
    profile = create_visual_profile(
        elfie_id="00000001",
        display_name="小狐",
        species_id="fox",
        seed=7,
    )
    YamlProfileStoreAdapter(layout.profile.parent).save(profile)
    YamlSelfhoodSeedAdapter(layout.brain).save(
        {
            "big_five": {
                "openness": 0.9,
                "conscientiousness": 0.6,
                "extraversion": 0.8,
                "agreeableness": 0.7,
                "neuroticism": 0.2,
            }
        }
    )
    adapter = SQLiteElfiesProjectionAdapter(db_path)

    result = adapter.load_profile("00000001")

    assert result.status == "ready"
    assert result.openness == 0.9
    assert result.neuroticism == 0.2
    assert result.appearance is not None
    assert result.appearance.species_id == "fox"
    assert result.appearance.profile_version == 2


def test_portrait_reader_returns_only_the_saved_png_view(tmp_path: Path) -> None:
    db_path = _database(tmp_path)
    layout = final_root_layout(tmp_path).elfie("00000001")
    layout.portrait_headshot.parent.mkdir(parents=True, exist_ok=True)
    content = b"\x89PNG\r\n\x1a\nportrait"
    layout.portrait_headshot.write_bytes(content)

    adapter = SQLiteElfiesProjectionAdapter(db_path)

    assert adapter.load_portrait("00000001") == content
    assert adapter.load_portrait("00000001", kind="full_body") is None


def test_cognition_reader_is_read_only_and_returns_typed_records(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    path = final_root_layout(tmp_path).elfie("00000001").knowledge_database
    path.parent.mkdir(parents=True)
    with SQLiteMemoryStoreAdapter(path) as store:
        store.add_node(
            MemoryNode(
                id="event-adoption",
                type="episodic",
                content="被 Alice 领养",
                metadata={
                    "timestamp": "2026-08-01T00:00:00Z",
                    "major_event": True,
                    "importance": 0.95,
                    "title": "被领养",
                    "topics": [{"label": "Alice", "category": "person"}],
                },
            )
        )
    before = path.stat().st_mtime_ns
    adapter = SQLiteElfiesProjectionAdapter(db_path)

    result = adapter.load_cognition("00000001")

    assert result.status == "ready"
    assert result.events[0].id == "event-adoption"
    assert result.events[0].topics[0].label == "Alice"
    assert path.stat().st_mtime_ns == before
