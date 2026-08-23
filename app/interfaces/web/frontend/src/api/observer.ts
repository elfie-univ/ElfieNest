import ky from "ky"
import { z } from "zod"

import { csrfHeaders, requestJson } from "./http"

const RoomSubscriptionSchema = z.object({
  kind: z.literal("room"),
  room_id: z.string().min(1),
  elfie_id: z.null().optional(),
}).strict()
const ElfieSubscriptionSchema = z.object({
  kind: z.literal("elfie"),
  elfie_id: z.string().min(1),
  room_id: z.null().optional(),
}).strict()
const ObserverSubscriptionSchema = z.discriminatedUnion("kind", [
  RoomSubscriptionSchema,
  ElfieSubscriptionSchema,
])
const ObserverMockMotionSchema = z.object({
  waypoint: z.number().int().min(0).max(5),
  sequence: z.number().int().positive(),
}).strict()
const ObserverEntitySchema = z.object({
  room_id: z.string(),
  zone_id: z.string().nullable(),
  posture: z.string(),
  active: z.boolean(),
  active_command_id: z.string().nullable(),
  species_id: z.string().nullable().default(null),
  appearance: z.record(z.string(), z.unknown()).default({}),
  home_anchor_id: z.string().nullable().default(null),
  mock_motion: ObserverMockMotionSchema.nullable().default(null),
}).strict()
const ObserverSnapshotSchema = z.object({
  protocol: z.literal(3),
  kind: z.literal("snapshot"),
  generation: z.number().int().positive(),
  sequence: z.number().int().positive(),
  scope: ObserverSubscriptionSchema,
  entities: z.record(z.string(), ObserverEntitySchema),
  entity_revisions: z.record(z.string(), z.number().int().positive()),
}).strict()
const ObserverDeltaSchema = z.object({
  protocol: z.literal(3),
  kind: z.literal("delta"),
  generation: z.number().int().positive(),
  sequence: z.number().int().positive(),
  scope: ObserverSubscriptionSchema,
  entity_id: z.string(),
  entity_revision: z.number().int().positive(),
  patch: ObserverEntitySchema.partial().refine((value) => Object.keys(value).length > 0),
}).strict()
const ObserverFrameSchema = z.discriminatedUnion("kind", [ObserverSnapshotSchema, ObserverDeltaSchema])
const ObserverCapabilitySchema = z.object({
  capability: z.string().min(1),
  idle_timeout_seconds: z.number().int().positive(),
}).strict()
const GodotBuildManifestSchema = z.object({
  files: z.record(z.string(), z.object({ sha256: z.string().length(64) }).passthrough()),
}).passthrough()

export type ObserverSubscription = z.infer<typeof ObserverSubscriptionSchema>
export type ObserverEntity = z.infer<typeof ObserverEntitySchema>
export type ObserverFrame = z.infer<typeof ObserverFrameSchema>
export type ObserverCursor = { readonly generation: number; readonly sequence: number }
export type ObserverSession = {
  readonly capability: string
  readonly idleTimeoutSeconds: number
}

function capabilityHeaders(capability: string, csrfToken?: string): HeadersInit {
  return csrfToken === undefined
    ? { "X-ElfieNest-Observer-Capability": capability }
    : {
        "X-CSRF-Token": csrfToken,
        "X-ElfieNest-Observer-Capability": capability,
      }
}

export async function openObserverSession(
  subscription: ObserverSubscription,
  csrfToken: string,
): Promise<ObserverSession> {
  const payload = await requestJson("/api/v1/observer/sessions", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ protocol: 3, role: "observer", subscription }),
  })
  const parsed = ObserverCapabilitySchema.parse(payload)
  return {
    capability: parsed.capability,
    idleTimeoutSeconds: parsed.idle_timeout_seconds,
  }
}

export async function closeObserverSession(
  capability: string,
  csrfToken: string,
  keepalive = false,
): Promise<void> {
  await requestJson("/api/v1/observer/sessions/current", {
    method: "DELETE",
    headers: capabilityHeaders(capability, csrfToken),
    keepalive,
  })
}

export async function nextObserverFrame(
  capability: string,
  cursor: ObserverCursor | null,
  signal?: AbortSignal,
): Promise<ObserverFrame | null> {
  const query = cursor === null
    ? ""
    : `?acknowledged_generation=${cursor.generation}&acknowledged_sequence=${cursor.sequence}`
  const init: RequestInit = { headers: capabilityHeaders(capability) }
  if (signal !== undefined) init.signal = signal
  const payload = await requestJson(`/api/v1/observer/frames${query}`, init)
  return payload === null ? null : ObserverFrameSchema.parse(payload)
}

export async function warmObserverAssets(): Promise<void> {
  try {
    const manifest = GodotBuildManifestSchema.parse(
      await ky.get("/runtime/godot/build-manifest.json", { credentials: "same-origin" }).json(),
    )
    const resourceNames = Object.keys(manifest.files).filter((name) => /\.(?:js|wasm|pck)$/.test(name))
    await Promise.all(resourceNames.map(async (name) => {
      await ky.get(`/runtime/godot/${encodeURIComponent(name)}`, { credentials: "same-origin" }).arrayBuffer()
    }))
  } catch (reason: unknown) {
    if (reason instanceof Error) return
    throw reason
  }
}
