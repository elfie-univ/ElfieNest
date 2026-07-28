import { useEffect, useId, useState } from "react"

import { Button } from "@/components/ui/button"
import { ButtonGroup } from "@/components/ui/button-group"
import { Input } from "@/components/ui/input"
import { FieldRow } from "./FieldRow"
import { Icon } from "./Icon"
import "./manage-controls.css"

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
  const descriptionId = error ? `${id}-error` : hint ? `${id}-hint` : undefined
  return <FieldRow
    control={<ButtonGroup className="number-stepper w-full">
      <Button aria-label={`减少${label}`} disabled={disabled || value <= min} onClick={() => stepValue(-1)} size="icon" type="button" variant="ghost">
        <Icon name="minus" size={16} />
      </Button>
      <Input
        aria-describedby={descriptionId}
        aria-invalid={error ? true : undefined}
        className="number-stepper__input text-center tabular-nums"
        disabled={disabled}
        id={id}
        inputMode="numeric"
        onBlur={commitDraft}
        onChange={(event) => setDraft(event.target.value)}
        type="text"
        value={draft}
      />
      <Button aria-label={`增加${label}`} disabled={disabled || value >= max} onClick={() => stepValue(1)} size="icon" type="button" variant="ghost">
        <Icon name="plus" size={16} />
      </Button>
    </ButtonGroup>}
    decorateControl={false}
    error={error}
    hint={hint}
    inputId={id}
    label={label}
  />
}
