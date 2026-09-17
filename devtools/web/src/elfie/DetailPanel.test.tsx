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
      duration_ms: 18,
      input: { source_domain: "communication", message: "你好，今天怎么样？" },
      output: { turn_id: "turn-1", frame_id: "frame-1", status: "completed" },
      raw: { typed_input: { source: "communication" } },
    },
    {
      number: "2",
      id: "context_workspace",
      title: "Context Workspace",
      status: "completed",
      duration_ms: 0.27,
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

const session = {
  profile: { name: "艾菲" },
  turns: [turn],
  current_state: turn.state_after,
} as unknown as ElfieSession;

function renderInspector(
  initialTab = "链路",
  selectedTurn: ElfieTurn | null = turn,
  focus: DetailFocus = "chain",
  defaultOpenDetails?: readonly string[],
): string {
  return renderToStaticMarkup(<DetailPanel
    defaultOpenDetails={defaultOpenDetails}
    focus={focus}
    initialTab={initialTab}
    onClose={() => undefined}
    open
    previewResult={null}
    selectedTurn={selectedTurn}
    session={session}
  />);
}

type FixtureNode = Record<string, unknown>;

function withChainNodes(
  overrides: Readonly<Record<number, (node: FixtureNode) => FixtureNode>>,
): ElfieTurn {
  const chain = observability.chain.map((node: FixtureNode, index: number) =>
    overrides[index] ? overrides[index](node) : node,
  );
  return { ...turn, trace: { stages: { observability: { ...observability, chain } } } } as unknown as ElfieTurn;
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
    expect(markup).toContain("耗时 18 ms");
    expect(markup).toContain("耗时 0.27 ms");
    expect(markup).toContain("2 个迭代");
    expect(markup).not.toContain("Memory skipped");
    expect(markup).not.toContain("个快照");
    expect(markup).not.toContain("revision 4");
    expect(markup).toContain('title="本轮输入：确认输入通道与处理内容"');
    expect(markup).toContain('title="结算：提交状态候选与记忆写回，落持久化证据"');
    expect(markup).not.toContain("data-tip=");
    expect(markup).not.toContain("trace-node-chevron");
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

  it("shows short anomaly reasons in collapsed stage metas", () => {
    const markup = renderInspector("链路", withChainNodes({
      5: (node) => ({ ...node, output: { ...(node.output as FixtureNode), result: { success: false, error: "delivery rejected" } } }),
      6: (node) => ({ ...node, output: { ...(node.output as FixtureNode), warnings: ["memory_write_degraded", "state_recomputed"] } }),
    }));

    expect(markup).toContain("交付失败");
    expect(markup).toContain("warning 2");
    expect(markup).not.toContain("个快照");
  });

  it("keeps a normal setup stage meta free of counts and reasons", () => {
    const markup = renderInspector("链路", withChainNodes({
      2: (node) => ({ ...node, baseline_memory: { ...(node.baseline_memory as FixtureNode), status: "recalled" } }),
    }));

    expect(markup).not.toContain("个快照");
    expect(markup).not.toContain("Memory skipped");
    expect(markup).toContain('title="运行准备：冻结外部状态与记忆版本，确定推理模式与预算"');
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

  it("shows the compiled prompt pair and complete model-call evidence without opaque metadata", () => {
    const enriched = withChainNodes({
      3: (node) => {
        const iterations = node.iterations as unknown as FixtureNode[];
        const firstIteration = iterations[0];
        if (firstIteration === undefined) throw new Error("fixture missing first iteration");
        return {
          ...node,
          iterations: [
            {
              ...firstIteration,
              context_build: {
                number: "4.1.1",
                status: "compiled",
                output: {
                  system_prompt: "COMPILED SYSTEM",
                  user_prompt: "COMPILED USER",
                },
                raw: { context_revision: 4, frame_id: "frame-1" },
              },
              model_call: {
                ...firstIteration.model_call as FixtureNode,
                status: "returned",
                effective_parameters: {
                  provider: "mock",
                  model: "elfie-mock",
                  reasoning_mode: "long",
                  response_mode: "direct_reply",
                  response_schema: "CognitiveAction",
                  response_schema_definition: { type: "object", properties: { type: { type: "string" } } },
                  temperature: 0.2,
                  max_tokens: 1536,
                  timeout_seconds: 11.5,
                  allowed_tools: [],
                  tool_definition_count: 0,
                  skill_count: 0,
                  context_revision: 4,
                  frame_id: "frame-1",
                },
                input: { system_prompt: "MODEL SYSTEM", user_prompt: "MODEL USER" },
                output: { response: "MODEL RAW RESPONSE" },
                response: "MODEL RAW RESPONSE",
              },
            },
            iterations[1],
          ],
        };
      },
    });
    const markup = renderInspector("链路", enriched, "chain", [
      "reasoning_run",
      "reasoning-4.1",
      "reasoning-4.1-context",
      "reasoning-4.1-model",
    ]);

    expect(markup).toContain("编译结果（完整消息）");
    expect(markup).toContain("COMPILED SYSTEM");
    expect(markup).toContain("COMPILED USER");
    expect(markup).toContain("有效参数");
    for (const label of ["推理模式", "响应结构", "采样温度", "最大输出 Token", "单次请求超时（秒）", "工具定义", "技能数量"]) {
      expect(markup).toContain(label);
    }
    expect(markup).toContain("无");
    expect(markup).toContain("模型输入（完整消息）");
    expect(markup).toContain("MODEL SYSTEM");
    expect(markup).toContain("模型原始输出");
    expect(markup).toContain("MODEL RAW RESPONSE");
    expect(markup).not.toContain("已记录");
    expect(markup).not.toContain("context v4");
    expect(markup).not.toContain("frame-1");
    expect(markup.match(/<strong>模型调用<\/strong>/g)).toHaveLength(1);
  });

  it("shows token usage only when reported and keeps elapsed time in the model-call header", () => {
    const enriched = withChainNodes({
      3: (node) => {
        const iterations = node.iterations as unknown as FixtureNode[];
        const firstIteration = iterations[0];
        if (firstIteration === undefined) throw new Error("fixture missing first iteration");
        return {
          ...node,
          iterations: [{
            ...firstIteration,
            model_call: {
              ...firstIteration.model_call as FixtureNode,
              prompt_tokens: 120,
              completion_tokens: 45,
              provider_latency_ms: 321.5,
            },
          }],
        };
      },
    });
    const markup = renderInspector("链路", enriched, "chain", ["reasoning_run", "reasoning-4.1", "reasoning-4.1-model"]);

    expect(markup).toContain("Token 用量");
    expect(markup).toContain("输入 Token");
    expect(markup).toContain("输出 Token");
    expect(markup).toContain("总 Token");
    expect(markup).toContain(">165<");
    expect(markup).not.toContain("Provider 延迟");
    expect(markup).not.toContain(">321.5<");

    const withoutUsage = renderInspector("链路", turn, "chain", ["reasoning_run", "reasoning-4.1", "reasoning-4.1-model"]);
    expect(withoutUsage).not.toContain("Token 用量");
  });

  it("keeps the ReasoningRun overview non-duplicative and hides empty iteration input", () => {
    const enriched = withChainNodes({
      3: (node) => {
        const iterations = node.iterations as unknown as FixtureNode[];
        const firstIteration = iterations[0];
        if (firstIteration === undefined) throw new Error("fixture missing first iteration");
        return {
          ...node,
          status: "safe_noop",
          output: {
            status: "safe_noop",
            model_calls: 1,
            tool_calls: 0,
            skill_calls: 0,
            failure_reason: "cognitive_action_validation_failed",
            fallback_reason: "cognitive_action_validation_failed",
            selected_mode: "json_text",
          },
          iterations: [{
            ...firstIteration,
            input: {},
            completion: [{ kind: "verify", status: "safe_noop", summary: "safe fallback" }],
            model_call: {
              ...firstIteration.model_call as FixtureNode,
              output: { response: "MODEL RAW RESPONSE", selected_mode: "json_text" },
            },
          }],
        };
      },
    });
    const markup = renderInspector("链路", enriched, "chain", [
      "reasoning_run",
      "reasoning-4.1",
      "reasoning-4.1-model",
    ]);

    expect(markup).toContain("模型调用次数");
    expect(markup).toContain("工具调用次数");
    expect(markup).toContain("技能调用次数");
    expect(markup).toContain("失败/回退原因");
    expect(markup).toContain("Host 解析模式");
    expect(markup).not.toContain("<dt>状态</dt>");
    expect(markup).not.toContain("失败原因");
    expect(markup).not.toContain("降级原因");
    expect(markup).not.toContain("迭代输入");
    expect(markup.match(/终止回退/g)).toHaveLength(1);
  });

  it("keeps every reasoning substep readable with duration-only collapsed metadata", () => {
    const enriched = withChainNodes({
      3: (node) => {
        const iterations = node.iterations as unknown as FixtureNode[];
        const firstIteration = iterations[0];
        if (firstIteration === undefined) throw new Error("fixture missing first iteration");
        return {
          ...node,
          iterations: [{
            ...firstIteration,
            context_build: { ...(firstIteration.context_build as FixtureNode), duration_ms: 0.9 },
            model_call: { ...(firstIteration.model_call as FixtureNode), duration_ms: 4110 },
            action: { ...(firstIteration.action as FixtureNode), duration_ms: 2.4 },
            observation_stage: { number: "4.1.4", status: "observed", duration_ms: 3.2, raw: { source: "test" } },
            completion: [{ kind: "verify", status: "accepted", summary: "reply accepted", duration_ms: 1.1 }],
            guard: { number: "4.1.6", status: "continued", duration_ms: 0.8, output: { decision: "继续" }, raw: { source: "test" } },
          }],
        };
      },
    });
    const markup = renderInspector("链路", enriched, "chain", ["reasoning_run", "reasoning-4.1"]);

    for (const title of ["上下文构建", "模型调用", "认知行动", "观察记录", "完成判定", "守卫判断"]) {
      expect(markup).toContain(`<strong>${title}</strong>`);
    }
    for (const duration of ["耗时 0.90 ms", "耗时 4.11 s", "耗时 2 ms", "耗时 1 ms", "耗时 0.80 ms"]) {
      expect(markup).toContain(duration);
    }
    expect(markup).not.toContain("elfie-mock ·");
    expect(markup).not.toContain("Host 解析</small>");
    expect(markup).not.toContain("Memory Recall");
    expect(markup).not.toContain("Observations");
  });

  it("keeps delivery as a child of governance", () => {
    const markup = renderInspector("链路", turn, "output");

    expect(markup).toContain("Governance and delivery");
    expect(markup).toContain("6.1");
    expect(markup).toContain("Delivery / Activity request");
  });

  it("shows the five setup owner snapshots without returning to raw JSON by default", () => {
    const markup = renderInspector("快照");

    expect(markup).toContain("进入推理时冻结状态");
    for (const label of ["Orientation", "Selfhood", "Emotion", "Energy", "Motivation"]) {
      expect(markup).toContain(label);
    }
    expect(markup).toContain("trace-disclosure-trigger");
    expect(markup).not.toContain("模块输入");
    expect(markup).not.toContain("模块输出");
    expect(markup).not.toContain("快照来源");
    expect(markup).not.toContain("冻结快照");
  });

  it("shows the model-facing Selfhood projection instead of its internal state", () => {
    const enriched = withChainNodes({
      2: (node) => ({
        ...node,
        selfhood_projection: {
          identity_core_text: "我是艾菲，是 ElfieNest 的居民。",
          adaptive_self_text: "我会先观察，再清楚地表达。",
        },
      }),
    });
    const markup = renderInspector("快照", enriched, "chain", ["setup", "setup-selfhood"]);

    expect(markup).toContain("身份核心投影");
    expect(markup).toContain("我是艾菲，是 ElfieNest 的居民。");
    expect(markup).toContain("自适应自我投影");
    expect(markup).toContain("我会先观察，再清楚地表达。");
    expect(markup).not.toContain("开放性");
    expect(markup).not.toContain("interaction_tendency_ids");
  });

  it("labels the trace as production provenance instead of claiming a real model", () => {
    const markup = renderInspector();

    expect(markup).toContain("记录来源");
    expect(markup).toContain("生产链路");
    expect(markup).not.toContain(">真实<");
  });

  it("hides the empty completion-fields placeholder while keeping the verdict", () => {
    const markup = renderInspector("链路", turn, "chain", ["reasoning_run", "reasoning-4.1", "4.1.completion-0"]);

    expect(markup).toContain("判断结果");
    expect(markup).toContain("reply accepted");
    expect(markup.match(/<p class="trace-muted">未采集<\/p>/g) ?? []).toHaveLength(1);
  });

  it("does not synthesize stage cards for a Turn without an observability trace", () => {
    const turnWithoutProjection = { ...turn, trace: { stages: {} } } as unknown as ElfieTurn;
    const markup = renderInspector("链路", turnWithoutProjection);

    expect(markup).not.toContain("Event admission");
    expect(markup).not.toContain("Context Workspace");
    expect(markup).toContain("未采集");
  });

  it("wires projected layer-2 blocks into stage details", () => {
    const enriched = withChainNodes({
      0: (node) => ({ ...node, admission: {
        admitted: true,
        trigger_reason: "greeting salience above defer threshold",
        cutoff_seq: 42,
        event_count: 3,
      } }),
      1: (node) => ({ ...node,
        appended: {
          message_count: 2,
          active_topic_message_count: 1,
          channel_id: "channel-dawn",
          conversation_id: "conversation-dawn",
          summaries: [{ summary_id: "summary-1", content: "主人正在筹备周末的纪录片之夜。", unresolved_count: 0 }],
        },
        output: {
          ...(node.output as FixtureNode),
          conversation: [{ role: "elfie", content: "上次的纪录片终于上线了。" }, { role: "owner", content: "记得一起看。" }],
        },
      }),
      2: (node) => ({ ...node,
        budget: { depth_basis: "quiet hours default depth", max_steps: 6, max_model_calls: 8, deadline_seconds: 30 },
        selfhood_projection: { identity_core_text: "艾菲，巢内晨间的狐狸", adaptive_self_text: "温和、好奇、偏好短句回应" },
      }),
      5: (node) => ({ ...node, routing: { routed: "reply_via_message", response_channel_id: "channel-dusk", memory_eligible: true } }),
      6: (node) => ({ ...node,
        memory_writeback: {
          candidates: [{ candidate_id: "cand-1", content: "主人分享了纪录片上线的好消息。", confidence: 0.8 }],
          commits: [{ event_id: "evt-9", status: "committed", content: "共同看纪录片的约定被记住了。", base_revision: 12, revision_after: 13 }],
          reinforcements: [{ target_kind: "episode", target_id: "episode-3", outcome_kind: "reinforced" }],
        },
        emotion_changes: {
          stage: "settlement",
          changed_dimensions: ["happiness"],
          dimensions: [{ name: "happiness", before: 0.6, after: 0.72 }],
        },
        energy_settlement: { consumed: 1.2, charged: 0.4, released: 0.2, energy_state: { energy: 87 } },
      }),
    });
    const openedStages = ["event_admission", "context_workspace", "setup", "governance_delivery", "settlement"];
    const markup = renderInspector("链路", enriched, "chain", openedStages);

    for (const title of ["输入通道", "文字", "上下文分区", "历史交互", "压缩摘要", "路由明细", "<strong>记忆写回</strong>", "情绪变化", "能量结算", "处理方式", "最大步数", "进入推理时冻结状态"]) {
      expect(markup).toContain(title);
    }
    for (const collapsedValue of [
      "greeting salience above defer threshold",
      "committed",
      "主人正在筹备周末的纪录片之夜。",
      "reply_via_message",
      "quiet hours default depth",
      "温和、好奇、偏好短句回应",
    ]) {
      expect(markup).not.toContain(collapsedValue);
    }
    expect(markup).toContain("上次的纪录片终于上线了。");
    expect(markup).toContain("记得一起看。");
    expect(markup).toContain('aria-label="历史交互"');
    expect(markup).not.toContain('trace-disclosure-title"><strong>历史交互');
    expect(markup).not.toContain("channel-dawn");
    expect(markup).not.toContain("conversation-dawn");

    const plain = renderInspector("链路", turn, "chain", ["event_admission", "context_workspace", "governance_delivery", "settlement"]);
    for (const title of ["上下文分区", "历史交互", "压缩摘要", "路由明细", "<strong>记忆写回</strong>", "情绪变化", "能量结算", "处理方式", "进入推理时冻结状态"]) {
      expect(plain).not.toContain(title);
    }
  });

  it("projects populated Context Workspace records and keeps history inline", () => {
    const enriched = withChainNodes({
      1: (node) => ({ ...node,
        appended: {
          channel_id: "channel-dawn",
          conversation_id: "conversation-dawn",
        },
        output: {
          ...(node.output as FixtureNode),
          workspace: {
            threads: [{
              channel_id: "channel-dawn",
              conversation_id: "conversation-dawn",
              messages: [
                { event_id: "event-prior", speaker: "主人", content: "上一轮历史", is_current: false },
                { event_id: "event-current", speaker: "主人", content: "当前消息正文", is_current: true },
                { event_id: "elfie-reply:intent-current", speaker: "艾菲", content: "当前回复正文", is_current: true },
              ],
              summaries: [{
                summary_id: "summary-1",
                occurred_from: "2026-09-06T10:00:00+00:00",
                occurred_to: "2026-09-06T10:30:00+00:00",
                content: "压缩过往",
                unresolved_items: ["待确认"],
              }],
              active_state: {
                state: "活跃",
                participants: ["owner-1", "elfie-1"],
                started_at: "2026-09-06T10:00:00+00:00",
                last_activity_at: "2026-09-07T10:00:00+00:00",
                pending_close: false,
                message_count: 1,
                summary_count: 1,
              },
              pending_states: [{ state: "待关闭", pending_close: true }],
            }],
            pending_replies: [{
              status: "待回执",
              channel_id: "channel-dawn",
              conversation_id: "conversation-dawn",
              content: "待发送回复",
              prepared_at: "2026-09-07T10:02:00+00:00",
              memory_eligible: true,
            }],
            pending_memory: [{
              status: "待写入 Memory",
              event_kind: "interaction",
              occurred_from: "2026-09-07T09:00:00+00:00",
              occurred_to: "2026-09-07T09:01:00+00:00",
              content_text: "待记忆经历",
              summary_text: "精简经历",
              stimulus: "触发输入",
              sensory: ["听觉"],
              metadata: { source: "lab" },
            }],
            checkpoint: {
              status: "已保存",
              thread_count: 1,
              pending_reply_count: 1,
              pending_memory_count: 1,
            },
          },
        },
      }),
    });
    const openedDetails = [
      "context_workspace",
      "context_workspace-summaries",
      "context_workspace-state",
      "context_workspace-pending-replies",
      "context_workspace-pending-memory",
      "context_workspace-checkpoint",
    ];
    const markup = renderInspector("链路", enriched, "chain", openedDetails);

    for (const title of ["上下文分区", "历史交互", "压缩摘要", "工作区活动状态", "待结算回复", "待写入 Memory", "恢复检查点"]) {
      expect(markup).toContain(title);
    }
    expect(markup).not.toContain("工作区组成");
    expect(markup).toContain("上一轮历史");
    expect(markup).toContain("开发者");
    expect(markup).not.toContain("未命名来源");
    expect(markup).toContain("压缩过往");
    expect(markup).toContain("待确认");
    expect(markup).toContain("活跃");
    expect(markup).toContain("待发送回复");
    expect(markup).toContain("待记忆经历");
    expect(markup).toContain("精简经历");
    expect(markup).toContain("已保存");
    expect(markup).not.toContain('<article class="trace-memory-point"><dl class="trace-fields">');
    expect(markup).toContain('aria-label="历史交互"');
    expect(markup).not.toContain("当前消息正文");
    expect(markup).not.toContain("当前回复正文");
    expect(markup).not.toContain('trace-disclosure-title"><strong>历史交互');
  });

  it("replaces opaque history actor IDs with semantic speaker labels", () => {
    const enriched = withChainNodes({
      1: (node) => ({ ...node,
        appended: { channel_id: "channel-dawn", conversation_id: "conversation-dawn" },
        output: {
          ...(node.output as FixtureNode),
          workspace: {
            threads: [{
              channel_id: "channel-dawn",
              conversation_id: "conversation-dawn",
              messages: [
                { event_id: "event-owner", speaker: "elfie-lab-owner", actor_id: "elfie-lab-owner", content: "开发者消息" },
                { event_id: "event-elfie", speaker: "54137848", actor_id: "54137848", content: "精灵回复" },
              ],
            }],
            pending_replies: [],
            pending_memory: [],
            checkpoint: { status: "已保存", thread_count: 1, pending_reply_count: 0, pending_memory_count: 0 },
          },
        },
      }),
    });
    const markup = renderInspector("链路", enriched, "chain", ["context_workspace"]);

    expect(markup).toContain("开发者");
    expect(markup).toContain("elfie");
    expect(markup).not.toContain("主人");
    expect(markup).not.toContain("Elfie");
    expect(markup).not.toContain("未命名来源");
    expect(markup).not.toContain("elfie-lab-owner");
    expect(markup).not.toContain("54137848");
  });

  it("prefers an explicit display name over the source category", () => {
    const enriched = withChainNodes({
      1: (node) => ({ ...node,
        appended: { channel_id: "channel-dawn", conversation_id: "conversation-dawn" },
        output: {
          ...(node.output as FixtureNode),
          workspace: {
            threads: [{
              channel_id: "channel-dawn",
              conversation_id: "conversation-dawn",
              messages: [
                { event_id: "event-owner-named", speaker_kind: "owner", display_name: "林然", content: "你好" },
                { event_id: "event-elfie-named", speaker_kind: "elfie", display_name: "小艾", content: "你好，我在" },
              ],
            }],
          },
        },
      }),
    });
    const markup = renderInspector("链路", enriched, "chain", ["context_workspace"]);

    expect(markup).toContain("林然");
    expect(markup).toContain("小艾");
    expect(markup).not.toContain("主人");
    expect(markup).not.toContain("未命名来源");
  });

  it("keeps event_admission focused on the selected input channel and value", () => {
    const enriched = withChainNodes({
      0: (node) => ({ ...node,
        input: {
          ...(node.input as FixtureNode),
          modalities: ["text"],
        },
        output: {
        ...(node.output as FixtureNode),
        interaction_scope: { kind: "channel", channel_id: "channel-dawn", conversation_id: "conversation-dawn", body_id: null, body_generation: null },
        response_scope: { external_domain: "nest", channel_id: null, conversation_id: null },
      } }),
    });
    const markup = renderInspector("链路", enriched, "chain", ["event_admission"]);

    expect(markup).toContain("输入通道");
    expect(markup).toContain("文字");
    expect(markup).toContain("消息");
    expect(markup).toContain("你好，今天怎么样？");
    expect(markup.match(/class="trace-field"/g)).toHaveLength(2);
    expect(markup).not.toContain("本轮处理");
    expect(markup).not.toContain("输入形式");
    expect(markup).not.toContain("交互范围");
    expect(markup).not.toContain("响应范围");
    expect(markup).not.toContain("channel-dawn");
    expect(markup).not.toContain("conversation-dawn");
    expect(markup).not.toContain("准入明细");
    expect(markup).not.toContain("事件显著性");
  });

  it("renders a compact non-text embodied input without exposing queue mechanics", () => {
    const embodied = withChainNodes({
      0: (node) => ({ ...node,
        input: {
          source_domain: "embodied",
          message: "外面有一头大象。",
          modalities: ["hearing", "vision", "environment", "touch"],
          modality_values: {
            hearing: "外面有一头大象。",
            vision: "已提供视觉输入（image/png）",
            environment: "温度 24°C",
            touch: "背部 · 力度 3",
          },
        },
      }),
    });
    const markup = renderInspector("链路", embodied, "chain", ["event_admission"]);

    expect(markup).toContain("现场");
    for (const row of ["听觉", "视觉", "环境", "触碰", "外面有一头大象。", "温度 24°C", "背部 · 力度 3"]) {
      expect(markup).toContain(row);
    }
    expect(markup.match(/class="trace-field"/g)).toHaveLength(5);
    expect(markup).not.toContain("本轮处理");
    expect(markup).not.toContain("截断序号");
    expect(markup).not.toContain("显著性");
  });

  it("uses browser-native title tooltips on stage and sub-step triggers", () => {
    const markup = renderInspector("链路", turn, "chain", ["reasoning_run", "reasoning-4.1"]);

    expect(markup).toContain('title="本轮输入：确认输入通道与处理内容"');
    expect(markup).toContain('title="上下文编译：按预算重新编译模型上下文，裁剪低相关材料"');
    expect(markup).toContain('title="模型调用：发送上下文，取回模型响应"');
    expect(markup).toContain('title="行动解析：把响应解析为类型化行动"');
    expect(markup).not.toContain('title="守卫判断：检查剩余预算与时间，决定是否继续"');
    expect(markup).not.toContain("data-tip=");
  });

  it("drops 1970 captured_at and unknown_fields state-diff rows and truncates long id arrays", () => {
    const longIds = Array.from({ length: 12 }, (_, index) =>
      `${index % 2 === 0 ? "execution_receipt_" : "turn_"}${index.toString(16).padStart(6, "0")}abcdef`);
    const enriched = withChainNodes({
      6: (node) => ({ ...node, output: { ...(node.output as FixtureNode), state_diff: {
        energy: { before: 88, after: 87 },
        captured_at: { before: "1970-01-01T00:00:00.000Z", after: "1970-01-01T00:00:00.001Z" },
        unknown_fields: { before: [], after: ["stale_field"] },
        source_event_ids: { before: [], after: longIds },
      } } }),
    });
    const markup = renderInspector("链路", enriched, "chain", ["settlement"]);

    expect(markup).toContain("88 → 87");
    expect(markup).not.toContain("1970");
    expect(markup).not.toContain("unknown_fields");
    expect(markup).not.toContain("stale_field");
    expect(markup).toContain("(12 项)");
    expect(markup).toContain("execution_rece…");
    expect(markup).not.toContain(longIds[0]);
  });

  it("renders settlement state changes as readable before → after rows", () => {
    const enriched = withChainNodes({
      6: (node) => ({ ...node, output: { ...(node.output as FixtureNode), state_diff: {
        energy: { before: 94.9, after: 94.91 },
        cognitive_consolidation: { revision: { before: 3, after: 4 } },
        orientation: { freshness: { before: "unknown", after: "current" } },
      } } }),
    });
    const markup = renderInspector("链路", enriched, "chain", ["settlement"]);

    expect(markup).toContain("94.9 → 94.91");
    expect(markup).toContain("认知整理 版本");
    expect(markup).toContain("3 → 4");
    expect(markup).toContain("定位 新鲜度");
    expect(markup).toContain("unknown → current");
    expect(markup).not.toContain('"before"');
    expect(markup).not.toContain('"after"');
  });
});
