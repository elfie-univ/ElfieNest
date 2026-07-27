import { useEffect, useState, type FormEvent } from "react"

import { ApiError, ownerElfies, ownerRead, ownerRooms, ownerWrite, type NestRoom, type OwnerElfie } from "../api/client"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"

type OwnerNestPanelProps = { readonly csrfToken: string }

export function OwnerNestPanel({ csrfToken }: OwnerNestPanelProps) {
  const [rooms, setRooms] = useState<readonly NestRoom[]>([])
  const [elfies, setElfies] = useState<readonly OwnerElfie[]>([])
  const [bedCount, setBedCount] = useState("4")
  const [selectedElfie, setSelectedElfie] = useState("")
  const [selectedHome, setSelectedHome] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = async (): Promise<void> => {
    try {
      const [loadedRooms, loadedElfies] = await Promise.all([ownerRooms(), ownerElfies()])
      setRooms(loadedRooms)
      setElfies(loadedElfies)
      const first = loadedRooms[0]
      setBedCount(String(first?.desired_bed_count ?? first?.beds.length ?? 4))
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "精灵巢数据加载失败")
    }
  }
  useEffect(() => { void load() }, [])

  const updateBeds = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    const parsed = Number(bedCount)
    if (!Number.isInteger(parsed) || parsed < 4 || parsed > 32) { setError("床位数必须是 4 到 32 的整数。"); return }
    if (!window.confirm(`确认将默认精灵巢调整为 ${parsed} 个床位吗？`)) return
    try {
      await ownerWrite("/api/owner/nest/rooms/default/bed-count", "PUT", csrfToken, { bed_count: parsed })
      setNotice("床位布局已保存，Godot 将收到新的期望布局。")
      setError(null)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "床位布局没有保存")
    }
  }
  const assignHome = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (!selectedElfie) { setError("请先选择精灵。"); return }
    try {
      await ownerWrite(`/api/owner/nest/elfies/${encodeURIComponent(selectedElfie)}/bed`, "PUT", csrfToken, { home_anchor_id: selectedHome || null })
      setNotice(selectedHome ? "家位已配置。" : "家位已清除。")
      setError(null)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "家位配置没有保存")
    }
  }
  const homes = rooms.flatMap((room) => room.beds.map((bed) => ({ id: String(bed.id), label: `${room.name} · ${bed.name}` })))
  return <section className="manage-card manage-card--wide">
    <div className="manage-head"><div><h2>精灵巢</h2><p>管理全局房间、床位与家位；家位不改变精灵的用户归属。</p></div><button className="button button--quiet" onClick={() => { void load() }} type="button">刷新</button></div>
    {error && <Notice kind="error" message={error} />}{notice && <Notice message={notice} />}
    <div className="nest-room-grid">{rooms.map((room) => <article className="nest-room" key={room.id}><strong>{room.name}</strong><small>{room.beds.filter((bed) => bed.occupant_name !== null).length}/{room.beds.length} 个床位已使用</small><ul>{room.beds.map((bed) => <li key={bed.id}>{bed.name}：{bed.occupant_name ?? "空闲"}</li>)}</ul></article>)}</div>
    <div className="manager-action-grid"><form className="manage-form" onSubmit={(event) => { void updateBeds(event) }}><label>床位数量<input max="32" min="4" onChange={(event) => setBedCount(event.target.value)} type="number" value={bedCount} /></label><button className="button" type="submit">确认重建布局</button></form><form className="manage-form" onSubmit={(event) => { void assignHome(event) }}><SelectField ariaLabel="选择要配置家位的精灵" onValueChange={setSelectedElfie} options={[{ label: "选择精灵", value: "" }, ...elfies.map((elfie) => ({ label: elfie.profile.name, value: elfie.elfie_id }))]} value={selectedElfie} /><SelectField ariaLabel="选择家位" onValueChange={setSelectedHome} options={[{ label: "清除家位", value: "" }, ...homes.map((home) => ({ label: home.label, value: home.id }))]} value={selectedHome} /><button className="button" type="submit">保存家位</button></form></div>
    <div className="manager-preview-links"><a className="button button--quiet" href="/runtime/godot">打开 Godot Web Runtime</a><CameraStatus /></div>
  </section>
}

function CameraStatus() {
  const [status, setStatus] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)
  const load = async (): Promise<void> => { try { setStatus(await ownerRead("/api/camera/status")); setError(null) } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "摄像头离线") } }
  useEffect(() => { void load() }, [])
  return <div>{error ? <span className="connection-state">摄像头：{error}</span> : <span className="connection-state">摄像头：{status === null ? "正在检查…" : "状态已读取"}</span>}<button className="button button--quiet" onClick={() => { void load() }} type="button">刷新摄像头</button></div>
}
