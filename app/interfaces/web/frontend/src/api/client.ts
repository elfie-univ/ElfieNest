import { z } from "zod"

import { ElfieIdValueSchema } from "@/shared/elfie-id"

import { csrfHeaders, requestJson } from "./http"
import { ProfileDetailSchema, ProfileSchema } from "./owner-elfies"

export * from "./http"
export * from "./owner-elfies"
export * from "./owner-foods"
export * from "./owner-nest"
export * from "./owner-providers"
export * from "./owner-users"
export * from "./roles"
export * from "./session"

export const ChatMessageSchema = z.object({
  id: z.number().int(),
  elfie_id: ElfieIdValueSchema,
  sender: z.union([z.literal("user"), z.literal("elfie"), z.literal("system")]),
  text: z.string(),
  created_at: z.string(),
})
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
  task: z.object({
    step: z.number().int().min(1).max(5),
    key: z.string(),
    state: z.string(),
    progress: z.number().int().min(0).max(100),
    error: z.string().nullable().optional(),
  }).nullable().optional(),
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
const SetupOllamaStateSchema = z.enum([
  "absent",
  "healthy",
  "stopped",
  "deleted",
  "installing",
  "failed",
  "cancelled",
  "repair_required",
])
const SetupOllamaDetectionSchema = z.object({
  state: SetupOllamaStateSchema,
  endpoint: z.string().nullable(),
  version: z.string().nullable(),
})
const SetupModelRecommendationSchema = z.object({
  memory_gb: z.number().int().min(0),
  recommended_model: z.string().nullable(),
  ollama_state: SetupOllamaStateSchema,
  ollama_endpoint: z.string().nullable(),
  installed_models: z.array(z.string()),
  recommended_model_available: z.boolean(),
})
const ConversationSchema = z.object({
  elfie_id: ElfieIdValueSchema,
  name: z.string(),
  portrait_url: z.string(),
  last_message_preview: z.string(),
  last_message_at: z.string().nullable(),
})
const AdoptionInfoSchema = z.object({
  personality_styles: z.array(z.string()),
  species_ids: z.array(z.string()),
  heights: z.array(z.string()),
  builds: z.array(z.string()),
  quota: z.object({
    used: z.number().int(),
    max: z.number().int(),
    remaining: z.number().int(),
    can_adopt: z.boolean(),
  }),
})
const AdoptionResultSchema = z.object({
  elfie_id: ElfieIdValueSchema,
  name: z.string(),
  species_id: z.string(),
})

export type ChatMessage = z.infer<typeof ChatMessageSchema>
export type Conversation = z.infer<typeof ConversationSchema>
export type AdoptionInfo = z.infer<typeof AdoptionInfoSchema>
export type SetupStatus = z.infer<typeof SetupStatusSchema>
export type SetupModelOption = z.infer<typeof SetupModelOptionSchema>
export type SetupOllamaDetection = z.infer<typeof SetupOllamaDetectionSchema>
export type SetupModelRecommendation = z.infer<typeof SetupModelRecommendationSchema>

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

async function postSetup(
  path: string,
  csrfToken: string,
  body: Record<string, unknown>,
): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson(path, {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify(body),
  }))
}

export function setupSkipOllama(csrfToken: string): Promise<SetupStatus> {
  return postSetup("/api/auth/setup/ollama", csrfToken, { decision: "skipped" })
}

export function setupBindExistingOllama(
  endpoint: string,
  csrfToken: string,
): Promise<SetupStatus> {
  return postSetup("/api/auth/setup/ollama", csrfToken, {
    decision: "bound_existing",
    endpoint,
  })
}

export async function setupOllamaDetection(): Promise<SetupOllamaDetection> {
  return SetupOllamaDetectionSchema.parse(
    await requestJson("/api/auth/setup/ollama-detection"),
  )
}

export function setupInstallOfficialOllama(csrfToken: string): Promise<SetupStatus> {
  return postSetup("/api/auth/setup/ollama/install", csrfToken, { confirmed: true })
}

export async function setupNest(bedCount: number, csrfToken: string): Promise<SetupStatus> {
  return SetupStatusSchema.parse(await requestJson("/api/auth/setup/nest", {
    method: "PUT",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ bed_count: bedCount }),
  }))
}

export async function setupModelRecommendation(): Promise<SetupModelRecommendation> {
  return SetupModelRecommendationSchema.parse(
    await requestJson("/api/auth/setup/model-recommendation"),
  )
}

export function setupSkipModel(csrfToken: string): Promise<SetupStatus> {
  return postSetup("/api/auth/setup/model", csrfToken, { decision: "skipped" })
}

export function setupConfiguredModel(
  modelReference: string,
  csrfToken: string,
): Promise<SetupStatus> {
  return postSetup("/api/auth/setup/model", csrfToken, {
    decision: "configured",
    model_reference: modelReference,
  })
}

export function setupPullModel(
  modelReference: string,
  csrfToken: string,
): Promise<SetupStatus> {
  return postSetup("/api/auth/setup/model/pull", csrfToken, {
    model_reference: modelReference,
    confirmed: true,
  })
}

export function setupComplete(csrfToken: string): Promise<SetupStatus> {
  return postSetup("/api/auth/setup/complete", csrfToken, {})
}

export async function conversations(): Promise<readonly Conversation[]> {
  return z.array(ConversationSchema).parse(await requestJson("/api/v1/conversations"))
}

export async function elfies(): Promise<readonly z.infer<typeof ProfileSchema>[]> {
  return z.array(ProfileSchema).parse(await requestJson("/api/v1/elfies"))
}

export async function messages(elfieId: string): Promise<readonly ChatMessage[]> {
  return z.array(ChatMessageSchema).parse(
    await requestJson(`/api/v1/conversations/${encodeURIComponent(elfieId)}/messages`),
  )
}

export async function profile(elfieId: string): Promise<z.infer<typeof ProfileDetailSchema>> {
  return ProfileDetailSchema.parse(
    await requestJson(`/api/v1/elfies/${encodeURIComponent(elfieId)}/profile`),
  )
}

export async function sendMessage(
  elfieId: string,
  text: string,
  csrfToken: string,
): Promise<ChatMessage> {
  return ChatMessageSchema.parse(await requestJson(
    `/api/v1/conversations/${encodeURIComponent(elfieId)}/messages`,
    {
      method: "POST",
      headers: csrfHeaders(csrfToken, true),
      body: JSON.stringify({ text }),
    },
  ))
}

export async function adoptionInfo(): Promise<AdoptionInfo> {
  return AdoptionInfoSchema.parse(await requestJson("/api/user/adoption-info"))
}

export async function adoptElfie(
  input: {
    readonly name: string
    readonly speciesId: string
    readonly personalityStyle: string
    readonly height: string
    readonly build: string
  },
  csrfToken: string,
): Promise<z.infer<typeof AdoptionResultSchema>> {
  return AdoptionResultSchema.parse(await requestJson("/api/user/adopt", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({
      name: input.name,
      species_id: input.speciesId,
      personality_style: input.personalityStyle,
      height: input.height,
      build: input.build,
    }),
  }))
}
