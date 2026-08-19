import { useEffect, useRef, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { adminElfies, ownerAssignBed, ownerRooms, ownerUpdateBedCount, type AdminElfie, type NestRoom } from "../api/client"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { BedDistribution } from "./BedDistribution"
import { ClassicNestFloorPlan } from "./ClassicNestFloorPlan"
import { ConfirmDialog } from "./ConfirmDialog"
import { Icon } from "./Icon"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { NumberField } from "./NumberField"
import { ObservationMonitor } from "./ObservationMonitor"
import { RefreshButton } from "./RefreshButton"
import { useToast } from "./ui/toast"

export function OwnerNestPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [rooms, setRooms] = useState<readonly NestRoom[] | null>(null)
  const [elfies, setElfies] = useState<readonly AdminElfie[] | null>(null)
  const [bedCount, setBedCount] = useState(0)
  const [showObserver, setShowObserver] = useState(false)
  const [confirmBeds, setConfirmBeds] = useState(false)
  const [savingBeds, setSavingBeds] = useState(false)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const { show } = useToast()
  const loadSequence = useRef(0)
  const load = async (): Promise<void> => {
    const sequence = loadSequence.current + 1
    loadSequence.current = sequence
    setRooms(null)
    setElfies(null)
    setBedCount(0)
    setError(null)
    try {
      const [nextRooms, nextElfies] = await Promise.all([ownerRooms(), adminElfies()])
      if (sequence !== loadSequence.current) return
      setRooms(nextRooms)
      setElfies(nextElfies)
      const room = nextRooms[0]
      setBedCount(room?.desired_bed_count ?? room?.beds.length ?? 0)
      setError(null)
    } catch (reason: unknown) {
      if (sequence !== loadSequence.current) return
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.load"))
      setRooms([])
      setElfies([])
      setBedCount(0)
    }
  }
  useEffect(() => { void load() }, [])
  const requestBedUpdate = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault()
    if (!Number.isInteger(bedCount) || bedCount < 4 || bedCount > 32) {
      setError(t("nest.bedCount.validation"))
      return
    }
    setConfirmBeds(true)
  }
  const confirmBedUpdate = async (): Promise<void> => {
    setSavingBeds(true)
    try {
      await ownerUpdateBedCount(bedCount, csrfToken)
      show({ kind: "success", message: t("nest.notices.layoutSaved") })
      setConfirmBeds(false)
      await load()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setSavingBeds(false)
    }
  }
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
  const monitorBedCount = room?.desired_bed_count ?? Math.max(4, bedCount, beds.length)
  return <section className="nest-console">
    <div className="manage-head"><RefreshButton label={t("nest.refresh")} onClick={() => { void load() }} /></div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} /> : null}
    {loading ? <p className="empty">{t("rawData.loading")}</p> : null}
    {!loading && error === null && room === undefined ? <p className="empty">{t("nest.assignment.empty")}</p> : null}
    {!loading && room ? <div className="nest-console__layout">
      <ClassicNestFloorPlan beds={beds} desiredBedCount={room.desired_bed_count ?? bedCount} roomName={room.name} />
      <aside className="nest-console__side">
        <section className="nest-side-card nest-camera-launch"><div className="nest-side-card__title"><h3>{t("nest.camera.title")}</h3></div><Button onClick={() => setShowObserver(true)} type="button"><Icon name="camera" size={16} />{t("nest.actions.openPreview")}</Button></section>
        <form aria-label={t("nest.bedCount.formLabel")} className="nest-side-card nest-bed-count-form" onSubmit={requestBedUpdate}><h3>{t("nest.bedCount.title")}</h3><NumberField label={t("nest.bedCount.label")} max={32} min={4} onChange={setBedCount} value={bedCount} /><Button type="submit">{t("nest.actions.saveLayout")}</Button></form>
        <BedDistribution elfies={loadedElfies} onAssign={assignBed} rooms={loadedRooms} />
        <section className="nest-side-card"><h3>{t("nest.events.title")}</h3><ul className="nest-events">{beds.flatMap((bed) => bed.occupant_name ? [<li key={bed.anchor_id}>{t("nest.events.occupied", { bed: bed.name, name: bed.occupant_name })}</li>] : [])}{beds.every((bed) => !bed.occupant_name) ? <li>{t("nest.events.empty")}</li> : null}</ul></section>
      </aside>
    </div> : null}
    {room ? <ManageDialog contentClassName="manage-dialog--camera" onOpenChange={setShowObserver} open={showObserver} title={t("nest.camera.dialogTitle")}><ObservationMonitor bedCount={monitorBedCount} mode="embedded" roomId={room.id} /></ManageDialog> : null}
    {room ? <ConfirmDialog confirmLabel={t("nest.actions.saveLayout")} description={t("nest.bedCount.confirmDescription", { count: bedCount })} onConfirm={() => { void confirmBedUpdate() }} onOpenChange={setConfirmBeds} open={confirmBeds} pending={savingBeds} title={t("nest.bedCount.confirmTitle")} /> : null}
  </section>
}
