import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useId } from "react"

import { FieldRow } from "./FieldRow"

export type SelectOption = {
  readonly group?: string
  readonly disabled?: boolean
  readonly label: string
  readonly value: string
}
export type SelectOptionGroup = {
  readonly label: string
  readonly options: readonly SelectOption[]
}
export type SelectFieldOption = SelectOption | SelectOptionGroup

type SelectFieldProps = {
  readonly disabled?: boolean
  readonly label: string
  readonly onValueChange: (value: string) => void
  readonly options: readonly SelectFieldOption[]
  readonly placeholder?: string
  readonly value: string
}

export function SelectField({
  disabled = false,
  label,
  onValueChange,
  options,
  placeholder,
  value,
}: SelectFieldProps) {
  const id = useId()
  const selectedOption = flattenOptions(options).find((option) => option.value === value)

  return <FieldRow
    control={({ inputId, labelId }) => <Select disabled={disabled} onValueChange={onValueChange} value={value}>
      <SelectTrigger aria-labelledby={labelId} className="w-full bg-secondary" disabled={disabled} id={inputId}>
        <SelectValue placeholder={placeholder}>{selectedOption?.label}</SelectValue>
      </SelectTrigger>
      <SelectContent position="popper">
        {options.map((entry) => isOptionGroup(entry)
          ? <SelectGroup key={entry.label}>
            <SelectLabel>{entry.label}</SelectLabel>
            {entry.options.map((option) => <SelectItem disabled={option.disabled ?? false} key={option.value} value={option.value}>{option.label}</SelectItem>)}
          </SelectGroup>
          : <SelectItem disabled={entry.disabled ?? false} key={entry.value} value={entry.value}>{entry.label}</SelectItem>)}
      </SelectContent>
    </Select>}
    inputId={id}
    label={label}
  />
}

function isOptionGroup(entry: SelectFieldOption): entry is SelectOptionGroup {
  return "options" in entry
}

function flattenOptions(entries: readonly SelectFieldOption[]): readonly SelectOption[] {
  return entries.flatMap((entry) => isOptionGroup(entry) ? entry.options : [entry])
}
