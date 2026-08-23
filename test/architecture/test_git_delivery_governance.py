"""Regression tests for explicit Git action authorization and one-PR delivery."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRANCH_SKILL = PROJECT_ROOT / ".agents/skills/git-submit-and-push/SKILL.md"
MAIN_SKILL = PROJECT_ROOT / ".agents/skills/git-main-delivery/SKILL.md"


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _action_matrix(relative_path: str) -> dict[str, str]:
    source = _read(relative_path)
    start = source.index("<!-- git-action-matrix:start -->")
    end = source.index("<!-- git-action-matrix:end -->", start)
    rows: dict[str, str] = {}
    for line in source[start:end].splitlines():
        if not line.startswith("| `"):
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        rows[columns[0].strip("`")] = columns[2].strip("`")
    return rows


def test_bilingual_action_matrices_have_the_same_bounded_actions() -> None:
    expected = {
        "implement": "local-work",
        "commit": "local-commit",
        "push": "branch-push",
        "create-pr": "one-pr-stop",
        "merge-main": "one-pr-merge",
        "complete": "no-git",
    }

    assert _action_matrix("CONTRIBUTING.md") == expected
    assert _action_matrix("CONTRIBUTING_zh.md") == expected


def test_plans_and_history_cannot_self_authorize_remote_git_actions() -> None:
    rules = _read("AGENTS.md")

    assert "已批准计划中明确包含的远端交付" not in rules
    assert "计划、ADR、技能或历史记录不能产生 Git 远端授权" in rules
    assert "direct-main-merge" in rules
    assert "ElfieNest 禁止" in rules


def test_branch_push_skill_contains_no_pr_merge_or_main_mutation() -> None:
    source = BRANCH_SKILL.read_text(encoding="utf-8")
    forbidden = (
        "gh pr create",
        "gh pr merge",
        "enqueuePullRequest",
        "dequeuePullRequest",
        "refs/heads/main",
        "git push origin HEAD:main",
    )

    for command in forbidden:
        assert command not in source


def test_pr_and_queue_mutations_exist_only_in_the_narrow_main_skill() -> None:
    mutations = (
        "gh pr create",
        "gh pr merge",
        "enqueuePullRequest",
        "dequeuePullRequest",
    )
    skill_sources = {
        path: path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / ".agents/skills").glob("*/SKILL.md")
    }

    for mutation in mutations:
        owners = {
            path.parent.name
            for path, source in skill_sources.items()
            if mutation in source
        }
        assert owners == {"git-main-delivery"}


def test_main_delivery_skill_freezes_one_candidate_and_fails_closed() -> None:
    source = MAIN_SKILL.read_text(encoding="utf-8")
    metadata = (MAIN_SKILL.parent / "agents/openai.yaml").read_text(encoding="utf-8")

    for required in (
        "每次最多创建或复用一个 PR",
        "--match-head-commit",
        "mergeQueueEntry",
        "required_approving_review_count",
        "required_reviewers",
        "候选 SHA 变化",
        "dequeuePullRequest",
        "无法确认",
        "停止",
    ):
        assert required in source
    assert "allow_implicit_invocation: false" in metadata


def test_solo_maintainer_review_limit_is_explicit_and_self_expiring() -> None:
    skill = MAIN_SKILL.read_text(encoding="utf-8")
    english = _read("docs/developer/contracts/repository-governance.md")
    chinese = _read("docs/zh/developer/contracts/repository-governance.md")

    assert "Known limitation: solo-maintainer stage" in english
    assert "second verified maintainer" in english
    assert "已知限制：单维护者阶段" in chinese
    assert "第二名具有仓库写权限的已验证维护者" in chinese
    assert "单维护者例外不能继续沿用" in skill


def test_contract_allows_one_long_lived_branch_but_requires_exact_multi_pr_approval() -> (
    None
):
    english = _read("docs/developer/contracts/repository-governance.md")
    chinese = _read("docs/zh/developer/contracts/repository-governance.md")

    assert "A feature branch may remain open across sessions and days" in english
    assert "exact PR count" in english
    assert "功能分支可以跨会话、跨天持续存在" in chinese
    assert "准确 PR 数量" in chinese


def test_delivery_slo_starts_at_final_candidate_release_and_never_resets_per_pr() -> (
    None
):
    english = _read("docs/developer/contracts/repository-governance.md")
    chinese = _read("docs/zh/developer/contracts/repository-governance.md")

    assert "final candidate" in english
    assert "must not reset for each Pull Request" in english
    assert "最终候选" in chinese
    assert "不得按每个 Pull Request 重新计时" in chinese


def test_pr_template_does_not_require_results_that_only_exist_after_creation() -> None:
    template = _read(".github/pull_request_template.md")

    assert "elfienest/ci-gate：" not in template
    assert "elfienest/merge-gate：" not in template
    assert "ci-gate` 与 `elfienest/merge-gate` 已成功" not in template
    assert "候选提交 SHA：" in template
    assert "用户验收" in template
