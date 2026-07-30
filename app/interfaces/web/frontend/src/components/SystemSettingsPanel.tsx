import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { z } from "zod"

import { ownerRead, ownerWrite } from "../api/client"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { CheckboxField } from "./CheckboxField"
import { Notice } from "./Notice"
import { NumberField } from "./NumberField"
import { RefreshButton } from "./RefreshButton"

const EngineSchema = z.object({ tick_interval_sec: z.number(), max_elfies_per_room: z.number().nullable() })
const AdoptionSchema = z.object({ max_elfies_per_user: z.number(), allowed_species_ids: z.array(z.string()), personality_presets_enabled: z.record(z.string(), z.boolean()) })
const SecuritySchema = z.object({ session_ttl_days: z.number(), rate_limit: z.object({ max_attempts: z.number(), window_seconds: z.number() }) })
type EngineSettings = z.infer<typeof EngineSchema>
type AdoptionSettings = z.infer<typeof AdoptionSchema>
type SecuritySettings = z.infer<typeof SecuritySchema>
type SettingsSection = "adoption" | "engine" | "security"
type SettingsNotice = "adoptionSaved" | "engineSaved" | "securitySaved"
const SPECIES_OPTIONS = [{ id: "dog" }, { id: "fox" }] as const

export function SystemSettingsPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [engine, setEngine] = useState<EngineSettings | null>(null)
  const [adoption, setAdoption] = useState<AdoptionSettings | null>(null)
  const [security, setSecurity] = useState<SecuritySettings | null>(null)
  const [saving, setSaving] = useState<SettingsSection | null>(null)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<SettingsNotice | null>(null)

  const load = async (): Promise<void> => {
    try {
      const [loadedEngine, loadedAdoption, loadedSecurity] = await Promise.all([
        ownerRead("/api/owner/system/engine"),
        ownerRead("/api/owner/system/adoption"),
        ownerRead("/api/owner/system/security"),
      ])
      setEngine(EngineSchema.parse(loadedEngine))
      setAdoption(AdoptionSchema.parse(loadedAdoption))
      setSecurity(SecuritySchema.parse(loadedSecurity))
      setError(null)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.load"))
    }
  }
  useEffect(() => { void load() }, [])

  const save = async (section: SettingsSection, value: unknown, nextNotice: SettingsNotice): Promise<void> => {
    setSaving(section)
    try {
      await ownerWrite(`/api/owner/system/${section}`, "PUT", csrfToken, value)
      setNotice(nextNotice)
      setError(null)
      await load()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setSaving(null)
    }
  }

  return <section className="system-settings">
    <div className="manage-head"><p>{t("systemSettings.description")}</p><RefreshButton disabled={saving !== null} label={t("systemSettings.actions.refresh")} onClick={() => { void load() }} /></div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} /> : null}
    {notice ? <Notice message={t(`systemSettings.notices.${notice}`)} /> : null}
    {!engine && !adoption && !security && !error ? <p className="empty-state">{t("systemSettings.loading")}</p> : null}
    <div className="system-settings__grid">
      {engine ? <EngineCard disabled={saving !== null} onChange={setEngine} onSave={() => { void save("engine", engine, "engineSaved") }} value={engine} /> : null}
      {adoption ? <AdoptionCard disabled={saving !== null} onChange={setAdoption} onSave={() => { void save("adoption", adoption, "adoptionSaved") }} value={adoption} /> : null}
      {security ? <SecurityCard disabled={saving !== null} onChange={setSecurity} onSave={() => { void save("security", security, "securitySaved") }} value={security} /> : null}
    </div>
  </section>
}

