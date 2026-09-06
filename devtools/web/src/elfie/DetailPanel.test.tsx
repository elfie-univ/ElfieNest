import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ElfieSession, ElfieTurn } from "./contracts";
import { DetailPanel } from "./DetailPanel";
import type { DetailFocus } from "./viewModel";

const observability = {
  source: "production_turn_record",
  chain: [
    {
      number: "1",
      id: "event_admission",
      title: "Event admission",
      status: "completed",
      input: { source_domain: "communication", message: "你好，今天怎么样？" },
      output: { turn_id: "turn-1", frame_id: "frame-1", status: "completed" },
      raw: { typed_input: { source: "communication" } },
    },
    {
      number: "2",
      id: "context_workspace",
      title: "Context Workspace",
      status: "completed",
      input: { turn_id: "turn-1", message: "你好，今天怎么样？" },
      output: { context_revision: 4, prompt_sections: ["CONTEXT_ONLY", "CURRENT_OBSERVATIONS"] },
      raw: { source: "ModelGenerationRequest.user_prompt", user_prompt: "CONTEXT_ONLY\n今天怎么样？" },
    },
    {
      number: "3",
      id: "setup",
      title: "Setup",
      status: "completed",
      input: { turn_id: "turn-1" },
      output: {
        reasoning_mode: "long",
        response_mode: "direct_reply",
        response_schema: "CognitiveAction@v1",
        temperature: 0.2,
        max_tokens: 1536,
        allowed_tools: [],
        capabilities: { provider: "mock", json_schema: true, tools: false },
      },
      owner_snapshots: [
        { id: "orientation", title: "Orientation", status: "recorded", input: { source_record: "state_before" }, output: { location: "巢内" }, evidence_basis: "state_before", raw: { location: "巢内" } },
        { id: "selfhood", title: "Selfhood", status: "recorded", input: { source_record: "state_before" }, output: { identity_core: { display_name: "艾菲" }, adaptive_self: { big_five: { openness: 0.5 } } }, raw: {} },
        { id: "emotion", title: "Emotion", status: "recorded", input: { source_record: "state_before" }, output: { primary_emotion: "happiness", emotions: { happiness: 0.7 } }, raw: {} },
        { id: "energy", title: "Energy", status: "recorded", input: { source_record: "state_before" }, output: { energy: 88, fatigue: 0.1 }, raw: {} },
        { id: "motivation", title: "Motivation", status: "recorded", input: { source_record: "state_before" }, output: { recovery_status: "stable" }, raw: {} },
      ],
      baseline_memory: { status: "skipped", query: "", reason: "baseline not needed", evidence_basis: "model_request.RELEVANT_MEMORY" },
      raw: { state_before: { energy: 88 } },
    },
    {
      number: "4",
      id: "reasoning_run",
      title: "ReasoningRun",
      status: "completed",
      output: { status: "completed", model_calls: 2, tool_calls: 0, skill_calls: 0 },
      iterations: [
        {
          number: "4.1",
          status: "completed",
          input: { context_revision: 4, observations_before_call: "" },
          context_build: { number: "4.1.1", status: "completed", input: { context_revision: 4 }, output: { user_prompt: "CURRENT_MESSAGE\n你好，今天怎么样？" }, raw: {} },
          model_call: {
            number: "4.1.2",
            status: "completed",
            input: { system_prompt: "你是艾菲。", user_prompt: "CURRENT_MESSAGE\n你好，今天怎么样？" },
            effective_parameters: { provider: "mock", model: "elfie-mock", reasoning_mode: "long", temperature: 0.2, max_tokens: 1536 },
            capabilities: { provider: "mock", json_schema: true, tools: false },
            output: { response: "{\"message\":\"我很好\"}", parsed_result: { action: "reply", message: "我很好" } },
            response: "{\"message\":\"我很好\"}",
            result: { action: "reply", message: "我很好" },
            raw: { request: { user_prompt: "CURRENT_MESSAGE\n你好，今天怎么样？" } },
          },
          action: { number: "4.1.3", status: "completed", output: { type: "recall_memory", query: "用户近况" }, raw: { source: "model_call" } },
          observations: [{ kind: "observation", operation: "memory_recall", status: "returned", query: "你好，今天怎么样？", reason: "relevant", returned_evidence: "主人喜欢被温柔问候。", raw: {} }],
          completion: [{ kind: "verify", status: "completed", summary: "reply accepted" }],
          guard: { number: "4.1.6", status: "skipped", output: {}, skip_reason: "separate Guard record is not persisted", evidence_basis: "ReasoningRun.status + ordered steps", raw: { source: "production_turn_record", available: false } },
        },
        {
          number: "4.2",
          status: "completed",
          input: { context_revision: 5 },
          context_build: { number: "4.2.1", status: "completed", input: { context_revision: 5 }, output: { user_prompt: "CURRENT_MESSAGE\n你好，今天怎么样？" }, raw: {} },
          model_call: {
            number: "4.2.2",
            status: "completed",
            input: { system_prompt: "你是艾菲。", user_prompt: "CURRENT_MESSAGE\n主人喜欢被温柔问候。" },
            effective_parameters: { provider: "mock", model: "elfie-mock", reasoning_mode: "long" },
            capabilities: { provider: "mock", json_schema: true, tools: false },
            output: { response: "{\"message\":\"我很好，谢谢关心。\"}", parsed_result: { action: "reply", message: "我很好，谢谢关心。" } },
            response: "{\"message\":\"我很好，谢谢关心。\"}",
            result: { action: "reply", message: "我很好，谢谢关心。" },
            raw: { request: { user_prompt: "CURRENT_MESSAGE\n主人喜欢被温柔问候。" } },
          },
          action: { number: "4.2.3", status: "completed", output: { type: "answer", content: "我很好，谢谢关心。" }, raw: { source: "model_call" } },
          observations: [],
          completion: [{ kind: "verify", status: "completed", summary: "reply accepted" }],
          guard: { number: "4.2.6", status: "skipped", output: {}, skip_reason: "separate Guard record is not persisted", evidence_basis: "ReasoningRun.status + ordered steps", raw: { source: "production_turn_record", available: false } },
        },
      ],
      raw: { steps: [{ kind: "model" }, { kind: "verify" }] },
    },
    {
      number: "5",
      id: "turn_decision",
      title: "TurnDecision",
      status: "completed",
      input: { reasoning_status: "completed", model_calls: 2 },
      output: { plan_id: "plan-1", message_texts: ["我很好，谢谢关心。"], message_intents: [{ intent_id: "message-1", status: "accepted" }] },
      raw: {},
    },
    {
      number: "6",
      id: "governance_delivery",
      title: "Governance and delivery",
      status: "completed",
      input: { message_intents: [{ intent_id: "message-1" }] },
      output: { result: { success: true, message: "我很好，谢谢关心。" }, receipts: [{ receipt_id: "receipt-1", status: "completed" }], activity_proposals: [] },
      delivery: {
        number: "6.1",
        id: "delivery",
        title: "Delivery / Activity request",
        status: "completed",
        input: { message_intents: [{ intent_id: "message-1" }] },
        output: { result: { success: true, message: "我很好，谢谢关心。" }, receipts: [{ receipt_id: "receipt-1", status: "completed" }] },
        activity_request: { title: "Activity request", status: "skipped", skip_reason: "no activity request in TurnDecision", evidence_basis: "TurnDecision.activity_intents", raw: {} },
        raw: { receipt_id: "receipt-1" },
      },
      raw: {},
    },
    {
      number: "7",
      id: "settlement",
      title: "Settlement",
      status: "completed",
      input: { turn_id: "turn-1", receipt_count: 1 },
      output: { recorded_turn_id: "turn-1", duration_ms: 240, state_after: { energy: 87, fatigue: 0.11, primary_emotion: "happiness" }, state_diff: { energy: { before: 88, after: 87 } }, warnings: [], cognitive_turn: { status: "completed" } },
      raw: {},
    },
  ],
};

