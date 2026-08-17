import { Button } from "@/components/ui/button"
import { useEffect, useRef, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import type {
  ProviderConnection,
  ProviderConnectionUpdate,
  ProviderOAuthLoginStart,
  ProviderProduct,
} from "../api/owner-providers"
import { describeApiError, resolveLocalizedError } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { Icon } from "./Icon"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"

type ProviderFormDialogProps = {
  readonly connection: ProviderConnection | null
  readonly onOpenChange: (open: boolean) => void
  readonly onAuthorize: (
    catalogId: string,
    alias: string | undefined,
    onStarted: (started: ProviderOAuthLoginStart) => void,
    signal: AbortSignal,
  ) => Promise<void>
  readonly onSave: (catalogId: string, draft: ProviderConnectionUpdate) => Promise<void>
  readonly open: boolean
  readonly products: readonly ProviderProduct[]
}

export function ProviderFormDialog({
  connection,
  onOpenChange,
  onAuthorize,
  onSave,
  open,
  products,
}: ProviderFormDialogProps) {
  const { i18n, t } = useTranslation("manage")
  const [alias, setAlias] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [selectedCatalogId, setSelectedCatalogId] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [oauthStart, setOauthStart] = useState<ProviderOAuthLoginStart | null>(null)
  const authorizationController = useRef<AbortController | null>(null)
  const authorizationAttempt = useRef(0)

  useEffect(() => {
    if (products.length === 0 || !open) return
    authorizationController.current?.abort()
    authorizationController.current = null
    setAlias(connection?.alias ?? "")
    setApiKey("")
    setSelectedCatalogId(connection?.catalog_id ?? products[0]?.catalog_id ?? "")
    setPending(false)
    setError(null)
    setOauthStart(null)
    return () => authorizationController.current?.abort()
  }, [connection, open, products])

  const product = products.find((item) => item.catalog_id === selectedCatalogId) ?? products[0]
  if (!product) return null
  const method = product.connection_method
  const brandName = products[0]?.brand.name ?? product.brand.name
  const title = connection
    ? t("providerConnections.form.titleEdit", { name: brandName })
    : t("providerConnections.form.titleConfigure", { name: brandName })

  const close = (): void => {
    authorizationController.current?.abort()
    onOpenChange(false)
  }

  const beginAuthorization = async (): Promise<void> => {
    const attempt = authorizationAttempt.current + 1
    authorizationAttempt.current = attempt
    authorizationController.current?.abort()
    const controller = new AbortController()
    authorizationController.current = controller
    setError(null)
    setOauthStart(null)
    setPending(true)
    try {
      await onAuthorize(
        product.catalog_id,
        alias.trim() || undefined,
        (started) => {
          if (authorizationAttempt.current === attempt) setOauthStart(started)
        },
        controller.signal,
      )
    } catch (reason: unknown) {
      if (!isAbort(reason) && authorizationAttempt.current === attempt) {
        setError(resolveLocalizedError(describeApiError(reason, "manage.save"), currentLocale(i18n)) ?? t("providerConnections.errors.save"))
      }
    } finally {
      if (authorizationAttempt.current === attempt) setPending(false)
    }
  }

  const copyAuthorizationCode = async (): Promise<void> => {
    if (!oauthStart) return
    await navigator.clipboard.writeText(oauthStart.user_code)
  }

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (method === "oauth" && !connection) {
      await beginAuthorization()
      return
    }
    setError(null)
    setPending(true)
    try {
      await onSave(product.catalog_id, {
        ...(alias.trim() ? { alias: alias.trim() } : {}),
        ...(!connection || apiKey ? { api_key: apiKey } : {}),
        ...(!connection ? { refresh_models: false, verify: false } : {}),
      })
    } catch (reason: unknown) {
      setError(resolveLocalizedError(describeApiError(reason, "manage.save"), currentLocale(i18n)) ?? t("providerConnections.errors.save"))
    } finally {
      setPending(false)
    }
  }

  const methodOptions = products.map((item) => ({
    label: connectionMethodLabel(item, t),
    value: item.catalog_id,
  }))

  return <ManageDialog contentClassName="provider-form-dialog" onOpenChange={(nextOpen) => { if (!nextOpen) close() }} open={open} title={title}>
    {error ? <Notice kind="error" message={error} /> : null}
    <form className="provider-form" onSubmit={(event) => { void submit(event) }}>
      <TextField label={t("providerConnections.form.alias")} onChange={setAlias} placeholder={product.name || brandName} value={alias} />
      {product.brand.brand_id !== "openai" && methodOptions.length === 1
        ? <TextField disabled label={t("providerConnections.form.method")} onChange={() => undefined} value={methodOptions[0]?.label ?? ""} />
        : <SelectField label={t("providerConnections.form.method")} onValueChange={setSelectedCatalogId} options={methodOptions} value={product.catalog_id} />}
      {method === "api_key" ? <TextField autoComplete="new-password" autoFocus label={t("providerConnections.form.apiKey")} onChange={setApiKey} required={!connection} type="password" value={apiKey} /> : null}
      {method === "oauth" && !connection && oauthStart ? <div className="provider-form__oauth" role="status">
        <p>{t("providerConnections.form.oauthCodeLabel")}</p>
        <div className="provider-form__oauth-code-row">
          <strong className="provider-form__oauth-code">{oauthStart.user_code}</strong>
          <Button aria-label={t("providerConnections.actions.copyCode")} onClick={() => { void copyAuthorizationCode() }} size="icon-sm" title={t("providerConnections.actions.copyCode")} type="button" variant="outline"><Icon name="copy" size={16} /></Button>
        </div>
        <Button asChild className="provider-form__oauth-open" variant="outline"><a href={oauthStart.authorization_url} rel="noreferrer" target="_blank">{t("providerConnections.form.oauthOpen")}</a></Button>
        <p>{pending ? t("providerConnections.form.oauthWaiting") : t("providerConnections.form.oauthCancelled")}</p>
      </div> : null}
      <div className="manage-actions">
        {method === "oauth" && !connection
          ? oauthStart
            ? <Button disabled={pending} onClick={() => { void beginAuthorization() }} type="button">{t("providerConnections.actions.regenerateCode")}</Button>
            : <Button disabled={pending || !product.oauth_available} type="submit">{pending ? t("providerConnections.actions.authorizing") : t("providerConnections.actions.authorize")}</Button>
          : <Button disabled={pending} type="submit">{pending ? t("providerConnections.actions.saving") : t("providerConnections.actions.save")}</Button>}
      </div>
    </form>
  </ManageDialog>
}

function connectionMethodLabel(product: ProviderProduct, t: (key: string) => string): string {
  if (product.connection_method === "oauth") return t("providerConnections.form.methods.chatgpt")
  if (product.brand.brand_id === "openai") return t("providerConnections.form.methods.openaiApi")
  return t("providerConnections.form.methods.apiKey")
}

function isAbort(reason: unknown): boolean {
  return reason instanceof DOMException && reason.name === "AbortError"
}
