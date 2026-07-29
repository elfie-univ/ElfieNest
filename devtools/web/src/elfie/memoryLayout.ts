export const RELATIONSHIP_VIEWBOX = { width: 340, height: 300 } as const;
export const KNOWLEDGE_VIEWBOX = { width: 340, height: 320 } as const;
export const WORLD_VIEWBOX = { width: 340, height: 340 } as const;
export const WORLD_RING_RADII = {
  self: 0,
  family: 42,
  nest: 72,
  society: 102,
  outside: 132,
} as const;

export type WeightedNode = {
  readonly id: string;
  readonly label: string;
  readonly weight?: number;
  readonly kind?: string | undefined;
};

export type DirectedLink = {
  readonly source: string;
  readonly target: string;
};

export type WorldRingKind = keyof typeof WORLD_RING_RADII;

export type WorldModel<Node extends WeightedNode = WeightedNode> = {
  readonly summary: string;
  readonly rings: readonly {
    readonly kind: WorldRingKind;
    readonly nodes: readonly Node[];
  }[];
};

export type PositionedNode<Node extends WeightedNode, Ring extends string | number> = Node & {
  readonly x: number;
  readonly y: number;
  readonly size: number;
  readonly ring: Ring;
};

const MAX_NODES = 20;
const TAU = Math.PI * 2;

function normalized(value: number | undefined): number {
  if (value === undefined || !Number.isFinite(value)) return 0.5;
  return Math.min(1, Math.max(0, value));
}

function sortedUnique<Node extends WeightedNode>(nodes: readonly Node[]): readonly Node[] {
  const sorted = [...nodes].sort((left, right) => {
    const weightDifference = normalized(right.weight) - normalized(left.weight);
    return weightDifference || left.id.localeCompare(right.id);
  });
  // This map is intentionally mutable: it is a local uniqueness accumulator.
  const unique = new Map<string, Node>();
  for (const node of sorted) {
    if (!unique.has(node.id)) unique.set(node.id, node);
  }
  return [...unique.values()];
}

export function nodeSize(weight: number | undefined): number {
  return 8 + normalized(weight) * 16;
}

export function edgeWidth(weight: number | undefined): number {
  return 1 + normalized(weight) * 3;
}

export function wrapLabel(label: string, maxUnits: number, maxLines: number): readonly string[] {
  const normalizedLabel = label.trim().replace(/\s+/gu, " ");
  if (!normalizedLabel || maxUnits < 2 || maxLines < 1) return [];
  const hasCjk = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u.test(normalizedLabel);
  const budget = hasCjk ? Math.max(1, Math.floor(maxUnits / 1.25)) : maxUnits;
  const characters = [...normalizedLabel];
  if (!normalizedLabel.includes(" ")) {
    const lines: string[] = [];
    for (let start = 0; start < characters.length && lines.length < maxLines; start += budget) {
      const isLast = lines.length === maxLines - 1;
      const remaining = characters.length - start;
      lines.push(isLast && remaining > budget
        ? `${characters.slice(start, start + budget - 1).join("")}…`
        : characters.slice(start, start + budget).join(""));
    }
    return lines;
  }

  const lines: string[] = [];
  let remaining = normalizedLabel;
  while (remaining && lines.length < maxLines) {
    const isLast = lines.length === maxLines - 1;
    if (isLast) {
      const tail = [...remaining];
      lines.push(tail.length > budget ? `${tail.slice(0, budget - 1).join("")}…` : remaining);
      break;
    }
    const words = remaining.split(" ");
    let line = words[0] ?? "";
    let consumed = 1;
    while (consumed < words.length) {
      const candidate = `${line} ${words[consumed]}`;
      if ([...candidate].length > budget) break;
      line = candidate;
      consumed += 1;
    }
    lines.push(line);
    remaining = words.slice(consumed).join(" ");
  }
  return lines;
}

