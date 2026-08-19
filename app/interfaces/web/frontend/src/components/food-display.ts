import type { FoodPackage } from "../api/admin/food-packages"
import type { OllamaStatus } from "../api/owner-ollama"
import type { ProviderConnection, ProviderModel } from "../api/owner-providers"

export const FOOD_MODEL_ROLES = ["primary", "reasoning", "vision", "tool", "fallback"] as const
export type FoodModelRole = (typeof FOOD_MODEL_ROLES)[number]
export type FoodModelStatus = "available" | "degraded" | "unavailable" | "unverified" | "unconfigured"
export type FoodLocalRuntime = Pick<OllamaStatus, "state" | "models">

type FoodModelSource = Pick<ProviderModel, "id" | "display_name" | "available" | "hidden" | "retired" | "verification">
type FoodConnectionSource = Pick<ProviderConnection, "connection_id" | "alias"> & {
  readonly models: readonly FoodModelSource[]
}

export type FoodModelCell = {
  readonly reference: string | null
  readonly label: string
  readonly local: boolean
  readonly status: FoodModelStatus
  readonly latencyLabel: string | null
}

export type FoodVisibilityProjection =
  | { readonly kind: "all"; readonly count: null }
  | { readonly kind: "users"; readonly count: number; readonly allCurrentUsers: boolean }
  | { readonly kind: "error"; readonly count: null }

export type FoodDisplayProjection = {
  readonly isLocal: boolean
  readonly models: Readonly<Record<FoodModelRole, FoodModelCell>>
  readonly visibility: FoodVisibilityProjection
}

export function projectFoodDisplay(
  food: FoodPackage,
  connections: readonly FoodConnectionSource[],
  currentUserCount = 0,
  localRuntime: FoodLocalRuntime | null = null,
  localConnectionIds: readonly string[] = [],
): FoodDisplayProjection {
  const models: Record<FoodModelRole, FoodModelCell> = {
    primary: projectModelCell(food.roles.primary?.model ?? null, connections, localRuntime, localConnectionIds),
    reasoning: projectModelCell(food.roles.reasoning?.model ?? null, connections, localRuntime, localConnectionIds),
    vision: projectModelCell(food.roles.vision?.model ?? null, connections, localRuntime, localConnectionIds),
    tool: projectModelCell(food.roles.tool?.model ?? null, connections, localRuntime, localConnectionIds),
    fallback: projectModelCell(food.roles.fallback?.model ?? null, connections, localRuntime, localConnectionIds),
  }
  return {
    isLocal: food.locality === "local",
    models,
    visibility: food.system_role || food.visibility_mode === "global"
      ? { kind: "all", count: null }
      : food.visibility_mode === "users"
        ? {
            kind: "users",
            count: food.visible_user_ids.length,
            allCurrentUsers: currentUserCount > 0 && food.visible_user_ids.length === currentUserCount,
          }
        : { kind: "error", count: null },
  }
}

function projectModelCell(
  reference: string | null,
  connections: readonly FoodConnectionSource[],
  localRuntime: FoodLocalRuntime | null,
  localConnectionIds: readonly string[],
): FoodModelCell {
  const parsed = parseReference(reference)
  const connection = connections.find((item) => item.connection_id === parsed.connectionId)
  const model = connection?.models.find((item) => item.id === parsed.modelId)
  const local = localConnectionIds.includes(parsed.connectionId)
  const status = reference ? modelStatus(model, local, localRuntime) : "unconfigured"
  return {
    reference,
    label: !reference
      ? ""
      : model && connection
        ? `${connection.alias} / ${model.display_name}`
        : reference,
    local,
    status,
    latencyLabel: formatLatency(model?.verification.latency_ms ?? null),
  }
}

function parseReference(reference: string | null): { readonly connectionId: string; readonly modelId: string } {
  if (!reference) return { connectionId: "", modelId: "—" }
  const separator = reference.indexOf("/")
  if (separator < 0) return { connectionId: "", modelId: reference }
  return { connectionId: reference.slice(0, separator), modelId: reference.slice(separator + 1) || reference }
}

function modelStatus(model: FoodModelSource | undefined, local: boolean, localRuntime: FoodLocalRuntime | null): FoodModelStatus {
  if (local) {
    if (!model || model.hidden || model.retired) return "unavailable"
    if (localRuntime === null || localRuntime.state === "unknown") return "unverified"
    if (localRuntime.state !== "healthy") return "unavailable"
    const runtimeModel = localRuntime.models.find((item) => item.id === model.id)
    if (runtimeModel === undefined) return "unverified"
    if (!runtimeModel.installed) return "unavailable"
    if (runtimeModel.availability_status === "degraded") return "degraded"
    if (runtimeModel.availability_status === "unavailable") return "unavailable"
    if (runtimeModel.availability_status === "available" || (runtimeModel.availability_status === undefined && runtimeModel.available === true)) return "available"
    return "unverified"
  }
  if (!model) return "unverified"
  if (model.hidden || model.retired || model.verification.status === "failed" || model.verification.availability_status === "unavailable") return "unavailable"
  if (model.verification.availability_status === "degraded") return "degraded"
  return model.available && model.verification.status === "passed" ? "available" : "unverified"
}

export function formatLatency(latencyMs: number | null): string | null {
  if (latencyMs === null) return null
  return latencyMs < 1000 ? `${Math.round(latencyMs)} ms` : `${(latencyMs / 1000).toFixed(1)} s`
}
