"""Knowledge Node title/context admission tests."""

import json

from elfie.brain.memory.consolidation import MemoryConsolidator
from elfie.brain.memory.memory_records import ClosedEpisode, ConsolidationRequest
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


class _KnowledgeProposal:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def ask_with_food(self, **_kwargs: object) -> str:
        return self.payload


class _EmptyProposal:
    def ask_with_food(self, **_kwargs: object) -> str:
        return '{"nodes":[],"mentions":[],"assertions":[]}'


def test_knowledge_node_keeps_one_short_title_and_sourced_context() -> None:
    content = "主题：情绪共鸣与身体状态。强烈情绪会在近距离共鸣并影响身体状态。"
    proposal = json.dumps(
        {
            "nodes": [
                {
                    "title": "情绪共鸣与身体状态",
                    "type": "knowledge",
                    "context": content,
                    "reusable_knowledge": True,
                }
            ],
            "mentions": [],
            "assertions": [],
        },
        ensure_ascii=False,
    )
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="knowledge-title-test") as store:
        store.record_episode(
            ClosedEpisode(
                "knowledge-episode", "knowledge-episode", "2026-01-01", content
            )
        )

        receipt = MemoryConsolidator(store, elfie_id="knowledge-title-test").run_batch(
            ConsolidationRequest(max_episodes=1),
            model_port=_KnowledgeProposal(proposal),
        )

        assert receipt.status == "completed"
        nodes = store.list_graph_nodes(limit=10)
        assert len(nodes) == 1
        assert nodes[0].node_type == "knowledge"
        assert nodes[0].label == "情绪共鸣与身体状态"
        assert nodes[0].description == content
        description = store.connection.execute(
            "SELECT kind, text FROM node_descriptions WHERE node_id=?",
            (nodes[0].node_id,),
        ).fetchone()
        assert tuple(description) == ("context", content)


def test_full_sentence_cannot_become_knowledge_title() -> None:
    content = "强烈情绪可以在近距离共鸣并影响身体状态；长期稳定的关系和积极情绪通常有助于维持状态。"
    proposal = json.dumps(
        {
            "nodes": [
                {
                    "label": content,
                    "type": "knowledge",
                    "description": content,
                    "reusable_knowledge": True,
                }
            ],
            "mentions": [],
            "assertions": [],
        },
        ensure_ascii=False,
    )
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="knowledge-title-reject") as store:
        store.record_episode(
            ClosedEpisode("knowledge-reject", "knowledge-reject", "2026-01-01", content)
        )

        receipt = MemoryConsolidator(
            store, elfie_id="knowledge-title-reject"
        ).run_batch(
            ConsolidationRequest(max_episodes=1),
            model_port=_KnowledgeProposal(proposal),
        )

        assert receipt.status == "failed"
        assert receipt.failed_episode_ids == ("knowledge-reject",)
        assert store.list_graph_nodes(limit=10) == ()
        assert store.get_episode("knowledge-reject").content_text == content


def test_empty_model_proposal_does_not_promote_ordinary_knowledge_text() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(
        elfie_id="knowledge-fallback-test"
    ) as store:
        store.record_episode(
            ClosedEpisode(
                "knowledge-fallback",
                "knowledge-fallback",
                "2026-01-01",
                "我读到“牛顿第三定律”，它解释了相互作用力。",
            )
        )

        receipt = MemoryConsolidator(
            store, elfie_id="knowledge-fallback-test"
        ).run_batch(
            ConsolidationRequest(max_episodes=1),
            model_port=_EmptyProposal(),
        )

        assert receipt.status == "completed"
        assert store.list_graph_nodes(limit=10) == ()
