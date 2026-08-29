import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { EvaluationRun } from "./contracts";
import {
  comparisonGradeForReports,
  EvaluationWorkspace,
  nextSelectedEvaluationRuns,
  nextSelectedReportIds,
  selectActiveEvaluationRun,
  shortEvaluationId,
} from "./EvaluationWorkspace";

describe("Elfie Lab batch evaluation workspace", () => {
  it("renders a separate report table instead of the single-Elfie guided flow", () => {
    const markup = renderToStaticMarkup(<EvaluationWorkspace
      elfies={[]}
      food="mock"
      foods={[]}
      onOpenExperiment={() => undefined}
      session={null}
    />);

    expect(markup).toContain("批量评测");
    expect(markup).toContain("评测批次");
    expect(markup).toContain("新建评测");
    expect(markup).toContain("批次 / 报告");
    expect(markup).not.toContain("运行评测");
    expect(markup).not.toContain("Godot");
  });

  it("classifies strict, observational, and incompatible selections honestly", () => {
    const base = {
      fixture_sha256: "fixture",
      test_plan_sha256: "plan",
      source_snapshot_sha256: "code-a",
      food_spec_sha256: "food-a",
      judge_spec_sha256: "judge",
    } as EvaluationRun;

    expect(comparisonGradeForReports(base, {
      ...base,
      food_spec_sha256: "food-b",
    } as EvaluationRun)).toBe("strict");
    expect(comparisonGradeForReports(base, {
      ...base,
      source_snapshot_sha256: "code-b",
      food_spec_sha256: "food-b",
    } as EvaluationRun)).toBe("observational");
    expect(comparisonGradeForReports(base, {
      ...base,
      judge_spec_sha256: "judge-b",
    } as EvaluationRun)).toBe("observational");
    expect(comparisonGradeForReports(base, {
      ...base,
      fixture_sha256: "another-fixture",
    } as EvaluationRun)).toBe("incompatible");
  });

  it("never carries another Elfie's result into a scoped legacy selection", () => {
    const oldRun = { elfie_id: "elfie-old", run_id: "evaluation-old", suite: "quick" } as EvaluationRun;
    const selectedRun = { elfie_id: "elfie-selected", run_id: "evaluation-selected", suite: "quick" } as EvaluationRun;
    expect(selectActiveEvaluationRun(oldRun, [selectedRun], "quick", "elfie-selected")).toBe(selectedRun);
  });

  it("labels report, batch, snapshot, and comparison identifiers by their real kind", () => {
    expect(shortEvaluationId("evaluation_deadbeef001122")).toBe("#R-deadbeef00");
    expect(shortEvaluationId("evaluation_batch_deadbeef001122")).toBe("#E-deadbeef00");
    expect(shortEvaluationId("evaluation_snapshot_deadbeef001122")).toBe("#S-deadbeef00");
    expect(shortEvaluationId("comparison-deadbeef001122")).toBe("#C-deadbeef00");
  });

  it("selects a paired batch atomically instead of leaving a partial A-only selection", () => {
    expect(nextSelectedReportIds(["outside"], ["a", "b"])).toBeNull();
    expect(nextSelectedReportIds(["a"], ["a", "b"])).toEqual(["a", "b"]);
    expect(nextSelectedReportIds(["a", "b"], ["a", "b"])).toEqual([]);
  });

  it("keeps a selected report available while choosing the second report on another page", () => {
    const first = { run_id: "evaluation-first" } as EvaluationRun;
    const second = { run_id: "evaluation-second" } as EvaluationRun;

    expect(nextSelectedEvaluationRuns([first], [second], [second.run_id])).toEqual([first, second]);
  });
});
