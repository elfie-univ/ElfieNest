import { describe, expect, it } from "vitest";

import { memoryCognitionSchema, sessionSchema } from "./contracts";
import {
  KNOWLEDGE_VIEWBOX,
  RELATIONSHIP_VIEWBOX,
  WORLD_RING_RADII,
  WORLD_VIEWBOX,
  edgeWidth,
  layoutKnowledge,
  layoutRelationship,
  layoutWorld,
  nodeSize,
  wrapLabel,
} from "./memoryLayout";

describe("dense memory API compatibility", () => {
  it("keeps current defaults when an old world-understanding payload crosses the boundary", () => {
    // Given: the payload shape emitted before structured dense-memory visuals.
    const payload = {
      elfie_id: "elfie-old",
      profile: {
        elfie_id: "elfie-old",
        name: "小闪",
        species_id: "dog",
        big_five: {
          openness: 0.5,
          conscientiousness: 0.5,
          extraversion: 0.5,
          agreeableness: 0.5,
          neuroticism: 0.5,
        },
        appearance: {},
        memory_cognition: { world_understanding: "家是安全的地方" },
      },
      current_state: {
        energy: 80,
        fatigue: 20,
        dominant_emotion: "calm",
        is_sleeping: false,
      },
      turns: [],
    };

    // When: the existing session boundary parses it.
    const parsed = sessionSchema.parse(payload);

    // Then: the old text and empty graph defaults remain observable.
    expect(parsed.profile.memory_cognition).toMatchObject({
      topics: [],
      important_events: [],
      relations: { nodes: [], links: [] },
      knowledge: { nodes: [], links: [] },
      world_understanding: "家是安全的地方",
    });
    expect(parsed.current_state.memory_count).toBe(0);
  });
});

const denseNodes = Array.from({ length: 24 }, (_, index) => ({
  id: `node-${String(index).padStart(2, "0")}`,
  label: `节点 ${index}`,
  kind: index === 0 ? "self" : index % 2 === 0 ? "human" : "elfie",
  weight: (24 - index) / 24,
}));

describe("dense memory boundary", () => {
  it("defaults missing optional visual fields without inventing nodes", () => {
    // Given: a minimal cognition payload.
    const payload = { world_understanding: "仍在学习" };

    // When: it crosses the API boundary.
    const parsed = memoryCognitionSchema.parse(payload);

    // Then: all structured visual collections are safely empty.
    expect(parsed.world_model.rings.map((ring) => ring.kind)).toEqual([
      "self", "family", "nest", "society", "outside",
    ]);
    expect(parsed.world_model.rings.map((ring) => ring.label)).toEqual([
      "自我", "家庭", "巢穴", "社会", "外部世界",
    ]);
    expect(parsed.world_model.rings.every((ring) => ring.nodes.length === 0)).toBe(true);
    expect(parsed.world_model.summary).toBe("仍在学习");
  });

  it("rejects malformed optional visual fields at the boundary", () => {
    // Given: an API value with an invalid scalar.
    const payload = { relations: { nodes: [{ id: "a", label: "A", weight: "high" }] } };

    // When: the boundary parses it.
    const parsed = memoryCognitionSchema.safeParse(payload);

    // Then: malformed data is rejected rather than leaking inward.
    expect(parsed.success).toBe(false);
  });
});

describe("relationship double-ring layout", () => {
  it("keeps one self centered and deterministically limits 24 inputs to 20", () => {
    // Given: more nodes than the visual contract allows.
    const firstInput = denseNodes.slice().reverse();

    // When: the same logical nodes are laid out repeatedly.
    const first = layoutRelationship(firstInput);
    const second = layoutRelationship(firstInput);

    // Then: the result is stable, capped, and centered on self.
    expect(first).toEqual(second);
    expect(first).toHaveLength(20);
    expect(first.filter((node) => node.ring === "center")).toEqual([
      expect.objectContaining({ id: "node-00", x: 170, y: 150 }),
    ]);
    expect(new Set(first.slice(1).map((node) => node.ring))).toEqual(new Set(["inner", "outer"]));
  });

  it("keeps 0, 1, and 20 node coordinates inside the relationship viewBox", () => {
    // Given: boundary-size relationship collections.
    const inputs = [[], denseNodes.slice(0, 1), denseNodes.slice(0, 20)];

    // When: each collection is laid out.
    const layouts = inputs.map(layoutRelationship);

    // Then: every rendered node including its size remains visible.
    expect(layouts[0]).toEqual([]);
    for (const layout of layouts) {
      for (const node of layout) {
        expect(node.x - node.size).toBeGreaterThanOrEqual(0);
        expect(node.x + node.size).toBeLessThanOrEqual(RELATIONSHIP_VIEWBOX.width);
        expect(node.y - node.size).toBeGreaterThanOrEqual(0);
        expect(node.y + node.size).toBeLessThanOrEqual(RELATIONSHIP_VIEWBOX.height);
      }
    }
  });
});

