import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useCallback, useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import { ownerRead, ownerWrite } from "../api/client"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { FieldRow } from "./FieldRow"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"

type OwnerDataPanelProps = {
  readonly title: string
  readonly description: string
  readonly readPath: string
  readonly csrfToken: string
  readonly writePath?: string
}

function renderJson(value: unknown): string { return JSON.stringify(value, null, 2) }

export function OwnerDataPanel({ title, description, readPath, csrfToken, writePath }: OwnerDataPanelProps) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [data, setData] = useState<unknown>(null)
  const [editor, setEditor] = useState("")
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = useCallback(async (): Promise<void> => {
    try { const loaded = await ownerRead(readPath); setData(loaded); setEditor(renderJson(loaded)); setError(null) }
    catch (reason: unknown) { if (!(reason instanceof Error)) throw reason; setError(describeApiError(reason, "manage.load")) }
  }, [readPath])
  useEffect(() => { void load() }, [load])
  const save = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault(); if (writePath === undefined) return
    try { const body: unknown = JSON.parse(editor); const updated = await ownerWrite(writePath, "PUT", csrfToken, body); setData(updated); setEditor(renderJson(updated)); setNotice(t("rawData.noticeSaved")); setError(null) }
    catch (reason: unknown) { if (reason instanceof SyntaxError) { setError(t("rawData.validationSyntax")); return } if (!(reason instanceof Error)) throw reason; setError(describeApiError(reason, "manage.save")) }
  }
  return <section className="manage-card"><div className="manage-head"><div><h2>{title}</h2><p>{description}</p></div><RefreshButton label={t("rawData.actions.refresh")} onClick={() => { void load() }} /></div>{error && <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} />}{notice && <Notice message={notice} />}{writePath === undefined ? <pre className="manage-json">{data === null ? t("rawData.loading") : renderJson(data)}</pre> : <form onSubmit={(event) => { void save(event) }}><FieldRow control={({ describedBy, inputId, labelId }) => <Textarea aria-describedby={describedBy} aria-labelledby={labelId} className="manage-json-input" id={inputId} onChange={(event) => setEditor(event.target.value)} value={editor} />} inputId={`${title}-json-config`} label={t("rawData.jsonLabel", { title })} /><Button type="submit">{t("rawData.actions.save")}</Button></form>}</section>
}
