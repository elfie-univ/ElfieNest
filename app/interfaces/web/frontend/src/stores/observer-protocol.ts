import { z } from "zod"

export const OBSERVER_CHANNEL = "elfienest.observer" as const
export const OBSERVER_PROTOCOL_VERSION = 1 as const
export const OBSERVER_CAMERA_COMMAND_KIND = "camera_command" as const

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
