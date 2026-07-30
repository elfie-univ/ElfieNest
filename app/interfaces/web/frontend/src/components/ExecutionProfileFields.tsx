import { Button } from "@/components/ui/button"
import { useTranslation } from "react-i18next"
import type { ExecutionProfile } from "../api/owner-foods"
import { NumberField } from "./NumberField"
import { SelectField, type SelectFieldOption, type SelectOption } from "./SelectField"
import { TextField } from "./TextField"

const NONE_MODEL = "__none__"
const REASONING_VALUES = ["off", "low", "balanced", "deep", "max", "verify"] as const

type ExecutionProfileFieldsProps = {
  readonly label: string
  readonly modelOptions: readonly SelectFieldOption[]
  readonly onChange: (profile: ExecutionProfile | null) => void
  readonly optional?: boolean
  readonly profile: ExecutionProfile | null
}

function defaultProfile(model = ""): ExecutionProfile {
  return {
    model,
    reasoning_profile: "balanced",
    max_tokens: 1500,
    temperature: 0.7,
    tools: [],
    provider_options: {},
  }
}

export function ExecutionProfileFields({
  label,
  modelOptions,
  onChange,
  optional = false,
  profile,
}: ExecutionProfileFieldsProps) {
  const { t } = useTranslation("manage")
  const reasoningOptions: readonly SelectOption[] = REASONING_VALUES.map((reasoning) => ({ label: t(`executionProfile.reasoning.${reasoning}`), value: reasoning }))
  const value = profile?.model || NONE_MODEL
  const options = withCurrentModel(modelOptions, profile?.model, optional, t("executionProfile.notConfigured"), (model) => t("executionProfile.fields.currentModel", { model }))
  const update = (patch: Partial<ExecutionProfile>): void => {
    onChange({ ...(profile ?? defaultProfile()), ...patch })
  }
  return <fieldset className="food-profile-fields">
    <legend>{label}</legend>
    <SelectField
      label={t("executionProfile.fields.model", { label })}
      onValueChange={(model) => onChange(model === NONE_MODEL ? null : { ...(profile ?? defaultProfile()), model })}
      options={options}
      value={value}
    />
    {profile ? <>
      <SelectField
        label={t("executionProfile.fields.reasoning", { label })}
        onValueChange={(reasoning_profile) => update({ reasoning_profile })}
        options={reasoningOptions}
        value={profile.reasoning_profile}
      />
      <div className="food-profile-fields__numbers">
        <NumberField label={t("executionProfile.fields.maxTokens", { label })} max={128000} min={1} onChange={(max_tokens) => update({ max_tokens })} step={100} value={profile.max_tokens} />
        <NumberField label={t("executionProfile.fields.temperature", { label })} max={2} min={0} onChange={(temperature) => update({ temperature })} step={0.1} value={profile.temperature} />
      </div>
      <TextField
        hint={t("executionProfile.toolsHint")}
        label={t("executionProfile.fields.tools", { label })}
        onChange={(tools) => update({ tools: tools.split(",").map((item) => item.trim()).filter(Boolean) })}
        value={profile.tools.join(", ")}
      />
      <ProviderOptionFields label={label} onChange={(provider_options) => update({ provider_options })} options={profile.provider_options} />
    </> : <p className="form-hint">{t("executionProfile.notConfiguredRole")}</p>}
  </fieldset>
}

function withCurrentModel(
  options: readonly SelectFieldOption[],
  current: string | undefined,
  optional: boolean,
  notConfiguredLabel: string,
  currentModelLabel: (model: string) => string,
): readonly SelectFieldOption[] {
  const result: SelectFieldOption[] = optional ? [{ label: notConfiguredLabel, value: NONE_MODEL }] : []
  if (current && !hasModelOption(options, current)) {
    result.push({ label: currentModelLabel(current), value: current })
  }
  result.push(...options)
  if (!optional && result.length === 0) result.push({ label: notConfiguredLabel, value: NONE_MODEL, disabled: true })
  return result
}

function hasModelOption(options: readonly SelectFieldOption[], value: string): boolean {
  return options.some((option) => "options" in option
    ? option.options.some((nested) => nested.value === value)
    : option.value === value)
}

function ProviderOptionFields({ label, onChange, options }: {
  readonly label: string
  readonly onChange: (value: Readonly<Record<string, unknown>>) => void
  readonly options: Readonly<Record<string, unknown>>
}) {
  const { t } = useTranslation("manage")
  const entries = Object.entries(options)
  const updateEntry = (index: number, nextKey: string, nextValue: string): void => {
    const nextEntries: [string, unknown][] = entries.map(([key, value], entryIndex) => entryIndex === index
      ? [nextKey, nextValue]
      : [key, value])
    onChange(Object.fromEntries(nextEntries.filter(([key]) => key.trim().length > 0)))
  }
  return <div className="food-provider-options">
    <div className="food-provider-options__heading"><span>{t("executionProfile.fields.providerOptions")}</span><Button variant="outline"
      onClick={() => onChange({ ...options, [`option_${entries.length + 1}`]: "" })}
      type="button"
    >{t("executionProfile.actions.addOption")}</Button></div>
    {entries.length === 0 ? <p className="form-hint">{t("executionProfile.noOptions")}</p> : entries.map(([key, value], index) => <div className="food-provider-options__row" key={`${key}-${index}`}>
      <TextField label={t("executionProfile.fields.optionKey", { label, number: index + 1 })} onChange={(nextKey) => updateEntry(index, nextKey, String(value))} value={key} />
      <TextField label={t("executionProfile.fields.optionValue", { label, number: index + 1 })} onChange={(nextValue) => updateEntry(index, key, nextValue)} value={String(value)} />
      <Button variant="outline" onClick={() => onChange(Object.fromEntries(entries.filter((_, entryIndex) => entryIndex !== index)))} type="button">{t("executionProfile.actions.delete")}</Button>
    </div>)}
  </div>
}
