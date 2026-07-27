import type { NestBed } from "../api/client"
import "./classic-nest-floorplan.css"

const ACTIVITY_ZONES = [
  { detail: "开放厨房 + 长餐桌", key: "dining", title: "聚餐区" },
  { detail: "圆桌聊天 + 交友", key: "chat", title: "休闲区" },
  { detail: "大沙发 + 大电视", key: "media", title: "影音室" },
  { detail: "器械 + 自由力量区", key: "gym", title: "健身房" },
] as const

type FloorBed = NestBed | undefined

function occupantLabel(bed: FloorBed): string {
  if (!bed) return "空闲"
  return bed.occupant_name ?? "空闲"
}

function BedSlot({ bed, index, side }: { readonly bed: FloorBed; readonly index: number; readonly side: "left" | "right" }) {
  const number = String(index + 1).padStart(2, "0")
  const occupant = occupantLabel(bed)
  const className = `floor-bed-unit ${side}${bed?.occupant_id ? " occupied" : ""}${bed ? "" : " reserve"}`
  return <div aria-label={`床位 ${number} · ${occupant}`} className={className}>
    <div className="bed-label-row"><span>{number}</span><strong>{occupant}</strong></div>
    <div className="bed-furniture">
      <div className="upper-bunk"><i /><span>上铺</span></div>
      <div className="under-desk-plan"><i /><b /><span>下桌</span></div>
    </div>
  </div>
}

function ActivityRoom({ groupIndex }: { readonly groupIndex: number }) {
  const zone = ACTIVITY_ZONES[groupIndex % ACTIVITY_ZONES.length] ?? ACTIVITY_ZONES[0]
  return <div className={`activity-room-card activity-${zone.key}`}>
    <div className="activity-room-head"><strong>{zone.title}</strong><span>{zone.detail}</span></div>
    <div className="activity-room-body"><div aria-hidden="true" className={`floor-zone-symbol ${zone.key}-symbol`}><i /><b /><span /></div></div>
  </div>
}

function FloorModule({ beds, groupIndex }: { readonly beds: readonly FloorBed[]; readonly groupIndex: number }) {
  const offset = groupIndex * 4
  return <div className="floor-module">
    <div className="module-activity-area"><ActivityRoom groupIndex={groupIndex} /></div>
    <div className="main-corridor"><span>主干道</span></div>
    <div className="module-dorm-area"><div className="room-unit">
      <div className="room-entry"><i /><span>{groupIndex + 1}号房间入口</span><i /></div>
      <div className="room-interior">
        <div className="bed-stack left"><BedSlot bed={beds[offset]} index={offset} side="left" /><BedSlot bed={beds[offset + 1]} index={offset + 1} side="left" /></div>
        <div className="inner-corridor"><span>内部通道</span></div>
        <div className="bed-stack right"><BedSlot bed={beds[offset + 2]} index={offset + 2} side="right" /><BedSlot bed={beds[offset + 3]} index={offset + 3} side="right" /></div>
      </div>
    </div></div>
  </div>
}

export function ClassicNestFloorPlan({ beds, desiredBedCount, roomName }: { readonly beds: readonly NestBed[]; readonly desiredBedCount: number; readonly roomName: string }) {
  const count = Math.max(4, desiredBedCount, beds.length)
  const groups = Math.max(1, Math.ceil(count / 4))
  const visualBeds = Array.from({ length: groups * 4 }, (_, index) => beds[index])
  return <section className="room-map-panel">
    <header><strong>{roomName} · 宿舍俯视图</strong><span>Godot 场景同步</span></header>
    <div className="room-map-scroll"><div className="room-map" style={{ width: `${96 + groups * 300 + 40}px` }}>
      <div aria-label={`${roomName} 建筑平面图`} className="nest-floorplan">
        <aside aria-label="虫洞终端" className="portal-entrance">
          <div className="portal-wall top"><span>主建筑体</span></div>
          <div className="wormhole-terminal"><i className="wormhole-ring outer" /><i className="wormhole-ring inner" /><i className="wormhole-core" /><strong>虫洞终端</strong><small>星际穿越</small></div>
          <div className="portal-wall bottom"><span>隔离边界</span></div>
        </aside>
        <div className="floor-modules">{Array.from({ length: groups }, (_, index) => <FloorModule beds={visualBeds} groupIndex={index} key={index} />)}</div>
      </div>
    </div></div>
  </section>
}
