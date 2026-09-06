import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const sharedStyles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
const sidebarSource = readFileSync(new URL("./ElfieSidebar.tsx", import.meta.url), "utf8");
const timelineSource = readFileSync(new URL("./TimelinePanel.tsx", import.meta.url), "utf8");
const legacyStyles = readFileSync(new URL("./legacy.css", import.meta.url), "utf8");
const parityStyles = readFileSync(new URL("./parity.css", import.meta.url), "utf8");
const antdStyles = readFileSync(new URL("../ui/devtools-antd.css", import.meta.url), "utf8");

describe("Elfie Lab interaction styles", () => {
  it("keeps the Nest Lab dark hover rule out of Elfie Lab", () => {
    // Given: Nest Lab and Elfie Lab share the top-level stylesheet.
    // When: the shared button hover rule is inspected.
    // Then: the dark rule is scoped to Nest Lab only.
    expect(sharedStyles).not.toMatch(/^button:hover:not\(:disabled\)/m);
    expect(sharedStyles).toContain(".view-toolbar .ant-btn");
  });

  it("shows each compact Elfie name in a hover tooltip", () => {
    // Given: the sidebar is collapsed and its Elfie switcher is open.
    // When: a compact avatar choice is hovered or keyboard-focused.
    // Then: its visible tooltip is sourced from that Elfie's name.
    expect(sidebarSource).toContain("data-tooltip={item.name}");
    expect(parityStyles).toContain(".compact-switcher-menu button[data-tooltip]::after");
  });

  it("preserves the approved single-Elfie control layout", () => {
    // Given: the single-Elfie workspace uses Ant Design controls.
    // When: the local compatibility rules are inspected.
    // Then: the food selector fills its row, tags remain inline, and both tool buttons keep their square surface.
    expect(antdStyles).toContain(".model-controls .ant-select { width: 100%; }");
    expect(antdStyles).not.toContain(".bubble.ant-btn > span { display: block; }");
    expect(antdStyles).toContain(".tool-button.ant-btn { width: 34px; min-width: 34px; height: 34px; padding: 0; border: 1px solid var(--border-default); border-radius: 8px");
    expect(timelineSource).not.toMatch(/className=(?:\{|\")tool-button.*shape=\"circle\"/);
    expect(timelineSource).toContain('className="turn-duration"');
    expect(timelineSource).not.toContain('className="process-line"');
    expect(legacyStyles).toContain("--panel-right: clamp(400px, 24vw, 480px);");
  });
});
