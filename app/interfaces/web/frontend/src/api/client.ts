import { z } from "zod"

import { csrfHeaders, requestJson } from "./http"
import { ProfileDetailSchema, ProfileSchema } from "./owner-elfies"

export * from "./http"
export * from "./owner-elfies"
export * from "./admin/food-packages"
export * from "./elfies/food-policy"
export * from "./owner-nest"
export * from "./owner-providers"
export * from "./owner-users"
export * from "./roles"
export * from "./session"

const SetupStatusSchema = z.object({
  need_setup: z.boolean(),
  complete: z.boolean(),
  current_step: z.number().int().min(1).max(4),
  locked: z.boolean(),
  csrf_token: z.string().nullable(),
  draft: z.object({
    owner_account_id: z.string().nullable(),
    display_name: z.string().nullable(),
    password_configured: z.boolean(),
    use_local_ollama: z.boolean().nullable(),
    ollama_installed: z.boolean(),
    model_id: z.string().nullable(),
    bed_count: z.number().int().nullable(),
    owner_configured: z.boolean(),
    offline_configured: z.boolean(),
    nest_configured: z.boolean(),
    locked_at: z.string().nullable(),
  }),
  steps: z.array(z.object({
    number: z.number().int().min(1).max(4),
    name: z.string(),
    status: z.string(),
    retry_action: z.string().nullable().optional(),
  })),
  last_error: z.string().nullable().optional(),
  install: z.object({
    phase: z.enum(["owner", "ollama", "model", "emergency_food", "nest"]),
    action_key: z.string(),
    state: z.enum(["idle", "running", "failed", "completed"]),
    progress: z.number().int().min(0).max(100),
    error_key: z.string().nullable(),
  }),
})
const SetupModelOptionSchema = z.object({
  model_id: z.string(),
  label: z.string(),
  approx_download_mb: z.number().int().positive(),
  recommended: z.boolean(),
})
export type SetupStatus = z.infer<typeof SetupStatusSchema>
export type SetupModelOption = z.infer<typeof SetupModelOptionSchema>

export async function setupStatus(): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/auth/setup-status"))
}

export async function setupModelCatalog(): Promise<readonly SetupModelOption[]> {
  return z.array(SetupModelOptionSchema).parse(
    await requestJson("/api/auth/setup/model-catalog"),
  )
}

export async function setupSaveOwnerDraft(
  accountId: string,
  displayName: string,
  password: string | null,
  confirmPassword: string | null,
  csrfToken: string,
): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/auth/setup/draft/owner", {
    method: "PUT",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({
      account_id: accountId,
      display_name: displayName || null,
      password,
      confirm_password: confirmPassword,
    }),
  }))
}

export async function setupSaveOfflineDraft(
  useLocalOllama: boolean,
  modelId: string | null,
  csrfToken: string,
): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/auth/setup/draft/offline", {
    method: "PUT",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ use_local_ollama: useLocalOllama, model_id: modelId }),
  }))
}

export async function setupSaveNestDraft(
  bedCount: number,
  csrfToken: string,
): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/auth/setup/draft/nest", {
    method: "PUT",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ bed_count: bedCount }),
  }))
}

export async function setupInstall(csrfToken: string): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/auth/setup/install", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ confirmed: true }),
  }))
}

export async function elfies(): Promise<readonly z.infer<typeof ProfileSchema>[]> {
  return z.array(ProfileSchema).parse(await requestJson("/api/v1/elfies"))
}

export async function profile(elfieId: string): Promise<z.infer<typeof ProfileDetailSchema>> {
  return ProfileDetailSchema.parse(
    await requestJson(`/api/v1/elfies/${encodeURIComponent(elfieId)}/profile`),
  )
}