function EngineCard({ disabled, onChange, onSave, value }: { readonly disabled: boolean; readonly onChange: (value: EngineSettings) => void; readonly onSave: () => void; readonly value: EngineSettings }) {
  const { t } = useTranslation("manage")
  const roomLimitEnabled = value.max_elfies_per_room !== null
  return <section className="system-setting-card">
    <div><h3>{t("systemSettings.engine.title")}</h3><p>{t("systemSettings.engine.description")}</p></div>
    <NumberField disabled={disabled} hint={t("systemSettings.engine.tickHint")} label={t("systemSettings.engine.tick")} max={3600} min={0.1} onChange={(tick) => onChange({ ...value, tick_interval_sec: tick })} step={0.1} value={value.tick_interval_sec} />
    <CheckboxField checked={roomLimitEnabled} disabled={disabled} hint={t("systemSettings.engine.roomLimitHint")} label={t("systemSettings.engine.roomLimit")} onChange={(checked) => onChange({ ...value, max_elfies_per_room: checked ? 1 : null })} />
    {roomLimitEnabled ? <NumberField disabled={disabled} hint={t("systemSettings.engine.maxPerRoomHint")} label={t("systemSettings.engine.maxPerRoom")} max={32} min={1} onChange={(limit) => onChange({ ...value, max_elfies_per_room: limit })} value={value.max_elfies_per_room ?? 1} /> : null}
    <Button disabled={disabled} onClick={onSave} type="button">{t("systemSettings.actions.saveEngine")}</Button>
  </section>
}

function AdoptionCard({ disabled, onChange, onSave, value }: { readonly disabled: boolean; readonly onChange: (value: AdoptionSettings) => void; readonly onSave: () => void; readonly value: AdoptionSettings }) {
  const { t } = useTranslation("manage")
  const toggleSpecies = (species: string, checked: boolean): void => onChange({
    ...value,
    allowed_species_ids: checked ? [...value.allowed_species_ids, species] : value.allowed_species_ids.filter((item) => item !== species),
  })
  return <section className="system-setting-card">
    <div><h3>{t("systemSettings.adoption.title")}</h3><p>{t("systemSettings.adoption.description")}</p></div>
    <NumberField disabled={disabled} hint={t("systemSettings.adoption.maxPerUserHint")} label={t("systemSettings.adoption.maxPerUser")} max={32} min={1} onChange={(limit) => onChange({ ...value, max_elfies_per_user: limit })} value={value.max_elfies_per_user} />
    <fieldset><legend>{t("systemSettings.adoption.species")}</legend>{SPECIES_OPTIONS.map((species) => {
      const checked = value.allowed_species_ids.includes(species.id)
      return <CheckboxField checked={checked} disabled={disabled || (checked && value.allowed_species_ids.length === 1)} hint={checked && value.allowed_species_ids.length === 1 ? t("systemSettings.adoption.speciesRequired") : ""} key={species.id} label={t(`systemSettings.species.${species.id}`)} onChange={(next) => toggleSpecies(species.id, next)} />
    })}</fieldset>
    <Button disabled={disabled} onClick={onSave} type="button">{t("systemSettings.actions.saveAdoption")}</Button>
  </section>
}

function SecurityCard({ disabled, onChange, onSave, value }: { readonly disabled: boolean; readonly onChange: (value: SecuritySettings) => void; readonly onSave: () => void; readonly value: SecuritySettings }) {
  const { t } = useTranslation("manage")
  return <section className="system-setting-card">
    <div><h3>{t("systemSettings.security.title")}</h3><p>{t("systemSettings.security.description")}</p></div>
    <NumberField disabled={disabled} hint={t("systemSettings.security.sessionTtlHint")} label={t("systemSettings.security.sessionTtl")} max={3650} min={1} onChange={(days) => onChange({ ...value, session_ttl_days: days })} value={value.session_ttl_days} />
    <NumberField disabled={disabled} hint={t("systemSettings.security.attemptsHint")} label={t("systemSettings.security.attempts")} max={1000} min={1} onChange={(attempts) => onChange({ ...value, rate_limit: { ...value.rate_limit, max_attempts: attempts } })} value={value.rate_limit.max_attempts} />
    <NumberField disabled={disabled} hint={t("systemSettings.security.windowHint")} label={t("systemSettings.security.window")} max={86400} min={1} onChange={(seconds) => onChange({ ...value, rate_limit: { ...value.rate_limit, window_seconds: seconds } })} value={value.rate_limit.window_seconds} />
    <Button disabled={disabled} onClick={onSave} type="button">{t("systemSettings.actions.saveSecurity")}</Button>
  </section>
}
