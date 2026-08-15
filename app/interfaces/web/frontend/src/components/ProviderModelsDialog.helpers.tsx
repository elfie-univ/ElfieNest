import { useTranslation } from "react-i18next"

import type { ProviderModel, ProviderModelDraft } from "../api/owner-providers"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select"

export type EditableModel = {
  original_id: string
  id: string
  display_name: string
  canonical_model_id: string | null
  context_window_tokens: number | null
  max_output_tokens: number | null
  supports_tools: boolean | null
  supports_vision: boolean | null
  supports_reasoning: boolean | null
  supports_structured_output: boolean | null | undefined
  request_profile_id: string | undefined
  request_profile_version: number | undefined
  hidden: boolean
}

export function toEditableModels(models: readonly ProviderModel[]): EditableModel[] {
  return models.map(toEditableModel)
}

export function toEditableModel(model: ProviderModel): EditableModel {
  return {
    original_id: model.id,
    id: model.id,
    display_name: model.display_name,
    canonical_model_id: model.canonical_model_id,
    context_window_tokens: model.context_window_tokens,
    max_output_tokens: model.max_output_tokens,
    supports_tools: model.supports_tools,
    supports_vision: model.supports_vision,
    supports_reasoning: model.supports_reasoning,
    supports_structured_output: model.supports_structured_output,
    request_profile_id: model.request_profile_id,
    request_profile_version: model.request_profile_version,
    hidden: model.hidden,
  }
}

export function toModelDraft(model: EditableModel): ProviderModelDraft {
  const optionalFields: {
    supports_structured_output?: boolean | null
    request_profile_id?: string
    request_profile_version?: number
  } = {}
  if (model.supports_structured_output !== undefined) {
    optionalFields.supports_structured_output = model.supports_structured_output
  }
  if (model.request_profile_id !== undefined) {
    optionalFields.request_profile_id = model.request_profile_id
  }
  if (model.request_profile_version !== undefined) {
    optionalFields.request_profile_version = model.request_profile_version
  }
  return {
    original_id: model.original_id,
    id: model.id.trim(),
    display_name: model.display_name.trim(),
    canonical_model_id: model.canonical_model_id,
    context_window_tokens: model.context_window_tokens,
    max_output_tokens: model.max_output_tokens,
    supports_tools: model.supports_tools,
    supports_vision: model.supports_vision,
    supports_reasoning: model.supports_reasoning,
    hidden: model.hidden,
    ...optionalFields,
  }
}

export function parseNullableInteger(value: string): number | null {
  if (!value.trim()) return null
  const parsed = Number(value)
  return Number.isInteger(parsed) ? parsed : null
}

export function formatTokens(value: number | null): string {
  if (value === null) return "?"
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value % 1_000_000 === 0 ? 0 : 1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(value % 1_000 === 0 ? 0 : 1)}K`
  return String(value)
}

type CapabilityCellProps = {
  readonly label: string
  readonly value: boolean | null
  readonly onChange: ((value: boolean | null) => void) | undefined
}

const CAPABILITY_OPTIONS = [
  { value: "true", mark: "✅" },
  { value: "false", mark: "❌" },
  { value: "unknown", mark: "?" },
] as const

type CapabilitySelection = typeof CAPABILITY_OPTIONS[number]["value"]

export function CapabilityCell({ label, value, onChange }: CapabilityCellProps) {
  const mark = capabilityMark(value)
  return onChange
    ? <Select onValueChange={(nextValue) => { onChange(parseCapabilitySelection(nextValue)) }} value={capabilitySelection(value)}>
      <SelectTrigger aria-label={label} className="provider-model-capability-select" size="sm"><SelectValue>{mark}</SelectValue></SelectTrigger>
      <SelectContent position="popper">
        {CAPABILITY_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.mark}</SelectItem>)}
      </SelectContent>
    </Select>
    : <span className="provider-model-capability" title={`${label}: ${mark}`}><strong>{mark}</strong></span>
}

function capabilitySelection(value: boolean | null): CapabilitySelection {
  if (value === true) return "true"
  if (value === false) return "false"
  return "unknown"
}

function capabilityMark(value: boolean | null): string {
  return value === true ? "✅" : value === false ? "❌" : "?"
}

function parseCapabilitySelection(value: string): boolean | null {
  switch (value) {
    case "true": return true
    case "false": return false
    case "unknown": return null
    default: return null
  }
}

export function ModelVerification({ model }: { readonly model: ProviderModel }) {
  const { t } = useTranslation("manage")
  const status = model.verification.availability_status
    ?? (model.verification.status === "passed"
      ? "available"
      : model.verification.status === "failed"
        ? "failed"
        : !model.available
          ? "unavailable"
          : "never")
  const label = status === "available"
    ? t("providerModels.labels.available")
    : status === "degraded"
      ? t("providerModels.labels.degraded")
    : status === "failed" || status === "unavailable"
      ? t("providerModels.labels.unavailable")
      : t("providerModels.labels.neverVerified")
  return <span className={`provider-model-status provider-model-status--${status}`}>
    <strong>{label}</strong>
    <span aria-hidden="true" className="provider-model-status-separator">/</span>
    {model.verification.latency_ms === null ? <small>?</small> : <small>{Math.round(model.verification.latency_ms)}ms</small>}
  </span>
}

export function sourceKey(source: string): "providerModels.sources.bundled" | "providerModels.sources.manual" | "providerModels.sources.official" | "providerModels.sources.remote" {
  if (source === "official") return "providerModels.sources.official"
  if (source === "remote_catalog") return "providerModels.sources.remote"
  if (source === "bundled_catalog") return "providerModels.sources.bundled"
  return "providerModels.sources.manual"
}
