import { z } from "zod"

export const OBSERVER_CHANNEL = "elfienest.observer" as const
export const OBSERVER_PROTOCOL_VERSION = 1 as const
export const OBSERVER_CAMERA_COMMAND_KIND = "camera_command" as const
export const OBSERVER_SEMANTIC_SNAPSHOT_KIND = "semantic_snapshot" as const
export const OBSERVER_WORLD_CONFIG_KIND = "world_config" as const

const semanticStringSchema = z.string().trim().min(1)
const cameraViewSchema = z.object({
  id: semanticStringSchema,
  label: semanticStringSchema,
}).strict()
const cameraCatalogEnvelopeSchema = z.object({
  channel: z.literal(OBSERVER_CHANNEL),
  version: z.literal(OBSERVER_PROTOCOL_VERSION),
  kind: z.literal("camera_catalog"),
  revision: z.number().int().positive(),
  views: z.array(cameraViewSchema).min(1),
  active_id: semanticStringSchema,
  presentation_paused: z.boolean(),
}).strict()
const observerCameraCommandSchema = z.discriminatedUnion("action", [
  z.object({
    channel: z.literal(OBSERVER_CHANNEL),
    version: z.literal(OBSERVER_PROTOCOL_VERSION),
    kind: z.literal(OBSERVER_CAMERA_COMMAND_KIND),
    action: z.literal("overview"),
  }).strict(),
  z.object({
    channel: z.literal(OBSERVER_CHANNEL),
    version: z.literal(OBSERVER_PROTOCOL_VERSION),
    kind: z.literal(OBSERVER_CAMERA_COMMAND_KIND),
    action: z.literal("select"),
    view_id: semanticStringSchema,
  }).strict(),
  z.object({
    channel: z.literal(OBSERVER_CHANNEL),
    version: z.literal(OBSERVER_PROTOCOL_VERSION),
    kind: z.literal(OBSERVER_CAMERA_COMMAND_KIND),
    action: z.literal("reset"),
  }).strict(),
  z.object({
    channel: z.literal(OBSERVER_CHANNEL),
    version: z.literal(OBSERVER_PROTOCOL_VERSION),
    kind: z.literal(OBSERVER_CAMERA_COMMAND_KIND),
    action: z.literal("set_local_presentation_paused"),
    paused: z.boolean(),
  }).strict(),
])
const observerWorldConfigSchema = z.object({
  channel: z.literal(OBSERVER_CHANNEL),
  version: z.literal(OBSERVER_PROTOCOL_VERSION),
  kind: z.literal(OBSERVER_WORLD_CONFIG_KIND),
  nest_id: semanticStringSchema,
  bed_count: z.number().int().min(4).max(32),
}).strict()
const observerSemanticScopeSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("room"), room_id: semanticStringSchema }).strict(),
  z.object({ kind: z.literal("elfie"), elfie_id: semanticStringSchema }).strict(),
])
const observerMockMotionSchema = z.object({
  waypoint: z.number().int().min(0).max(5),
  sequence: z.number().int().positive(),
}).strict()
const observerSemanticEntitySchema = z.object({
  room_id: semanticStringSchema,
  zone_id: semanticStringSchema.nullable(),
  posture: semanticStringSchema,
  active: z.boolean(),
  active_command_id: semanticStringSchema.nullable(),
  species_id: semanticStringSchema.nullable(),
  appearance: z.record(z.string(), z.unknown()),
  home_anchor_id: semanticStringSchema.nullable(),
  mock_motion: observerMockMotionSchema.nullable().default(null),
}).strict()
const observerSemanticSnapshotSchema = z.object({
  channel: z.literal(OBSERVER_CHANNEL),
  version: z.literal(OBSERVER_PROTOCOL_VERSION),
  kind: z.literal(OBSERVER_SEMANTIC_SNAPSHOT_KIND),
  protocol: z.literal(3),
  generation: z.number().int().positive(),
  sequence: z.number().int().positive(),
  scope: observerSemanticScopeSchema,
  entities: z.record(z.string().min(1), observerSemanticEntitySchema),
  entity_revisions: z.record(z.string().min(1), z.number().int().positive()),
}).strict().refine(
  (value) => Object.keys(value.entities).every((entityId) => Object.prototype.hasOwnProperty.call(value.entity_revisions, entityId))
    && Object.keys(value.entities).length === Object.keys(value.entity_revisions).length,
  { message: "semantic entity revisions must match entities" },
).refine((value) => !containsForbiddenCoordinateKey(value), {
  message: "semantic observer payload cannot contain geometry",
})

type ParsedCameraCatalogEnvelope = z.infer<typeof cameraCatalogEnvelopeSchema>
type JsonParseResult =
  | { readonly kind: "invalid" }
  | { readonly kind: "parsed"; readonly value: unknown }

