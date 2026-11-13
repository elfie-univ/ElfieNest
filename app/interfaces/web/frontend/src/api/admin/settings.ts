import { z } from "zod"

import { ownerRead, ownerWrite } from "../http"

export const RuntimeSettingsSchema = z.object({
  tick_interval_sec: z.number().positive(),
}).strict()

export const ElfieSettingsSchema = z.object({
  max_elfies_per_user: z.number().int().min(1).max(32),
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

const clockTime = z.string().regex(/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/)
export const EnvironmentScheduleSchema = z.object({
  daylight_source: z.enum(["manual", "local"]),
  sunrise_time: clockTime, sunset_time: clockTime, rest_time: clockTime,
  latitude: z.number().finite().min(-90).max(90).nullable(),
  longitude: z.number().finite().min(-180).max(180).nullable(),
}).strict()
export const EnvironmentSettingsSchema = z.object({
  settings: EnvironmentScheduleSchema,
  today: z.object({ date: z.string(), timezone: z.string(), sunrise_time: clockTime.nullable(),
    sunset_time: clockTime.nullable(), condition: z.enum(["normal", "polar_day", "polar_night"]) }).strict(),
}).strict()
export type EnvironmentSettings = z.infer<typeof EnvironmentSettingsSchema>
export type EnvironmentSchedule = z.infer<typeof EnvironmentScheduleSchema>
const ENVIRONMENT_PATH = "/api/v1/admin/settings/environment"

export async function environmentSettings(): Promise<EnvironmentSettings> {
  return EnvironmentSettingsSchema.parse(await ownerRead(ENVIRONMENT_PATH))
}
export async function updateEnvironmentSettings(settings: EnvironmentSchedule, csrfToken: string): Promise<EnvironmentSettings> {
  return EnvironmentSettingsSchema.parse(await ownerWrite(ENVIRONMENT_PATH, "PUT", csrfToken, { settings }))
}

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
