import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { ownerWrite } from "../../api/client"
import { SelectField } from "../SelectField"
import type { CareSettings } from "./model"

type ProfileCareSettingsProps = {
  readonly csrfToken?: string | undefined
  readonly elfieId?: string | undefined
  readonly onSaved?: (() => Promise<void>) | undefined
  readonly settings: CareSettings
}

export function ProfileCareSettings({ csrfToken, elfieId, onSaved, settings }: ProfileCareSettingsProps) {
  const { t } = useTranslation("chat")
  const food = settings.food
  const defaultFoodId = food.selectedId || food.options[0]?.id || ""
  const [selectedFoodId, setSelectedFoodId] = useState(defaultFoodId)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const editable = csrfToken !== undefined && elfieId !== undefined && onSaved !== undefined && food.options.length > 0

  useEffect(() => {
    setSelectedFoodId(defaultFoodId)
  }, [defaultFoodId])

  const save = async (): Promise<void> => {
    if (!editable || elfieId === undefined || csrfToken === undefined || onSaved === undefined || selectedFoodId === "") return
    setSaving(true)
    setError(null)
    try {
      await ownerWrite(
        `/api/user/elfies/${encodeURIComponent(elfieId)}/food-policy/`,
        "PUT",
        csrfToken,
        { main_food_id: selectedFoodId },
      )
      await onSaved()
    } catch (reason: unknown) {
      setError(reason instanceof Error && reason.message ? reason.message : t("profile.private.food.saveError"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="profile-private-care">
      {editable ? (
        <div className="profile-private-care__editor">
          <SelectField
            disabled={saving}
            label={t("profile.private.food.selected")}
            onValueChange={(value) => {
              setSelectedFoodId(value)
              setError(null)
            }}
            options={food.options.map((option) => ({ label: option.label, value: option.id }))}
            value={selectedFoodId}
          />
          <Button disabled={saving} onClick={() => { void save() }} type="button">
            {saving ? t("profile.private.food.saving") : t("profile.private.food.save")}
          </Button>
        </div>
      ) : <>
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
      </>}
      {error ? <p className="profile-private-care__notice" role="alert">{error}</p> : null}
      {food.unavailable ? <p className="profile-private-care__notice">{t("profile.private.food.unavailable")}</p> : null}
    </div>
  )
}
