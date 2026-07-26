import { useEffect, useState } from "react"

import { ApiError, createManagedUser, deleteManagedUser, ownerUsers, updateManagedUser, type OwnerUser } from "../api/client"
import { Avatar } from "./Avatar"
import { CheckboxField } from "./CheckboxField"
import { ConfirmDialog } from "./ConfirmDialog"
import { Icon } from "./Icon"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { NumberField } from "./NumberField"
import { TextField } from "./TextField"

export function ManageUsersPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [users, setUsers] = useState<readonly OwnerUser[]>([])
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<OwnerUser | null>(null)
  const [deleting, setDeleting] = useState<OwnerUser | null>(null)
  const [deletePending, setDeletePending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = async (): Promise<void> => {
    try { setUsers(await ownerUsers()); setError(null) }
    catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "用户列表加载失败") }
  }
  useEffect(() => { void load() }, [])
  const remove = async (entry: OwnerUser): Promise<void> => {
    setDeletePending(true)
    try {
      await deleteManagedUser(entry.id, csrfToken)
      setDeleting(null); setNotice("用户已从本地精灵巢移除。"); await load()
    } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "用户没有移除") }
    finally { setDeletePending(false) }
  }
  return <section className="manage-card manage-card--wide">
    <div className="manage-head"><div><h2>本地成员</h2><p>管理员只维护成员关系、领养上限与移除权限；头像、名称和密码由用户本人管理。</p></div><div className="manage-actions"><button className="button" onClick={() => setCreating(true)} type="button"><Icon name="plus" size={16} />添加用户</button><button className="button button--quiet" onClick={() => { void load() }} type="button">刷新</button></div></div>
    {error ? <Notice kind="error" message={error} /> : null}{notice ? <Notice message={notice} /> : null}
    <div className="user-id-grid">{users.length === 0 ? <p className="empty">暂无普通用户。</p> : users.map((entry) => <UserCard key={entry.id} onEdit={() => setEditing(entry)} onRemove={() => setDeleting(entry)} user={entry} />)}</div>
    <CreateUserDialog csrfToken={csrfToken} onClose={() => setCreating(false)} onSaved={async () => { setCreating(false); setNotice("本地用户已创建。"); await load() }} open={creating} />
    {editing ? <QuotaDialog csrfToken={csrfToken} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); setNotice("领养上限已更新。"); await load() }} user={editing} /> : null}
    <ConfirmDialog confirmLabel="确认移除" danger description={deleting ? `确认移除 ${deleting.display_name} 吗？该操作只移除本地成员账号，不会删除精灵。` : "确认移除这个用户吗？"} onConfirm={() => { if (deleting) void remove(deleting) }} onOpenChange={(open) => { if (!open && !deletePending) setDeleting(null) }} open={deleting !== null} pending={deletePending} title="移除本地用户" />
  </section>
}

function UserCard({ onEdit, onRemove, user }: { readonly onEdit: () => void; readonly onRemove: () => void; readonly user: OwnerUser }) {
  const protectedRemoval = user.elfie_count > 0
  return <article className="user-id-card">
    <Avatar imageUrl={user.avatar_url} name={user.display_name} />
    <div className="user-id-card__body"><div className="user-id-card__title"><div><h3>{user.display_name}</h3><p>@{user.username} · ID {user.id} · 普通成员</p></div><span className="user-status user-status--unknown"><i />状态未知</span></div><dl><div><dt>名下精灵 / 上限</dt><dd>{user.elfie_count} / {user.effective_elfie_limit}</dd></div><div><dt>上限来源</dt><dd>{user.elfie_quota_override === null ? "系统默认" : "单独设置"}</dd></div><div><dt>加入时间</dt><dd>{user.created_at}</dd></div></dl><div className="user-id-card__actions"><button aria-label={`编辑 ${user.username} 的领养上限`} className="button button--quiet" onClick={onEdit} type="button"><Icon name="pencil" size={15} />编辑上限</button><button aria-label={`移除 ${user.username}`} className="button button--quiet button--danger" disabled={protectedRemoval} onClick={onRemove} title={protectedRemoval ? "名下仍有精灵，不能移除" : "移除用户"} type="button"><Icon name="x" size={15} />移除</button></div></div>
  </article>
}

function QuotaDialog({ csrfToken, onClose, onSaved, user }: { readonly csrfToken: string; readonly onClose: () => void; readonly onSaved: () => Promise<void>; readonly user: OwnerUser }) {
  const [useDefault, setUseDefault] = useState(user.elfie_quota_override === null)
  const [quota, setQuota] = useState(user.effective_elfie_limit)
  const [error, setError] = useState<string | null>(null)
  const save = async (): Promise<void> => {
    try { await updateManagedUser(user.id, { elfie_quota_override: useDefault ? null : quota }, csrfToken); await onSaved() }
    catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "领养上限没有保存") }
  }
  return <ManageDialog description="只修改这个成员最多可领养的精灵数量；账号资料由本人维护。" onOpenChange={(open) => { if (!open) onClose() }} open title="编辑领养上限"><form onSubmit={(event) => { event.preventDefault(); void save() }}>{error ? <Notice kind="error" message={error} /> : null}<CheckboxField checked={useDefault} hint={`当前系统默认上限为 ${user.elfie_quota_override === null ? user.effective_elfie_limit : "全局配置值"}`} label="沿用系统默认上限" onChange={setUseDefault} /><NumberField disabled={useDefault} label="领养上限" max={32} min={1} onChange={setQuota} value={quota} /><div className="manage-actions"><button className="button" type="submit">保存上限</button><button className="button button--quiet" onClick={onClose} type="button">取消</button></div></form></ManageDialog>
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
  return <ManageDialog description="当前阶段账号保存在本机。二维码邀请与统一身份将在账户中心接入后实现。" onOpenChange={(next) => { if (!next) onClose() }} open={open} title="添加本地用户"><form onSubmit={(event) => { event.preventDefault(); void save() }}>{error ? <Notice kind="error" message={error} /> : null}<TextField autoFocus label="用户名" onChange={setUsername} required value={username} /><TextField autoComplete="new-password" label="初始密码" onChange={setPassword} required type="password" value={password} /><div className="manage-actions"><button className="button" type="submit">创建用户</button><button className="button button--quiet" onClick={onClose} type="button">取消</button></div></form></ManageDialog>
}
