import { z } from "zod"

import { ownerWrite, requestJson } from "../http"

export const TelegramAccountSchema = z.object({
  elfie_id: z.string().min(1),
  state: z.enum(["unconfigured", "waiting_pairing", "active", "attention"]),
  bot_username: z.string().nullable(),
  bot_display_name: z.string().nullable(),
  bound_telegram_username: z.string().nullable(),
  bound_display_name: z.string().nullable(),
  last_checked_at: z.string().nullable(),
  issue: z.string().nullable(),
}).strict()

export const TelegramPairingSessionSchema = z.object({
  deep_link: z.string().url(),
  expires_at: z.string().min(1),
}).strict()

export type TelegramAccount = z.infer<typeof TelegramAccountSchema>
export type TelegramPairingSession = z.infer<typeof TelegramPairingSessionSchema>

function telegramAccountPath(elfieId: string): string {
  return `/api/v1/elfies/${encodeURIComponent(elfieId)}/communication-accounts/telegram`
}

export async function telegramAccount(elfieId: string): Promise<TelegramAccount> {
  return TelegramAccountSchema.parse(await requestJson(telegramAccountPath(elfieId)))
}

export async function configureTelegramAccount(
  elfieId: string,
  botToken: string,
  csrfToken: string,
): Promise<TelegramAccount> {
  return TelegramAccountSchema.parse(await ownerWrite(
    telegramAccountPath(elfieId),
    "PUT",
    csrfToken,
    { bot_token: botToken },
  ))
}

export async function disconnectTelegramAccount(
  elfieId: string,
  csrfToken: string,
): Promise<TelegramAccount> {
  return TelegramAccountSchema.parse(await ownerWrite(
    telegramAccountPath(elfieId),
    "DELETE",
    csrfToken,
  ))
}

export async function createTelegramPairingSession(
  elfieId: string,
  csrfToken: string,
): Promise<TelegramPairingSession> {
  return TelegramPairingSessionSchema.parse(await ownerWrite(
    `${telegramAccountPath(elfieId)}/pairing-sessions`,
    "POST",
    csrfToken,
  ))
}
