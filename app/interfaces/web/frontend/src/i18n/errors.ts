import type { SupportedLocale } from "./locale"

import type { ChatSocketErrorEvent } from "../api/chat-socket"
import { ApiError, type ApiValidationDetail } from "../api/http"
import { resources } from "./resources"

export const errorOperations = [
  "auth.login",
  "setup.load",
  "setup.save",
  "setup.install",
  "setup.pull",
  "setup.complete",
  "chat.load",
  "chat.send",
  "chat.connect",
  "manage.load",
  "manage.save",
  "manage.delete",
  "monitor.connect",
  "monitor.control",
] as const

export type ErrorOperation = (typeof errorOperations)[number]

export type LocalizedErrorState =
  | { readonly kind: "api"; readonly operation: ErrorOperation; readonly reason: unknown }
  | string
  | null

class UnexpectedErrorOperationError extends Error {
  public readonly name = "UnexpectedErrorOperationError"

  public constructor() {
    super("Unexpected localized error operation")
  }
}

function assertNever(_operation: never): never {
  throw new UnexpectedErrorOperationError()
}

function operationFallback(
  operation: ErrorOperation,
  locale: SupportedLocale,
): string {
  const localeResources = resources[locale]
  switch (operation) {
    case "auth.login":
      return localeResources.auth.errors.login
    case "setup.load":
      return localeResources.setup.errors.load
    case "setup.save":
      return localeResources.setup.errors.save
    case "setup.install":
      return localeResources.setup.errors.install
    case "setup.pull":
      return localeResources.setup.errors.pull
    case "setup.complete":
      return localeResources.setup.errors.complete
    case "chat.load":
      return localeResources.chat.errors.load
    case "chat.send":
      return localeResources.chat.errors.send
    case "chat.connect":
      return localeResources.chat.errors.connect
    case "manage.load":
      return localeResources.manage.errors.load
    case "manage.save":
      return localeResources.manage.errors.save
    case "manage.delete":
      return localeResources.manage.errors.delete
    case "monitor.connect":
      return localeResources.monitor.errors.connect
    case "monitor.control":
      return localeResources.monitor.errors.control
    default:
      return assertNever(operation)
  }
}

export function localizeApiError(
  reason: unknown,
  operation: ErrorOperation,
  locale: SupportedLocale,
): string {
  if (reason instanceof ApiError && reason.validationDetails.length > 0) {
    return localizeValidationDetails(reason.validationDetails, locale)
  }
  return localizeBackendDetail(
    reason instanceof ApiError ? reason.message : null,
    operation,
    locale,
  )
}

function validationField(field: string, locale: SupportedLocale): string {
  const fields = resources[locale].manage.apiValidation.fields
  switch (field) {
    case "provider_id": return fields.providerId
    case "api_base": return fields.apiBase
    case "api_key": return fields.apiKey
    case "display_name": return fields.displayName
    case "test_model": return fields.testModel
    default: return field
  }
}

function validationMessage(detail: ApiValidationDetail, locale: SupportedLocale): string {
  const messages = resources[locale].manage.apiValidation.messages
  switch (detail.type) {
    case "missing": return messages.missing
    case "string_pattern_mismatch": return messages.pattern
    case "string_too_long": return messages.tooLong
    case "url_parsing": return messages.url
    default: return messages.invalid
  }
}

function localizeValidationDetails(
  details: readonly ApiValidationDetail[],
  locale: SupportedLocale,
): string {
  const copy = resources[locale].manage.apiValidation
  return details.map((detail) => {
    const rawField = detail.loc?.at(-1)
    const field = typeof rawField === "string" ? validationField(rawField, locale) : null
    const message = validationMessage(detail, locale)
    return field === null ? message : `${field}${copy.fieldSeparator}${message}`
  }).join(copy.detailSeparator)
}

export function describeApiError(reason: unknown, operation: ErrorOperation): Exclude<LocalizedErrorState, string | null> {
  return { kind: "api", operation, reason }
}

export function resolveLocalizedError(error: LocalizedErrorState, locale: SupportedLocale): string | null {
  if (error === null || typeof error === "string") return error
  return localizeApiError(error.reason, error.operation, locale)
}

export function localizeBackendDetail(
  detail: string | null,
  operation: ErrorOperation,
  locale: SupportedLocale,
): string {
  if (locale === "zh-CN" && detail !== null && detail.length > 0) return detail
  return operationFallback(operation, locale)
}

export function localizeSocketError(
  error: ChatSocketErrorEvent,
  operation: ErrorOperation,
  locale: SupportedLocale,
): string {
  return localizeBackendDetail(error.detail, operation, locale)
}
