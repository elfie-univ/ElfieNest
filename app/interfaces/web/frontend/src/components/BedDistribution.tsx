import { Button } from "@/components/ui/button"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import type { NestBed, NestRoom, OwnerElfie } from "../api/client"
import { compareLocalizedText, currentLocale } from "../i18n/format"
import { Avatar } from "./Avatar"
import { Icon } from "./Icon"
import { SelectField } from "./SelectField"

type BedDistributionProps = {
  readonly elfies: readonly OwnerElfie[]
  readonly onAssign: (elfieId: string, anchorId: string | null) => Promise<boolean>
  readonly rooms: readonly NestRoom[]
}

function assignedBed(elfie: OwnerElfie, beds: readonly NestBed[]): NestBed | undefined {
  return beds.find((bed) => bed.occupant_id === elfie.elfie_id)
    ?? beds.find((bed) => bed.name === elfie.profile.nest.bed_name)
}

export function BedDistribution({ elfies, onAssign, rooms }: BedDistributionProps) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const beds = rooms.flatMap((room) => room.beds)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [selection, setSelection] = useState("unassigned")
  const [saving, setSaving] = useState(false)
  const ordered = [...elfies].sort((left, right) => {
    const leftBed = assignedBed(left, beds)
    const rightBed = assignedBed(right, beds)
    if (!leftBed && rightBed) return -1
    if (leftBed && !rightBed) return 1
    return compareLocalizedText(
      leftBed?.name ?? left.profile.name,
      rightBed?.name ?? right.profile.name,
      locale,
    )
  })
  const beginEdit = (elfie: OwnerElfie): void => {
    setEditingId(elfie.elfie_id)
    setSelection(assignedBed(elfie, beds)?.anchor_id ?? "unassigned")
  }
  const save = async (elfieId: string): Promise<void> => {
    setSaving(true)
    const saved = await onAssign(elfieId, selection === "unassigned" ? null : selection)
    setSaving(false)
    if (saved) setEditingId(null)
  }
  return <section className="nest-side-card bed-distribution"><h3>{t("nest.assignment.title")}</h3>
    <ul aria-label={t("nest.assignment.listLabel")}>{ordered.length === 0 ? <li className="bed-distribution__empty">{t("nest.assignment.empty")}</li> : ordered.map((elfie) => {
      const bed = assignedBed(elfie, beds)
      const editing = editingId === elfie.elfie_id
      return <li key={elfie.elfie_id}>
        <div className="bed-distribution__summary"><Avatar imageUrl={elfie.profile.portrait_url} name={elfie.profile.name} /><span><strong>{elfie.profile.name}</strong><small>{bed?.name ?? t("nest.assignment.unassigned")}</small></span><Button aria-label={t("nest.actions.editBedFor", { name: elfie.profile.name })} onClick={() => beginEdit(elfie)} size="icon" type="button" variant="ghost"><Icon name="pencil" size={16} /></Button></div>
        {editing ? <div className="bed-distribution__editor"><SelectField label={t("nest.assignment.bedFor", { name: elfie.profile.name })} onValueChange={setSelection} options={[{ label: t("nest.assignment.unassigned"), value: "unassigned" }, ...beds.map((item) => ({ disabled: Boolean(item.occupant_id && item.occupant_id !== elfie.elfie_id), label: item.occupant_name ? `${item.name}${t("nest.assignment.occupiedSuffix", { name: item.occupant_name })}` : `${item.name}${t("nest.assignment.freeSuffix")}`, value: item.anchor_id }))]} value={selection} /><div className="manage-actions"><Button disabled={saving} onClick={() => { void save(elfie.elfie_id) }} type="button">{saving ? t("nest.actions.saving") : t("nest.actions.save")}</Button><Button variant="outline" disabled={saving} onClick={() => setEditingId(null)} type="button">{t("nest.actions.cancel")}</Button></div></div> : null}
      </li>
    })}</ul>
  </section>
}
