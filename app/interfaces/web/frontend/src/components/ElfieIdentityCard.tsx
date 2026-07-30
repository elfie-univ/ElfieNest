import { useState } from "react"

import type { OwnerElfie } from "../api/client"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ApiError, ownerWrite } from "../api/client"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { StatusIndicator } from "./StatusIndicator"

const zhWordSegmenter = new Intl.Segmenter("zh-CN", { granularity: "word" })

type ElfieIdentityCardProps = {
  readonly csrfToken: string
  readonly elfie: OwnerElfie
  readonly mockMode?: boolean
  readonly onError: (message: string) => void
  readonly onSaved: () => Promise<void>
}

export function ElfieIdentityCard({ csrfToken, elfie, mockMode = false, onError, onSaved }: ElfieIdentityCardProps) {
  const [editing, setEditing] = useState(false)
  const [defaultFood, setDefaultFood] = useState(elfie.food_policy.main_food_id || elfie.food_policy.effective_main_food_id)
  const [saving, setSaving] = useState(false)
  const profile = elfie.profile
  const statusLabel = profile.status.label || "状态未知"
  const save = async (): Promise<void> => {
    setSaving(true)
    try {
      await ownerWrite(
        `/api/user/elfies/${encodeURIComponent(elfie.elfie_id)}/food-policy/`,
        "PUT",
        csrfToken,
        {
          main_food_id: defaultFood,
        },
      )
      setEditing(false)
      await onSaved()
    } catch (reason: unknown) {
      onError(reason instanceof ApiError ? reason.message : "粮食策略没有保存")
    } finally {
      setSaving(false)
    }
  }
  const cancel = (): void => {
    setDefaultFood(elfie.food_policy.main_food_id || elfie.food_policy.effective_main_food_id)
    setEditing(false)
  }
  return <Card asChild><article className="elfie-id-card">
    <div aria-label={`${profile.name} 的头像`} className="elfie-id-card__portrait">
      {profile.portrait_url
        ? <img alt={`${profile.name} 的头像`} src={profile.portrait_url} />
        : <span>{profile.name.slice(0, 1)}</span>}
    </div>
    <div className="elfie-id-card__body">
      <StatusIndicator label={statusLabel} tone={profile.status.tone} />
      <dl className="elfie-id-card__identity">
        <IdentityField label="姓名" value={profile.name} />
        <IdentityField label="主人姓名" value={elfie.owner.username || "未分配"} />
        <IdentityField label="物种" value={profile.species_id} />
        <IdentityField label="性别" value={profile.gender ?? "未登记"} />
        <IdentityField label="出生日期" value={profile.birth_date ?? "未登记"} />
        <IdentityField label="领养日期" value={formatDateOnly(elfie.created_at)} />
        <IdentityField label="ID" value={elfie.elfie_id} />
        <IdentityField label="床位号" value={profile.nest.bed_name ?? "未分配"} />
      </dl>
    </div>
    {editing ? <div className="elfie-id-card__editor">
        <SelectField
        disabled={saving}
        label="主粮"
        onValueChange={setDefaultFood}
        options={elfie.food_policy.main_food_options.map((food) => ({ label: food.display_name, value: food.food_id }))}
        value={defaultFood}
      />
    </div> : <dl className="elfie-id-card__food">
      <IdentityField label="主粮" value={elfie.food_policy.main_food_options.find((food) => food.food_id === elfie.food_policy.effective_main_food_id)?.display_name ?? "未配置"} />
    </dl>}
    <dl className="elfie-id-card__summary">
      <IdentityField
        label="简介"
        phraseAware={Boolean(profile.summary)}
        value={profile.summary ?? "暂无简介"}
      />
    </dl>
    {saving ? <Notice message="正在保存粮食策略…" /> : null}
    <div className="elfie-id-card__actions">
      {editing
        ? <><Button aria-label={`保存 ${profile.name}`} disabled={saving || mockMode} onClick={() => { void save() }} type="button">保存</Button><Button aria-label={`取消 ${profile.name}`} disabled={saving} onClick={cancel} type="button" variant="outline">取消</Button></>
        : <Button aria-label={`编辑 ${profile.name}`} disabled={mockMode} onClick={() => setEditing(true)} type="button" variant="outline">编辑</Button>}
    </div>
  </article></Card>
}

function IdentityField({ className, label, phraseAware = false, value }: {
  readonly className?: string
  readonly label: string
  readonly phraseAware?: boolean
  readonly value: string
}) {
  return <div className={className}><dt>{label}</dt><dd>{phraseAware ? <PhraseAwareText value={value} /> : value}</dd></div>
}

function formatDateOnly(value: string): string {
  return value.split(/[ T]/)[0] ?? value
}

function PhraseAwareText({ value }: { readonly value: string }) {
  const segments = [...zhWordSegmenter.segment(value)]
  return <>{segments.map((entry) => <span key={entry.index}>{entry.segment}</span>)}</>
}
