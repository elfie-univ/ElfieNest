import { z } from "zod"

import { ownerRead, ownerWrite } from "../http"

export const RuntimeSettingsSchema = z.object({
  tick_interval_sec: z.number().positive(),
}).strict()

export const ElfieSettingsSchema = z.object({
  max_elfies_per_user: z.number().int().min(1).max(32),
  allowed_species_ids: z.array(z.enum(["dog", "fox", "cat"])).min(1),
  personality_presets_enabled: z.record(z.string(), z.boolean()),
}).strict()

export const SecuritySettingsSchema = z.object({
  session_ttl_days: z.number().int().min(1),
  rate_limit: z.object({
    max_attempts: z.number().int().min(1),
    window_seconds: z.number().int().min(1),
  }).strict(),
}).strict()

export type RuntimeSettings = z.infer<typeof RuntimeSettingsSchema>
export type ElfieSettings = z.infer<typeof ElfieSettingsSchema>
export type SecuritySettings = z.infer<typeof SecuritySettingsSchema>

const RUNTIME_PATH = "/api/v1/admin/settings/runtime"
const ELFIES_PATH = "/api/v1/admin/settings/elfies"
const SECURITY_PATH = "/api/v1/admin/settings/security"

export async function runtimeSettings(): Promise<RuntimeSettings> {
  return RuntimeSettingsSchema.parse(await ownerRead(RUNTIME_PATH))
}

export async function elfieSettings(): Promise<ElfieSettings> {
  return ElfieSettingsSchema.parse(await ownerRead(ELFIES_PATH))
}

export async function securitySettings(): Promise<SecuritySettings> {
  return SecuritySettingsSchema.parse(await ownerRead(SECURITY_PATH))
}

export async function updateRuntimeSettings(
  settings: RuntimeSettings,
  csrfToken: string,
): Promise<RuntimeSettings> {
  return RuntimeSettingsSchema.parse(
    await ownerWrite(RUNTIME_PATH, "PATCH", csrfToken, settings),
  )
}

export async function updateElfieSettings(
  settings: ElfieSettings,
  csrfToken: string,
): Promise<ElfieSettings> {
  return ElfieSettingsSchema.parse(
    await ownerWrite(ELFIES_PATH, "PATCH", csrfToken, settings),
  )
}

export async function updateSecuritySettings(
  settings: SecuritySettings,
  csrfToken: string,
): Promise<SecuritySettings> {
  return SecuritySettingsSchema.parse(
    await ownerWrite(SECURITY_PATH, "PATCH", csrfToken, settings),
  )
}
