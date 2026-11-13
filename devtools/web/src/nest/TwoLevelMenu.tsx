import { Cascader } from "antd";
import { useRef } from "react";

type Option = { value: string; label: string; disabled?: boolean };
export type MenuGroup = { label: string; options: readonly Option[] };
type Props = {
  label: string;
  groups: readonly MenuGroup[];
  value: string;
  placeholder?: string;
  disabled?: boolean;
  onSelect: (value: string) => void;
};

export function cascadeOptions(groups: readonly MenuGroup[]) {
  return groups.filter(group => group.options.length > 0).map(group => ({
    value: group.label, label: group.label, children: [...group.options],
  }));
}

export function cascadePath(groups: readonly MenuGroup[], value: string, previous: string[] = []): string[] {
  const group = groups.find(item => item.options.some(option => option.value === value));
  const next = group ? [group.label, value] : [];
  // rc-cascader resets its expanded category when the controlled path identity
  // changes. Live catalogs must not reset a category the user just opened.
  return next.length === previous.length && next.every((part,index)=>part === previous[index]) ? previous : next;
}

export function selectCascadeOption(groups: readonly MenuGroup[], path: readonly (string | number)[], onSelect: (value: string) => void) {
  if (path.length !== 2) return;
  const option = groups.find(group => group.label === path[0])?.options.find(item => item.value === path[1]);
  if (option && !option.disabled) onSelect(option.value);
}

export function TwoLevelMenu({ label, groups, value, placeholder = "请选择", disabled = false, onSelect }: Props) {
  const selectedPath = useRef<string[]>([]);
  selectedPath.current = cascadePath(groups, value, selectedPath.current);
  return <Cascader size="small" aria-label={label} className="nest-cascade-select"
    classNames={{ popup: { root: "nest-cascade-popup" } }} placement="topLeft"
    options={cascadeOptions(groups)} value={selectedPath.current}
    placeholder={placeholder} disabled={disabled} allowClear={false}
    expandTrigger="click" changeOnSelect={false}
    displayRender={labels => labels.at(-1)}
    showSearch={{ filter: (input, path) => path.some(option => String(option.label).toLowerCase().includes(input.toLowerCase())) }}
    onChange={path => selectCascadeOption(groups, path, onSelect)} />;
}
