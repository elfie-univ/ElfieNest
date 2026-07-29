import { z } from "zod"

import { ElfieIdValueSchema } from "@/shared/elfie-id"

export const GRAPH_PREVIEW_LIMIT = 20
export const GRAPH_DETAIL_LIMIT = 50

export const BIG_FIVE_TRAITS = [
  "openness",
  "conscientiousness",
  "extraversion",
  "agreeableness",
  "neuroticism",
] as const

const GraphModes = ["preview", "detail"] as const

export const AccountIdSchema = z.string().min(1).brand("AccountId")
export const ElfieIdSchema = ElfieIdValueSchema.brand("ElfieId")
const GraphNodeIdSchema = z.string().min(1).brand("GraphNodeId")

export type AccountId = z.infer<typeof AccountIdSchema>
export type ElfieId = z.infer<typeof ElfieIdSchema>
export type GraphMode = (typeof GraphModes)[number]

const ViewerSchema = z.object({
  accountId: AccountIdSchema,
  role: z.union([z.literal("owner"), z.literal("user")]),
  displayName: z.string().min(1),
}).readonly()

const AdopterSchema = z.object({
  accountId: AccountIdSchema,
  displayName: z.string().min(1),
}).readonly()

const AdoptionMetadataSchema = z.object({
  adoptedAt: z.string().min(1),
  ageLabel: z.string().min(1),
}).readonly()

const BigFiveSchema = z.object({
  openness: z.number().min(0).max(1),
  conscientiousness: z.number().min(0).max(1),
  extraversion: z.number().min(0).max(1),
  agreeableness: z.number().min(0).max(1),
  neuroticism: z.number().min(0).max(1),
}).readonly()

const AppearanceSchema = z.object({
  bodyPlan: z.string().min(1),
  palette: z.string().min(1),
  signature: z.string().min(1),
}).readonly()

const PublicProfileSchema = z.object({
  elfieId: ElfieIdSchema,
  name: z.string().min(1),
  speciesId: z.string().min(1),
  gender: z.string().min(1).nullable().default(null),
  biography: z.string().default(""),
  portraitUrl: z.string().default(""),
  appearance: AppearanceSchema,
  bigFive: BigFiveSchema,
}).readonly()

const GraphNodeSchema = z.object({
  id: GraphNodeIdSchema,
  label: z.string().min(1),
}).readonly()

const GraphEdgeSchema = z.object({
  source: GraphNodeIdSchema,
  target: GraphNodeIdSchema,
  label: z.string().min(1),
  directed: z.boolean().default(false),
}).readonly()

const GraphSchema = z.object({
  nodes: z.array(GraphNodeSchema).readonly(),
  edges: z.array(GraphEdgeSchema).readonly(),
}).readonly()

const MemoryModuleSchema = z.object({
  title: z.literal("记忆与认知"),
  topics: z.array(z.object({
    label: z.string().min(1),
    count: z.number().int().min(0),
  }).readonly()).readonly(),
  experienceCount: z.number().int().min(0),
}).readonly()

const TimelineModuleSchema = z.object({
  title: z.literal("重要经历"),
  entries: z.array(z.object({
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    title: z.string().min(1),
    detail: z.string().min(1),
  }).readonly()).readonly(),
}).readonly()

const RelationshipGraphModuleSchema = z.object({
  title: z.literal("关系认知"),
  graph: GraphSchema,
}).readonly()

const KnowledgeGraphModuleSchema = z.object({
  title: z.literal("知识与信念"),
  graph: GraphSchema,
}).readonly()

const WorldGraphModuleSchema = z.object({
  title: z.literal("世界理解"),
  graph: GraphSchema,
}).readonly()

const FoodStrategyModuleSchema = z.object({
  title: z.literal("粮食策略"),
  food: z.object({
    selected: z.string().min(1),
    allowed: z.array(z.string().min(1)).min(1).readonly(),
    fallback: z.string().min(1),
  }).readonly(),
}).readonly()

const PrivateCognitionSchema = z.object({
  modules: z.tuple([
    MemoryModuleSchema,
    TimelineModuleSchema,
    RelationshipGraphModuleSchema,
    KnowledgeGraphModuleSchema,
    WorldGraphModuleSchema,
    FoodStrategyModuleSchema,
  ]).readonly(),
}).readonly()

const ExperienceFixtureSchema = z.object({
  adopter: AdopterSchema,
  adoption: AdoptionMetadataSchema.default({ adoptedAt: "未登记", ageLabel: "未登记" }),
  publicProfile: PublicProfileSchema,
  privateCognition: PrivateCognitionSchema,
}).readonly()

export type Viewer = z.infer<typeof ViewerSchema>
export type PublicProfile = z.infer<typeof PublicProfileSchema>
export type PrivateCognition = z.infer<typeof PrivateCognitionSchema>
export type ExperienceFixture = z.infer<typeof ExperienceFixtureSchema>
export type Graph = z.infer<typeof GraphSchema>
export type GraphProjection = {
  readonly nodes: readonly z.infer<typeof GraphNodeSchema>[]
  readonly edges: readonly z.infer<typeof GraphEdgeSchema>[]
  readonly truncatedNodeCount: number
}

export function parseViewer(input: unknown): Viewer {
  return ViewerSchema.parse(input)
}

export function parseExperienceFixture(input: unknown): ExperienceFixture {
  return ExperienceFixtureSchema.parse(input)
}

export function projectGraph(graph: Graph, mode: GraphMode): GraphProjection {
  const limit = graphLimit(mode)
  const nodes = graph.nodes.slice(0, limit)
  const visibleIds = new Set(nodes.map((node) => node.id))
  return {
    nodes,
    edges: graph.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)),
    truncatedNodeCount: Math.max(0, graph.nodes.length - nodes.length),
  }
}

function graphLimit(mode: GraphMode): number {
  switch (mode) {
    case "preview":
      return GRAPH_PREVIEW_LIMIT
    case "detail":
      return GRAPH_DETAIL_LIMIT
    default:
      return assertNever(mode)
  }
}

function assertNever(value: never): never {
  throw new RangeError(`Unexpected graph mode: ${String(value)}`)
}
