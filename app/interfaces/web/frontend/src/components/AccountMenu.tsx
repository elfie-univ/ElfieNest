import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react"

import {
  ApiError,
  changePassword,
  saveLandingPage,
  saveTheme,
  type ClientUser,
  type ThemeKey,
  updateProfile,
} from "../api/client"
import { Avatar } from "./Avatar"
import { Icon, type IconName } from "./Icon"
import { SelectField } from "./SelectField"

const THEMES = [
  { key: "warm-paper", label: "暖纸与陶土", description: "默认" },
  { key: "harbor-blue", label: "港湾蓝", description: "清爽" },
  { key: "orchid-archive", label: "兰紫档案", description: "安静" },
  { key: "moss-green", label: "苔藓绿", description: "自然" },
] as const satisfies readonly { readonly key: ThemeKey; readonly label: string; readonly description: string }[]

type AccountSection = "landing" | "password" | "profile" | "theme"
type Feedback = { readonly kind: "error" | "info"; readonly message: string; readonly section: AccountSection }

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

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof ApiError ? reason.message : fallback
}

function sectionSummary(section: AccountSection, user: ClientUser): string {
  switch (section) {
    case "profile": return "显示名与头像颜色"
    case "password": return "更新登录凭据"
    case "theme": return THEMES.find((theme) => theme.key === user.theme_key)?.label ?? "暖纸与陶土"
    case "landing": return user.default_landing_page === "chat" ? "聊天页" : "管理页"
  }
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
    <button aria-expanded={active} className="account-menu__setting-toggle" onClick={onToggle} type="button">
      <Icon name={icon} size={17} />
      <span><strong>{label}</strong><small>{summary}</small></span>
      <Icon name={active ? "chevron-up" : "chevron-down"} size={17} />
    </button>
    {active ? <div className="account-menu__setting-body">{children}</div> : null}
  </section>
}

