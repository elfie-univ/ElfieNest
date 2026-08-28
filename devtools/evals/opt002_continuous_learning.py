"""Run the deterministic OPT-002 continuous-learning evaluation.

The evaluator exercises the source-first Memory contract without a provider.
It deliberately reports machine facts only; model quality and owner experience
remain separate gates in the Stage 1 E1 evaluation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Mapping, Sequence, cast

from elfie.brain.memory import (
    AliasInput,
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    ConsolidationRequest,
    EvidenceInput,
    MentionInput,
    NodeInput,
    RecallRequest,
)
from elfie.brain.memory.consolidation import MemoryConsolidator
from elfie.brain.memory.model_food import MemoryModelPort
from elfie.brain.reasoning.conversation_context import ConversationContextStore
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    ExternalExecutionDomain,
    PerceptionEvent,
    ResponseScope,
    SocialPayload,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    DeliveryReceipt,
    DeliveryStatus,
    MessageDirection,
    TextPart,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    TraceId,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "build" / "evaluations" / "stage1-chat" / "opt002-current"
SCENARIO_SET = "opt002-continuous-learning.v1"
NOW = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)


class _FailingProposalModel:
    def ask_with_food(
        self,
        prompt: str,
        *,
        food_key: str | None,
        elfie_id: str | None,
        scene: str,
        semantic_role: str,
        energy: float,
        task_complexity: int,
        allowed_skills: list[str] | None,
    ) -> str:
        del prompt, food_key, elfie_id, scene, semantic_role, energy, task_complexity
        del allowed_skills
        raise TimeoutError("provider unavailable")


class _FailingChannel:
    channel_id = "chat"

    def __init__(self) -> None:
        self.connected = False

    @property
    def is_connected(self) -> bool:
        return self.connected

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        return DeliveryReceipt.for_envelope(
            envelope,
            status=DeliveryStatus.FAILED,
            error_code="synthetic_delivery_failure",
            error_message="synthetic evaluation failure",
            retryable=True,
        )


def _frame(index: int, text: str, *, at: datetime) -> TurnFrame:
    owner = ActorRef(actor_id=ActorId("owner-1"), source_kind="owner")
    event = PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId(f"opt002-owner-{index}"),
            elfie_id=ElfieId("opt002-elfie"),
            source=owner,
            occurred_at=at,
            received_at=at,
            trace_id=TraceId(f"opt002-trace-{index}"),
        ),
        payload=SocialPayload(
            type="social",
            channel_id="chat",
            conversation_id="owner-chat",
            sender=owner,
            content=text,
        ),
    )
    return TurnFrame(
        frame_id=EventId(f"opt002-frame-{index}"),
        elfie_id=ElfieId("opt002-elfie"),
        revision=index,
        captured_at=at,
        cutoff_seq=index,
        trigger_reason=TriggerReason.CONVERSATION_QUIET,
        source_domain=SourceDomain.COMMUNICATION,
        interaction_scope=CommunicationScope(
            channel_id="chat", conversation_id="owner-chat"
        ),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id="chat",
            conversation_id="owner-chat",
        ),
        events=(event,),
    )


def _episode(episode_id: str, content: str, day: int = 1) -> ClosedEpisode:
    occurred = NOW + timedelta(days=day - 1)
    return ClosedEpisode(
        episode_id=episode_id,
        idempotency_key=episode_id,
        occurred_from=occurred.isoformat(),
        content_text=content,
        source_event_ids=(f"source-{episode_id}",),
    )


def _consolidate(
    store: SQLiteMemoryStoreAdapter,
    *,
    model_port: MemoryModelPort | None = None,
    limit: int = 8,
) -> list[Any]:
    consolidator = MemoryConsolidator(store)
    receipts: list[Any] = []
    for _ in range(16):
        if not store.pending_episodes(limit=limit):
            break
        receipt = consolidator.run_batch(
            ConsolidationRequest(max_episodes=limit), model_port=model_port
        )
        receipts.append(receipt)
        if not receipt.consolidated_episode_ids and not receipt.failed_episode_ids:
            break
    return receipts


def _result(
    scenario_id: str, checks: Mapping[str, bool], **details: Any
) -> Dict[str, Any]:
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "scenario_id": scenario_id,
        "passed": not failed,
        "checks": dict(checks),
        "failures": failed,
        "details": details,
    }


def _scenario_episode_boundaries() -> Dict[str, Any]:
    context = ConversationContextStore(topic_idle_seconds=60)
    context.observe(_frame(1, "我们讨论周末去爬山。", at=NOW), NOW)
    context.observe(
        _frame(2, "我想带一件外套。", at=NOW + timedelta(seconds=1)),
        NOW + timedelta(seconds=1),
    )
    context.observe(
        _frame(3, "换个话题，厨房要买什么？", at=NOW + timedelta(seconds=2)),
        NOW + timedelta(seconds=2),
    )
    context.close_topics(captured_at=NOW + timedelta(seconds=3))
    episodes = context.pending_closed_episodes()
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        receipts = [store.record_episode(item) for item in episodes]
        duplicate = store.record_episode(episodes[0])
        _consolidate(store)
        return _result(
            "episode-boundaries",
            {
                "same_topic_is_one_episode": len(episodes) == 2
                and episodes[0].source_event_ids
                == ("opt002-owner-1", "opt002-owner-2"),
                "topic_shift_is_new_episode": episodes[1].source_event_ids
                == ("opt002-owner-3",),
                "source_first_persisted": all(
                    receipt.status in {"committed", "duplicate"} for receipt in receipts
                ),
                "duplicate_source_is_idempotent": duplicate.status == "duplicate",
            },
            episode_count=len(episodes),
        )


def _scenario_entities_aliases_and_ambiguity() -> Dict[str, Any]:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            _episode("episode-alias", "我有个朋友叫小雨，小雨也叫雨宝。")
        )
        _consolidate(store)
        alias_nodes = store.find_graph_nodes("雨宝")

        for episode_id, node_id, label, evidence_id in (
            ("episode-amb-a", "person-amb-a", "甲", "evidence-amb-a"),
            ("episode-amb-b", "person-amb-b", "乙", "evidence-amb-b"),
        ):
            store.record_episode(_episode(episode_id, f"有一个人叫{label}。"))
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id=episode_id,
                    nodes=(NodeInput(node_id, "person", label),),
                    aliases=(AliasInput(node_id, "小名", evidence_id=evidence_id),),
                    mentions=(
                        MentionInput(episode_id, "小名", resolution_state="ambiguous"),
                    ),
                    evidence=(
                        EvidenceInput(
                            evidence_id,
                            "episode",
                            episode_id,
                            excerpt=f"有一个人叫{label}。",
                        ),
                    ),
                )
            )
        ambiguous = store.find_graph_nodes("小名")
        return _result(
            "entities-aliases-ambiguity",
            {
                "alias_resolves_to_canonical": bool(alias_nodes)
                and alias_nodes[0].label == "小雨",
                "ambiguous_alias_keeps_two_nodes": len(ambiguous) == 2
                and {item.label for item in ambiguous} == {"甲", "乙"},
                "ambiguous_projection_is_not_dropped": store.get_episode(
                    "episode-amb-a"
                )
                is not None
                and store.get_episode("episode-amb-b") is not None,
            },
        )


def _scenario_owner_correction_and_restart(path: Path) -> Dict[str, Any]:
    first = SQLiteMemoryStoreAdapter(path)
    first.record_episode(_episode("episode-name-old", "我叫小林", day=1))
    first.record_episode(_episode("episode-name-new", "我不叫小林了，叫小周。", day=2))
    _consolidate(first)
    first.close()

    reopened = SQLiteMemoryStoreAdapter(path)
    owner = reopened.find_graph_nodes("主人")
    bundle = reopened.recall(
        RecallRequest(
            seed_node_ids=(owner[0].node_id,), mode="basic", assertion_limit=8
        )
    )
    active_values = {
        str(item.object_literal)
        for item in bundle.assertions
        if item.status == "active"
    }
    active_name_claims = [
        item
        for item in bundle.assertions
        if item.predicate == "preferred_name" and item.object_literal == "小周"
    ]
    result = _result(
        "owner-correction-restart",
        {
            "new_value_is_active_and_linked": bool(active_name_claims)
            and bool(active_name_claims[0].qualifiers.get("supersedes_assertion_id")),
            "restart_returns_latest_active_value": active_values == {"小周"},
            "old_evidence_remains_traceable": reopened.get_evidence(
                "evidence:episode-name-old"
            )
            is not None,
        },
    )
    reopened.close()
    return result


def _scenario_conflicts() -> Dict[str, Any]:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        for episode_id, evidence_id, polarity, text in (
            ("episode-conflict-a", "evidence-conflict-a", "positive", "主人喜欢香菜"),
            ("episode-conflict-b", "evidence-conflict-b", "negative", "主人不喜欢香菜"),
        ):
            store.record_episode(
                _episode(episode_id, text, day=1 if polarity == "positive" else 2)
            )
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id=episode_id,
                    nodes=(
                        NodeInput("owner", "person", "主人"),
                        NodeInput("food", "food", "香菜"),
                    ),
                    evidence=(
                        EvidenceInput(evidence_id, "episode", episode_id, excerpt=text),
                    ),
                    assertions=(
                        AssertionInput(
                            "owner",
                            "likes",
                            object_node_id="food",
                            polarity=cast(Literal["positive", "negative"], polarity),
                            evidence_ids=(evidence_id,),
                        ),
                    ),
                )
            )
        bundle = store.recall(RecallRequest(seed_node_ids=("owner",), mode="basic"))
        polarities = {item.qualifiers.get("polarity") for item in bundle.assertions}
        return _result(
            "conflicting-claims",
            {
                "both_polarities_remain": polarities == {"positive", "negative"},
                "one_conflict_group_is_visible": len(bundle.conflicts) == 1,
                "both_sources_are_visible": {item.source_id for item in bundle.evidence}
                == {"episode-conflict-a", "episode-conflict-b"},
            },
        )


def _scenario_idempotency() -> Dict[str, Any]:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        episode = _episode("episode-duplicate", "主人喜欢香菜")
        first = store.record_episode(episode)
        second = store.record_episode(episode)
        first_batch = _consolidate(store)
        second_batch = _consolidate(store)
        owner = store.find_graph_nodes("主人")
        assertions = store.graph_assertions_for((owner[0].node_id,)) if owner else ()
        return _result(
            "idempotent-replay",
            {
                "duplicate_episode_is_deduped": first.status == "committed"
                and second.status == "duplicate"
                and store.count_nodes("episodic") == 1,
                "duplicate_consolidation_is_noop": len(first_batch) == 1
                and not second_batch,
                "projection_has_no_duplicate_assertions": len(assertions)
                == len({item.assertion_id for item in assertions}),
            },
        )


def _scenario_failure_retry() -> Dict[str, Any]:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        episode = _episode("episode-retry", "我叫小林")
        store.record_episode(episode)
        failed = _consolidate(store, model_port=_FailingProposalModel())
        # Move the synthetic record to the retry boundary without touching
        # production data, then run the same deterministic worker again.
        time.sleep(2.2)
        recovered = _consolidate(store)
        row = store.get_episode("episode-retry")
        return _result(
            "failure-retry-convergence",
            {
                "failed_model_keeps_source_retryable": bool(failed)
                and failed[0].failed_episode_ids == ("episode-retry",)
                and row is not None
                and row.content_text == episode.content_text,
                "retry_converges_to_consolidated": any(
                    "episode-retry" in receipt.consolidated_episode_ids
                    for receipt in recovered
                ),
                "source_evidence_survives": store.get_evidence("evidence:episode-retry")
                is not None,
            },
        )


def _scenario_delivery_failure() -> Dict[str, Any]:
    context = ConversationContextStore()
    frame = _frame(1, "我喜欢蓝色。", at=NOW)
    context.observe(frame, NOW)
    hub = CommunicationHub("opt002-elfie")
    hub.register_channel(_FailingChannel(), connect=True)
    elfie = ActorRef(actor_id=ActorId("opt002-elfie"), source_kind="elfie")
    owner = ActorRef(actor_id=ActorId("owner-1"), source_kind="owner")
    envelope = CommunicationEnvelope(
        meta=MessageMeta(
            event_id=EventId("opt002-reply"),
            elfie_id=ElfieId("opt002-elfie"),
            source=elfie,
            occurred_at=NOW + timedelta(seconds=1),
            received_at=NOW + timedelta(seconds=1),
            trace_id=TraceId("opt002-reply-trace"),
        ),
        account_id="owner-account",
        channel_id="chat",
        conversation_id="owner-chat",
        sender=elfie,
        recipients=(owner,),
        direction=MessageDirection.OUTBOUND,
        dedupe_key="opt002-reply-dedupe",
        parts=(TextPart(text="我记住了。"),),
    )
    receipt = hub.send_envelope(envelope)
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(_episode("episode-owner-claim", "我喜欢蓝色"))
        _consolidate(store)
        integrity = store.integrity_report()
        owner_nodes = store.find_graph_nodes("主人")
        owner_claims = (
            store.graph_assertions_for((owner_nodes[0].node_id,)) if owner_nodes else ()
        )
        return _result(
            "delivery-failure-boundary",
            {
                "receipt_is_failed": receipt.status is DeliveryStatus.FAILED,
                "failed_reply_not_in_working_history": (
                    lambda messages: (
                        len(messages) == 2
                        and all(
                            message.sender.source_kind == "owner"
                            for message in messages
                        )
                    )
                )(
                    context.observe(
                        _frame(2, "继续聊。", at=NOW + timedelta(seconds=2)), NOW
                    ).messages
                ),
                "no_fake_completed_interaction": integrity["episodes"] == 1,
                "owner_claim_survives_separately": any(
                    item.predicate == "likes" for item in owner_claims
                ),
            },
        )


def _scenario_isolation() -> Dict[str, Any]:
    with (
        SQLiteMemoryStoreAdapter.in_memory() as first,
        SQLiteMemoryStoreAdapter.in_memory() as second,
    ):
        first.record_episode(
            _episode("episode-elfie-a", "我有个朋友叫小雨。我喜欢蓝色。")
        )
        second.record_episode(
            _episode("episode-elfie-b", "我有个朋友叫小雨。我喜欢红色。")
        )
        _consolidate(first)
        _consolidate(second)
        first_owner = first.find_graph_nodes("主人")[0].node_id
        second_owner = second.find_graph_nodes("主人")[0].node_id
        first_likes = {
            str(item.object_literal)
            for item in first.graph_assertions_for((first_owner,))
            if item.predicate == "likes"
        }
        second_likes = {
            str(item.object_literal)
            for item in second.graph_assertions_for((second_owner,))
            if item.predicate == "likes"
        }
        return _result(
            "elfie-isolation",
            {
                "same_name_is_not_cross_store_data": first_likes == {"蓝色"}
                and second_likes == {"红色"},
                "each_store_has_its_own_episode": first.count_nodes("episodic")
                == second.count_nodes("episodic")
                == 1,
                "each_store_has_its_own_graph": bool(first.find_graph_nodes("小雨"))
                and bool(second.find_graph_nodes("小雨")),
            },
        )


def _source_revision() -> Dict[str, Any]:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = (
            subprocess.run(
                ["git", "diff", "--quiet"], cwd=str(ROOT), check=False
            ).returncode
            != 0
        )
        return {"head": head, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"head": "unknown", "dirty": True}


def run(output: Path | None = None) -> Dict[str, Any]:
    scenario_functions: tuple[tuple[str, Callable[[], Dict[str, Any]]], ...]
    with tempfile.TemporaryDirectory(prefix="elfie-opt002-") as raw_root:
        restart_path = Path(raw_root) / "knowledge.sqlite"
        scenario_functions = (
            ("episode-boundaries", _scenario_episode_boundaries),
            ("entities-aliases-ambiguity", _scenario_entities_aliases_and_ambiguity),
            (
                "owner-correction-restart",
                lambda: _scenario_owner_correction_and_restart(restart_path),
            ),
            ("conflicting-claims", _scenario_conflicts),
            ("idempotent-replay", _scenario_idempotency),
            ("failure-retry-convergence", _scenario_failure_retry),
            ("delivery-failure-boundary", _scenario_delivery_failure),
            ("elfie-isolation", _scenario_isolation),
        )
        results: list[Dict[str, Any]] = []
        for _name, function in scenario_functions:
            try:
                results.append(function())
            except Exception as error:  # noqa: BLE001 - evaluator reports the failed gate
                results.append(
                    {
                        "scenario_id": _name,
                        "passed": False,
                        "checks": {},
                        "failures": [str(error)],
                        "details": {"error": str(error)},
                    }
                )
    report: Dict[str, Any] = {
        "scenario_set": {"version": SCENARIO_SET, "scenario_count": len(results)},
        "source_revision": _source_revision(),
        "results": results,
        "machine_gate_passed": all(item.get("passed") is True for item in results),
        "passed": all(item.get("passed") is True for item in results),
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return report


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the deterministic OPT-002 evaluation."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "report.json")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    report = run(args.output)
    print(
        json.dumps(
            {
                "status": "passed" if report["passed"] else "failed",
                "json": str(args.output),
                "scenario_count": report["scenario_set"]["scenario_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
