import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent } from "react"
import { useTranslation } from "react-i18next"

import {
  changePassword,
  logout,
  saveLandingPage,
  saveTheme,
  type ClientUser,
  type Gender,
  type ThemeKey,
  uploadAvatar,
  updateProfile,
} from "../api/client"
import { isManagerRole } from "../api/roles"
import { Avatar } from "./Avatar"
import { accountDisplayName } from "./AccountIdentity"
import { Icon } from "./Icon"
import { AccountSettingRow } from "./AccountSettingRow"
import { LanguageSwitcher } from "./LanguageSwitcher"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"
import { ConfirmDialog } from "./ConfirmDialog"
import { localizeApiError } from "../i18n/errors"
import { currentLocale } from "../i18n/format"

const THEMES = [
  { descriptionKey: "themes.warmPaper.description", key: "warm-paper", labelKey: "themes.warmPaper.label" },
  { descriptionKey: "themes.harborBlue.description", key: "harbor-blue", labelKey: "themes.harborBlue.label" },
  { descriptionKey: "themes.orchidArchive.description", key: "orchid-archive", labelKey: "themes.orchidArchive.label" },
  { descriptionKey: "themes.mossGreen.description", key: "moss-green", labelKey: "themes.mossGreen.label" },
] satisfies readonly {
  readonly descriptionKey: "themes.warmPaper.description" | "themes.harborBlue.description" | "themes.orchidArchive.description" | "themes.mossGreen.description"
  readonly key: ThemeKey
  readonly labelKey: "themes.warmPaper.label" | "themes.harborBlue.label" | "themes.orchidArchive.label" | "themes.mossGreen.label"
}[]

type AccountSection = "identity" | "landing" | "language" | "password" | "theme"
type Feedback =
  | { readonly kind: "error"; readonly reason: unknown; readonly section: AccountSection }
  | { readonly kind: "info"; readonly messageKey: "feedback.landingSaved" | "feedback.passwordSaved" | "feedback.themeSaved"; readonly section: AccountSection }

type AccountMenuProps = {
  readonly compact?: boolean
  readonly onUpdated: () => Promise<void>
  readonly user: ClientUser
}

type AccountMenuPanelProps = {
  readonly onClose: () => void
  readonly onLoggedOut?: () => void
  readonly onUpdated: () => Promise<void>
  readonly user: ClientUser
}

