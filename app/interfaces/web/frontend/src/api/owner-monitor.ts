import { z } from "zod"

import { ApiError, ownerRead } from "./client"

const HealthSchema = z.object({
  status: z.string(),
  engine_ready: z.boolean(),
  godot_web_ready: z.boolean(),
  godot_runtime_ready: z.boolean(),
}).strict()

const RuntimeEventSchema = z.object({
  event_type: z.string(),
  status: z.string(),
  subject: z.string(),
  metadata: z.record(z.string(), z.unknown()),
}).passthrough()

const RuntimeStatusSchema = z.object({
  status: z.string(),
  observer: z.object({ event_count: z.number(), last_event: RuntimeEventSchema.nullable() }),
}).strict()

const UserSummarySchema = z.object({
  presence: z.enum(["online", "away", "offline"]),
}).passthrough()

const ElfieSummarySchema = z.object({
  elfie_id: z.string(),
  profile: z.object({
    online_status: z.enum(["online", "offline", "unknown"]),
  }).passthrough(),
}).passthrough()

const RoomSummarySchema = z.object({
  beds: z.array(z.object({ occupant_id: z.string().nullable() }).passthrough()),
}).passthrough()

const ProviderSummarySchema = z.object({
  catalog_id: z.string(),
  alias: z.string(),
  enabled: z.boolean(),
  archived: z.boolean(),
  verification: z.object({ status: z.enum(["never", "passed", "failed"]) }).passthrough(),
  models: z.array(z.object({
    available: z.boolean(),
    hidden: z.boolean(),
    retired: z.boolean(),
  }).passthrough()),
}).passthrough()

const OllamaStatusSchema = z.object({
  state: z.enum(["absent", "healthy", "stopped", "deleted", "installing", "failed", "cancelled", "repair_required"]),
  recommended_model: z.string().nullable(),
  installed_model_count: z.number().int().min(0),
}).passthrough()

export type MonitorHealth = z.infer<typeof HealthSchema>
export type MonitorRuntimeStatus = z.infer<typeof RuntimeStatusSchema>
export type MonitorUser = z.infer<typeof UserSummarySchema>
export type MonitorElfie = z.infer<typeof ElfieSummarySchema>
export type MonitorRoom = z.infer<typeof RoomSummarySchema>
export type MonitorProvider = z.infer<typeof ProviderSummarySchema>
export type MonitorOllama = z.infer<typeof OllamaStatusSchema>

export const MONITOR_SOURCE_KEYS = ["health", "runtime", "users", "elfies", "rooms", "providers", "ollama"] as const
export type MonitorSourceKey = (typeof MONITOR_SOURCE_KEYS)[number]

export type MonitorSnapshot = {
  readonly health: MonitorHealth | null
  readonly runtime: MonitorRuntimeStatus | null
  readonly users: readonly MonitorUser[] | null
  readonly elfies: readonly MonitorElfie[] | null
  readonly rooms: readonly MonitorRoom[] | null
  readonly providers: readonly MonitorProvider[] | null
  readonly ollama: MonitorOllama | null
  readonly failedSources: readonly MonitorSourceKey[]
  readonly authRequired: boolean
}

async function readSchema<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  return schema.parse(await ownerRead(path))
}

function sourceValue<T>(result: PromiseSettledResult<T>): T | null {
  return result.status === "fulfilled" ? result.value : null
}

function sourceFailed<T>(result: PromiseSettledResult<T>): boolean {
  return result.status === "rejected"
}

function sourceRequiresAuth(result: PromiseSettledResult<unknown>): boolean {
  return result.status === "rejected" && result.reason instanceof ApiError && (result.reason.status === 401 || result.reason.status === 403)
}

export async function loadMonitorSnapshot(): Promise<MonitorSnapshot> {
  const results = await Promise.allSettled([
    readSchema("/api/health", HealthSchema),
    readSchema("/api/owner/runtime/status", RuntimeStatusSchema),
    readSchema("/api/owner/users", z.array(UserSummarySchema)),
    readSchema("/api/owner/elfies", z.array(ElfieSummarySchema)),
    readSchema("/api/owner/nest/rooms", z.array(RoomSummarySchema)),
    readSchema("/api/owner/providers/connections", z.array(ProviderSummarySchema)),
    readSchema("/api/owner/providers/ollama", OllamaStatusSchema),
  ] as const)
  const [health, runtime, users, elfies, rooms, providers, ollama] = results
  const failedSources: MonitorSourceKey[] = []
  if (sourceFailed(health)) failedSources.push("health")
  if (sourceFailed(runtime)) failedSources.push("runtime")
  if (sourceFailed(users)) failedSources.push("users")
  if (sourceFailed(elfies)) failedSources.push("elfies")
  if (sourceFailed(rooms)) failedSources.push("rooms")
  if (sourceFailed(providers)) failedSources.push("providers")
  if (sourceFailed(ollama)) failedSources.push("ollama")
  const authRequired = results.some(sourceRequiresAuth)
  return {
    health: sourceValue(health),
    runtime: sourceValue(runtime),
    users: sourceValue(users),
    elfies: sourceValue(elfies),
    rooms: sourceValue(rooms),
    providers: sourceValue(providers),
    ollama: sourceValue(ollama),
    failedSources,
    authRequired,
  }
}
