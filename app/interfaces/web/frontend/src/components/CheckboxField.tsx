import * as Checkbox from "@radix-ui/react-checkbox"
import { useId } from "react"

import { Icon } from "./Icon"
import "./manager-controls.css"

type CheckboxFieldProps = {
  readonly checked: boolean
  readonly disabled?: boolean
  readonly hint?: string
  readonly label: string
  readonly onChange: (checked: boolean) => void
}

export function CheckboxField({ checked, disabled = false, hint, label, onChange }: CheckboxFieldProps) {
  const id = useId()
  return <div className="manager-checkbox-field">
    <Checkbox.Root aria-label={label} checked={checked} disabled={disabled} id={id} onCheckedChange={(next) => onChange(next === true)}>
      <Checkbox.Indicator><Icon name="check" size={15} /></Checkbox.Indicator>
    </Checkbox.Root>
    <label htmlFor={id}>
      <span>{label}</span>
      {hint ? <small>{hint}</small> : null}
    </label>
  </div>
}
