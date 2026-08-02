import { useState } from "react"
import { useTranslation } from "react-i18next"

import type { OwnerElfie } from "../api/client"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ownerWrite } from "../api/client"
import { currentLocale, segmentWords } from "../i18n/format"
import { describeApiError, type LocalizedErrorState } from "../i18n/errors"
import type { SupportedLocale } from "../i18n/locale"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { StatusIndicator } from "./StatusIndicator"

type ElfieIdentityCardProps = {
  readonly csrfToken: string
  readonly elfie: OwnerElfie
  readonly mockMode?: boolean
  readonly onError: (error: LocalizedErrorState) => void
  readonly onSaved: () => Promise<void>
}

export function ElfieIdentityCard({ csrfToken, elfie, mockMode = false, onError, onSaved }: ElfieIdentityCardProps) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [editing, setEditing] = useState(false)
  const [defaultFood, setDefaultFood] = useState(elfie.food_policy.main_food_id || elfie.food_policy.effective_main_food_id)
  const [saving, setSaving] = useState(false)
  const profile = elfie.profile
  const statusLabel = profile.status.code === "at_nest"
    ? t("elfies.values.atNest")
    : profile.status.code === "awake"
      ? t("elfies.values.awake")
      : profile.status.code === "sleeping"
        ? t("elfies.values.sleeping")
        : t("elfies.values.unknownStatus")
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
      onError(describeApiError(reason, "manage.save"))
    } finally {
      setSaving(false)
    }
  }
  const cancel = (): void => {
    setDefaultFood(elfie.food_policy.main_food_id || elfie.food_policy.effective_main_food_id)
    setEditing(false)
  }
  return <Card asChild><article className="elfie-id-card">
    <div aria-label={t("elfies.aria.portrait", { name: profile.name })} className="elfie-id-card__portrait">
      {profile.portrait_url
        ? <img alt={t("elfies.aria.portrait", { name: profile.name })} src={profile.portrait_url} />
        : <span>{profile.name.slice(0, 1)}</span>}
    </div>
    <div className="elfie-id-card__body">
      <StatusIndicator label={statusLabel} tone={profile.status.tone} />
      <dl className="elfie-id-card__identity">
        <IdentityField label={t("elfies.fields.name")} value={profile.name} />
        <IdentityField label={t("elfies.fields.owner")} value={elfie.owner.display_name ?? elfie.owner.account_id} />
        <IdentityField label={t("elfies.fields.species")} value={profile.species_id} />
        <IdentityField label={t("elfies.fields.gender")} value={profile.gender ?? t("elfies.values.notRegistered")} />
        <IdentityField label={t("elfies.fields.birthDate")} value={profile.birth_date ?? t("elfies.values.notRegistered")} />
        <IdentityField label={t("elfies.fields.adoptionDate")} value={formatDateOnly(elfie.created_at)} />
        <IdentityField label={t("elfies.fields.id")} value={elfie.elfie_id} />
        <IdentityField label={t("elfies.fields.bed")} value={profile.nest.bed_name ?? t("elfies.values.notAssigned")} />
      </dl>
    </div>
    {editing ? <div className="elfie-id-card__editor">
        <SelectField
        disabled={saving}
        label={t("elfies.fields.stapleFood")}
        onValueChange={setDefaultFood}
        options={elfie.food_policy.main_food_options.map((food) => ({ label: food.display_name, value: food.food_id }))}
        value={defaultFood}
      />
    </div> : <dl className="elfie-id-card__food">
      <IdentityField label={t("elfies.fields.stapleFood")} value={elfie.food_policy.main_food_options.find((food) => food.food_id === elfie.food_policy.effective_main_food_id)?.display_name ?? t("elfies.values.none")} />
    </dl>}
    <dl className="elfie-id-card__summary">
      <IdentityField
        label={t("elfies.fields.summary")}
        phraseAware={Boolean(profile.summary)}
        value={profile.summary ?? t("elfies.values.summaryMissing")}
        locale={locale}
      />
    </dl>
    {saving ? <Notice message={t("elfies.notices.savingFood")} /> : null}
    <div className="elfie-id-card__actions">
      {editing
        ? <><Button aria-label={t("elfies.actions.saveFor", { name: profile.name })} disabled={saving || mockMode} onClick={() => { void save() }} type="button">{t("elfies.actions.save")}</Button><Button aria-label={t("elfies.actions.cancelFor", { name: profile.name })} disabled={saving} onClick={cancel} type="button" variant="outline">{t("elfies.actions.cancel")}</Button></>
        : <Button aria-label={t("elfies.actions.editFor", { name: profile.name })} disabled={mockMode} onClick={() => setEditing(true)} type="button" variant="outline">{t("elfies.actions.edit")}</Button>}
    </div>
  </article></Card>
}

function IdentityField({ className, label, locale, phraseAware = false, value }: {
  readonly className?: string
  readonly label: string
  readonly locale?: SupportedLocale
  readonly phraseAware?: boolean
  readonly value: string
}) {
  return <div className={className}><dt>{label}</dt><dd>{phraseAware && locale ? <PhraseAwareText locale={locale} value={value} /> : value}</dd></div>
}

function formatDateOnly(value: string): string {
  return value.split(/[ T]/)[0] ?? value
}

function PhraseAwareText({ locale, value }: { readonly locale: SupportedLocale; readonly value: string }) {
  const segments = segmentWords(value, locale)
  return <>{segments.map((entry) => <span key={entry.index}>{entry.segment}</span>)}</>
}
