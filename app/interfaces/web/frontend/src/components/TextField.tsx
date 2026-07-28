import { useId, type HTMLInputAutoCompleteAttribute, type HTMLInputTypeAttribute } from "react"

import { Input } from "@/components/ui/input"
import { FieldRow } from "./FieldRow"
import "./manage-controls.css"

type TextFieldProps = {
  readonly autoComplete?: HTMLInputAutoCompleteAttribute
  readonly autoFocus?: boolean
  readonly disabled?: boolean
  readonly error?: string
  readonly hint?: string
  readonly label: string
  readonly minLength?: number
  readonly name?: string
  readonly onChange: (value: string) => void
  readonly placeholder?: string
  readonly readOnly?: boolean
  readonly required?: boolean
  readonly type?: HTMLInputTypeAttribute
  readonly value: string
}

export function TextField({
  autoComplete,
  autoFocus = false,
  disabled = false,
  error,
  hint,
  label,
  minLength,
  name,
  onChange,
  placeholder,
  readOnly = false,
  required = false,
  type = "text",
  value,
}: TextFieldProps) {
  const id = useId()
  return <FieldRow
    control={<Input
      autoComplete={autoComplete}
      autoFocus={autoFocus}
      disabled={disabled}
      id={id}
      minLength={minLength}
      name={name}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      readOnly={readOnly}
      required={required}
      type={type}
      value={value}
    />}
    error={error}
    hint={hint}
    inputId={id}
    label={label}
  />
}
