import * as Select from "@radix-ui/react-select"

import { Icon } from "./Icon"
import "./select-field.css"

export type SelectOption = {
  readonly disabled?: boolean
  readonly label: string
  readonly value: string
}

type SelectFieldProps = {
  readonly ariaLabel: string
  readonly disabled?: boolean
  readonly onValueChange: (value: string) => void
  readonly options: readonly SelectOption[]
  readonly placeholder?: string
  readonly value: string
}

export function SelectField({
  ariaLabel,
  disabled = false,
  onValueChange,
  options,
  placeholder,
  value,
}: SelectFieldProps) {
  const selectedOption = options.find((option) => option.value === value)

  return <Select.Root disabled={disabled} onValueChange={onValueChange} value={value}>
    <Select.Trigger aria-label={ariaLabel} className="select-field__trigger">
      <Select.Value placeholder={placeholder}>{selectedOption?.label}</Select.Value>
      <Select.Icon asChild><Icon name="chevron-down" size={16} /></Select.Icon>
    </Select.Trigger>
    <Select.Portal>
      <Select.Content className="select-field__content" position="popper" sideOffset={6}>
        <Select.Viewport className="select-field__viewport">
          {options.map((option) => <Select.Item className="select-field__item" disabled={option.disabled ?? false} key={option.value} value={option.value}>
            <Select.ItemText>{option.label}</Select.ItemText>
            <Select.ItemIndicator className="select-field__indicator"><Icon name="check" size={15} /></Select.ItemIndicator>
          </Select.Item>)}
        </Select.Viewport>
      </Select.Content>
    </Select.Portal>
  </Select.Root>
}
