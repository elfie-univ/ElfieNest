import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const sharedStyles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
const sidebarSource = readFileSync(new URL("./ElfieSidebar.tsx", import.meta.url), "utf8");
const parityStyles = readFileSync(new URL("./parity.css", import.meta.url), "utf8");

describe("Elfie Lab interaction styles", () => {
  it("keeps the Nest Lab dark hover rule out of Elfie Lab", () => {
    // Given: Nest Lab and Elfie Lab share the top-level stylesheet.
    // When: the shared button hover rule is inspected.
    // Then: the dark rule is scoped to Nest Lab only.
    expect(sharedStyles).not.toMatch(/^button:hover:not\(:disabled\)/m);
    expect(sharedStyles).toContain(".nest-console button:hover:not(:disabled)");
  });

  it("shows each compact Elfie name in a hover tooltip", () => {
    // Given: the sidebar is collapsed and its Elfie switcher is open.
    // When: a compact avatar choice is hovered or keyboard-focused.
    // Then: its visible tooltip is sourced from that Elfie's name.
    expect(sidebarSource).toContain("data-tooltip={item.name}");
    expect(parityStyles).toContain(".compact-switcher-menu button[data-tooltip]::after");
  });
});
