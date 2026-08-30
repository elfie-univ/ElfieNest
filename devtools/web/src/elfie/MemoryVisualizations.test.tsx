import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ElfieSidebar } from "./ElfieSidebar";
import { memoryCognitionSchema, sessionSchema, type ElfieSession } from "./contracts";
import {
  ImpactTimeline,
  KnowledgeGraph,
  RelationshipGraph,
  TopicWall,
  WorldRings,
} from "./MemoryVisualizations";

const doNothing = (): void => undefined;

function renderSidebar(session: ElfieSession | null): string {
  return renderToStaticMarkup(<ElfieSidebar
    collapsed={false}
    food=""
    foods={[]}
    iframeRef={{ current: null }}
    items={[]}
    menuOpen={false}
    onCollapse={doNothing}
    onCreate={doNothing}
    onDelete={doNothing}
    onEditPersonality={doNothing}
    onFood={doNothing}
    onMenu={doNothing}
    onNewFood={doNothing}
    onSelect={doNothing}
    portraitEpoch={0}
    preview={doNothing}
    previewStatus=""
    runtimeWarning=""
    session={session}
  />);
}

describe("Elfie memory visualization SSR boundary", () => {
  it("keeps the existing empty Elfie sidebar renderable without a browser DOM", () => {
    // Given: no selected Elfie session.
    // When: React renders the existing component at the server boundary.
    const markup = renderSidebar(null);

    // Then: the established empty-state outcome remains available.
    expect(markup).toContain("创建第一只");
    expect(markup).not.toContain("本地开发环境");
  });
});

const relationNodes = Array.from({ length: 20 }, (_, index) => ({
  id: `relation-${index}`,
  label: index === 19 ? "这是一个非常非常长而且需要明确截断的中文关系名字" : `关系 ${index}`,
  kind: index === 0 ? "self" as const : index % 2 === 0 ? "human" as const : "elfie" as const,
  weight: 1 - index / 25,
}));
const relationshipLinks = [
  ...relationNodes.slice(1).map((node, index) => ({
    source: "relation-0",
    target: node.id,
    label: "朋友",
    relation_kind: index % 2 === 0 ? "friend" : "family",
    weight: 0.2 + index / 25,
  })),
  {
    source: "relation-2",
    target: "relation-5",
    label: "认识",
    relation_kind: "acquaintance",
    weight: 0.7,
  },
];
const knowledgeNodes = Array.from({ length: 20 }, (_, index) => ({
  id: `knowledge-${index}`,
  label: `知识 ${index}`,
  kind: index % 2 === 0 ? "knowledge" as const : "belief" as const,
  weight: 1 - index / 25,
  confidence: 0.4 + index / 40,
  source_event_ids: [`event-${index}`],
}));
const chainLinks = Array.from({ length: 19 }, (_, index) => ({
  source: `knowledge-${index}`,
  target: `knowledge-${index + 1}`,
  label: "支持",
  relation_kind: index % 2 === 0 ? "supports" : "conflicts",
  weight: 0.2 + index / 25,
}));
const memory = memoryCognitionSchema.parse({
  topics: Array.from({ length: 20 }, (_, index) => ({
    label: `主题 ${index}`,
    weight: 1 - index / 25,
    category: ["people", "location", "emotion", "activity"][index % 4],
  })),
  important_events: Array.from({ length: 20 }, (_, index) => ({
    id: `event-${index}`,
    content: `经历 ${index}`,
    timestamp: `2026-07-${String(20 - index).padStart(2, "0")}T10:00:00Z`,
    emotion: "curious",
    importance: index / 19,
    people: [`伙伴 ${index}`],
    changed: `理解发生变化 ${index}`,
  })),
  relations: {
    nodes: relationNodes,
    links: relationshipLinks,
  },
  knowledge: { nodes: knowledgeNodes, links: chainLinks },
  world_understanding: "世界由可以逐渐理解的层次组成。",
  world_model: {
    summary: "世界由可以逐渐理解的层次组成。",
    rings: (["self", "family", "nest", "society", "outside"] as const).map((kind, ringIndex) => ({
      kind,
      label: kind,
      nodes: Array.from({ length: [1, 5, 5, 5, 4][ringIndex] ?? 0 }, (_, index) => ({
        id: `${kind}-${index}`,
        label: `${kind} ${index}`,
        weight: 1 - (ringIndex * 4 + index) / 25,
      })),
    })),
  },
});
const denseSession = sessionSchema.parse({
  elfie_id: "elfie-dense",
  profile: {
    elfie_id: "elfie-dense",
    name: "验收小狗",
    species_id: "dog",
    big_five: {
      openness: 0.8,
      conscientiousness: 0.7,
      extraversion: 0.6,
      agreeableness: 0.9,
      neuroticism: 0.3,
    },
    appearance: {},
    memory_cognition: memory,
  },
  current_state: {
    energy: 80,
    fatigue: 20,
    primary_emotion: "happiness",
    is_sleeping: false,
    memory_count: 20,
  },
  turns: [],
});

