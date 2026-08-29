import { useState } from "react";
import { Button } from "antd";

import type { ElfieSession } from "./contracts";
import {
  KNOWLEDGE_VIEWBOX,
  RELATIONSHIP_VIEWBOX,
  WORLD_RING_RADII,
  WORLD_VIEWBOX,
  edgeWidth,
  layoutKnowledge,
  layoutRelationship,
  layoutWorld,
  wrapLabel,
} from "./memoryLayout";
import "./MemoryVisualizations.css";

type Memory = ElfieSession["profile"]["memory_cognition"];

type Graph = Memory["relations"];
type GraphNode = Pick<Graph["nodes"][number], "id" | "label">;

function nodeText(node: GraphNode, x: number, y: number, units = 8): React.JSX.Element {
  const lines = wrapLabel(node.label, units, 2);
  const firstY = y - ((lines.length - 1) * 5);
  return <text className="memory-node-label" textAnchor="middle" x={x} y={firstY}>
    {lines.map((line, index) => <tspan key={`${node.id}-${index}`} x={x} dy={index === 0 ? 0 : 10}>{line}</tspan>)}
  </text>;
}

function dashPattern(kind: string): string | undefined {
  const patterns: Readonly<Record<string, string>> = {
    owner: "1 0", family: "2 2", friend: "7 3", acquaintance: "2 5",
    conflicts: "2 4", revises: "8 3", supports: "1 0", derived_from: "5 3",
  };
  return patterns[kind];
}

const knowledgeRelationLabels: Readonly<Record<string, string>> = {
  derived_from: "来源于",
  supports: "支持",
  conflicts: "冲突",
  revises: "修正",
};

export function RelationshipGraph({ graph }: Readonly<{ graph: Memory["relations"] }>): React.JSX.Element {
  const nodes = layoutRelationship(graph.nodes);
  const positions = new Map(nodes.map((node) => [node.id, node]));
  return <div className="memory-visual relationship-visual" data-memory-visual="relationship">
    <svg aria-label="关系认知网络" className="memory-graph relationship-graph" role="img" viewBox={`0 0 ${RELATIONSHIP_VIEWBOX.width} ${RELATIONSHIP_VIEWBOX.height}`}>
      <title>关系认知网络</title><desc>当前精灵居中，节点大小表示重要度，连线同时展示精灵与其他人物之间的关系。</desc>
      {nodes.length === 0 ? <text className="graph-empty" textAnchor="middle" x="170" y="150">互动后将形成关系网络</text> : <>
        {graph.links.map((link) => {
          const from = positions.get(link.source);
          const to = positions.get(link.target);
          if (!from || !to) return null;
          const middleX = (from.x + to.x) / 2;
          const middleY = (from.y + to.y) / 2;
          return <g data-memory-link={`${link.source}:${link.target}`} data-relation-kind={link.relation_kind} key={`${link.source}:${link.target}:${link.relation_kind}`}>
            <line className="memory-link" strokeDasharray={dashPattern(link.relation_kind)} strokeWidth={edgeWidth(link.weight)} x1={from.x} x2={to.x} y1={from.y} y2={to.y} />
            {link.label ? <text className="memory-link-label" textAnchor="middle" x={middleX} y={middleY - 3}>{link.label}</text> : null}
          </g>;
        })}
        {nodes.map((node) => {
          const isElfie = node.kind === "elfie";
          const shape = node.kind === "self" ? "self" : isElfie ? "elfie" : "human";
          return <g className={`memory-node ${shape}`} data-memory-node={node.id} data-node-shape={shape} key={node.id}>
            {isElfie
              ? <rect height={node.size * 1.7} rx="7" width={node.size * 2.5} x={node.x - node.size * 1.25} y={node.y - node.size * 0.85} />
              : <circle cx={node.x} cy={node.y} r={node.size} />}
            {nodeText(node, node.x, node.y + 3, isElfie ? 11 : 8)}
          </g>;
        })}
      </>}
    </svg>
  </div>;
}

