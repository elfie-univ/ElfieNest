import { useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { login, safeLoginNextPath } from "../api/client"
import { LanguageSwitcher } from "../components/LanguageSwitcher"
import { Notice } from "../components/Notice"
import { TextField } from "../components/TextField"
import { localizeApiError } from "../i18n/errors"
import { currentLocale } from "../i18n/format"

function safeNext(): string {
  return safeLoginNextPath(new URLSearchParams(window.location.search).get("next"))
}

export function LoginPage() {
  const { i18n, t } = useTranslation("auth")
  const { t: commonT } = useTranslation("common")
  const [accountId, setAccountId] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<unknown | null>(null)
  const [saving, setSaving] = useState(false)
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      window.location.assign(await login(accountId.trim(), password, safeNext()))
    } catch (reason: unknown) {
      setError(reason)
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="page login-page">
      <section aria-label={commonT("language.label")} className="setup-locale-control">
        <LanguageSwitcher variant="compact" />
      </section>
      <section className="panel login">
        <p className="login__wordmark">ELFIE NEST</p>
        <img
          alt="ELFIE NEST"
          className="login__logo"
          src={new URL("../../../../../../docs/public/assets/logo.png", import.meta.url).href}
        />
        <p className="login__brand">{t("login.brand")}</p>
        <h1>{t("login.title")}</h1>
        <form onSubmit={(event) => { void submit(event) }}>
          <TextField
            autoComplete="username"
            label={t("login.fields.account")}
            onChange={setAccountId}
            required
            value={accountId}
          />
          <TextField
            autoComplete="current-password"
            label={t("login.fields.password")}
            onChange={setPassword}
            required
            type="password"
            value={password}
          />
          {error !== null ? <Notice kind="error" message={localizeApiError(error, "auth.login", currentLocale(i18n))} /> : null}
          <Button
            className="mt-1 h-11 w-full rounded-xl"
            disabled={saving}
            type="submit"
          >
            {saving ? t("login.submitting") : t("login.action")}
          </Button>
        </form>
      </section>
    </main>
  )
}