function attributeCount(markup: string, attribute: string): number {
  return markup.split(`${attribute}=`).length - 1;
}

describe("dense memory visualization semantics", () => {
  it("integrates every dense view into default-collapsed memory panels", () => {
    // Given: a complete session carrying the dense cognition projection.
    // When: the user-visible sidebar renders.
    const markup = renderSidebar(denseSession);

    // Then: all dedicated views are present and no panel is forced open.
    expect(markup).toContain('data-memory-visual="relationship"');
    expect(markup).toContain('data-memory-visual="knowledge"');
    expect(markup).toContain('data-memory-visual="world"');
    expect(attributeCount(markup, "data-memory-node")).toBe(60);
    expect(attributeCount(markup, "data-memory-topic")).toBe(20);
    expect(attributeCount(markup, "data-memory-event")).toBe(20);
    expect(markup).not.toContain("<details open");
  });

  it("renders all 20 relationship, knowledge, and world nodes deterministically", () => {
    // Given: three projected dense-memory models with 20 real nodes each.
    const relationship = renderToStaticMarkup(<RelationshipGraph graph={memory.relations} />);
    const knowledge = renderToStaticMarkup(<KnowledgeGraph graph={memory.knowledge} />);
    const world = renderToStaticMarkup(<WorldRings model={memory.world_model} />);

    // When: the visualizations render repeatedly.
    const first = `${relationship}${knowledge}${world}`;
    const second = `${renderToStaticMarkup(<RelationshipGraph graph={memory.relations} />)}${renderToStaticMarkup(<KnowledgeGraph graph={memory.knowledge} />)}${renderToStaticMarkup(<WorldRings model={memory.world_model} />)}`;

    // Then: counts, shapes, links, arrows, ring semantics, and coordinates are stable.
    expect(first).toBe(second);
    expect(attributeCount(relationship, "data-memory-node")).toBe(20);
    expect(attributeCount(knowledge, "data-memory-node")).toBe(20);
    expect(attributeCount(world, "data-memory-node")).toBe(20);
    expect(attributeCount(world, "data-memory-ring")).toBe(5);
    expect(relationship).toContain('data-node-shape="human"');
    expect(relationship).toContain('data-node-shape="elfie"');
    expect(relationship).toContain('data-memory-link="relation-2:relation-5"');
    expect(relationship).not.toContain("relationship-list");
    expect(relationship).toContain('stroke-dasharray="2 2"');
    expect(relationship).toContain('stroke-width="1.6"');
    expect(relationship).toContain('stroke-width="3.76"');
    expect(knowledge).toContain('marker-end="url(#knowledge-arrow)"');
    expect(knowledge).toContain('data-relation-kind="conflicts"');
    expect(knowledge).toContain('data-knowledge-relation="derived_from">来源于');
    expect(knowledge).toContain('data-knowledge-relation="supports">支持');
    expect(knowledge).toContain('data-knowledge-relation="conflicts">冲突');
    expect(knowledge).toContain('data-knowledge-relation="revises">修正');
    expect(relationship).toContain("…");
  });

  it("ignores dangling links and renders honest empty states", () => {
    // Given: an empty relationship graph and knowledge with one dangling link.
    const sparseMemory = memoryCognitionSchema.parse({
      knowledge: {
        nodes: [{ id: "knowledge-0", label: "知识" }],
        links: [{ source: "missing", target: "knowledge-0" }],
      },
    });
    const sparse = <>
      <RelationshipGraph graph={{ nodes: [], links: [] }} />
      <KnowledgeGraph graph={sparseMemory.knowledge} />
    </>;

    // When: the sparse visuals are rendered.
    const markup = renderToStaticMarkup(sparse);

    // Then: no invented or dangling edge is emitted.
    expect(attributeCount(markup, "data-memory-link")).toBe(0);
    expect(markup).toContain("互动后将形成关系网络");
  });

  it("renders only a high-contrast topic cloud and clear impact-sized timeline cards", () => {
    // Given: the projected topic and event collections.
    const content = <><TopicWall topics={memory.topics} /><ImpactTimeline events={memory.important_events} /></>;

    // When: compact supporting views render.
    const markup = renderToStaticMarkup(content);

    // Then: no frontend slice drops an item and semantic detail stays visible.
    expect(attributeCount(markup, "data-memory-topic")).toBe(20);
    expect(attributeCount(markup, "data-memory-event")).toBe(20);
    expect(markup).not.toContain("topic-ranking");
    expect(markup).toContain("font-size:42px");
    expect(markup).toContain("width:22px");
    expect(markup).toContain('class="event-card"');
    expect(markup).toContain("伙伴 19");
    expect(markup).toContain("理解发生变化 19");
  });
});
