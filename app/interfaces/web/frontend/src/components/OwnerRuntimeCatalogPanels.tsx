import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Textarea } from "@/components/ui/textarea"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { z } from "zod"

import { ownerRead, ownerWrite } from "../api/client"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { FieldRow } from "./FieldRow"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"
import { SelectField } from "./SelectField"

const ModelSchema = z.object({ model_id: z.string(), provider: z.string(), display_name: z.string(), capabilities: z.array(z.string()), context_window: z.number(), cost_tier: z.number().int(), visible: z.boolean(), active: z.boolean() })
const ToolsSchema = z.object({ tools: z.record(z.string(), z.unknown()) })
type Model = z.infer<typeof ModelSchema>

export function OwnerModelPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [models, setModels] = useState<readonly Model[]>([])
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = useCallback(async (): Promise<void> => { try { setModels(z.array(ModelSchema).parse(await ownerRead("/api/owner/models/"))); setError(null) } catch (reason: unknown) { if (!(reason instanceof Error)) throw reason; setError(describeApiError(reason, "manage.load")) } }, [])
  useEffect(() => { void load() }, [load])
  const update = async (model: Model, change: { readonly visible?: boolean; readonly cost_tier?: number }): Promise<void> => { try { await ownerWrite(`/api/owner/models/${encodeURIComponent(model.model_id)}`, "PUT", csrfToken, change); setNotice(t("modelCatalog.noticeSaved", { name: model.display_name })); await load() } catch (reason: unknown) { if (!(reason instanceof Error)) throw reason; setError(describeApiError(reason, "manage.save")) } }
  const scan = async (): Promise<void> => { try { const result = await ownerWrite("/api/owner/models/scan", "POST", csrfToken); setNotice(t("modelCatalog.noticeScanned", { result: JSON.stringify(result) })) } catch (reason: unknown) { if (!(reason instanceof Error)) throw reason; setError(describeApiError(reason, "manage.save")) } }
  return <section className="manage-card manage-card--wide"><div className="manage-head"><div><h2>{t("modelCatalog.title")}</h2><p>{t("modelCatalog.description")}</p></div><div className="manage-actions"><RefreshButton label={t("modelCatalog.actions.refresh")} onClick={() => { void load() }} /><Button variant="outline" onClick={() => { void scan() }} type="button">{t("modelCatalog.actions.scan")}</Button></div></div>{error && <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} />}{notice && <Notice message={notice} />}<div className="catalog-table">{models.map((model) => <article key={model.model_id}><strong>{model.display_name}</strong><code>{model.model_id}</code><small>{model.provider} · {model.active ? t("modelCatalog.active") : t("modelCatalog.inactive")} · {model.capabilities.join(", ")}</small><label><Checkbox checked={model.visible} onCheckedChange={(checked) => { void update(model, { visible: checked === true }) }} /> {t("modelCatalog.visible")}</label><SelectField label={t("modelCatalog.costTier", { name: model.display_name })} onValueChange={(value) => { void update(model, { cost_tier: Number(value) }) }} options={[0, 1, 2, 3, 4].map((tier) => ({ label: String(tier), value: String(tier) }))} value={String(model.cost_tier)} /></article>)}</div></section>
}

export function OwnerToolPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [tools, setTools] = useState<Record<string, unknown>>({})
  const [selectedKey, setSelectedKey] = useState("")
  const [editor, setEditor] = useState("{}")
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = useCallback(async (): Promise<void> => { try { const data = ToolsSchema.parse(await ownerRead("/api/owner/runtime/tools/")); setTools(data.tools); setError(null) } catch (reason: unknown) { if (!(reason instanceof Error)) throw reason; setError(describeApiError(reason, "manage.load")) } }, [])
  useEffect(() => { void load() }, [load])
  const select = (key: string): void => { setSelectedKey(key); setEditor(JSON.stringify(tools[key] ?? {}, null, 2)) }
  const save = async (): Promise<void> => { if (!selectedKey) return; try { const parsed: unknown = JSON.parse(editor); if (!isJsonObject(parsed)) { setError(t("runtimeTools.validationObject")); return } await ownerWrite(`/api/owner/runtime/tools/${encodeURIComponent(selectedKey)}`, "PUT", csrfToken, parsed); setNotice(t("runtimeTools.noticeSaved")); setError(null); await load() } catch (reason: unknown) { if (reason instanceof SyntaxError) { setError(t("runtimeTools.validationSyntax")); return } if (!(reason instanceof Error)) throw reason; setError(describeApiError(reason, "manage.save")) } }
  const verify = async (): Promise<void> => { if (!selectedKey) return; try { const result = await ownerWrite(`/api/owner/runtime/tools/${encodeURIComponent(selectedKey)}/verify`, "POST", csrfToken); setNotice(t("runtimeTools.noticeVerified", { result: JSON.stringify(result) })); setError(null) } catch (reason: unknown) { if (!(reason instanceof Error)) throw reason; setError(describeApiError(reason, "manage.save")) } }
  return <section className="manage-card manage-card--wide"><div className="manage-head"><div><h2>{t("runtimeTools.title")}</h2><p>{t("runtimeTools.description")}</p></div><RefreshButton label={t("runtimeTools.actions.refresh")} onClick={() => { void load() }} /></div>{error && <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} />}{notice && <Notice message={notice} />}<div className="tool-editor"><div className="tool-list">{Object.entries(tools).map(([key, value]) => <button className={selectedKey === key ? "list-row list-row--active" : "list-row"} data-slot="button" data-variant="ghost" key={key} onClick={() => select(key)} type="button"><strong>{key}</strong><small>{JSON.stringify(value)}</small></button>)}</div><div><FieldRow control={({ describedBy, inputId, labelId }) => <Textarea aria-describedby={describedBy} aria-labelledby={labelId} className="manage-json-input" disabled={!selectedKey} id={inputId} onChange={(event) => setEditor(event.target.value)} value={editor} />} inputId="tool-json-config" label={t("runtimeTools.jsonLabel")} /><div className="manage-actions"><Button disabled={!selectedKey} onClick={() => { void save() }} type="button">{t("runtimeTools.actions.save")}</Button><Button variant="outline" disabled={!selectedKey} onClick={() => { void verify() }} type="button">{t("runtimeTools.actions.verify")}</Button></div></div></div></section>
}

function isJsonObject(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value) }