export function layoutRelationship<Node extends WeightedNode>(
  nodes: readonly Node[],
): readonly PositionedNode<Node, "center" | "inner" | "outer">[] {
  const ordered = sortedUnique(nodes);
  const self = ordered.find((node) => node.kind === "self");
  const others = ordered.filter((node) => node.id !== self?.id).slice(0, self ? MAX_NODES - 1 : MAX_NODES);
  const positioned: PositionedNode<Node, "center" | "inner" | "outer">[] = self
    ? [{ ...self, x: 170, y: 150, size: nodeSize(self.weight), ring: "center" }]
    : [];
  const innerCount = Math.min(8, others.length);
  for (const [index, node] of others.entries()) {
    const isInner = index < innerCount;
    const ringNodes = isInner ? innerCount : others.length - innerCount;
    const ringIndex = isInner ? index : index - innerCount;
    const radius = isInner ? 78 : 124;
    const angle = -Math.PI / 2 + (TAU * ringIndex) / Math.max(1, ringNodes);
    positioned.push({
      ...node,
      x: 170 + radius * Math.cos(angle),
      y: 150 + radius * Math.sin(angle),
      size: nodeSize(node.weight),
      ring: isInner ? "inner" : "outer",
    });
  }
  return positioned;
}

export function layoutKnowledge<Node extends WeightedNode>(
  nodes: readonly Node[],
  links: readonly DirectedLink[],
): readonly (PositionedNode<Node, number> & { readonly column: number })[] {
  const selected = sortedUnique(nodes).slice(0, MAX_NODES);
  const selectedIds = new Set(selected.map((node) => node.id));
  // These collections are local accumulators for deterministic Kahn ordering.
  const indegree = new Map(selected.map((node) => [node.id, 0]));
  const targets = new Map<string, string[]>();
  for (const link of links) {
    if (!selectedIds.has(link.source) || !selectedIds.has(link.target) || link.source === link.target) continue;
    const outgoing = targets.get(link.source) ?? [];
    if (outgoing.includes(link.target)) continue;
    outgoing.push(link.target);
    targets.set(link.source, outgoing);
    indegree.set(link.target, (indegree.get(link.target) ?? 0) + 1);
  }
  const byId = new Map(selected.map((node) => [node.id, node]));
  const available = selected.filter((node) => indegree.get(node.id) === 0);
  const ordered: Node[] = [];
  while (available.length > 0) {
    available.sort((left, right) => left.id.localeCompare(right.id));
    const next = available.shift();
    if (!next) break;
    ordered.push(next);
    for (const target of (targets.get(next.id) ?? []).slice().sort()) {
      const remaining = (indegree.get(target) ?? 0) - 1;
      indegree.set(target, remaining);
      const targetNode = byId.get(target);
      if (remaining === 0 && targetNode) available.push(targetNode);
    }
  }
  const orderedIds = new Set(ordered.map((node) => node.id));
  ordered.push(...selected.filter((node) => !orderedIds.has(node.id)));
  const columns: Node[][] = Array.from({ length: 4 }, () => []);
  for (const [index, node] of ordered.entries()) {
    const column = Math.min(3, Math.floor((index * 4) / Math.max(1, ordered.length)));
    columns[column]?.push(node);
  }
  return columns.flatMap((columnNodes, column) => columnNodes.map((node, row) => ({
    ...node,
    x: 24 + (292 * column) / 3,
    y: columnNodes.length === 1 ? 160 : 24 + (272 * row) / Math.max(1, columnNodes.length - 1),
    size: nodeSize(node.weight),
    ring: column,
    column,
  })));
}

export function layoutWorld<Node extends WeightedNode>(model: WorldModel<Node>): readonly PositionedNode<Node, WorldRingKind>[] {
  const rings: readonly WorldRingKind[] = ["self", "family", "nest", "society", "outside"];
  const positioned: PositionedNode<Node, WorldRingKind>[] = [];
  const seen = new Set<string>();
  for (const kind of rings) {
    const ringNodes = sortedUnique(model.rings
      .filter((ring) => ring.kind === kind)
      .flatMap((ring) => ring.nodes))
      .filter((node) => !seen.has(node.id));
    const selected = kind === "self" ? ringNodes.slice(0, 1) : ringNodes;
    for (const [index, node] of selected.entries()) {
      if (positioned.length >= MAX_NODES) return positioned;
      seen.add(node.id);
      const radius = WORLD_RING_RADII[kind];
      const angle = kind === "self" ? 0 : -Math.PI / 2 + (TAU * index) / Math.max(1, selected.length);
      positioned.push({
        ...node,
        x: 170 + radius * Math.cos(angle),
        y: 170 + radius * Math.sin(angle),
        size: nodeSize(node.weight),
        ring: kind,
      });
    }
  }
  return positioned;
}
