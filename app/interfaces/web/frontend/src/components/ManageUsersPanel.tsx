import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ApiError, createManagedUser, deleteManagedUser, ownerUsers, resetManagedUserPassword, updateManagedUser, type OwnerUser } from "../api/client"
import { Avatar } from "./Avatar"
import { ConfirmDialog } from "./ConfirmDialog"
import { Icon } from "./Icon"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"
import { StatusIndicator } from "./StatusIndicator"
import { TextField } from "./TextField"
import { MOCK_USERS } from "./owner-card-mock-data"

export function ManageUsersPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [users, setUsers] = useState<readonly OwnerUser[]>([])
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<OwnerUser | null>(null)
  const [resetting, setResetting] = useState<OwnerUser | null>(null)
  const [deletePending, setDeletePending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [mockMode, setMockMode] = useState(false)
  const showDemoData = (reason?: unknown): void => {
    setUsers(MOCK_USERS)
    setMockMode(true)
    setError(null)
    setNotice(reason instanceof ApiError ? `后端暂不可用，当前显示演示数据：${reason.message}` : "后端暂不可用，当前显示演示数据")
  }
  const load = async (): Promise<void> => {
    try {
      const loadedUsers = await ownerUsers()
      if (loadedUsers.length === 0) {
        showDemoData()
        return
      }
      setUsers(loadedUsers)
      setMockMode(false)
      setError(null)
      setNotice(null)
    } catch (reason: unknown) {
      showDemoData(reason)
    }
  }
  useEffect(() => { void load() }, [])
  const remove = async (entry: OwnerUser): Promise<void> => {
    setDeletePending(true)
    try {
      await deleteManagedUser(entry.account_id, csrfToken)
      setDeleting(null); setNotice("用户已从本地精灵巢移除。"); await load()
    } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "用户没有移除") }
    finally { setDeletePending(false) }
  }
  const resetPassword = async (entry: OwnerUser): Promise<void> => {
    try {
      await resetManagedUserPassword(entry.account_id, csrfToken)
      setResetting(null)
      if (entry.role === "owner") {
        window.location.assign("/login")
        return
      }
      setNotice("密码已重置为 123456。")
    } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "密码没有重置") }
  }
  return <section className="manage-card manage-card--wide">
    <div className="manage-head"><div><h2>本地成员</h2><p>管理员只维护成员关系、领养上限与移除权限；头像、名称和密码<span className="manage-copy__phrase">由用户本人管理</span>。</p></div><div className="manage-actions"><Button onClick={() => setCreating(true)} type="button"><Icon name="plus" size={16} />添加用户</Button><RefreshButton label="刷新" onClick={() => { void load() }} /></div></div>
    {error ? <Notice kind="error" message={error} /> : null}{notice ? <Notice message={notice} /> : null}
    <div className="user-id-grid">{users.length === 0 ? <p className="empty">暂无成员。</p> : users.map((entry) => <UserCard csrfToken={csrfToken} key={entry.account_id} mockMode={mockMode} onError={setError} onRemove={() => setDeleting(entry)} onReset={() => setResetting(entry)} onSaved={async () => { setNotice("领养上限已更新。"); await load() }} user={entry} />)}</div>
    <CreateUserDialog csrfToken={csrfToken} onClose={() => setCreating(false)} onSaved={async () => { setCreating(false); setNotice("本地用户已创建。"); await load() }} open={creating} />
    <ConfirmDialog confirmLabel="确认移除" danger description={deleting ? `确认移除 ${deleting.display_name} 吗？该操作只移除本地成员账号，不会删除精灵。` : "确认移除这个用户吗？"} onConfirm={() => { if (deleting) void remove(deleting) }} onOpenChange={(open) => { if (!open && !deletePending) setDeleting(null) }} open={deleting !== null} pending={deletePending} title="移除本地用户" />
    <ConfirmDialog confirmLabel="重置为 123456" description={resetting ? `确认将 ${resetting.display_name} 的密码重置为 123456 吗？该账号的所有会话会立即失效。` : "确认重置密码吗？"} onConfirm={() => { if (resetting) void resetPassword(resetting) }} onOpenChange={(open) => { if (!open) setResetting(null) }} open={resetting !== null} title="重置登录密码" />
  </section>
}

