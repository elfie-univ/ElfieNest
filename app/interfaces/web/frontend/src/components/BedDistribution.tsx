import { Button } from "@/components/ui/button"
import { useState } from "react"

import type { NestBed, NestRoom, OwnerElfie } from "../api/client"
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
  const beds = rooms.flatMap((room) => room.beds)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [selection, setSelection] = useState("unassigned")
  const [saving, setSaving] = useState(false)
  const ordered = [...elfies].sort((left, right) => {
    const leftBed = assignedBed(left, beds)
    const rightBed = assignedBed(right, beds)
    if (!leftBed && rightBed) return -1
    if (leftBed && !rightBed) return 1
    return (leftBed?.name ?? left.profile.name).localeCompare(rightBed?.name ?? right.profile.name, "zh-CN")
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
  return <section className="nest-side-card bed-distribution"><h3>床位分布</h3>
    <ul aria-label="床位分布">{ordered.map((elfie) => {
      const bed = assignedBed(elfie, beds)
      const editing = editingId === elfie.elfie_id
      return <li key={elfie.elfie_id}>
        <div className="bed-distribution__summary"><Avatar imageUrl={elfie.profile.portrait_url} name={elfie.profile.name} /><span><strong>{elfie.profile.name}</strong><small>{bed?.name ?? "未分配"}</small></span><Button aria-label={`编辑${elfie.profile.name}的床位`} onClick={() => beginEdit(elfie)} size="icon" type="button" variant="ghost"><Icon name="pencil" size={16} /></Button></div>
        {editing ? <div className="bed-distribution__editor"><SelectField label={`${elfie.profile.name} 床位`} onValueChange={setSelection} options={[{ label: "未分配", value: "unassigned" }, ...beds.map((item) => ({ disabled: Boolean(item.occupant_id && item.occupant_id !== elfie.elfie_id), label: `${item.name}${item.occupant_name ? ` · ${item.occupant_name}` : " · 空闲"}`, value: item.anchor_id }))]} value={selection} /><div className="manage-actions"><Button disabled={saving} onClick={() => { void save(elfie.elfie_id) }} type="button">{saving ? "保存中…" : "保存"}</Button><Button variant="outline" disabled={saving} onClick={() => setEditingId(null)} type="button">取消</Button></div></div> : null}
      </li>
    })}</ul>
  </section>
}