export function AccountMenuPanel({ onClose, onLoggedOut, onUpdated, user }: AccountMenuPanelProps) {
  const { i18n, t } = useTranslation("account")
  const [expanded, setExpanded] = useState<AccountSection | null>(null)
  const [accountIdInput, setAccountIdInput] = useState(user.account_id)
  const [birthDateInput, setBirthDateInput] = useState(user.birth_date ?? "")
  const [displayNameInput, setDisplayNameInput] = useState(user.display_name ?? "")
  const [editingIdentity, setEditingIdentity] = useState(false)
  const [genderInput, setGenderInput] = useState<Gender>(user.gender === "female" ? "female" : "male")
  const [identityConfirmOpen, setIdentityConfirmOpen] = useState(false)
  const [oldPassword, setOldPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [landing, setLanding] = useState<"chat" | "manage">(user.default_landing_page === "chat" ? "chat" : "manage")
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState<unknown | null>(null)
  const [saving, setSaving] = useState<AccountSection | null>(null)
  const fileInput = useRef<HTMLInputElement | null>(null)
  const panelRef = useRef<HTMLElement | null>(null)
  const csrfToken = user.csrf_token ?? ""
  const displayName = accountDisplayName(user)
  const roleDescription = user.role === "owner"
    ? t("identity.ownerRole")
    : user.role === "admin" ? t("identity.adminRole") : t("identity.userRole")
  const gender = user.gender === "female" ? "female" : "male"
  const genderLabel = gender === "female" ? t("identity.genderFemale") : t("identity.genderMale")
  const sectionSummary = (section: AccountSection): string => {
    switch (section) {
      case "password": return t("sections.passwordSummary")
      case "theme": switch (user.theme_key) {
        case "harbor-blue": return t("themes.harborBlue.label")
        case "orchid-archive": return t("themes.orchidArchive.label")
        case "moss-green": return t("themes.mossGreen.label")
        case "warm-paper": return t("themes.warmPaper.label")
      }
      case "landing": return user.default_landing_page === "chat" ? t("landing.chat") : t("landing.manage")
      case "language": return t("language.current")
      case "identity": return ""
    }
  }

  useEffect(() => {
    setAccountIdInput(user.account_id)
    setBirthDateInput(user.birth_date ?? "")
    setDisplayNameInput(user.display_name ?? "")
    setGenderInput(user.gender === "female" ? "female" : "male")
    setLanding(user.default_landing_page === "chat" ? "chat" : "manage")
  }, [user.account_id, user.birth_date, user.default_landing_page, user.display_name, user.gender])

  useEffect(() => {
    const closeWhenOutside = (event: MouseEvent): void => {
      if (!(event.target instanceof Element)) return
      const isInsideAccountPanel = panelRef.current?.contains(event.target) ?? false
      const isInsideAccountTrigger = event.target.closest(".account-menu__trigger") !== null
      const isInsideSelectPortal = event.target.closest('[data-slot="select-content"], [role="listbox"], [role="option"]') !== null
      const isInsideDialog = event.target.closest('[role="dialog"], [data-slot="alert-dialog-overlay"]') !== null
      if (!isInsideAccountPanel && !isInsideAccountTrigger && !isInsideSelectPortal && !isInsideDialog) onClose()
    }
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key !== "Escape" || document.querySelector('[role="dialog"]')) return
      onClose()
    }
    document.addEventListener("mousedown", closeWhenOutside)
    document.addEventListener("keydown", closeOnEscape)
    return () => {
      document.removeEventListener("mousedown", closeWhenOutside)
      document.removeEventListener("keydown", closeOnEscape)
    }
  }, [onClose])

  const toggle = (section: AccountSection): void => {
    setExpanded((current) => current === section ? null : section)
    setFeedback(null)
  }
  const reportError = (section: AccountSection, reason: unknown): void => setFeedback({ kind: "error", reason, section })
  const reportSuccess = (section: AccountSection, messageKey: Extract<Feedback, { readonly kind: "info" }>["messageKey"]): void => setFeedback({ kind: "info", messageKey, section })
  const saveIdentity = async (): Promise<void> => {
    setSaving("identity")
    try {
      await updateProfile({
        account_id: accountIdInput.trim(),
        birth_date: birthDateInput.trim() || null,
        display_name: displayNameInput.trim(),
        gender: genderInput,
      }, csrfToken)
      await onUpdated(); setEditingIdentity(false); setIdentityConfirmOpen(false)
    } catch (reason: unknown) { if (!(reason instanceof Error)) throw reason; reportError("identity", reason) }
    finally { setSaving(null) }
  }
  const saveIdentityOnEnter = (event: ReactKeyboardEvent<HTMLInputElement>): void => {
    if (event.key !== "Enter") return
    event.preventDefault()
    setIdentityConfirmOpen(true)
  }
  const uploadIdentityAvatar = async (file: File): Promise<void> => {
    setSaving("identity")
    try {
      await uploadAvatar(file, csrfToken)
      await onUpdated()
    } catch (reason: unknown) { if (!(reason instanceof Error)) throw reason; reportError("identity", reason) }
    finally { setSaving(null) }
  }
  const selectTheme = async (themeKey: ThemeKey): Promise<void> => {
    setSaving("theme")
    try {
      await saveTheme(themeKey, csrfToken)
      await onUpdated(); reportSuccess("theme", "feedback.themeSaved")
    } catch (reason: unknown) { if (!(reason instanceof Error)) throw reason; reportError("theme", reason) }
    finally { setSaving(null) }
  }
  const savePassword = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault(); setSaving("password")
    try {
      await changePassword(oldPassword, newPassword, csrfToken)
      setOldPassword(""); setNewPassword(""); reportSuccess("password", "feedback.passwordSaved")
    } catch (reason: unknown) { if (!(reason instanceof Error)) throw reason; reportError("password", reason) }
    finally { setSaving(null) }
  }
  const saveLanding = async (): Promise<void> => {
    setSaving("landing")
    try {
      await saveLandingPage(landing, csrfToken)
      await onUpdated(); reportSuccess("landing", "feedback.landingSaved")
    } catch (reason: unknown) { if (!(reason instanceof Error)) throw reason; reportError("landing", reason) }
    finally { setSaving(null) }
  }
  const logoutSession = async (): Promise<void> => {
    setLoggingOut(true)
    setLogoutError(null)
    try {
      await logout(csrfToken)
      if (onLoggedOut) onLoggedOut()
      else window.location.assign("/login")
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setLogoutError(reason)
      setLoggingOut(false)
    }
  }

  return <section aria-label={t("panel.label")} className="account-menu__panel" ref={panelRef}>
    <section className="account-menu__identity">
      <input accept="image/png,image/jpeg,image/webp" aria-label={t("identity.uploadAvatar")} className="account-menu__avatar-input" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadIdentityAvatar(file); event.target.value = "" }} ref={fileInput} type="file" />
      <button aria-label={t("identity.uploadAvatar")} className="account-menu__avatar-button" data-slot="button" data-variant="ghost" disabled={saving !== null} onClick={() => fileInput.current?.click()} type="button"><Avatar imageUrl={user.avatar_url} name={displayName} /></button>
      <div className="account-menu__identity-content">
        {editingIdentity ? <div className="account-menu__identity-edit">
          <div className="account-menu__identity-name-row">
            <Input aria-label={t("identity.editDisplayName")} autoFocus maxLength={64} onChange={(event) => setDisplayNameInput(event.target.value)} onKeyDown={saveIdentityOnEnter} placeholder={user.account_id} value={displayNameInput} />
            <label className="account-menu__gender-field"><span>{t("identity.gender")}</span><select aria-label={t("identity.gender")} onChange={(event) => setGenderInput(event.target.value === "female" ? "female" : "male")} value={genderInput}><option value="male">{t("identity.genderMale")}</option><option value="female">{t("identity.genderFemale")}</option></select></label>
          </div>
          <label className="account-menu__identity-edit-row"><span className="account-menu__identity-edit-label">{t("identity.accountLabel")}</span><Input aria-label={t("identity.accountLabel")} maxLength={32} minLength={3} onChange={(event) => setAccountIdInput(event.target.value)} value={accountIdInput} /></label>
          <label className="account-menu__identity-edit-row"><span className="account-menu__identity-edit-label">{t("identity.roleLabel")}</span><Input aria-label={t("identity.roleLabel")} readOnly value={roleDescription} /></label>
          <label className="account-menu__identity-edit-row"><span className="account-menu__identity-edit-label">{t("identity.birthDate")}</span><Input aria-label={t("identity.birthDate")} onChange={(event) => setBirthDateInput(event.target.value)} type="date" value={birthDateInput} /></label>
          <div className="account-menu__identity-actions"><Button disabled={saving !== null} onClick={() => { setEditingIdentity(false); setAccountIdInput(user.account_id); setBirthDateInput(user.birth_date ?? ""); setDisplayNameInput(user.display_name ?? ""); setGenderInput(gender) }} type="button" variant="ghost">{t("identity.cancelEdit")}</Button><Button disabled={saving !== null} onClick={() => setIdentityConfirmOpen(true)} type="button">{saving === "identity" ? t("landing.saving") : t("identity.save")}</Button></div>
        </div> : <div className="account-menu__identity-display">
          <div className="account-menu__identity-name-line"><h2>{displayName}</h2><span aria-label={genderLabel} className="account-menu__gender-icon" role="img"><Icon name={gender === "female" ? "venus" : "mars"} size={15} /></span></div>
          <p><span className="account-menu__identity-label">{t("identity.accountLabel")}</span>{user.account_id}</p>
          <p><span className="account-menu__identity-label">{t("identity.roleLabel")}</span>{roleDescription}</p>
          {user.birth_date ? <p><span className="account-menu__identity-label">{t("identity.birthDate")}</span>{user.birth_date}</p> : null}
        </div>}
      </div>
      {editingIdentity ? null : <Button aria-label={t("identity.editDisplayName")} className="account-menu__edit" disabled={saving !== null} onClick={() => setEditingIdentity(true)} size="icon" type="button" variant="ghost"><Icon name="pencil" size={16} /></Button>}
    </section>
    <AccountSettingRow active={expanded === "password"} icon="lock-keyhole" label={t("sections.password")} onToggle={() => toggle("password")} summary={sectionSummary("password")}>
      <form className="account-menu__form" onSubmit={(event) => { void savePassword(event) }}>
        <TextField autoComplete="current-password" label={t("password.current")} onChange={setOldPassword} required type="password" value={oldPassword} />
        <TextField autoComplete="new-password" label={t("password.next")} minLength={6} onChange={setNewPassword} required type="password" value={newPassword} />
        <Button variant="outline" disabled={saving === "password"} type="submit">{saving === "password" ? t("password.saving") : t("password.action")}</Button>
      </form>
    </AccountSettingRow>
    <AccountSettingRow active={expanded === "theme"} icon="palette" label={t("sections.theme")} onToggle={() => toggle("theme")} summary={sectionSummary("theme")}>
      <div className="account-menu__themes">{THEMES.map((theme) => <button aria-pressed={user.theme_key === theme.key} className={user.theme_key === theme.key ? "theme-choice theme-choice--active" : "theme-choice"} data-slot="button" data-variant="outline" disabled={saving === "theme"} key={theme.key} onClick={() => { void selectTheme(theme.key) }} type="button"><i aria-hidden="true" className={`theme-choice__swatch theme-choice__swatch--${theme.key}`} /><span><strong>{t(theme.labelKey)}</strong><small>{t(theme.descriptionKey)}</small></span></button>)}</div>
    </AccountSettingRow>
    <AccountSettingRow active={expanded === "language"} icon="globe-2" label={t("sections.language")} onToggle={() => toggle("language")} summary={sectionSummary("language")}>
      <section aria-label={t("language.sectionLabel")} className="account-menu__language"><LanguageSwitcher /></section>
    </AccountSettingRow>
    {isManagerRole(user.role) ? <AccountSettingRow active={expanded === "landing"} icon="house" label={t("sections.landing")} onToggle={() => toggle("landing")} summary={sectionSummary("landing")}>
      <div className="account-menu__landing"><SelectField label={t("landing.field")} onValueChange={(value) => setLanding(value === "chat" ? "chat" : "manage")} options={[{ label: t("landing.manage"), value: "manage" }, { label: t("landing.chat"), value: "chat" }]} value={landing} /><Button className="account-menu__landing-action" disabled={saving === "landing"} onClick={() => { void saveLanding() }} type="button">{saving === "landing" ? t("landing.saving") : t("landing.action")}</Button></div>
    </AccountSettingRow> : null}
    <ConfirmDialog description={t("identity.confirmDescription")} onConfirm={() => { void saveIdentity() }} onOpenChange={setIdentityConfirmOpen} open={identityConfirmOpen} pending={saving === "identity"} title={t("identity.confirmTitle")} />
    {feedback && (feedback.section === "identity" || expanded === feedback.section) ? <Notice kind={feedback.kind} message={feedback.kind === "error" ? localizeApiError(feedback.reason, "manage.save", currentLocale(i18n)) : t(feedback.messageKey)} /> : null}
    {logoutError ? <Notice kind="error" message={localizeApiError(logoutError, "manage.save", currentLocale(i18n))} /> : null}
    <section aria-label={t("session.sectionLabel")} className="account-menu__session">
      <Button className="account-menu__logout" disabled={loggingOut || saving !== null} onClick={() => { void logoutSession() }} type="button" variant="ghost">
        <Icon name="log-out" size={17} />
        {loggingOut ? t("session.loggingOut") : t("session.logout")}
      </Button>
    </section>
  </section>
}

export function AccountMenu({ compact = false, onUpdated, user }: AccountMenuProps) {
  const { t } = useTranslation("account")
  const [open, setOpen] = useState(false)
  const displayName = accountDisplayName(user)

  return <div className={compact ? "account-menu account-menu--compact" : "account-menu"}>
    <button aria-expanded={open} aria-haspopup="dialog" aria-label={compact ? t("trigger.compact") : undefined} className="account-menu__trigger" data-slot="button" data-tooltip={compact ? t("trigger.tooltip") : undefined} data-variant="ghost" onClick={() => setOpen((current) => !current)} type="button">
      <Avatar imageUrl={user.avatar_url} name={displayName} />
      {!compact ? <span><strong>{displayName}</strong></span> : null}
    </button>
    {open ? <AccountMenuPanel onClose={() => setOpen(false)} onUpdated={onUpdated} user={user} /> : null}
  </div>
}
