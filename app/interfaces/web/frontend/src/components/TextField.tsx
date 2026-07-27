import { useId, type HTMLInputAutoCompleteAttribute, type HTMLInputTypeAttribute } from "react"

import "./manage-controls.css"

type TextFieldProps = {
  readonly autoComplete?: HTMLInputAutoCompleteAttribute
  readonly autoFocus?: boolean
  readonly disabled?: boolean
  readonly error?: string
  readonly hint?: string
  readonly label: string
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
  name,
  onChange,
  placeholder,
  readOnly = false,
  required = false,
  type = "text",
  value,
}: TextFieldProps) {
  const id = useId()
  const descriptionId = error || hint ? `${id}-description` : undefined
  return <label className="manage-field" htmlFor={id}>
    <span>{label}</span>
    <input
      aria-describedby={descriptionId}
      aria-invalid={error ? true : undefined}
      autoComplete={autoComplete}
      autoFocus={autoFocus}
      disabled={disabled}
      id={id}
      name={name}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      readOnly={readOnly}
      required={required}
      type={type}
      value={value}
    />
    {error ? <small className="manage-field__error" id={descriptionId}>{error}</small> : null}
    {!error && hint ? <small id={descriptionId}>{hint}</small> : null}
  </label>
}
