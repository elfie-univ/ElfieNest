import { useTranslation } from "react-i18next"

import type { CareSettings } from "./model"

type ProfileCareSettingsProps = {
  readonly settings: CareSettings
}

export function ProfileCareSettings({ settings }: ProfileCareSettingsProps) {
  const { t } = useTranslation("chat")
  const food = settings.food
  return (
    <div className="profile-private-care">
      <dl className="profile-private-care__summary">
        <div>
          <dt>{t("profile.private.food.selected")}</dt>
          <dd>{food.selectedLabel || food.selectedId || t("profile.private.food.unconfigured")}</dd>
        </div>
      </dl>
      {food.options.length > 0 ? (
        <ul aria-label={t("profile.private.food.options")} className="profile-private-care__options">
          {food.options.map((option) => <li className={option.id === food.selectedId ? "profile-private-care__option profile-private-care__option--selected" : "profile-private-care__option"} key={option.id}>{option.label}</li>)}
        </ul>
      ) : <p className="profile-private-module__empty">{t("profile.private.food.noOptions")}</p>}
      {food.unavailable ? <p className="profile-private-care__notice">{t("profile.private.food.unavailable")}</p> : null}
    </div>
  )
}