describe("knowledge four-column layout", () => {
  it("places 20 nodes stably across four bounded columns", () => {
    // Given: a directed chain supplied in reverse order.
    const nodes = denseNodes.slice(0, 20).reverse();
    const links = denseNodes.slice(0, 19).map((node, index) => ({
      source: node.id,
      target: denseNodes[index + 1]?.id ?? "",
    }));

    // When: the graph is laid out twice.
    const first = layoutKnowledge(nodes, links);
    const second = layoutKnowledge(nodes, links);

    // Then: all four columns are used and every node stays visible.
    expect(first).toEqual(second);
    expect(new Set(first.map((node) => node.column))).toEqual(new Set([0, 1, 2, 3]));
    for (const node of first) {
      expect(node.x - node.size).toBeGreaterThanOrEqual(0);
      expect(node.x + node.size).toBeLessThanOrEqual(KNOWLEDGE_VIEWBOX.width);
      expect(node.y - node.size).toBeGreaterThanOrEqual(0);
      expect(node.y + node.size).toBeLessThanOrEqual(KNOWLEDGE_VIEWBOX.height);
    }
  });
});

describe("world five-ring layout", () => {
  it("places self once at center and other nodes on their declared radii", () => {
    // Given: 24 nodes distributed over the five semantic rings.
    const kinds = ["self", "family", "nest", "society", "outside"] as const;
    const rings = kinds.map((kind, ringIndex) => ({
      kind,
      nodes: denseNodes.slice(ringIndex * 5, ringIndex * 5 + 5),
    }));

    // When: the world is laid out.
    const layout = layoutWorld({ summary: "", rings });

    // Then: it caps at 20, centers self once, and honors every ring radius.
    expect(layout).toHaveLength(20);
    expect(layout.filter((node) => node.ring === "self")).toEqual([
      expect.objectContaining({ x: 170, y: 170 }),
    ]);
    for (const node of layout) {
      const radius = Math.hypot(node.x - 170, node.y - 170);
      expect(radius).toBeCloseTo(WORLD_RING_RADII[node.ring], 8);
      expect(node.x - node.size).toBeGreaterThanOrEqual(0);
      expect(node.x + node.size).toBeLessThanOrEqual(WORLD_VIEWBOX.width);
    }
  });
});

describe("dense visual scalar and label mapping", () => {
  it("maps node and edge weights monotonically within visible bounds", () => {
    // Given: low, middle, and high normalized weights.
    const weights = [-1, 0, 0.5, 1, 2];

    // When: weights are mapped to visual sizes.
    const nodes = weights.map(nodeSize);
    const edges = weights.map(edgeWidth);

    // Then: clamping and monotonicity preserve the configured ranges.
    expect(nodes).toEqual([8, 8, 16, 24, 24]);
    expect(edges).toEqual([1, 1, 2.5, 4, 4]);
  });

  it("wraps Chinese and English labels to two bounded lines with truncation", () => {
    // Given: long CJK, spaced Latin, and unbroken Latin labels.
    const labels = [
      "这是一个非常非常长的中文关系标签",
      "a very long relationship label for family",
      "Supercalifragilisticexpialidocious",
    ];

    // When: labels are wrapped for a compact node.
    const wrapped = labels.map((label) => wrapLabel(label, 8, 2));

    // Then: each label is deterministic, bounded, and visibly truncated.
    expect(wrapped[0]).toEqual(["这是一个非常", "非常长的中…"]);
    expect(wrapped[1]).toEqual(["a very", "long re…"]);
    expect(wrapped[2]).toEqual(["Supercal", "ifragil…"]);
  });
});