function UserCard({ csrfToken, mockMode, onError, onRemove, onReset, onSaved, user }: { readonly csrfToken: string; readonly mockMode: boolean; readonly onError: (message: string) => void; readonly onRemove: () => void; readonly onReset: () => void; readonly onSaved: () => Promise<void>; readonly user: OwnerUser }) {
  const [editing, setEditing] = useState(false)
  const [quota, setQuota] = useState(String(user.effective_elfie_limit))
  const [saving, setSaving] = useState(false)
  const protectedRemoval = user.role === "owner" || user.elfie_count > 0
  const presenceLabel = user.online_status === "online" ? "在线" : "离线"
  const deleteReason = user.role === "owner" ? "Owner 不能删除。" : user.elfie_count > 0 ? "名下仍有精灵，不能删除。" : null
  const save = async (): Promise<void> => {
    const nextQuota = Number.parseInt(quota, 10)
    if (!Number.isInteger(nextQuota) || nextQuota < 1) {
      onError("精灵上限必须是不小于 1 的整数。")
      return
    }
    setSaving(true)
    try {
      await updateManagedUser(user.account_id, { elfie_quota_override: nextQuota }, csrfToken)
      setEditing(false)
      await onSaved()
    } catch (reason: unknown) {
      onError(reason instanceof ApiError ? reason.message : "领养上限没有保存")
    } finally {
      setSaving(false)
    }
  }
  const cancel = (): void => {
    setQuota(String(user.effective_elfie_limit))
    setEditing(false)
  }
  return <Card asChild><article className="user-id-card">
    <Avatar imageUrl={user.avatar_url} name={user.display_name} />
    <div className="user-id-card__body">
      <StatusIndicator label={presenceLabel} tone={user.online_status === "online" ? "active" : "inactive"} />
      <dl className="user-id-card__identity">
        <IdentityField label="姓名" value={user.display_name} />
        <IdentityField label="性别" value={user.gender ?? "未登记"} />
        <IdentityField label="登录账号" value={`@${user.account_id}`} />
        <IdentityField label="出生日期" value={user.birth_date ?? "未登记"} />
        <IdentityField label="当前角色" value={user.role === "owner" ? "Owner" : "普通成员"} />
        <IdentityField label="加入时间" value={formatDateOnly(user.created_at)} />
        <IdentityField label="当前精灵数" value={String(user.elfie_count)} />
        <div>
          <dt><label htmlFor={`quota-${user.account_id}`}>精灵上限</label></dt>
          <dd>{editing
            ? <Input aria-label="精灵上限" disabled={saving} id={`quota-${user.account_id}`} inputMode="numeric" min={1} onChange={(event) => setQuota(event.target.value)} type="number" value={quota} />
            : user.effective_elfie_limit}</dd>
        </div>
      </dl>
      <div className="user-id-card__actions">{editing
        ? <><Button aria-label={`保存 ${user.account_id}`} disabled={saving} onClick={() => { void save() }} type="button">保存</Button><Button aria-label={`取消 ${user.account_id}`} disabled={saving} onClick={cancel} type="button" variant="outline">取消</Button></>
        : <Button aria-label={`编辑 ${user.account_id}`} disabled={mockMode} onClick={() => setEditing(true)} type="button" variant="outline"><Icon name="pencil" size={15} />编辑</Button>}<Button aria-label={`重置密码 ${user.account_id}`} disabled={mockMode} onClick={onReset} type="button" variant="outline"><Icon name="lock-keyhole" size={15} />重置密码</Button><Button aria-label={`删除用户 ${user.account_id}`} aria-describedby={deleteReason ? `delete-reason-${user.account_id}` : undefined} disabled={mockMode || protectedRemoval} onClick={onRemove} title={mockMode ? "演示数据不可操作" : deleteReason ?? "删除用户"} type="button" variant="destructive"><Icon name="x" size={15} />删除用户</Button>{mockMode ? <small>演示数据仅供查看。</small> : deleteReason ? <small id={`delete-reason-${user.account_id}`}>{deleteReason}</small> : null}</div>
    </div>
  </article></Card>
}

function IdentityField({ className, label, value }: {
  readonly className?: string
  readonly label: string
  readonly value: string
}) {
  return <div className={className}><dt>{label}</dt><dd>{value}</dd></div>
}

function formatDateOnly(value: string): string {
  return value.split(/[ T]/)[0] ?? value
}

function CreateUserDialog({ csrfToken, onClose, onSaved, open }: { readonly csrfToken: string; readonly onClose: () => void; readonly onSaved: () => Promise<void>; readonly open: boolean }) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const save = async (): Promise<void> => {
    if (!username.trim() || !password) { setError("请输入用户名和初始密码。"); return }
    try { await createManagedUser(username.trim(), password, csrfToken); await onSaved() }
    catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "本地用户没有创建") }
  }
  return <ManageDialog description="当前阶段账号保存在本机。二维码邀请与统一身份将在账户中心接入后实现。" onOpenChange={(next) => { if (!next) onClose() }} open={open} title="添加本地用户"><form onSubmit={(event) => { event.preventDefault(); void save() }}>{error ? <Notice kind="error" message={error} /> : null}<TextField autoFocus label="用户名" onChange={setUsername} required value={username} /><TextField autoComplete="new-password" label="初始密码" onChange={setPassword} required type="password" value={password} /><div className="manage-actions"><Button type="submit">创建用户</Button><Button onClick={onClose} type="button" variant="outline">取消</Button></div></form></ManageDialog>
}
