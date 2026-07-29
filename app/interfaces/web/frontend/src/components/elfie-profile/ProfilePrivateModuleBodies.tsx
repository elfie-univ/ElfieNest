import { useId } from "react"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

import type { PrivateCognition } from "./model"

type MemoryModule = PrivateCognition["modules"][0]
type TimelineModule = PrivateCognition["modules"][1]
type ConfigModule = PrivateCognition["modules"][5]

export function MemoryModuleBody({ module }: { readonly module: MemoryModule }) {
  return (
    <div className="profile-private-module__memory">
      <p className="profile-private-module__count">{module.experienceCount} 条经历</p>
      {module.topics.length > 0 ? (
        <ul className="profile-private-module__topics" aria-label="记忆主题">
          {module.topics.map((topic) => (
            <li key={topic.label}>
              <span>{topic.label}</span>
              <small>{topic.count} 次</small>
            </li>
          ))}
        </ul>
      ) : (
        <p className="profile-private-module__empty">尚未形成记忆主题。</p>
      )}
    </div>
  )
}

export function TimelineModuleBody({ module }: { readonly module: TimelineModule }) {
  if (module.entries.length === 0) {
    return <p className="profile-private-module__empty">还没有被标记为重要的经历。</p>
  }
  return (
    <ol className="profile-private-module__timeline" aria-label="重要经历时间线">
      {module.entries.map((entry) => (
        <li key={`${entry.date}-${entry.title}`}>
          <time dateTime={entry.date}>{entry.date}</time>
          <strong>{entry.title}</strong>
          <p>{entry.detail}</p>
        </li>
      ))}
    </ol>
  )
}

export function ConfigModuleBody({ module }: { readonly module: ConfigModule }) {
  const foodId = useId()
  const fallbackId = useId()
  return (
    <div className="profile-private-module__config">
      <MockSelect
        id={foodId}
        label="主粮"
        options={module.food.allowed}
        value={module.food.selected}
      />
      <MockSelect
        id={fallbackId}
        label="备用粮"
        options={module.food.allowed}
        value={module.food.fallback}
      />
      <dl className="profile-private-module__config-notes">
        <div><dt>可选粮食</dt><dd>{module.food.allowed.join("、")}</dd></div>
      </dl>
      <p className="profile-private-module__notice">可选粮食由管理员维护，此处不能增删。</p>
    </div>
  )
}

type MockSelectProps = {
  readonly id: string
  readonly label: string
  readonly options: readonly string[]
  readonly value: string
}

function MockSelect({ id, label, options, value }: MockSelectProps) {
  return (
    <div className="profile-private-module__field">
      <label htmlFor={id}>{label}</label>
      <Select defaultValue={value}>
        <SelectTrigger id={id} aria-label={label}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  )
}
