import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { EvaluationRun } from "./contracts";
import {
  EvaluationWorkspace,
  selectActiveEvaluationRun,
} from "./EvaluationWorkspace";

describe("Elfie Lab evaluation workspace", () => {
  it("presents one-click comparison without exposing internal family jargon", () => {
    const markup = renderToStaticMarkup(<EvaluationWorkspace
      food="mock"
      foods={[]}
      onOpenExperiment={() => undefined}
      session={null}
    />);

    expect(markup).toContain("版本评测");
    expect(markup).toContain("快速检查");
    expect(markup).toContain("标准评测");
    expect(markup).toContain("运行评测");
    expect(markup).not.toContain("场景家族");
    expect(markup).not.toContain("Godot");
  });

  it("does not start a run with an unconfigured candidate Food", () => {
    const markup = renderToStaticMarkup(<EvaluationWorkspace
      food="elfie_lab_test"
      foods={[{
        key: "elfie_lab_test",
        display_name: "Elfie Lab 测试粮",
        description: "请先配置测试粮食",
        model: "",
        reasoning: "",
        ready_for_attempt: false,
        unavailable_reason: "尚未配置测试粮食",
      }]}
      onOpenExperiment={() => undefined}
      session={null}
    />);

    expect(markup).toMatch(
      /<button class="evaluation-primary-action" disabled=""[^>]*>运行评测<\/button>/,
    );
    expect(markup).toContain("尚未配置，不能运行评测");
  });

  it("never carries another Elfie's result into the selected workspace", () => {
    const oldRun = {
      elfie_id: "elfie-old",
      run_id: "evaluation-old",
      suite: "quick",
    } as EvaluationRun;
    const selectedRun = {
      elfie_id: "elfie-selected",
      run_id: "evaluation-selected",
      suite: "quick",
    } as EvaluationRun;

    expect(
      selectActiveEvaluationRun(
        oldRun,
        [selectedRun],
        "quick",
        "elfie-selected",
      ),
    ).toBe(selectedRun);
  });
});
