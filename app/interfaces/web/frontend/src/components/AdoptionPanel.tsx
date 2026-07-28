import { Button } from "@/components/ui/button"
import { useEffect, useState, type FormEvent } from "react"

import { adoptionInfo, adoptElfie, ApiError, type AdoptionInfo } from "../api/client"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"

type AdoptionPanelProps = { readonly csrfToken: string; readonly onAdopted: (elfieId: string) => Promise<void> }

function initialValue(options: readonly string[]): string { return options[0] ?? "" }

export function AdoptionPanel({ csrfToken, onAdopted }: AdoptionPanelProps) {
  const [info, setInfo] = useState<AdoptionInfo | null>(null)
  const [name, setName] = useState("")
  const [speciesId, setSpeciesId] = useState("")
  const [personalityStyle, setPersonalityStyle] = useState("")
  const [height, setHeight] = useState("")
  const [build, setBuild] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => { void adoptionInfo().then((loaded) => { setInfo(loaded); setSpeciesId(initialValue(loaded.species_ids)); setPersonalityStyle(initialValue(loaded.personality_styles)); setHeight(initialValue(loaded.heights)); setBuild(initialValue(loaded.builds)) }).catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "领养信息加载失败")) }, [])
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault(); setSaving(true); setError(null)
    try { const result = await adoptElfie({ name: name.trim(), speciesId, personalityStyle, height, build }, csrfToken); await onAdopted(result.elfie_id) }
    catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "领养未完成") }
    finally { setSaving(false) }
  }
  if (info === null) return <section className="manage-card"><h2>领养一只精灵</h2>{error ? <Notice kind="error" message={error} /> : <p>正在准备领养选项…</p>}</section>
  return <section className="manage-card"><h2>领养一只精灵</h2><p>你可以领养 {info.quota.remaining}/{info.quota.max} 位精灵。领养后只归属于你的聊天与资料空间。</p><form className="manage-form" onSubmit={(event) => { void submit(event) }}><TextField label="精灵名字" onChange={setName} required value={name} /><SelectField label="物种" onValueChange={setSpeciesId} options={info.species_ids.map((value) => ({ label: value, value }))} value={speciesId} /><SelectField label="人格风格" onValueChange={setPersonalityStyle} options={info.personality_styles.map((value) => ({ label: value, value }))} value={personalityStyle} /><SelectField label="身高" onValueChange={setHeight} options={info.heights.map((value) => ({ label: value, value }))} value={height} /><SelectField label="体型" onValueChange={setBuild} options={info.builds.map((value) => ({ label: value, value }))} value={build} /><Button disabled={!info.quota.can_adopt || saving} type="submit">{saving ? "正在领养…" : "确认领养"}</Button></form>{error && <Notice kind="error" message={error} />}</section>
}
