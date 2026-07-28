import { useId } from "react"

import { Checkbox } from "@/components/ui/checkbox"
import "./manage-controls.css"

type CheckboxFieldProps = {
  readonly checked: boolean
  readonly disabled?: boolean
  readonly hint?: string
  readonly label: string
  readonly onChange: (checked: boolean) => void
}

export function CheckboxField({ checked, disabled = false, hint, label, onChange }: CheckboxFieldProps) {
  const id = useId()
  return <div className="manage-checkbox-field">
    <Checkbox aria-label={label} checked={checked} className="size-5 border-2 border-[var(--border)] bg-[var(--surface-field)] data-checked:border-[var(--accent)] data-checked:bg-[var(--accent)]" disabled={disabled} id={id} onCheckedChange={(next) => onChange(next === true)} />
    <label htmlFor={id}>
      <span>{label}</span>
      {hint ? <small>{hint}</small> : null}
    </label>
  </div>
}
