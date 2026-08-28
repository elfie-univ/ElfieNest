import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ElfieSession } from "./contracts";
import { TimelinePanel } from "./TimelinePanel";

const doNothing = (): void => undefined;

function renderTimeline(): string {
  return renderToStaticMarkup(<TimelinePanel
    food="mock"
    onOpenEvaluation={doNothing}
    onPreviewIntent={doNothing}
    onSelectTurn={doNothing}
    onSend={async () => true}
    onUpload={async () => ({ id: "media-1", mimeType: "image/png" })}
    portraitEpoch={0}
    session={null}
  />);
}

function renderTimelineWithTurn(): string {
  const session = {
    profile: { name: "艾菲", portrait_url: "" },
    turns: [{
      turn_id: "turn-1",
      timestamp: "2026-08-13T09:00:00Z",
      stimulus_bundle: {
        source_domain: "embodied",
        message: "",
        vision_media_id: "media-1",
      },
      used_state_injection: false,
      duration_ms: 12,
      result: { success: true, message: "看到了" },
      decision: {
        spoken_texts: ["看到了"],
        message_texts: [],
        action_intents: [],
        motion_intents: [],
        expression_intents: [],
      },
      state_after: {},
      state_diff: {},
    }],
  } as unknown as ElfieSession;
  return renderToStaticMarkup(<TimelinePanel
    food="mock"
    onOpenEvaluation={doNothing}
    onPreviewIntent={doNothing}
    onSelectTurn={doNothing}
    onSend={async () => true}
    onUpload={async () => ({ id: "media-1", mimeType: "image/png" })}
    portraitEpoch={0}
    session={session}
  />);
}

describe("Elfie Lab composer", () => {
  it("keeps the message/scene source selector visible inside the composer footer", () => {
    const markup = renderTimeline();

    expect(markup).toContain('class="timeline-heading-title"');
    expect(markup).toContain('role="radiogroup" aria-label="输入来源"');
    expect(markup).toContain('title="消息">消息</div>');
    expect(markup).toContain('title="现场">现场</div>');
    expect(markup.indexOf('aria-label="输入来源"')).toBeGreaterThan(
      markup.indexOf('class="message-field-footer"'),
    );
    expect(markup).not.toContain("通信消息");
    expect(markup).not.toContain("具身感知");
  });

  it("shows a real attachment entry without exposing scene-only wording", () => {
    const markup = renderTimeline();

    expect(markup).not.toContain('aria-label="添加视觉输入"');
    expect(markup).toContain('aria-label="添加附件"');
    expect(markup).toContain("image/png,image/jpeg,image/webp,application/pdf");
    expect(markup).toContain('aria-label="输入设置"');
  });

  it("labels timeline turns with both their source and modality", () => {
    expect(renderTimelineWithTurn()).toContain("现场 · 视觉");
  });
});
