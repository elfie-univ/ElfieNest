import { useId } from "react"
import { useTranslation } from "react-i18next"

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
  const { t } = useTranslation("chat")
  return (
    <div className="profile-private-module__memory">
      <p className="profile-private-module__count">{t("profile.private.experienceCount", { count: module.experienceCount })}</p>
      {module.topics.length > 0 ? (
        <ul className="profile-private-module__topics" aria-label={t("profile.private.memoryTopics")}>
          {module.topics.map((topic) => (
            <li key={topic.label}>
              <span>{topic.label}</span>
              <small>{t("profile.private.topicCount", { count: topic.count })}</small>
            </li>
          ))}
        </ul>
      ) : (
        <p className="profile-private-module__empty">{t("profile.private.noTopics")}</p>
      )}
    </div>
  )
}

export function TimelineModuleBody({ module }: { readonly module: TimelineModule }) {
  const { t } = useTranslation("chat")
  if (module.entries.length === 0) {
    return <p className="profile-private-module__empty">{t("profile.private.noTimeline")}</p>
  }
  return (
    <ol className="profile-private-module__timeline" aria-label={t("profile.private.timeline")}>
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
  const { t } = useTranslation("chat")
  const foodId = useId()
  const fallbackId = useId()
  return (
    <div className="profile-private-module__config">
      <MockSelect
        id={foodId}
        label={t("profile.private.primaryFood")}
        options={module.food.allowed}
        value={module.food.selected}
      />
      <MockSelect
        id={fallbackId}
        label={t("profile.private.fallbackFood")}
        options={module.food.allowed}
        value={module.food.fallback}
      />
      <dl className="profile-private-module__config-notes">
        <div><dt>{t("profile.private.allowedFood")}</dt><dd>{module.food.allowed.join(t("profile.private.foodSeparator"))}</dd></div>
      </dl>
      <p className="profile-private-module__notice">{t("profile.private.foodNotice")}</p>
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
