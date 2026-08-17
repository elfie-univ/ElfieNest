import { useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { login, register, safeLoginNextPath } from "../api/client"
import { LanguageSwitcher } from "../components/LanguageSwitcher"
import { Notice } from "../components/Notice"
import { TextField } from "../components/TextField"
import { localizeApiError } from "../i18n/errors"
import { currentLocale } from "../i18n/format"

const loginFullLogoUrl = new URL("../../../../../../docs/public/assets/elfienest-full-logo-transparent.png", import.meta.url).href

function safeNext(): string {
  return safeLoginNextPath(new URLSearchParams(window.location.search).get("next"))
}

type AuthMode = "login" | "register"

export function LoginPage() {
  const { i18n, t } = useTranslation("auth")
  const { t: commonT } = useTranslation("common")
  const [mode, setMode] = useState<AuthMode>("login")
  const [accountId, setAccountId] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState<unknown | null>(null)
  const [passwordMismatch, setPasswordMismatch] = useState(false)
  const [saving, setSaving] = useState(false)
  const registration = mode === "register"

  const switchMode = (nextMode: AuthMode): void => {
    setMode(nextMode)
    setError(null)
    setPasswordMismatch(false)
    setPassword("")
    setConfirmPassword("")
  }

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setError(null)
    setPasswordMismatch(false)
    if (registration && password !== confirmPassword) {
      setPasswordMismatch(true)
      return
    }
    setSaving(true)
    try {
      const landingPath = registration
        ? await register(displayName.trim(), accountId.trim(), password, safeNext())
        : await login(accountId.trim(), password, safeNext())
      window.location.assign(landingPath)
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
        <img
          alt="ELFIE NEST"
          className="login__logo"
          src={loginFullLogoUrl}
        />
        <form onSubmit={(event) => { void submit(event) }}>
          {registration ? <TextField
            autoComplete="name"
            label={t("login.fields.displayName")}
            onChange={setDisplayName}
            required
            value={displayName}
          /> : null}
          <TextField
            autoComplete="username"
            label={t("login.fields.account")}
            onChange={setAccountId}
            required
            value={accountId}
          />
          <TextField
            autoComplete={registration ? "new-password" : "current-password"}
            label={t("login.fields.password")}
            {...(registration ? { minLength: 6 } : {})}
            onChange={(value) => { setPasswordMismatch(false); setPassword(value) }}
            required
            type="password"
            value={password}
          />
          {registration ? <TextField
            autoComplete="new-password"
            label={t("login.fields.confirmPassword")}
            minLength={6}
            onChange={(value) => { setPasswordMismatch(false); setConfirmPassword(value) }}
            required
            type="password"
            value={confirmPassword}
          /> : null}
          {passwordMismatch ? <Notice kind="error" message={t("login.passwordMismatch")} /> : null}
          {error !== null ? <Notice kind="error" message={localizeApiError(error, registration ? "auth.register" : "auth.login", currentLocale(i18n))} /> : null}
          <Button
            className="mt-1 h-11 w-full rounded-xl"
            disabled={saving}
            type="submit"
          >
            {saving
              ? registration ? t("login.registerSubmitting") : t("login.submitting")
              : registration ? t("login.registerAction") : t("login.action")}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-muted-foreground">
          <Button
            className="h-auto px-0"
            disabled={saving}
            onClick={() => switchMode(registration ? "login" : "register")}
            size="sm"
            type="button"
            variant="link"
          >
            {registration ? t("login.switchToLogin") : t("login.switchToRegister")}
          </Button>
        </p>
      </section>
    </main>
  )
}
