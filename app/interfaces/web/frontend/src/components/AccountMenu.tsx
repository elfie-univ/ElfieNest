import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import {
  changePassword,
  saveLandingPage,
  saveTheme,
  type ClientUser,
  type ThemeKey,
  uploadAvatar,
  updateProfile,
} from "../api/client"
import { Avatar } from "./Avatar"
import { Icon, type IconName } from "./Icon"
import { LanguageSwitcher } from "./LanguageSwitcher"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"
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

type AccountSection = "landing" | "language" | "password" | "theme"
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
  readonly onUpdated: () => Promise<void>
  readonly user: ClientUser
}

function SettingRow({
  active,
  children,
  icon,
  label,
  onToggle,
  summary,
}: {
  readonly active: boolean
  readonly children: ReactNode
  readonly icon: IconName
  readonly label: string
  readonly onToggle: () => void
  readonly summary: string
}) {
  return <section className={active ? "account-menu__setting account-menu__setting--active" : "account-menu__setting"}>
    <button aria-expanded={active} className="account-menu__setting-toggle" data-slot="button" data-variant="ghost" onClick={onToggle} type="button">
      <Icon name={icon} size={17} />
      <span><strong>{label}</strong><small>{summary}</small></span>
      <Icon name={active ? "chevron-up" : "chevron-down"} size={17} />
    </button>
    {active ? <div className="account-menu__setting-body">{children}</div> : null}
  </section>
}

export function AccountMenuPanel({ onClose, onUpdated, user }: AccountMenuPanelProps) {
  const { i18n, t } = useTranslation("account")
  const [expanded, setExpanded] = useState<AccountSection | null>(null)
  const [nickname, setNickname] = useState(user.nickname ?? "")
  const [editingIdentity, setEditingIdentity] = useState(false)
  const [oldPassword, setOldPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [landing, setLanding] = useState<"chat" | "manage">(user.default_landing_page === "chat" ? "chat" : "manage")
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [saving, setSaving] = useState<AccountSection | null>(null)
  const fileInput = useRef<HTMLInputElement | null>(null)
  const csrfToken = user.csrf_token ?? ""
  const displayName = user.nickname?.trim() || user.username
  const roleDescription = user.role === "owner" ? t("identity.ownerRole") : t("identity.userRole")
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
    }
  }

  useEffect(() => {
    setNickname(user.nickname ?? "")
    setLanding(user.default_landing_page === "chat" ? "chat" : "manage")
  }, [user.default_landing_page, user.nickname])

  const toggle = (section: AccountSection): void => {
    setExpanded((current) => current === section ? null : section)
    setFeedback(null)
  }
  const reportError = (section: AccountSection, reason: unknown): void => setFeedback({ kind: "error", reason, section })
  const reportSuccess = (section: AccountSection, messageKey: Extract<Feedback, { readonly kind: "info" }>["messageKey"]): void => setFeedback({ kind: "info", messageKey, section })
  const saveIdentity = async (): Promise<void> => {
    setSaving("theme")
    try {
      await updateProfile({ nickname: nickname.trim() }, csrfToken)
      await onUpdated(); setEditingIdentity(false)
    } catch (reason: unknown) {
      reportError("theme", reason)
    }
    finally { setSaving(null) }
  }
  const saveIdentityOnEnter = (event: ReactKeyboardEvent<HTMLInputElement>): void => {
    if (event.key !== "Enter") return
    event.preventDefault()
    void saveIdentity()
  }
  const uploadIdentityAvatar = async (file: File): Promise<void> => {
    setSaving("theme")
    try {
      await uploadAvatar(file, csrfToken)
      await onUpdated()
    } catch (reason: unknown) {
      reportError("theme", reason)
    }
    finally { setSaving(null) }
  }
  const selectTheme = async (themeKey: ThemeKey): Promise<void> => {
    setSaving("theme")
    try {
      await saveTheme(themeKey, csrfToken)
      await onUpdated(); reportSuccess("theme", "feedback.themeSaved")
    } catch (reason: unknown) {
      reportError("theme", reason)
    }
    finally { setSaving(null) }
  }
  const savePassword = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault(); setSaving("password")
    try {
      await changePassword(oldPassword, newPassword, csrfToken)
      setOldPassword(""); setNewPassword(""); reportSuccess("password", "feedback.passwordSaved")
    } catch (reason: unknown) {
      reportError("password", reason)
    }
    finally { setSaving(null) }
  }
  const saveLanding = async (): Promise<void> => {
    setSaving("landing")
    try {
      await saveLandingPage(landing, csrfToken)
      await onUpdated(); reportSuccess("landing", "feedback.landingSaved")
    } catch (reason: unknown) {
      reportError("landing", reason)
    }
    finally { setSaving(null) }
  }

  return <section aria-label={t("panel.label")} className="account-menu__panel">
    <header><p className="brand"><Icon name="user" size={14} />{t("panel.title")}</p><Button aria-label={t("panel.close")} className="account-menu__close" onClick={onClose} size="icon" type="button" variant="ghost"><Icon name="x" /></Button></header>
    <section className="account-menu__identity">
      <input accept="image/png,image/jpeg,image/webp" aria-label={t("identity.uploadAvatar")} className="account-menu__avatar-input" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadIdentityAvatar(file); event.target.value = "" }} ref={fileInput} type="file" />
      <button aria-label={t("identity.uploadAvatar")} className="account-menu__avatar-button" data-slot="button" data-variant="ghost" disabled={saving !== null} onClick={() => fileInput.current?.click()} type="button"><Avatar imageUrl={user.avatar_url} name={displayName} /></button>
      <div>{editingIdentity ? <Input aria-label={t("identity.editDisplayName")} autoFocus maxLength={32} onChange={(event) => setNickname(event.target.value)} onKeyDown={saveIdentityOnEnter} placeholder={user.username} value={nickname} /> : <h2>{displayName}</h2>}<p>@{user.account_id}</p><small>{roleDescription}</small></div>
      <Button aria-label={editingIdentity ? t("identity.saveDisplayName") : t("identity.editDisplayName")} className="account-menu__edit" disabled={saving !== null} onClick={() => { if (editingIdentity) void saveIdentity(); else setEditingIdentity(true) }} size="icon" type="button" variant="ghost"><Icon name="pencil" size={16} /></Button>
    </section>
    <SettingRow active={expanded === "password"} icon="lock-keyhole" label={t("sections.password")} onToggle={() => toggle("password")} summary={sectionSummary("password")}>
      <form className="account-menu__form" onSubmit={(event) => { void savePassword(event) }}>
        <TextField autoComplete="current-password" label={t("password.current")} onChange={setOldPassword} required type="password" value={oldPassword} />
        <TextField autoComplete="new-password" label={t("password.next")} minLength={6} onChange={setNewPassword} required type="password" value={newPassword} />
        <Button variant="outline" disabled={saving === "password"} type="submit">{saving === "password" ? t("password.saving") : t("password.action")}</Button>
      </form>
    </SettingRow>
    <SettingRow active={expanded === "theme"} icon="palette" label={t("sections.theme")} onToggle={() => toggle("theme")} summary={sectionSummary("theme")}>
      <div className="account-menu__themes">{THEMES.map((theme) => <button aria-pressed={user.theme_key === theme.key} className={user.theme_key === theme.key ? "theme-choice theme-choice--active" : "theme-choice"} data-slot="button" data-variant="outline" disabled={saving === "theme"} key={theme.key} onClick={() => { void selectTheme(theme.key) }} type="button"><i aria-hidden="true" className={`theme-choice__swatch theme-choice__swatch--${theme.key}`} /><span><strong>{t(theme.labelKey)}</strong><small>{t(theme.descriptionKey)}</small></span></button>)}</div>
    </SettingRow>
    <SettingRow active={expanded === "language"} icon="globe-2" label={t("sections.language")} onToggle={() => toggle("language")} summary={sectionSummary("language")}>
      <section aria-label={t("language.sectionLabel")} className="account-menu__language"><LanguageSwitcher /></section>
    </SettingRow>
    {user.role === "owner" ? <SettingRow active={expanded === "landing"} icon="house" label={t("sections.landing")} onToggle={() => toggle("landing")} summary={sectionSummary("landing")}>
      <div className="account-menu__landing"><SelectField label={t("landing.field")} onValueChange={(value) => setLanding(value === "chat" ? "chat" : "manage")} options={[{ label: t("landing.manage"), value: "manage" }, { label: t("landing.chat"), value: "chat" }]} value={landing} /><Button className="account-menu__landing-action" disabled={saving === "landing"} onClick={() => { void saveLanding() }} type="button">{saving === "landing" ? t("landing.saving") : t("landing.action")}</Button></div>
    </SettingRow> : null}
    {feedback && expanded === feedback.section ? <Notice kind={feedback.kind} message={feedback.kind === "error" ? localizeApiError(feedback.reason, "manage.save", currentLocale(i18n)) : t(feedback.messageKey)} /> : null}
  </section>
}