export function KnowledgeGraph({ graph }: Readonly<{ graph: Memory["knowledge"] }>): React.JSX.Element {
  const nodes = layoutKnowledge(graph.nodes, graph.links);
  const positions = new Map(nodes.map((node) => [node.id, node]));
  const [selectedId, setSelectedId] = useState(nodes[0]?.id ?? "");
  const selected = nodes.find((node) => node.id === selectedId) ?? nodes[0];
  const activeId = selected?.id ?? "";
  return <div className="memory-visual knowledge-visual" data-memory-visual="knowledge">
    <svg aria-label="知识与信念图" className="memory-graph knowledge-graph" role="img" viewBox={`0 0 ${KNOWLEDGE_VIEWBOX.width} ${KNOWLEDGE_VIEWBOX.height}`}>
      <title>知识与信念依赖图</title><desc>知识按方向从左到右排列，箭头表示真实投影关系。</desc>
      <defs><marker id="knowledge-arrow" markerHeight="6" markerWidth="7" orient="auto" refX="6" refY="3"><path d="M0,0 L7,3 L0,6 Z" /></marker></defs>
      {nodes.length === 0 ? <text className="graph-empty" textAnchor="middle" x="170" y="160">尚未沉淀知识与信念</text> : <>
        {graph.links.map((link) => {
          const from = positions.get(link.source);
          const to = positions.get(link.target);
          if (!from || !to) return null;
          const adjacent = link.source === activeId || link.target === activeId;
          const relationLabel = knowledgeRelationLabels[link.relation_kind] ?? link.label;
          return <g key={`${link.source}:${link.target}:${link.relation_kind}`}>
            <line className={adjacent ? "memory-link is-adjacent" : "memory-link"} data-memory-link={`${link.source}:${link.target}`} data-relation-kind={link.relation_kind} markerEnd="url(#knowledge-arrow)" strokeDasharray={dashPattern(link.relation_kind)} strokeWidth={edgeWidth(link.weight)} x1={from.x} x2={to.x} y1={from.y} y2={to.y} />
            {adjacent && relationLabel ? <text className="knowledge-link-label" textAnchor="middle" x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 3}>{relationLabel}</text> : null}
          </g>;
        })}
        {nodes.map((node) => <g className={`memory-node knowledge-node ${node.kind ?? "knowledge"}`} data-memory-node={node.id} data-node-shape={node.kind ?? "knowledge"} key={node.id}>
          <rect height={node.size * 1.8} rx={node.kind === "belief" ? node.size : 5} width={node.size * 2.5} x={node.x - node.size * 1.25} y={node.y - node.size * 0.9} />
          {nodeText(node, node.x, node.y + 3, 10)}
        </g>)}
      </>}
    </svg>
    <div className="knowledge-legend" aria-label="知识关系图例">{Object.entries(knowledgeRelationLabels).map(([kind, label]) => <span data-knowledge-relation={kind} key={kind}>{label}</span>)}</div>
    {nodes.length > 0 ? <div className="knowledge-controls" aria-label="选择知识节点">{nodes.map((node) => <Button aria-pressed={node.id === activeId} key={node.id} onClick={() => setSelectedId(node.id)} size="small" type={node.id === activeId ? "primary" : "default"}>{node.label}</Button>)}</div> : null}
    {selected ? <div className="knowledge-detail" data-selected-knowledge={selected.id}><strong>{selected.label}</strong><span>可信度 {Math.round((selected.confidence ?? 0.5) * 100)}%</span><small>来源经历：{selected.source_event_ids.length ? selected.source_event_ids.join("、") : "尚未投影"}</small></div> : null}
  </div>;
}

export function WorldRings({ model }: Readonly<{ model: Memory["world_model"] }>): React.JSX.Element {
  const nodes = layoutWorld(model);
  return <div className="memory-visual world-visual" data-memory-visual="world">
    <svg aria-label="世界理解同心圆" className="memory-graph world-graph" role="img" viewBox={`0 0 ${WORLD_VIEWBOX.width} ${WORLD_VIEWBOX.height}`}>
      <title>世界理解同心圆</title><desc>从自我、家庭、巢穴、社会到外部世界的五层认知地图。</desc>
      {model.rings.map((ring) => <g data-memory-ring={ring.kind} key={ring.kind}>
        <circle className={`world-ring ${ring.kind}`} cx="170" cy="170" r={WORLD_RING_RADII[ring.kind]} />
        <text className="world-ring-label" x="174" y={167 - WORLD_RING_RADII[ring.kind]}>{ring.label}</text>
      </g>)}
      {nodes.map((node) => <g className={`memory-node world-node ${node.ring}`} data-memory-node={node.id} data-node-shape="world" key={node.id}>
        <circle cx={node.x} cy={node.y} r={Math.min(11, node.size)} />
        {nodeText(node, node.x, node.y + 3, 7)}
      </g>)}
    </svg>
    <p className="world-understanding">{model.summary}</p>
  </div>;
}

const topicClasses: Readonly<Record<string, string>> = {
  people: "people", person: "people", 人物: "people",
  location: "location", place: "location", 地点: "location",
  emotion: "emotion", 情绪: "emotion",
  activity: "activity", 活动: "activity",
};

export function TopicWall({ topics }: Readonly<{ topics: Memory["topics"] }>): React.JSX.Element {
  const ordered = [...topics].sort((left, right) => right.weight - left.weight || left.label.localeCompare(right.label));
  return <div className="topic-memory" data-memory-visual="topics">
    <div className="topic-cloud">{ordered.length ? ordered.map((topic) => <span className={`topic-${topicClasses[topic.category] ?? "other"}`} data-memory-topic={topic.label} key={topic.label} style={{ fontSize: `${12 + Math.pow(topic.weight, 2.2) * 30}px` }}>{topic.label}</span>) : <small>互动后将在这里形成记忆主题</small>}</div>
  </div>;
}

function eventDate(timestamp: string | undefined): string {
  if (!timestamp) return "未标记日期";
  return timestamp.slice(0, 10);
}

export function ImpactTimeline({ events }: Readonly<{ events: Memory["important_events"] }>): React.JSX.Element {
  const ordered = [...events].sort((left, right) => (right.timestamp ?? "").localeCompare(left.timestamp ?? "") || left.id.localeCompare(right.id));
  return <div className="event-timeline" data-memory-visual="timeline">{ordered.length ? ordered.map((event) => {
    const diameter = 10 + event.importance * 12;
    return <article data-memory-event={event.id} key={event.id || `${event.timestamp}-${event.content}`}>
      <span aria-hidden="true" className="event-impact" style={{ height: `${diameter}px`, width: `${diameter}px` }} />
      <time>{eventDate(event.timestamp)}</time>
      <div className="event-card"><p>{event.content}</p>
        {event.people.length ? <small className="event-people">涉及：{event.people.join("、")}</small> : null}
        {event.changed ? <small className="event-changed">改变：{event.changed}</small> : null}
      </div>
    </article>;
  }) : <p className="projection-empty">尚无重要经历</p>}</div>;
}
