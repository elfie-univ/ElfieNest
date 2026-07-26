import { useEffect, useState } from "react"

import { ApiError, ownerCameraStatus, ownerSelectCameraView, type CameraStatus } from "../api/client"
import { Notice } from "./Notice"

function cameraCategory(label: string, index: number): string {
  if (index === 0 || label === "整体总览") return "总览"
  if (label.startsWith("区域俯视")) return "区域"
  if (label.endsWith("宿舍")) return "宿舍"
  if (label === "传送室") return "入口"
  return "活动区"
}

export function CameraPreview({ csrfToken }: { readonly csrfToken: string }) {
  const [status, setStatus] = useState<CameraStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = async (): Promise<void> => {
    try {
      setStatus(await ownerCameraStatus())
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "摄像头状态读取失败")
    }
  }
  useEffect(() => { void load() }, [])
  const select = async (index: number): Promise<void> => {
    try {
      await ownerSelectCameraView(index, csrfToken)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "摄像头机位切换失败")
    }
  }
  const labels = status?.labels.length ? status.labels : ["整体总览"]
  return <section className="camera-dialog-content">
    {error ? <Notice kind="error" message={error} /> : null}
    <div className={`camera-preview camera-preview--dialog${status?.online ? " has-frame" : ""}`}>
      {status?.online ? <img alt="精灵巢实时摄像头画面" src={`/api/camera/frame.jpg?v=${status.frame_version}`} /> : <span>摄像头离线</span>}
      <strong>{labels[status?.desired_index ?? 0] ?? "整体总览"}</strong>
      <small>{status?.online ? "Godot 正在上报实时画面" : `期望 ${status?.desired_bed_count ?? "—"} 床位，已上报 ${status?.reported_bed_count ?? "—"}`}</small>
    </div>
    <div aria-label="摄像头机位" className="camera-view-strip" role="listbox">{labels.map((label, index) => <button aria-selected={status?.desired_index === index} className={status?.desired_index === index ? "camera-view-button active" : "camera-view-button"} key={label} onClick={() => { void select(index) }} role="option" type="button"><span>{cameraCategory(label, index)}</span><strong>{label}</strong></button>)}</div>
    {status?.layout_syncing ? <p className="connection-state">Godot 正在同步床位布局。</p> : null}
  </section>
}
