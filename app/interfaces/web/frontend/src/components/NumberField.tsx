import { useEffect, useId, useState } from "react"

import { Icon } from "./Icon"
import "./manager-controls.css"

type NumberFieldProps = {
  readonly disabled?: boolean
  readonly error?: string
  readonly hint?: string
  readonly label: string
  readonly max: number
  readonly min: number
  readonly onChange: (value: number) => void
  readonly step?: number
  readonly value: number
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function NumberField({
  disabled = false,
  error,
  hint,
  label,
  max,
  min,
  onChange,
  step = 1,
  value,
}: NumberFieldProps) {
  const id = useId()
  const [draft, setDraft] = useState(String(value))
  useEffect(() => setDraft(String(value)), [value])

  const commitDraft = (): void => {
    const parsed = Number(draft)
    if (!Number.isFinite(parsed)) {
      setDraft(String(value))
      return
    }
    const next = clamp(parsed, min, max)
    setDraft(String(next))
    onChange(next)
  }
  const stepValue = (direction: -1 | 1): void => {
    const next = clamp(value + direction * step, min, max)
    setDraft(String(next))
    onChange(next)
  }
  const descriptionId = error || hint ? `${id}-description` : undefined
  return <div className="manager-field manager-number-field">
    <label htmlFor={id}>{label}</label>
    <div className="manager-number-field__control">
      <button aria-label={`减少${label}`} disabled={disabled || value <= min} onClick={() => stepValue(-1)} type="button">
        <Icon name="minus" size={16} />
      </button>
      <input
        aria-describedby={descriptionId}
        aria-invalid={error ? true : undefined}
        disabled={disabled}
        id={id}
        inputMode="numeric"
        onBlur={commitDraft}
        onChange={(event) => setDraft(event.target.value)}
        type="text"
        value={draft}
      />
      <button aria-label={`增加${label}`} disabled={disabled || value >= max} onClick={() => stepValue(1)} type="button">
        <Icon name="plus" size={16} />
      </button>
    </div>
    {error ? <small className="manager-field__error" id={descriptionId}>{error}</small> : null}
    {!error && hint ? <small id={descriptionId}>{hint}</small> : null}
  </div>
}
