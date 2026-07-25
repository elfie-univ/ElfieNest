import { useEffect, useState } from "react"
import { z } from "zod"

import { ApiError, ownerRead, ownerWrite } from "../api/client"
import { Notice } from "./Notice"

const CameraStatusSchema = z.object({
  online: z.boolean(), labels: z.array(z.string()), active_index: z.number().int(), desired_index: z.number().int(),
  frame_version: z.number().int(), layout_syncing: z.boolean(), desired_bed_count: z.number().int(), reported_bed_count: z.number().int().nullable()
})
type CameraStatus = z.infer<typeof CameraStatusSchema>

export function CameraPreview({ csrfToken }: { readonly csrfToken: string }) {
  const [status, setStatus] = useState<CameraStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = async (): Promise<void> => {
    try { setStatus(CameraStatusSchema.parse(await ownerRead("/api/camera/status"))); setError(null) }
    catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "摄像头状态读取失败") }
  }
  useEffect(() => { void load() }, [])
  const select = async (index: number): Promise<void> => {
    try { await ownerWrite("/api/camera/view", "PUT", csrfToken, { index }); await load() }
    catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "摄像头机位切换失败") }
  }
  const frameUrl = status === null ? "" : `/api/camera/frame.jpg?v=${status.frame_version}`
  return <section className="manage-card"><div className="manage-head"><div><h2>实时房间摄像头</h2><p>{status?.online ? "Godot 正在上报实时画面。" : "Godot 未上报画面；保留离线状态而不伪造预览。"}</p></div><button className="button button--quiet" onClick={() => { void load() }} type="button">刷新</button></div>{error && <Notice kind="error" message={error} />}{status?.online ? <img alt="精灵巢实时摄像头画面" className="camera-frame" src={frameUrl} /> : <p className="empty">摄像头离线 · 期望 {status?.desired_bed_count ?? "—"} 床位，已上报 {status?.reported_bed_count ?? "—"}</p>}<div className="manage-actions">{status?.labels.map((label, index) => <button className={status.desired_index === index ? "button" : "button button--quiet"} key={label} onClick={() => { void select(index) }} type="button">{label}</button>)}</div>{status?.layout_syncing && <p className="connection-state">Godot 正在同步床位布局。</p>}</section>
}
