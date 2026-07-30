import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { ownerAssignBed, ownerElfies, ownerRooms, ownerUpdateBedCount, type NestRoom, type OwnerElfie } from "../api/client"
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
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [rooms, setRooms] = useState<readonly NestRoom[]>([])
  const [elfies, setElfies] = useState<readonly OwnerElfie[]>([])
  const [bedCount, setBedCount] = useState(4)
  const [showObserver, setShowObserver] = useState(false)
  const [confirmBeds, setConfirmBeds] = useState(false)
  const [savingBeds, setSavingBeds] = useState(false)
  const [error, setError] = useState<LocalizedErrorState>(null)
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
      setError(describeApiError(reason, "manage.load"))
      setRooms([DEMO_ROOM])
      setElfies(MOCK_ELFIES)
      setBedCount(DEMO_ROOM.desired_bed_count ?? DEMO_ROOM.beds.length)
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
      setNotice(t("nest.notices.layoutSaved"))
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
      setNotice(anchorId ? t("nest.notices.assigned") : t("nest.notices.cleared"))
      await load()
      return true
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
      return false
    }
  }
  const room = rooms[0]
  const beds = room?.beds ?? []
  return <section className="nest-console">
    <div className="manage-head"><div><h2>{t("nest.title")}</h2><p>{t("nest.description")}</p></div><RefreshButton label={t("nest.refresh")} onClick={() => { void load() }} /></div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} /> : null}{notice ? <Notice message={notice} /> : null}
    <div className="nest-console__layout">
      <ClassicNestFloorPlan beds={beds} desiredBedCount={room?.desired_bed_count ?? bedCount} roomName={room?.name ?? "Local Nest"} />
      <aside className="nest-console__side">
        <section className="nest-side-card nest-camera-launch"><div className="nest-side-card__title"><h3>{t("nest.camera.title")}</h3><span className="status-indicator status-indicator--inactive"><i />{t("nest.camera.availableOnDemand")}</span></div><Button onClick={() => setShowObserver(true)} type="button"><Icon name="camera" size={16} />{t("nest.actions.openPreview")}</Button></section>
        <form aria-label={t("nest.bedCount.formLabel")} className="nest-side-card nest-bed-count-form" onSubmit={requestBedUpdate}><h3>{t("nest.bedCount.title")}</h3><NumberField label={t("nest.bedCount.label")} max={32} min={4} onChange={setBedCount} value={bedCount} /><Button type="submit">{t("nest.actions.saveLayout")}</Button></form>
        <BedDistribution elfies={elfies} onAssign={assignBed} rooms={rooms} />
        <section className="nest-side-card"><h3>{t("nest.events.title")}</h3><ul className="nest-events">{beds.flatMap((bed) => bed.occupant_name ? [<li key={bed.anchor_id}>{t("nest.events.occupied", { bed: bed.name, name: bed.occupant_name })}</li>] : [])}{beds.every((bed) => !bed.occupant_name) ? <li>{t("nest.events.empty")}</li> : null}</ul></section>
      </aside>
    </div>
    <ManageDialog contentClassName="manage-dialog--camera" onOpenChange={setShowObserver} open={showObserver} title={t("nest.camera.dialogTitle")}><ObservationMonitor roomId={room?.id ?? "local-nest"} /></ManageDialog>
    <ConfirmDialog confirmLabel={t("nest.actions.saveLayout")} description={t("nest.bedCount.confirmDescription", { count: bedCount })} onConfirm={() => { void confirmBedUpdate() }} onOpenChange={setConfirmBeds} open={confirmBeds} pending={savingBeds} title={t("nest.bedCount.confirmTitle")} />
  </section>
}