export function AccountMenuPanel({ onClose, onUpdated, user }: AccountMenuPanelProps) {
  const [expanded, setExpanded] = useState<AccountSection | null>(null)
  const [nickname, setNickname] = useState(user.nickname ?? "")
  const [avatarColor, setAvatarColor] = useState(user.avatar_color ?? 0)
  const [oldPassword, setOldPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [landing, setLanding] = useState<"chat" | "manage">(user.default_landing_page === "chat" ? "chat" : "manage")
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [saving, setSaving] = useState<AccountSection | null>(null)
  const csrfToken = user.csrf_token ?? ""
  const displayName = user.nickname?.trim() || user.username
  const roleDescription = user.role === "owner" ? "Owner · 系统管理权限" : "用户 · 聊天与精灵空间"

  useEffect(() => {
    setNickname(user.nickname ?? "")
    setAvatarColor(user.avatar_color ?? 0)
    setLanding(user.default_landing_page === "chat" ? "chat" : "manage")
  }, [user.avatar_color, user.default_landing_page, user.nickname])

  const toggle = (section: AccountSection): void => {
    setExpanded((current) => current === section ? null : section)
    setFeedback(null)
  }
  const report = (section: AccountSection, kind: Feedback["kind"], message: string): void => setFeedback({ kind, message, section })
  const saveProfile = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault(); setSaving("profile")
    try {
      await updateProfile({ nickname: nickname.trim(), avatarColor, avatarKind: user.avatar_kind ?? "initials" }, csrfToken)
      await onUpdated(); report("profile", "info", "个人资料已保存。")
    } catch (reason: unknown) { report("profile", "error", errorMessage(reason, "个人资料没有保存")) }
    finally { setSaving(null) }
  }
  const selectTheme = async (themeKey: ThemeKey): Promise<void> => {
    setSaving("theme")
    try {
      await saveTheme(themeKey, csrfToken)
      await onUpdated(); report("theme", "info", "系统配色已保存。")
    } catch (reason: unknown) { report("theme", "error", errorMessage(reason, "系统配色没有保存")) }
    finally { setSaving(null) }
  }
  const savePassword = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault(); setSaving("password")
    try {
      await changePassword(oldPassword, newPassword, csrfToken)
      setOldPassword(""); setNewPassword(""); report("password", "info", "密码已更新。")
    } catch (reason: unknown) { report("password", "error", errorMessage(reason, "密码没有更新")) }
    finally { setSaving(null) }
  }
  const saveLanding = async (): Promise<void> => {
    setSaving("landing")
    try {
      await saveLandingPage(landing, csrfToken)
      await onUpdated(); report("landing", "info", "默认登录页已保存。")
    } catch (reason: unknown) { report("landing", "error", errorMessage(reason, "默认登录页没有保存")) }
    finally { setSaving(null) }
  }

  return <section aria-label="个人与外观设置" className="account-menu__panel">
    <header><p className="brand"><Icon name="user" size={14} />个人设置</p><button aria-label="关闭个人设置" className="account-menu__close" onClick={onClose} type="button"><Icon name="x" /></button></header>
    <section className="account-menu__identity">
      <Avatar name={displayName} />
      <div><h2>{displayName}</h2><p>ID: {user.id} · @{user.username}</p><small>{roleDescription}</small></div>
      <button aria-label="编辑个人资料" className="account-menu__edit" onClick={() => toggle("profile")} type="button"><Icon name="pencil" size={16} /></button>
    </section>
    <SettingRow active={expanded === "profile"} icon="user" label="个人资料" onToggle={() => toggle("profile")} summary={sectionSummary("profile", user)}>
      <form className="account-menu__form" onSubmit={(event) => { void saveProfile(event) }}>
        <label>显示名称<input maxLength={32} onChange={(event) => setNickname(event.target.value)} placeholder={user.username} value={nickname} /></label>
        <label>头像颜色<SelectField ariaLabel="选择头像颜色" onValueChange={(value) => setAvatarColor(Number(value))} options={Array.from({ length: 8 }, (_, index) => ({ label: `颜色 ${index + 1}`, value: String(index) }))} value={String(avatarColor)} /></label>
        <button className="button button--quiet" disabled={saving === "profile"} type="submit">{saving === "profile" ? "正在保存…" : "保存资料"}</button>
      </form>
    </SettingRow>
    <SettingRow active={expanded === "password"} icon="lock-keyhole" label="修改密码" onToggle={() => toggle("password")} summary={sectionSummary("password", user)}>
      <form className="account-menu__form" onSubmit={(event) => { void savePassword(event) }}>
        <label>当前密码<input autoComplete="current-password" onChange={(event) => setOldPassword(event.target.value)} required type="password" value={oldPassword} /></label>
        <label>新密码<input autoComplete="new-password" minLength={6} onChange={(event) => setNewPassword(event.target.value)} required type="password" value={newPassword} /></label>
        <button className="button button--quiet" disabled={saving === "password"} type="submit">{saving === "password" ? "正在更新…" : "更新密码"}</button>
      </form>
    </SettingRow>
    <SettingRow active={expanded === "theme"} icon="palette" label="系统配色" onToggle={() => toggle("theme")} summary={sectionSummary("theme", user)}>
      <div className="account-menu__themes">{THEMES.map((theme) => <button aria-pressed={user.theme_key === theme.key} className={user.theme_key === theme.key ? "theme-choice theme-choice--active" : "theme-choice"} disabled={saving === "theme"} key={theme.key} onClick={() => { void selectTheme(theme.key) }} type="button"><i aria-hidden="true" className={`theme-choice__swatch theme-choice__swatch--${theme.key}`} /><span><strong>{theme.label}</strong><small>{theme.description}</small></span></button>)}</div>
    </SettingRow>
    {user.role === "owner" ? <SettingRow active={expanded === "landing"} icon="house" label="默认登录页" onToggle={() => toggle("landing")} summary={sectionSummary("landing", user)}>
      <div className="account-menu__landing"><SelectField ariaLabel="选择默认登录页" onValueChange={(value) => setLanding(value === "chat" ? "chat" : "manage")} options={[{ label: "管理页", value: "manage" }, { label: "聊天页", value: "chat" }]} value={landing} /><button className="button button--quiet" disabled={saving === "landing"} onClick={() => { void saveLanding() }} type="button">{saving === "landing" ? "正在保存…" : "保存默认页"}</button></div>
    </SettingRow> : null}
    {feedback && expanded === feedback.section ? <p className={feedback.kind === "error" ? "notice notice--error" : "notice notice--info"}>{feedback.message}</p> : null}
  </section>
}

export function AccountMenu({ compact = false, onUpdated, user }: AccountMenuProps) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement | null>(null)
  const displayName = user.nickname?.trim() || user.username

  useEffect(() => {
    if (!open) return undefined
    const closeWhenOutside = (event: MouseEvent): void => {
      if (!(event.target instanceof Element)) return
      const isInsideAccountMenu = root.current?.contains(event.target) ?? false
      const isInsideSelectPortal = event.target.closest(".select-field__content") !== null
      if (!isInsideAccountMenu && !isInsideSelectPortal) setOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent): void => { if (event.key === "Escape") setOpen(false) }
    document.addEventListener("mousedown", closeWhenOutside)
    document.addEventListener("keydown", closeOnEscape)
    return () => { document.removeEventListener("mousedown", closeWhenOutside); document.removeEventListener("keydown", closeOnEscape) }
  }, [open])

  return <div className={compact ? "account-menu account-menu--compact" : "account-menu"} ref={root}>
    <button aria-expanded={open} aria-haspopup="dialog" aria-label={compact ? "打开个人设置" : undefined} className="account-menu__trigger" data-tooltip={compact ? "个人设置" : undefined} onClick={() => setOpen((current) => !current)} type="button">
      <Avatar name={displayName} />
      {!compact ? <span><strong>{displayName}</strong><small>{user.role === "owner" ? "Owner" : "用户设置"}</small></span> : null}
    </button>
    {open ? <AccountMenuPanel onClose={() => setOpen(false)} onUpdated={onUpdated} user={user} /> : null}
  </div>
}
