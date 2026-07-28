import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"
import { z } from "zod"

import { ApiError, ownerRead, ownerWrite } from "../api/client"
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
const SPECIES_OPTIONS = [{ id: "dog", label: "狗" }, { id: "fox", label: "狐狸" }] as const

export function SystemSettingsPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [engine, setEngine] = useState<EngineSettings | null>(null)
  const [adoption, setAdoption] = useState<AdoptionSettings | null>(null)
  const [security, setSecurity] = useState<SecuritySettings | null>(null)
  const [saving, setSaving] = useState<SettingsSection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

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
      setError(reason instanceof ApiError ? reason.message : "系统设置加载失败")
    }
  }
  useEffect(() => { void load() }, [])

  const save = async (section: SettingsSection, value: unknown, message: string): Promise<void> => {
    setSaving(section)
    try {
      await ownerWrite(`/api/owner/system/${section}`, "PUT", csrfToken, value)
      setNotice(message)
      setError(null)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "设置没有保存")
    } finally {
      setSaving(null)
    }
  }

  return <section className="system-settings">
    <div className="manage-head"><p>常用本机参数按模块保存，所有数值在提交前均有明确范围。</p><RefreshButton disabled={saving !== null} label="重新读取" onClick={() => { void load() }} /></div>
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    {!engine && !adoption && !security && !error ? <p className="empty-state">正在加载系统设置…</p> : null}
    <div className="system-settings__grid">
      {engine ? <EngineCard disabled={saving !== null} onChange={setEngine} onSave={() => { void save("engine", engine, "引擎设置已保存。") }} value={engine} /> : null}
      {adoption ? <AdoptionCard disabled={saving !== null} onChange={setAdoption} onSave={() => { void save("adoption", adoption, "领养设置已保存。") }} value={adoption} /> : null}
      {security ? <SecurityCard disabled={saving !== null} onChange={setSecurity} onSave={() => { void save("security", security, "安全设置已保存；现有会话限制已刷新。") }} value={security} /> : null}
    </div>
  </section>
}

function EngineCard({ disabled, onChange, onSave, value }: { readonly disabled: boolean; readonly onChange: (value: EngineSettings) => void; readonly onSave: () => void; readonly value: EngineSettings }) {
  const roomLimitEnabled = value.max_elfies_per_room !== null
  return <section className="system-setting-card">
    <div><h3>引擎设置</h3><p>控制本机精灵巢的运行节奏与房间容量。</p></div>
    <NumberField disabled={disabled} hint="0.1–3600 秒" label="运行 Tick（秒）" max={3600} min={0.1} onChange={(tick) => onChange({ ...value, tick_interval_sec: tick })} step={0.1} value={value.tick_interval_sec} />
    <CheckboxField checked={roomLimitEnabled} disabled={disabled} hint="关闭时不限制每个房间的精灵数量" label="限制每房精灵数" onChange={(checked) => onChange({ ...value, max_elfies_per_room: checked ? 1 : null })} />
    {roomLimitEnabled ? <NumberField disabled={disabled} hint="1–32 位" label="每房最大精灵数" max={32} min={1} onChange={(limit) => onChange({ ...value, max_elfies_per_room: limit })} value={value.max_elfies_per_room ?? 1} /> : null}
    <Button disabled={disabled} onClick={onSave} type="button">保存引擎设置</Button>
  </section>
}

function AdoptionCard({ disabled, onChange, onSave, value }: { readonly disabled: boolean; readonly onChange: (value: AdoptionSettings) => void; readonly onSave: () => void; readonly value: AdoptionSettings }) {
  const toggleSpecies = (species: string, checked: boolean): void => onChange({
    ...value,
    allowed_species_ids: checked ? [...value.allowed_species_ids, species] : value.allowed_species_ids.filter((item) => item !== species),
  })
  return <section className="system-setting-card">
    <div><h3>领养设置</h3><p>限制成员可领养数量与当前开放物种。</p></div>
    <NumberField disabled={disabled} hint="1–32 位" label="每用户最多精灵数" max={32} min={1} onChange={(limit) => onChange({ ...value, max_elfies_per_user: limit })} value={value.max_elfies_per_user} />
    <fieldset><legend>允许物种</legend>{SPECIES_OPTIONS.map((species) => {
      const checked = value.allowed_species_ids.includes(species.id)
      return <CheckboxField checked={checked} disabled={disabled || (checked && value.allowed_species_ids.length === 1)} hint={checked && value.allowed_species_ids.length === 1 ? "至少保留一个物种" : ""} key={species.id} label={species.label} onChange={(next) => toggleSpecies(species.id, next)} />
    })}</fieldset>
    <Button disabled={disabled} onClick={onSave} type="button">保存领养设置</Button>
  </section>
}

function SecurityCard({ disabled, onChange, onSave, value }: { readonly disabled: boolean; readonly onChange: (value: SecuritySettings) => void; readonly onSave: () => void; readonly value: SecuritySettings }) {
  return <section className="system-setting-card">
    <div><h3>安全设置</h3><p>控制登录会话有效期和失败尝试限制。</p></div>
    <NumberField disabled={disabled} hint="1–3650 天" label="会话有效期（天）" max={3650} min={1} onChange={(days) => onChange({ ...value, session_ttl_days: days })} value={value.session_ttl_days} />
    <NumberField disabled={disabled} hint="1–1000 次" label="尝试次数上限" max={1000} min={1} onChange={(attempts) => onChange({ ...value, rate_limit: { ...value.rate_limit, max_attempts: attempts } })} value={value.rate_limit.max_attempts} />
    <NumberField disabled={disabled} hint="1–86400 秒" label="限制窗口（秒）" max={86400} min={1} onChange={(seconds) => onChange({ ...value, rate_limit: { ...value.rate_limit, window_seconds: seconds } })} value={value.rate_limit.window_seconds} />
    <Button disabled={disabled} onClick={onSave} type="button">保存安全设置</Button>
  </section>
}