export function AccountMenu({ compact = false, onUpdated, user }: AccountMenuProps) {
  const { t } = useTranslation("account")
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement | null>(null)
  const displayName = user.nickname?.trim() || user.username

  useEffect(() => {
    if (!open) return undefined
    const closeWhenOutside = (event: MouseEvent): void => {
      if (!(event.target instanceof Element)) return
      const isInsideAccountMenu = root.current?.contains(event.target) ?? false
      const isInsideSelectPortal = event.target.closest('[data-slot="select-content"], [role="listbox"], [role="option"]') !== null
      if (!isInsideAccountMenu && !isInsideSelectPortal) setOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent): void => { if (event.key === "Escape") setOpen(false) }
    document.addEventListener("mousedown", closeWhenOutside)
    document.addEventListener("keydown", closeOnEscape)
    return () => { document.removeEventListener("mousedown", closeWhenOutside); document.removeEventListener("keydown", closeOnEscape) }
  }, [open])

  return <div className={compact ? "account-menu account-menu--compact" : "account-menu"} ref={root}>
    <button aria-expanded={open} aria-haspopup="dialog" aria-label={compact ? t("trigger.compact") : undefined} className="account-menu__trigger" data-slot="button" data-tooltip={compact ? t("trigger.tooltip") : undefined} data-variant="ghost" onClick={() => setOpen((current) => !current)} type="button">
      <Avatar imageUrl={user.avatar_url} name={displayName} />
      {!compact ? <span><strong>{displayName}</strong><small>{user.role === "owner" ? t("trigger.owner") : t("trigger.user")}</small></span> : null}
    </button>
    {open ? <AccountMenuPanel onClose={() => setOpen(false)} onUpdated={onUpdated} user={user} /> : null}
  </div>
}
