import { z } from "zod"

import { csrfHeaders, requestJson } from "./http"

const SetupStatusSchema = z.object({
  need_setup: z.boolean(),
  complete: z.boolean(),
  current_step: z.number().int().min(1).max(4),
  locked: z.boolean(),
  csrf_token: z.string().nullable(),
  draft: z.object({
    owner_account_id: z.string().nullable(), display_name: z.string().nullable(),
    password_configured: z.boolean(), use_local_ollama: z.boolean().nullable(),
    ollama_installed: z.boolean(), model_id: z.string().nullable(), bed_count: z.number().int().nullable(),
    owner_configured: z.boolean(), offline_configured: z.boolean(), nest_configured: z.boolean(), locked_at: z.string().nullable(),
  }),
  steps: z.array(z.object({
    number: z.number().int().min(1).max(4), name: z.string(),
    status: z.enum(["pending", "current", "completed"]), retry_action: z.string().nullable(),
  })),
  last_error: z.string().nullable(),
  install: z.object({
    phase: z.enum(["owner", "ollama", "model", "emergency_food", "nest"]),
    action_key: z.string(), state: z.enum(["idle", "running", "failed", "completed", "cancelled"]),
    progress: z.number().int().min(0).max(100), error_key: z.string().nullable(),
  }),
})
const SetupModelOptionSchema = z.object({
  model_id: z.string(), label: z.string(), approx_download_mb: z.number().int().positive(), recommended: z.boolean(),
})
const SetupModelCollectionSchema = z.object({ items: z.array(SetupModelOptionSchema) })
const SetupOllamaObservationSchema = z.object({
  endpoint: z.string().nullable(),
  platform: z.enum(["darwin", "linux", "win32"]),
  state: z.enum(["absent", "healthy", "stopped", "deleted", "installing", "failed", "cancelled", "repair_required"]),
  version: z.string().nullable(),
})

export type SetupStatus = z.infer<typeof SetupStatusSchema>
export type SetupModelOption = z.infer<typeof SetupModelOptionSchema>
export type SetupOllamaObservation = z.infer<typeof SetupOllamaObservationSchema>

export async function setupStatus(): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/v1/setup/status", { cache: "no-store" }))
}
export async function setupModelCatalog(): Promise<readonly SetupModelOption[]> {
  return SetupModelCollectionSchema.parse(await requestJson("/api/v1/setup/models")).items
}
export async function setupInspectOllama(): Promise<SetupOllamaObservation> {
  return SetupOllamaObservationSchema.parse(await requestJson("/api/v1/setup/ollama"))
}
export async function setupSaveOwnerDraft(accountId: string, displayName: string, password: string | null, confirmPassword: string | null, csrfToken: string): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/v1/setup/draft/owner", {
    method: "PUT", headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ account_id: accountId, display_name: displayName || null, password, confirm_password: confirmPassword }),
  }))
}
export async function setupSaveOfflineDraft(useLocalOllama: boolean, modelId: string | null, csrfToken: string): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/v1/setup/draft/offline", {
    method: "PUT", headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ use_local_ollama: useLocalOllama, model_id: modelId }),
  }))
}
export async function setupSaveNestDraft(bedCount: number, csrfToken: string): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/v1/setup/draft/nest", {
    method: "PUT", headers: csrfHeaders(csrfToken, true), body: JSON.stringify({ bed_count: bedCount }),
  }))
}
export async function setupInstall(csrfToken: string): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/v1/setup/installation", {
    method: "POST", headers: csrfHeaders(csrfToken, true), body: JSON.stringify({ confirmed: true }),
  }))
}
export async function setupCancel(csrfToken: string): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/v1/setup/installation/cancel", {
    method: "POST", headers: csrfHeaders(csrfToken, true),
  }))
}
