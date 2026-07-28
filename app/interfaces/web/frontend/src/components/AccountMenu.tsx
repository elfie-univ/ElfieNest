import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react"

import {
  ApiError,
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
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"

const THEMES = [
  { key: "warm-paper", label: "暖纸与陶土", description: "默认" },
  { key: "harbor-blue", label: "港湾蓝", description: "清爽" },
  { key: "orchid-archive", label: "兰紫档案", description: "安静" },
  { key: "moss-green", label: "苔藓绿", description: "自然" },
] as const satisfies readonly { readonly key: ThemeKey; readonly label: string; readonly description: string }[]

type AccountSection = "landing" | "password" | "theme"
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

function sectionSummary(section: AccountSection, user: ClientUser): string {
  switch (section) {
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
    <button aria-expanded={active} className="account-menu__setting-toggle" data-slot="button" data-variant="ghost" onClick={onToggle} type="button">
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
  const [editingIdentity, setEditingIdentity] = useState(false)
  const [oldPassword, setOldPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [landing, setLanding] = useState<"chat" | "manage">(user.default_landing_page === "chat" ? "chat" : "manage")
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [saving, setSaving] = useState<AccountSection | null>(null)
  const fileInput = useRef<HTMLInputElement | null>(null)
  const csrfToken = user.csrf_token ?? ""
  const displayName = user.nickname?.trim() || user.username
  const roleDescription = user.role === "owner" ? "Owner · 系统管理权限" : "用户 · 聊天与精灵空间"

  useEffect(() => {
    setNickname(user.nickname ?? "")
    setLanding(user.default_landing_page === "chat" ? "chat" : "manage")
  }, [user.default_landing_page, user.nickname])

  const toggle = (section: AccountSection): void => {
    setExpanded((current) => current === section ? null : section)
    setFeedback(null)
  }
  const report = (section: AccountSection, kind: Feedback["kind"], message: string): void => setFeedback({ kind, message, section })
  const saveIdentity = async (): Promise<void> => {
    setSaving("theme")
    try {
      await updateProfile({ nickname: nickname.trim() }, csrfToken)
      await onUpdated(); setEditingIdentity(false)
    } catch (reason: unknown) {
      report("theme", "error", reason instanceof ApiError ? reason.message : "显示名称没有保存")
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
      report("theme", "error", reason instanceof ApiError ? reason.message : "头像没有上传")
    }
    finally { setSaving(null) }
  }
  const selectTheme = async (themeKey: ThemeKey): Promise<void> => {
    setSaving("theme")
    try {
      await saveTheme(themeKey, csrfToken)
      await onUpdated(); report("theme", "info", "系统配色已保存。")
    } catch (reason: unknown) {
      report("theme", "error", reason instanceof ApiError ? reason.message : "系统配色没有保存")
    }
    finally { setSaving(null) }
  }
  const savePassword = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault(); setSaving("password")
    try {
      await changePassword(oldPassword, newPassword, csrfToken)
      setOldPassword(""); setNewPassword(""); report("password", "info", "密码已更新。")
    } catch (reason: unknown) {
      report("password", "error", reason instanceof ApiError ? reason.message : "密码没有更新")
    }
    finally { setSaving(null) }
  }
  const saveLanding = async (): Promise<void> => {
    setSaving("landing")
    try {
      await saveLandingPage(landing, csrfToken)
      await onUpdated(); report("landing", "info", "默认登录页已保存。")
    } catch (reason: unknown) {
      report("landing", "error", reason instanceof ApiError ? reason.message : "默认登录页没有保存")
    }
    finally { setSaving(null) }
  }

  return <section aria-label="个人与外观设置" className="account-menu__panel">
    <header><p className="brand"><Icon name="user" size={14} />个人设置</p><Button aria-label="关闭个人设置" className="account-menu__close" onClick={onClose} size="icon" type="button" variant="ghost"><Icon name="x" /></Button></header>
    <section className="account-menu__identity">
      <input accept="image/png,image/jpeg,image/webp" aria-label="上传本地头像" className="account-menu__avatar-input" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadIdentityAvatar(file); event.target.value = "" }} ref={fileInput} type="file" />
      <button aria-label="上传本地头像" className="account-menu__avatar-button" data-slot="button" data-variant="ghost" disabled={saving !== null} onClick={() => fileInput.current?.click()} type="button"><Avatar imageUrl={user.avatar_url} name={displayName} /></button>
      <div>{editingIdentity ? <Input aria-label="显示名称" autoFocus maxLength={32} onChange={(event) => setNickname(event.target.value)} onKeyDown={saveIdentityOnEnter} placeholder={user.username} value={nickname} /> : <h2>{displayName}</h2>}<p>@{user.account_id}</p><small>{roleDescription}</small></div>
      <Button aria-label={editingIdentity ? "保存显示名称" : "编辑显示名称"} className="account-menu__edit" disabled={saving !== null} onClick={() => { if (editingIdentity) void saveIdentity(); else setEditingIdentity(true) }} size="icon" type="button" variant="ghost"><Icon name="pencil" size={16} /></Button>
    </section>
    <SettingRow active={expanded === "password"} icon="lock-keyhole" label="修改密码" onToggle={() => toggle("password")} summary={sectionSummary("password", user)}>
      <form className="account-menu__form" onSubmit={(event) => { void savePassword(event) }}>
        <TextField autoComplete="current-password" label="当前密码" onChange={setOldPassword} required type="password" value={oldPassword} />
        <TextField autoComplete="new-password" label="新密码" minLength={6} onChange={setNewPassword} required type="password" value={newPassword} />
        <Button variant="outline" disabled={saving === "password"} type="submit">{saving === "password" ? "正在更新…" : "更新密码"}</Button>
      </form>
    </SettingRow>
    <SettingRow active={expanded === "theme"} icon="palette" label="系统配色" onToggle={() => toggle("theme")} summary={sectionSummary("theme", user)}>
      <div className="account-menu__themes">{THEMES.map((theme) => <button aria-pressed={user.theme_key === theme.key} className={user.theme_key === theme.key ? "theme-choice theme-choice--active" : "theme-choice"} data-slot="button" data-variant="outline" disabled={saving === "theme"} key={theme.key} onClick={() => { void selectTheme(theme.key) }} type="button"><i aria-hidden="true" className={`theme-choice__swatch theme-choice__swatch--${theme.key}`} /><span><strong>{theme.label}</strong><small>{theme.description}</small></span></button>)}</div>
    </SettingRow>
    {user.role === "owner" ? <SettingRow active={expanded === "landing"} icon="house" label="默认登录页" onToggle={() => toggle("landing")} summary={sectionSummary("landing", user)}>
      <div className="account-menu__landing"><SelectField label="默认登录页" onValueChange={(value) => setLanding(value === "chat" ? "chat" : "manage")} options={[{ label: "管理页", value: "manage" }, { label: "聊天页", value: "chat" }]} value={landing} /><Button variant="outline" disabled={saving === "landing"} onClick={() => { void saveLanding() }} type="button">{saving === "landing" ? "正在保存…" : "保存默认页"}</Button></div>
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
      const isInsideSelectPortal = event.target.closest('[data-slot="select-content"], [role="listbox"], [role="option"]') !== null
      if (!isInsideAccountMenu && !isInsideSelectPortal) setOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent): void => { if (event.key === "Escape") setOpen(false) }
    document.addEventListener("mousedown", closeWhenOutside)
    document.addEventListener("keydown", closeOnEscape)
    return () => { document.removeEventListener("mousedown", closeWhenOutside); document.removeEventListener("keydown", closeOnEscape) }
  }, [open])

  return <div className={compact ? "account-menu account-menu--compact" : "account-menu"} ref={root}>
    <button aria-expanded={open} aria-haspopup="dialog" aria-label={compact ? "打开个人设置" : undefined} className="account-menu__trigger" data-slot="button" data-tooltip={compact ? "个人设置" : undefined} data-variant="ghost" onClick={() => setOpen((current) => !current)} type="button">
      <Avatar imageUrl={user.avatar_url} name={displayName} />
      {!compact ? <span><strong>{displayName}</strong><small>{user.role === "owner" ? "Owner" : "用户设置"}</small></span> : null}
    </button>
    {open ? <AccountMenuPanel onClose={() => setOpen(false)} onUpdated={onUpdated} user={user} /> : null}
  </div>
}
