import { Button } from "@/components/ui/button"
import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import { adoptionInfo, adoptElfie, type AdoptionInfo } from "../api/client"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"

type AdoptionPanelProps = { readonly csrfToken: string; readonly onAdopted: (elfieId: string) => Promise<void> }

function initialValue(options: readonly string[]): string { return options[0] ?? "" }

export function AdoptionPanel({ csrfToken, onAdopted }: AdoptionPanelProps) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [info, setInfo] = useState<AdoptionInfo | null>(null)
  const [name, setName] = useState("")
  const [speciesId, setSpeciesId] = useState("")
  const [personalityStyle, setPersonalityStyle] = useState("")
  const [height, setHeight] = useState("")
  const [build, setBuild] = useState("")
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => { void adoptionInfo().then((loaded) => { setInfo(loaded); setSpeciesId(initialValue(loaded.species_ids)); setPersonalityStyle(initialValue(loaded.personality_styles)); setHeight(initialValue(loaded.heights)); setBuild(initialValue(loaded.builds)) }).catch((reason: unknown) => setError(describeApiError(reason, "manage.load"))) }, [])
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault(); setSaving(true); setError(null)
    try { const result = await adoptElfie({ name: name.trim(), speciesId, personalityStyle, height, build }, csrfToken); await onAdopted(result.elfie_id) }
    catch (reason: unknown) { setError(describeApiError(reason, "manage.save")) }
    finally { setSaving(false) }
  }
  const errorMessage = resolveLocalizedError(error, locale)
  if (info === null) return <section className="manage-card"><h2>{t("adoption.title")}</h2>{errorMessage ? <Notice kind="error" message={errorMessage} /> : <p>{t("adoption.loading")}</p>}</section>
  return <section className="manage-card"><h2>{t("adoption.title")}</h2><p>{t("adoption.description", { max: info.quota.max, remaining: info.quota.remaining })}</p><form className="manage-form" onSubmit={(event) => { void submit(event) }}><TextField label={t("adoption.fields.name")} onChange={setName} required value={name} /><SelectField label={t("adoption.fields.species")} onValueChange={setSpeciesId} options={info.species_ids.map((value) => ({ label: value, value }))} value={speciesId} /><SelectField label={t("adoption.fields.personality")} onValueChange={setPersonalityStyle} options={info.personality_styles.map((value) => ({ label: value, value }))} value={personalityStyle} /><SelectField label={t("adoption.fields.height")} onValueChange={setHeight} options={info.heights.map((value) => ({ label: value, value }))} value={height} /><SelectField label={t("adoption.fields.build")} onValueChange={setBuild} options={info.builds.map((value) => ({ label: value, value }))} value={build} /><Button disabled={!info.quota.can_adopt || saving} type="submit">{saving ? t("adoption.actions.adopting") : t("adoption.actions.adopt")}</Button></form>{errorMessage && <Notice kind="error" message={errorMessage} />}</section>
}
