import { useState } from "react"
import { useTranslation } from "react-i18next"

import { updateElfieFoodPolicy } from "../api/client"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { currentLocale, segmentWords } from "../i18n/format"
import { describeApiError, type LocalizedErrorState } from "../i18n/errors"
import type { SupportedLocale } from "../i18n/locale"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { StatusIndicator } from "./StatusIndicator"
import type { ManagedElfie } from "./managed-elfie"

type ElfieIdentityCardProps = {
  readonly csrfToken: string
  readonly elfie: ManagedElfie
  readonly onError: (error: LocalizedErrorState) => void
  readonly onSaved: () => Promise<void>
}

export function ElfieIdentityCard({ csrfToken, elfie, onError, onSaved }: ElfieIdentityCardProps) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [editing, setEditing] = useState(false)
  const [defaultFood, setDefaultFood] = useState(elfie.foodPolicy.main_food_id || elfie.foodPolicy.effective_main_food_id)
  const [saving, setSaving] = useState(false)
  const profile = elfie.profile
  const status = profileStatus(elfie.embodiment.state)
  const statusLabel = status.code === "at_nest"
    ? t("elfies.values.atNest")
    : status.code === "awake"
      ? t("elfies.values.awake")
      : status.code === "sleeping"
        ? t("elfies.values.sleeping")
        : t("elfies.values.unknownStatus")
  const save = async (): Promise<void> => {
    setSaving(true)
    try {
      await updateElfieFoodPolicy(elfie.profile.elfie_id, defaultFood, csrfToken)
      setEditing(false)
      await onSaved()
    } catch (reason: unknown) {
      onError(describeApiError(reason, "manage.save"))
    } finally {
      setSaving(false)
    }
  }
  const cancel = (): void => {
    setDefaultFood(elfie.foodPolicy.main_food_id || elfie.foodPolicy.effective_main_food_id)
    setEditing(false)
  }
  return <Card asChild><article className="elfie-id-card">
    <div className="identity-card__layout elfie-id-card__layout">
      <div aria-label={t("elfies.aria.portrait", { name: profile.name })} className="elfie-id-card__portrait">
        {profile.portrait_url
          ? <img alt={t("elfies.aria.portrait", { name: profile.name })} src={profile.portrait_url} />
          : <span>{profile.name.slice(0, 1)}</span>}
      </div>
      <div className="elfie-id-card__body">
        <StatusIndicator label={statusLabel} tone={status.tone} />
        <dl className="elfie-id-card__identity identity-card__primary">
          <IdentityField label={t("elfies.fields.name")} value={profile.name} />
          <IdentityField label={t("elfies.fields.owner")} value={elfie.owner.display_name ?? elfie.owner.account_id} />
          <IdentityField label={t("elfies.fields.species")} value={profile.species_id} />
          <IdentityField label={t("elfies.fields.gender")} value={profile.gender ?? t("elfies.values.notRegistered")} />
        </dl>
        <dl className="elfie-id-card__identity identity-card__secondary">
          <IdentityField label={t("elfies.fields.birthDate")} value={profile.birth_date ?? t("elfies.values.notRegistered")} />
          <IdentityField label={t("elfies.fields.adoptionDate")} value={formatDateOnly(profile.adopted_at)} />
          <IdentityField label={t("elfies.fields.id")} value={profile.elfie_id} />
          <IdentityField label={t("elfies.fields.bed")} value={elfie.nestBed?.name ?? t("elfies.values.notAssigned")} />
        </dl>
      </div>
      {editing ? <div className="elfie-id-card__editor identity-card__full-row">
          <SelectField
          disabled={saving}
          label={t("elfies.fields.stapleFood")}
          onValueChange={setDefaultFood}
          options={elfie.foodPolicy.main_food_options.map((food) => ({ label: food.display_name, value: food.food_id }))}
          value={defaultFood}
        />
      </div> : <dl className="elfie-id-card__food identity-card__full-row">
        <IdentityField label={t("elfies.fields.stapleFood")} value={elfie.foodPolicy.main_food_options.find((food) => food.food_id === elfie.foodPolicy.effective_main_food_id)?.display_name ?? t("elfies.values.none")} />
      </dl>}
      <dl className="elfie-id-card__summary identity-card__full-row">
        <IdentityField
          label={t("elfies.fields.summary")}
          phraseAware={Boolean(profile.summary)}
          value={profile.summary ?? t("elfies.values.summaryMissing")}
          locale={locale}
        />
      </dl>
      {saving ? <Notice message={t("elfies.notices.savingFood")} /> : null}
      <div className="elfie-id-card__actions identity-card__full-row">
        {editing
          ? <><Button aria-label={t("elfies.actions.saveFor", { name: profile.name })} disabled={saving} onClick={() => { void save() }} type="button">{t("elfies.actions.save")}</Button><Button aria-label={t("elfies.actions.cancelFor", { name: profile.name })} disabled={saving} onClick={cancel} type="button" variant="outline">{t("elfies.actions.cancel")}</Button></>
          : <Button aria-label={t("elfies.actions.editFor", { name: profile.name })} onClick={() => setEditing(true)} type="button" variant="outline">{t("elfies.actions.edit")}</Button>}
      </div>
    </div>
  </article></Card>
}

function profileStatus(state: ManagedElfie["embodiment"]["state"]): { readonly code: string; readonly tone: string } {
  switch (state) {
    case "at_nest": return { code: "at_nest", tone: "active" }
    case "hosted": return { code: "awake", tone: "active" }
    case "offline": return { code: "unknown", tone: "inactive" }
    case "switching_to_hosted":
    case "returning_to_nest": return { code: "unknown", tone: "transition" }
  }
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
