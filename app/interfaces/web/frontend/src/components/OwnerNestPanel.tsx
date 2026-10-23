import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { adminElfies, ownerAssignBed, ownerRooms, type AdminElfie, type NestRoom } from "../api/client"
import { FIXED_BED_COUNT } from "../constants"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { BedDistribution } from "./BedDistribution"
import { ClassicNestFloorPlan } from "./ClassicNestFloorPlan"
import { Icon } from "./Icon"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { ObservationMonitor } from "./ObservationMonitor"
import { RefreshButton } from "./RefreshButton"
import { useToast } from "./ui/toast"

type LayoutSyncState = "idle" | "syncing" | "timed_out"

const LAYOUT_SYNC_INTERVAL_MS = 500
const LAYOUT_SYNC_MAX_ATTEMPTS = 10

export function OwnerNestPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [rooms, setRooms] = useState<readonly NestRoom[] | null>(null)
  const [elfies, setElfies] = useState<readonly AdminElfie[] | null>(null)
  const [showObserver, setShowObserver] = useState(false)
  const [layoutSyncState, setLayoutSyncState] = useState<LayoutSyncState>("idle")
  const [error, setError] = useState<LocalizedErrorState>(null)
  const { show } = useToast()
  const loadSequence = useRef(0)
  const load = async (): Promise<NestRoom | undefined> => {
    const sequence = loadSequence.current + 1
    loadSequence.current = sequence
    setLayoutSyncState("idle")
    setRooms(null)
    setElfies(null)
    setError(null)
    try {
      const [nextRooms, nextElfies] = await Promise.all([ownerRooms(), adminElfies()])
      if (sequence !== loadSequence.current) return undefined
      setRooms(nextRooms)
      setElfies(nextElfies)
      const room = nextRooms[0]
      setError(null)
      return room
    } catch (reason: unknown) {
      if (sequence !== loadSequence.current) return undefined
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.load"))
      setRooms([])
      setElfies([])
      return undefined
    }
  }
  useEffect(() => { void load() }, [])
  const assignBed = async (elfieId: string, anchorId: string | null): Promise<boolean> => {
    try {
      await ownerAssignBed(elfieId, anchorId, csrfToken)
      show({ kind: "success", message: t(anchorId ? "nest.notices.assigned" : "nest.notices.cleared") })
      await load()
      return true
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
      return false
    }
  }
  const loadedRooms = rooms ?? []
  const loadedElfies = elfies ?? []
  const loading = rooms === null || elfies === null
  const room = loadedRooms[0]
  const beds = room?.beds ?? []
  const layoutPending = room !== undefined && beds.length !== room.desired_bed_count
  useEffect(() => {
    if (!layoutPending || layoutSyncState !== "idle") return
    let cancelled = false
    setLayoutSyncState("syncing")
    const poll = async (): Promise<void> => {
      for (let attempt = 0; attempt < LAYOUT_SYNC_MAX_ATTEMPTS; attempt += 1) {
        await new Promise<void>((resolve) => { window.setTimeout(resolve, LAYOUT_SYNC_INTERVAL_MS) })
        if (cancelled) return
        try {
          const nextRooms = await ownerRooms()
          if (cancelled) return
          setRooms(nextRooms)
          const nextRoom = nextRooms[0]
          if (nextRoom === undefined || nextRoom.beds.length === nextRoom.desired_bed_count) {
            setLayoutSyncState("idle")
            return
          }
        } catch {
          // Keep the saved durable value visible; the bounded timeout below
          // tells the owner when the runtime still has not converged.
        }
      }
      if (!cancelled) setLayoutSyncState("timed_out")
    }
    void poll()
    return () => { cancelled = true }
  }, [layoutPending, room?.desired_bed_count])
  const bedCountStatus = layoutPending
    ? layoutSyncState === "timed_out"
      ? t("nest.bedCount.syncTimeout", { applied: beds.length, count: FIXED_BED_COUNT })
      : t("nest.bedCount.applying", { applied: beds.length, count: FIXED_BED_COUNT })
    : room === undefined
      ? null
      : t("nest.bedCount.fixed", { count: FIXED_BED_COUNT })
  return <section className="nest-console">
    <div className="manage-head"><RefreshButton label={t("nest.refresh")} onClick={() => { void load() }} /></div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} /> : null}
    {loading ? <p className="empty">{t("rawData.loading")}</p> : null}
    {!loading && error === null && room === undefined ? <p className="empty">{t("nest.assignment.empty")}</p> : null}
    {!loading && room ? <div className="nest-console__layout">
      <ClassicNestFloorPlan beds={beds} desiredBedCount={FIXED_BED_COUNT} roomName={room.name} />
      <aside className="nest-console__side">
        <section className="nest-side-card nest-camera-launch"><div className="nest-side-card__title"><h3>{t("nest.camera.title")}</h3></div><Button onClick={() => setShowObserver(true)} type="button"><Icon name="camera" size={16} />{t("nest.actions.openPreview")}</Button></section>
        <section aria-label={t("nest.bedCount.title")} className="nest-side-card nest-bed-count-form"><h3>{t("nest.bedCount.title")}</h3>{bedCountStatus ? <p aria-live="polite" className={`nest-bed-count-form__status${layoutPending ? " nest-bed-count-form__status--pending" : ""}`}>{bedCountStatus}</p> : null}</section>
        <BedDistribution elfies={loadedElfies} onAssign={assignBed} rooms={loadedRooms} />
        <section className="nest-side-card"><h3>{t("nest.events.title")}</h3><ul className="nest-events">{beds.flatMap((bed) => bed.occupant_name ? [<li key={bed.anchor_id}>{t("nest.events.occupied", { bed: bed.name, name: bed.occupant_name })}</li>] : [])}{beds.every((bed) => !bed.occupant_name) ? <li>{t("nest.events.empty")}</li> : null}</ul></section>
      </aside>
    </div> : null}
    {room ? <ManageDialog contentClassName="manage-dialog--camera" onOpenChange={setShowObserver} open={showObserver} title={t("nest.camera.dialogTitle")}><ObservationMonitor mode="embedded" roomId={room.id} /></ManageDialog> : null}
  </section>
}
