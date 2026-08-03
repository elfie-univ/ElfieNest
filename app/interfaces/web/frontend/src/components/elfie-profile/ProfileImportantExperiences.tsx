import { useTranslation } from "react-i18next"

import type { ImportantExperiences } from "./model"

type ProfileImportantExperiencesProps = {
  readonly experiences: ImportantExperiences
  readonly status: "ready" | "empty" | "unavailable"
}

export function ProfileImportantExperiences({ experiences, status }: ProfileImportantExperiencesProps) {
  const { t } = useTranslation("chat")
  if (status !== "ready" || experiences.entries.length === 0) {
    return <p className="profile-private-module__empty">{t("profile.private.experiences.empty")}</p>
  }
  const entries = [...experiences.entries].sort((left, right) =>
    right.occurredAt > left.occurredAt ? 1 : right.occurredAt < left.occurredAt ? -1 : right.id > left.id ? 1 : right.id < left.id ? -1 : 0,
  )
  return (
    <ol aria-label={t("profile.private.experiences.timeline")} className="profile-private-experiences">
      {entries.map((entry) => (
        <li className="profile-private-experiences__item" key={entry.id}>
          <time dateTime={entry.occurredAt}>{entry.occurredAt.slice(0, 10)}</time>
          <div className="profile-private-experiences__card">
            <strong>{entry.title}</strong>
            <p>{entry.changed}</p>
            {entry.people.length > 0 ? <small>{t("profile.private.experiences.people", { people: entry.people.join(t("profile.private.experiences.peopleSeparator")) })}</small> : null}
          </div>
        </li>
      ))}
    </ol>
  )
}