export type ObserverCameraView = {
  readonly id: string
  readonly label: string
}

export type ObserverCameraCatalog = {
  readonly activeId: string
  readonly presentationPaused: boolean
  readonly revision: number
  readonly views: readonly ObserverCameraView[]
}

export type ObserverCameraCommand =
  | {
    readonly action: "overview"
    readonly channel: typeof OBSERVER_CHANNEL
    readonly kind: typeof OBSERVER_CAMERA_COMMAND_KIND
    readonly version: typeof OBSERVER_PROTOCOL_VERSION
  }

  | {
    readonly action: "select"
    readonly channel: typeof OBSERVER_CHANNEL
    readonly kind: typeof OBSERVER_CAMERA_COMMAND_KIND
    readonly version: typeof OBSERVER_PROTOCOL_VERSION
    readonly view_id: string
  }
  | {
    readonly action: "reset"
    readonly channel: typeof OBSERVER_CHANNEL
    readonly kind: typeof OBSERVER_CAMERA_COMMAND_KIND
    readonly version: typeof OBSERVER_PROTOCOL_VERSION
  }
  | {
    readonly action: "set_local_presentation_paused"
    readonly channel: typeof OBSERVER_CHANNEL
    readonly kind: typeof OBSERVER_CAMERA_COMMAND_KIND
    readonly paused: boolean
    readonly version: typeof OBSERVER_PROTOCOL_VERSION
  }

export type ObserverSemanticSnapshot = z.infer<typeof observerSemanticSnapshotSchema>
export type ObserverWorldConfig = z.infer<typeof observerWorldConfigSchema>

function parseJson(value: string): JsonParseResult {
  try {
    const parsed: unknown = JSON.parse(value)
    return { kind: "parsed", value: parsed }
  } catch (reason: unknown) {
    if (reason instanceof SyntaxError) return { kind: "invalid" }
    throw reason
  }
}

function toCameraCatalog(envelope: ParsedCameraCatalogEnvelope): ObserverCameraCatalog | null {
  const viewIds = new Set<string>()
  for (const view of envelope.views) {
    if (viewIds.has(view.id)) return null
    viewIds.add(view.id)
  }
  if (!viewIds.has(envelope.active_id)) return null
  return {
    activeId: envelope.active_id,
    presentationPaused: envelope.presentation_paused,
    revision: envelope.revision,
    views: envelope.views.map((view) => ({ id: view.id, label: view.label })),
  }
}

export function parseObserverCameraCatalog(value: unknown): ObserverCameraCatalog | null {
  if (typeof value !== "string") return null
  const json = parseJson(value)
  switch (json.kind) {
    case "invalid":
      return null
    case "parsed": {
      const parsed = cameraCatalogEnvelopeSchema.safeParse(json.value)
      return parsed.success ? toCameraCatalog(parsed.data) : null
    }
  }
}

export function parseObserverCameraCommand(value: unknown): ObserverCameraCommand | null {
  const parsed = observerCameraCommandSchema.safeParse(value)
  return parsed.success ? parsed.data : null
}

export function parseObserverWorldConfig(value: unknown): ObserverWorldConfig | null {
  const candidate = typeof value === "string" ? parseJson(value) : { kind: "parsed" as const, value }
  if (candidate.kind === "invalid") return null
  const parsed = observerWorldConfigSchema.safeParse(candidate.value)
  return parsed.success ? parsed.data : null
}

export function createObserverWorldConfig(nestId: string, bedCount: number): ObserverWorldConfig {
  return {
    channel: OBSERVER_CHANNEL,
    version: OBSERVER_PROTOCOL_VERSION,
    kind: OBSERVER_WORLD_CONFIG_KIND,
    nest_id: nestId,
    bed_count: bedCount,
  }
}

export function parseObserverSemanticSnapshot(value: unknown): ObserverSemanticSnapshot | null {
  const candidate = typeof value === "string" ? parseJson(value) : { kind: "parsed" as const, value }
  if (candidate.kind === "invalid") return null
  const parsed = observerSemanticSnapshotSchema.safeParse(candidate.value)
  return parsed.success ? parsed.data : null
}

const FORBIDDEN_SEMANTIC_KEYS = new Set([
  "x", "y", "z", "position", "positions", "transform", "transforms", "coordinates",
  "fov", "frame", "frames", "credential", "credentials", "token", "nonce", "authority",
])

function containsForbiddenCoordinateKey(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsForbiddenCoordinateKey)
  if (typeof value !== "object" || value === null) return false
  return Object.entries(value).some(([key, nested]) => (
    FORBIDDEN_SEMANTIC_KEYS.has(key) || containsForbiddenCoordinateKey(nested)
  ))
}
