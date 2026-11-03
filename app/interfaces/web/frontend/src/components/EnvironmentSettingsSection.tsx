import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { environmentSettings, updateEnvironmentSettings, type EnvironmentSchedule, type EnvironmentSettings } from "../api/admin/settings"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"
import { Button } from "./ui/button"

export function EnvironmentSettingsSection({ csrfToken }: { readonly csrfToken: string }) {
  const { t, i18n } = useTranslation("manage")
  const key = "systemSettings.environment"
  const [saved, setSaved] = useState<EnvironmentSettings | null>(null)
  const [draft, setDraft] = useState<EnvironmentSchedule | null>(null)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [locationError, setLocationError] = useState("")
  const [saving, setSaving] = useState(false)
  const [locating, setLocating] = useState(false)
  const [savedNotice, setSavedNotice] = useState(false)
  useEffect(() => {
    let live = true
    const load = async () => {
      try {
        const value = await environmentSettings()
        if (!live) return
        setSaved(value)
        setDraft(current => current ?? value.settings)
        setError(null)
      } catch (reason) {
        if (live) setError(describeApiError(reason, "manage.load"))
      }
    }
    void load()
    const timer = window.setInterval(() => { void load() }, 60_000)
    return () => { live = false; window.clearInterval(timer) }
  }, [])

  function locate() {
    setLocationError("")
    setSavedNotice(false)
    if (!navigator.geolocation) { setLocationError(t(`${key}.locationUnavailable`)); return }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(position => {
      setDraft(current => current === null ? null : { ...current,
        latitude: Number(position.coords.latitude.toFixed(2)), longitude: Number(position.coords.longitude.toFixed(2)) })
      setLocating(false)
    }, () => { setLocating(false); setLocationError(t(`${key}.locationUnavailable`)) },
    { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 })
  }

  async function save() {
    if (draft === null) return
    setSaving(true)
    setSavedNotice(false)
    try {
      const value = await updateEnvironmentSettings(draft, csrfToken)
      setSaved(value); setDraft(value.settings); setError(null); setSavedNotice(true)
    } catch (reason) { setError(describeApiError(reason, "manage.save")) }
    finally { setSaving(false) }
  }

  const local = draft?.daylight_source === "local"
  const matchesSavedLocation = saved?.settings.daylight_source === "local" && saved.settings.latitude === draft?.latitude && saved.settings.longitude === draft?.longitude
  const busy = saving || locating
  return <section className="system-advanced__group" aria-label={t(`${key}.title`)}>
    <h3>{t(`${key}.title`)}</h3>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, currentLocale(i18n)) ?? t("errors.save")} /> : null}
    {locationError ? <Notice kind="error" message={locationError} /> : null}
    {savedNotice ? <Notice kind="success" message={t(`${key}.saved`)} /> : null}
    {draft ? <>
      <SelectField label={t(`${key}.source`)} value={draft.daylight_source} disabled={busy}
        options={[{ value: "manual", label: t(`${key}.manual`) }, { value: "local", label: t(`${key}.local`) }]}
        onValueChange={value => { if (value === "manual" || value === "local") { setDraft({ ...draft, daylight_source: value }); setSavedNotice(false) } }} />
      {local ? <>
        <Button type="button" disabled={busy} onClick={locate}>{t(`${key}.${locating ? "locating" : "useLocation"}`)}</Button>
        <p className="field-hint">{t(`${key}.locationHint`)}</p>
        {draft.latitude !== null && draft.longitude !== null ? <p>{t(`${key}.coordinates`, { latitude: draft.latitude, longitude: draft.longitude })}</p> : <Notice kind="info" message={t(`${key}.needsLocation`)} />}
      </> : null}
      <TextField label={t(`${key}.sunrise`)} type="time" value={local ? (matchesSavedLocation ? saved?.today.sunrise_time ?? "" : "") : draft.sunrise_time}
        readOnly={local} disabled={busy} hint={local ? t(`${key}.automaticHint`) : ""}
        onChange={value => setDraft({ ...draft, sunrise_time: value })} />
      <TextField label={t(`${key}.sunset`)} type="time" value={local ? (matchesSavedLocation ? saved?.today.sunset_time ?? "" : "") : draft.sunset_time}
        readOnly={local} disabled={busy} hint={local ? t(`${key}.automaticHint`) : ""}
        onChange={value => setDraft({ ...draft, sunset_time: value })} />
      <TextField label={t(`${key}.rest`)} type="time" value={draft.rest_time} disabled={busy}
        hint={t(`${key}.restHint`)} onChange={value => setDraft({ ...draft, rest_time: value })} />
      {saved ? <p className="field-hint">{t(`${key}.clock`, { date: saved.today.date, timezone: saved.today.timezone })}</p> : null}
      {local && matchesSavedLocation && saved?.today.condition !== "normal" ? <Notice kind="info" message={t(`${key}.${saved?.today.condition === "polar_day" ? "polarDay" : "polarNight"}`)} /> : null}
      <div className="system-advanced__actions"><Button type="button" disabled={busy || (local && draft.latitude === null)} onClick={() => { void save() }}>{t(`${key}.save`)}</Button></div>
    </> : !error ? <p>{t("systemSettings.loading")}</p> : null}
  </section>
}
