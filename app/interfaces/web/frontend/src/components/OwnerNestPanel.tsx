import { useEffect, useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import { ApiError, ownerAssignBed, ownerElfies, ownerRooms, ownerUpdateBedCount, type NestRoom, type OwnerElfie } from "../api/client"
import { BedDistribution } from "./BedDistribution"
import { ClassicNestFloorPlan } from "./ClassicNestFloorPlan"
import { ConfirmDialog } from "./ConfirmDialog"
import { Icon } from "./Icon"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { NumberField } from "./NumberField"
import { ObserverSurface } from "./ObserverSurface"
import { MOCK_ELFIES } from "./owner-card-mock-data"
import { RefreshButton } from "./RefreshButton"

const DEMO_ROOM: NestRoom = {
  id: "local-nest",
  name: "Local Nest",
  desired_bed_count: 4,
  beds: [
    { anchor_id: "demo-bed-1", id: "demo-bed-1", name: "床位 1", occupant_id: "12345678", occupant_name: "Happy", occupant_species_id: "fox" },
    { anchor_id: "demo-bed-2", id: "demo-bed-2", name: "床位 2", occupant_id: "23456789", occupant_name: "Kettle", occupant_species_id: "fox" },
    { anchor_id: "demo-bed-3", id: "demo-bed-3", name: "床位 3", occupant_id: null, occupant_name: null, occupant_species_id: null },
    { anchor_id: "demo-bed-4", id: "demo-bed-4", name: "床位 4", occupant_id: null, occupant_name: null, occupant_species_id: null },
  ],
}

export function OwnerNestPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [rooms, setRooms] = useState<readonly NestRoom[]>([])
  const [elfies, setElfies] = useState<readonly OwnerElfie[]>([])
  const [bedCount, setBedCount] = useState(4)
  const [showObserver, setShowObserver] = useState(false)
  const [confirmBeds, setConfirmBeds] = useState(false)
  const [savingBeds, setSavingBeds] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = async (): Promise<void> => {
    try {
      const [nextRooms, nextElfies] = await Promise.all([ownerRooms(), ownerElfies()])
      const visibleRooms = nextRooms.length > 0 ? nextRooms : [DEMO_ROOM]
      const visibleElfies = nextElfies.length > 0 ? nextElfies : MOCK_ELFIES
      setRooms(visibleRooms)
      setElfies(visibleElfies)
      const room = visibleRooms[0]
      setBedCount(room?.desired_bed_count ?? room?.beds.length ?? 4)
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "精灵巢数据加载失败")
      setRooms([DEMO_ROOM])
      setElfies(MOCK_ELFIES)
      setBedCount(DEMO_ROOM.desired_bed_count ?? DEMO_ROOM.beds.length)
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
      setNotice("期望床位数已保存；3D 观察不可用时，平面图与床位分配仍可继续使用。")
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
    <div className="manage-head"><div><h2>宿舍平面与床位</h2><p>经典宿舍俯视图呈现公共活动带、主干道与床位；几何事实仍由 Godot Runtime 管理。</p></div><RefreshButton label="刷新房间数据" onClick={() => { void load() }} /></div>
    {error ? <Notice kind="error" message={error} /> : null}{notice ? <Notice message={notice} /> : null}
    <div className="nest-console__layout">
      <ClassicNestFloorPlan beds={beds} desiredBedCount={room?.desired_bed_count ?? bedCount} roomName={room?.name ?? "Local Nest"} />
      <aside className="nest-console__side">
        <section className="nest-side-card nest-camera-launch"><div className="nest-side-card__title"><h3>摄像头</h3><span className="status-indicator status-indicator--inactive"><i />按需打开</span></div><Button onClick={() => setShowObserver(true)} type="button"><Icon name="camera" size={16} />打开预览</Button></section>
        <form aria-label="床位数量设置" className="nest-side-card nest-bed-count-form" onSubmit={requestBedUpdate}><h3>房间床位数</h3><NumberField label="床位数" max={32} min={4} onChange={setBedCount} value={bedCount} /><Button type="submit">保存布局</Button></form>
        <BedDistribution elfies={elfies} onAssign={assignBed} rooms={rooms} />
        <section className="nest-side-card"><h3>房间事件</h3><ul className="nest-events">{beds.filter((bed) => bed.occupant_name).map((bed) => <li key={bed.anchor_id}>{bed.name}：{bed.occupant_name} 已在位</li>)}{beds.every((bed) => !bed.occupant_name) ? <li>暂无床位占用事件</li> : null}</ul></section>
      </aside>
    </div>
    <ManageDialog contentClassName="manage-dialog--camera" description="在弹窗中进入房间 3D 观察；拖动可查看房间，滚轮或双指缩放。" onOpenChange={setShowObserver} open={showObserver} title="实时房间摄像头"><ObserverSurface kind="room" roomId={room?.id ?? "local-nest"} title="房间 3D 观察" /></ManageDialog>
    <ConfirmDialog confirmLabel="保存布局" description={`确认向 Godot 提交 ${bedCount} 个期望床位吗？这不会由管理端直接修改 3D 几何。`} onConfirm={() => { void confirmBedUpdate() }} onOpenChange={setConfirmBeds} open={confirmBeds} pending={savingBeds} title="确认调整床位" />
  </section>
}
