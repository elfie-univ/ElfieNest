import { Button } from "@/components/ui/button"
import type { ExecutionProfile } from "../api/owner-foods"
import { NumberField } from "./NumberField"
import { SelectField, type SelectFieldOption, type SelectOption } from "./SelectField"
import { TextField } from "./TextField"

const NONE_MODEL = "__none__"
const REASONING_OPTIONS: readonly SelectOption[] = [
  { label: "关闭", value: "off" },
  { label: "低", value: "low" },
  { label: "均衡", value: "balanced" },
  { label: "深度", value: "deep" },
  { label: "最大", value: "max" },
  { label: "校验", value: "verify" },
]

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
  const value = profile?.model || NONE_MODEL
  const options = withCurrentModel(modelOptions, profile?.model, optional)
  const update = (patch: Partial<ExecutionProfile>): void => {
    onChange({ ...(profile ?? defaultProfile()), ...patch })
  }
  return <fieldset className="food-profile-fields">
    <legend>{label}</legend>
    <SelectField
      label={`${label}模型`}
      onValueChange={(model) => onChange(model === NONE_MODEL ? null : { ...(profile ?? defaultProfile()), model })}
      options={options}
      value={value}
    />
    {profile ? <>
      <SelectField
        label={`${label}推理档位`}
        onValueChange={(reasoning_profile) => update({ reasoning_profile })}
        options={REASONING_OPTIONS}
        value={profile.reasoning_profile}
      />
      <div className="food-profile-fields__numbers">
        <NumberField label={`${label}最大 Tokens`} max={128000} min={1} onChange={(max_tokens) => update({ max_tokens })} step={100} value={profile.max_tokens} />
        <NumberField label={`${label}温度`} max={2} min={0} onChange={(temperature) => update({ temperature })} step={0.1} value={profile.temperature} />
      </div>
      <TextField
        hint="多个工具用逗号分隔；留空表示不额外启用工具。"
        label={`${label}工具`}
        onChange={(tools) => update({ tools: tools.split(",").map((item) => item.trim()).filter(Boolean) })}
        value={profile.tools.join(", ")}
      />
      <ProviderOptionFields label={label} onChange={(provider_options) => update({ provider_options })} options={profile.provider_options} />
    </> : <p className="form-hint">该角色当前未配置。</p>}
  </fieldset>
}

function withCurrentModel(
  options: readonly SelectFieldOption[],
  current: string | undefined,
  optional: boolean,
): readonly SelectFieldOption[] {
  const result: SelectFieldOption[] = optional ? [{ label: "未配置", value: NONE_MODEL }] : []
  if (current && !hasModelOption(options, current)) {
    result.push({ label: `${current}（当前）`, value: current })
  }
  result.push(...options)
  if (!optional && result.length === 0) result.push({ label: "未配置", value: NONE_MODEL, disabled: true })
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
  const entries = Object.entries(options)
  const updateEntry = (index: number, nextKey: string, nextValue: string): void => {
    const nextEntries: [string, unknown][] = entries.map(([key, value], entryIndex) => entryIndex === index
      ? [nextKey, nextValue]
      : [key, value])
    onChange(Object.fromEntries(nextEntries.filter(([key]) => key.trim().length > 0)))
  }
  return <div className="food-provider-options">
    <div className="food-provider-options__heading"><span>Provider 参数</span><Button variant="outline"
      onClick={() => onChange({ ...options, [`option_${entries.length + 1}`]: "" })}
      type="button"
    >添加参数</Button></div>
    {entries.length === 0 ? <p className="form-hint">没有额外 Provider 参数。</p> : entries.map(([key, value], index) => <div className="food-provider-options__row" key={`${key}-${index}`}>
      <TextField label={`${label}参数名 ${index + 1}`} onChange={(nextKey) => updateEntry(index, nextKey, String(value))} value={key} />
      <TextField label={`${label}参数值 ${index + 1}`} onChange={(nextValue) => updateEntry(index, key, nextValue)} value={String(value)} />
      <Button variant="outline" onClick={() => onChange(Object.fromEntries(entries.filter((_, entryIndex) => entryIndex !== index)))} type="button">删除</Button>
    </div>)}
  </div>
}