const turn = {
  turn_id: "turn-1",
  timestamp: "2026-09-04T06:00:00.000Z",
  stimulus_bundle: { source_domain: "communication", message: "你好，今天怎么样？" },
  result: { success: true, message: "我很好，谢谢关心。" },
  duration_ms: 240,
  state_before: { energy: 88 },
  state_after: { energy: 87 },
  state_diff: { energy: { before: 88, after: 87 } },
  decision: { spoken_texts: [], message_texts: ["我很好，谢谢关心。"], message_intents: [], speech_intents: [], motion_intents: [], expression_intents: [], action_intents: [], activity_intents: [], noop_intents: [] },
  trace: { stages: { observability } },
} as unknown as ElfieTurn;

const session = { turns: [turn], current_state: turn.state_after } as unknown as ElfieSession;

function renderInspector(
  initialTab = "链路",
  selectedTurn: ElfieTurn | null = turn,
  focus: DetailFocus = "chain",
): string {
  return renderToStaticMarkup(<DetailPanel
    focus={focus}
    initialTab={initialTab}
    onClose={() => undefined}
    open
    previewResult={null}
    selectedTurn={selectedTurn}
    session={session}
  />);
}

describe("Elfie Lab Turn Inspector", () => {
  it("does not render a right panel without a selected Turn", () => {
    expect(renderInspector("链路", null)).toBe("");
  });

  it("renders the seven production stages and actual reasoning iterations", () => {
    const markup = renderInspector();

    expect(markup).toContain("Turn 处理链路");
    for (const label of ["Event admission", "Context Workspace", "Setup", "ReasoningRun", "TurnDecision", "Governance and delivery", "Settlement"]) {
      expect(markup).toContain(label);
    }
    const stagePositions = ["Event admission", "Context Workspace", "Setup", "ReasoningRun", "TurnDecision", "Governance and delivery", "Settlement"]
      .map((label) => markup.indexOf(label));
    expect(stagePositions).toEqual([...stagePositions].sort((left, right) => left - right));
    expect(markup).toContain("4.1");
    expect(markup).toContain("4.2");
    expect(markup).not.toContain("4.1.1");
    expect(markup).not.toContain("4.1.2");
    expect(markup).not.toContain("4.2.2");
    expect(markup).not.toContain("有效参数");
    expect(markup).not.toContain("模型输入");
    expect(markup).not.toContain("模型原始输出");
    expect(markup).not.toContain("查看原始 JSON");
    expect(markup).not.toContain("对下一步影响");
    expect(markup).not.toContain("本轮处理链路");
    expect(markup).not.toContain("detail-tabs");
  });

  it("keeps the production reasoning tree collapsed below the selected Run", () => {
    const markup = renderInspector();

    expect(markup).toContain("trace-disclosure-trigger");
    expect(markup).toContain("4.1");
    expect(markup).toContain("Iteration");
    expect(markup).toContain("aria-expanded=\"false\"");
    expect(markup).not.toContain("模型输入（完整消息）");
    expect(markup).not.toContain("模型原始输出");
  });

  it("keeps delivery as a child of governance", () => {
    const markup = renderInspector("链路", turn, "output");

    expect(markup).toContain("Governance and delivery");
    expect(markup).toContain("6.1");
    expect(markup).toContain("Delivery / Activity request");
  });

  it("shows the five setup owner snapshots without returning to raw JSON by default", () => {
    const markup = renderInspector("快照");

    expect(markup).toContain("模块快照");
    for (const label of ["Orientation", "Selfhood", "Emotion", "Energy", "Motivation"]) {
      expect(markup).toContain(label);
    }
    expect(markup).toContain("trace-disclosure-trigger");
    expect(markup).not.toContain("模块输入");
    expect(markup).not.toContain("模块输出");
    expect(markup).not.toContain("模块视图");
  });

  it("labels the trace as production provenance instead of claiming a real model", () => {
    const markup = renderInspector();

    expect(markup).toContain("记录来源");
    expect(markup).toContain("生产链路");
    expect(markup).not.toContain(">真实<");
  });

  it("does not synthesize stage cards for a Turn without an observability trace", () => {
    const turnWithoutProjection = { ...turn, trace: { stages: {} } } as unknown as ElfieTurn;
    const markup = renderInspector("链路", turnWithoutProjection);

    expect(markup).not.toContain("Event admission");
    expect(markup).not.toContain("Context Workspace");
    expect(markup).toContain("未采集");
  });
});
