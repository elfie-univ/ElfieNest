import type { NestBed } from "../api/client"
import { useTranslation } from "react-i18next"
import "./classic-nest-floorplan.css"

const ACTIVITY_ZONES = [
  { detailKey: "nest.floorplan.diningDetail", key: "dining", titleKey: "nest.floorplan.diningTitle" },
  { detailKey: "nest.floorplan.socialDetail", key: "chat", titleKey: "nest.floorplan.socialTitle" },
  { detailKey: "nest.floorplan.mediaDetail", key: "media", titleKey: "nest.floorplan.mediaTitle" },
  { detailKey: "nest.floorplan.gymDetail", key: "gym", titleKey: "nest.floorplan.gymTitle" },
] as const

type FloorBed = NestBed | undefined

function BedSlot({ bed, index, side }: { readonly bed: FloorBed; readonly index: number; readonly side: "left" | "right" }) {
  const { t } = useTranslation("manage")
  const number = String(index + 1).padStart(2, "0")
  const occupant = bed?.occupant_name ?? t("nest.floorplan.vacant")
  const className = `floor-bed-unit ${side}${bed?.occupant_id ? " occupied" : ""}${bed ? "" : " reserve"}`
  return <div aria-label={t("nest.floorplan.ariaBed", { number, occupant })} className={className}>
    <div className="bed-label-row"><span>{number}</span><strong>{occupant}</strong></div>
    <div className="bed-furniture">
      <div className="upper-bunk"><i /><span>{t("nest.floorplan.bedUpper")}</span></div>
      <div className="under-desk-plan"><i /><b /><span>{t("nest.floorplan.bedDesk")}</span></div>
    </div>
  </div>
}

function ActivityRoom({ groupIndex }: { readonly groupIndex: number }) {
  const { t } = useTranslation("manage")
  const zone = ACTIVITY_ZONES[groupIndex % ACTIVITY_ZONES.length] ?? ACTIVITY_ZONES[0]
  return <div className={`activity-room-card activity-${zone.key}`}>
    <div className="activity-room-head"><strong>{t(zone.titleKey)}</strong><span>{t(zone.detailKey)}</span></div>
    <div className="activity-room-body"><div aria-hidden="true" className={`floor-zone-symbol ${zone.key}-symbol`}><i /><b /><span /></div></div>
  </div>
}

function FloorModule({ beds, groupIndex }: { readonly beds: readonly FloorBed[]; readonly groupIndex: number }) {
  const { t } = useTranslation("manage")
  const offset = groupIndex * 4
  return <div className="floor-module">
    <div className="module-activity-area"><ActivityRoom groupIndex={groupIndex} /></div>
    <div className="main-corridor"><span>{t("nest.floorplan.corridor")}</span></div>
    <div className="module-dorm-area"><div className="room-unit">
      <div className="room-entry"><i /><span>{t("nest.floorplan.roomEntry", { number: groupIndex + 1 })}</span><i /></div>
      <div className="room-interior">
        <div className="bed-stack left"><BedSlot bed={beds[offset]} index={offset} side="left" /><BedSlot bed={beds[offset + 1]} index={offset + 1} side="left" /></div>
        <div className="inner-corridor"><span>{t("nest.floorplan.innerCorridor")}</span></div>
        <div className="bed-stack right"><BedSlot bed={beds[offset + 2]} index={offset + 2} side="right" /><BedSlot bed={beds[offset + 3]} index={offset + 3} side="right" /></div>
      </div>
    </div></div>
  </div>
}

export function ClassicNestFloorPlan({ beds, desiredBedCount, roomName }: { readonly beds: readonly NestBed[]; readonly desiredBedCount: number; readonly roomName: string }) {
  const { t } = useTranslation("manage")
  const count = Math.max(4, desiredBedCount, beds.length)
  const groups = Math.max(1, Math.ceil(count / 4))
  const visualBeds = Array.from({ length: groups * 4 }, (_, index) => beds[index])
  return <section className="room-map-panel">
    <header><strong>{t("nest.floorplan.floorplanTitle", { roomName })}</strong><span>{t("nest.floorplan.sceneSync")}</span></header>
    <div className="room-map-scroll"><div className="room-map" style={{ width: `${96 + groups * 300 + 40}px` }}>
      <div aria-label={t("nest.floorplan.ariaPlan", { roomName })} className="nest-floorplan">
        <aside aria-label={t("nest.floorplan.ariaTerminal")} className="portal-entrance">
          <div className="portal-wall top"><span>{t("nest.floorplan.building")}</span></div>
          <div className="wormhole-terminal"><i className="wormhole-ring outer" /><i className="wormhole-ring inner" /><i className="wormhole-core" /><strong>{t("nest.floorplan.terminal")}</strong><small>{t("nest.floorplan.terminalDetail")}</small></div>
          <div className="portal-wall bottom"><span>{t("nest.floorplan.isolation")}</span></div>
        </aside>
        <div className="floor-modules">{Array.from({ length: groups }, (_, index) => <FloorModule beds={visualBeds} groupIndex={index} key={index} />)}</div>
      </div>
    </div></div>
  </section>
}
