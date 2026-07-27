import { useEffect, useState, type FormEvent } from "react"

import { ApiError, ownerAssignBed, ownerCameraStatus, ownerElfies, ownerRooms, ownerUpdateBedCount, type CameraStatus, type NestRoom, type OwnerElfie } from "../api/client"
import { BedDistribution } from "./BedDistribution"
import { CameraPreview } from "./CameraPreview"
import { ClassicNestFloorPlan } from "./ClassicNestFloorPlan"
import { ConfirmDialog } from "./ConfirmDialog"
import { Icon } from "./Icon"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { NumberField } from "./NumberField"

function cameraSyncLabel(camera: CameraStatus | null): string {
  if (!camera || camera.reported_bed_count === null) return "等待 Godot 上报"
  if (camera.layout_syncing) return "同步中"
  return "已同步"
}

export function OwnerNestPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [rooms, setRooms] = useState<readonly NestRoom[]>([])
  const [elfies, setElfies] = useState<readonly OwnerElfie[]>([])
  const [bedCount, setBedCount] = useState(4)
  const [camera, setCamera] = useState<CameraStatus | null>(null)
  const [showCamera, setShowCamera] = useState(false)
  const [confirmBeds, setConfirmBeds] = useState(false)
  const [savingBeds, setSavingBeds] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = async (): Promise<void> => {
    try {
      const [nextRooms, nextElfies, nextCamera] = await Promise.all([ownerRooms(), ownerElfies(), ownerCameraStatus()])
      setRooms(nextRooms)
      setElfies(nextElfies)
      setCamera(nextCamera)
      const room = nextRooms[0]
      setBedCount(room?.desired_bed_count ?? room?.beds.length ?? 4)
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "精灵巢数据加载失败")
    }
  }
  useEffect(() => { void load() }, [])
  const requestBedUpdate = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault()
    if (!Number.isInteger(bedCount) || bedCount < 4 || bedCount > 32) {
      setError("床位数必须是 4 到 32 的整数。")
      return
    }
    setConfirmBeds(true)
  }
  const confirmBedUpdate = async (): Promise<void> => {
    setSavingBeds(true)
    try {
      await ownerUpdateBedCount(bedCount, csrfToken)
      setNotice("期望床位数已保存，正在等待 Godot 同步布局。")
      setConfirmBeds(false)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "床位布局没有保存")
    } finally {
      setSavingBeds(false)
    }
  }
  const assignBed = async (elfieId: string, anchorId: string | null): Promise<boolean> => {
    try {
      await ownerAssignBed(elfieId, anchorId, csrfToken)
      setNotice(anchorId ? "床位已分配。" : "床位分配已清除。")
      await load()
      return true
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "床位分配没有保存")
      return false
    }
  }
  const room = rooms[0]
  const beds = room?.beds ?? []
  return <section className="nest-console">
    <div className="manage-head"><div><h2>宿舍平面与床位</h2><p>经典宿舍俯视图呈现公共活动带、主干道与床位；几何事实仍由 Godot Runtime 管理。</p></div><button className="button button--quiet" onClick={() => { void load() }} type="button">刷新房间数据</button></div>
    {error ? <Notice kind="error" message={error} /> : null}{notice ? <Notice message={notice} /> : null}
    <div className="nest-console__layout">
      <ClassicNestFloorPlan beds={beds} desiredBedCount={room?.desired_bed_count ?? bedCount} roomName={room?.name ?? "Local Nest"} />
      <aside className="nest-console__side">
        <section className="nest-side-card"><div className="nest-side-card__title"><h3>摄像头</h3><span className={camera?.online ? "status-dot status-dot--online" : "status-dot"}>{camera?.online ? "实时" : "离线"}</span></div><div className={`camera-preview${camera?.online ? " has-frame" : ""}`}>{camera?.online ? <img alt="精灵巢摄像头缩略图" src={`/api/camera/frame.jpg?v=${camera.frame_version}`} /> : <span>摄像头离线</span>}<strong>{camera?.labels[camera.active_index] ?? "整体总览"}</strong></div><button className="button" onClick={() => setShowCamera(true)} type="button"><Icon name="camera" size={16} />打开预览</button></section>
        <form className="nest-side-card" onSubmit={requestBedUpdate}><h3>床位数</h3><NumberField hint={`已上报 ${camera?.reported_bed_count ?? "—"} / 期望 ${camera?.desired_bed_count ?? bedCount} · ${cameraSyncLabel(camera)}`} label="期望床位" max={32} min={4} onChange={setBedCount} value={bedCount} /><button className="button" type="submit">保存布局</button></form>
        <BedDistribution elfies={elfies} onAssign={assignBed} rooms={rooms} />
        <section className="nest-side-card"><h3>房间事件</h3><ul className="nest-events">{beds.filter((bed) => bed.occupant_name).map((bed) => <li key={bed.anchor_id}>{bed.name}：{bed.occupant_name} 已在位</li>)}{beds.every((bed) => !bed.occupant_name) ? <li>暂无床位占用事件</li> : null}</ul></section>
      </aside>
    </div>
    <ManageDialog contentClassName="manage-dialog--camera" description="可在此切换 Godot 已上报的摄像机位。" onOpenChange={setShowCamera} open={showCamera} title="实时房间摄像头"><CameraPreview csrfToken={csrfToken} /></ManageDialog>
    <ConfirmDialog confirmLabel="保存布局" description={`确认向 Godot 提交 ${bedCount} 个期望床位吗？这不会由管理端直接修改 3D 几何。`} onConfirm={() => { void confirmBedUpdate() }} onOpenChange={setConfirmBeds} open={confirmBeds} pending={savingBeds} title="确认调整床位" />
  </section>
}
