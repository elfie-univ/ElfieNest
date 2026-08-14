import { Button } from "@/components/ui/button"
import type { TFunction } from "i18next"
import { useTranslation } from "react-i18next"

import { Icon } from "../Icon"
import type { ElfieProfileProjection } from "./projection"

type PersonalIdentityFrameProps = {
  readonly onBack: () => void
  readonly onChat: () => void
  readonly portraitOverride?: string
  readonly projection: ElfieProfileProjection
}

export function PersonalIdentityFrame({
  onBack,
  onChat,
  portraitOverride = "",
  projection,
}: PersonalIdentityFrameProps) {
  const { t } = useTranslation("chat")
  const profile = projection.publicProfile
  const species = speciesLabel(profile.speciesId, t)
  const gender = normalizedGender(profile.gender, t)

  return (
    <header className="profile-dossier__identity">
      <Button
        aria-label={t("profile.identity.back")}
        className="profile-dossier__back"
        onClick={onBack}
        size="icon-sm"
        type="button"
        variant="ghost"
      >
        <Icon name="chevron-down" />
      </Button>

      <Portrait name={profile.name} portraitUrl={portraitOverride || profile.portraitUrl} t={t} />

      <div className="profile-dossier__identity-copy">
        <div className="profile-dossier__name-row">
          <h1>{profile.name}</h1>
          <div className="profile-dossier__attributes" aria-label={t("profile.identity.publicAttributes")}>
            {gender === null ? null : (
              <span
                aria-label={gender.label}
                className={`profile-dossier__gender profile-dossier__gender--${gender.tone}`}
              >
                {gender.symbol}
              </span>
            )}
            <span aria-label={species} className="profile-dossier__species">
              {speciesIcon(profile.speciesId)}
            </span>
          </div>
        </div>
        <IdentityMetadata projection={projection} t={t} />
        <div className="profile-dossier__biography">
          <span>{t("profile.identity.biographyLabel")}</span>
          <p>{profile.biography.trim() || t("profile.identity.missingBiography")}</p>
        </div>
      </div>

      <Button className="profile-dossier__chat" onClick={onChat} type="button">
        <Icon name="messages-square" />
        {t("profile.identity.enterChat")}
      </Button>

    </header>
  )
}

function IdentityMetadata({ projection, t }: {
  readonly projection: ElfieProfileProjection
  readonly t: TFunction<"chat">
}) {
  const ageLabel = projection.kind === "adopter" ? projection.adoption.ageLabel : projection.ageLabel
  return (
    <dl className="profile-dossier__metadata">
      <div><dt>{t("profile.identity.age")}</dt><dd>{localizedAge(ageLabel, t)}</dd></div>
      <div><dt>{t("profile.identity.owner")}</dt><dd>{projection.kind === "adopter" ? <strong>{t("profile.identity.me")}</strong> : projection.ownerDisplayName}</dd></div>
      {projection.kind === "adopter" ? (
        <>
          <div><dt>{t("profile.identity.adoptedAt")}</dt><dd>{displayFallback(projection.adoption.adoptedAt, t)}</dd></div>
          <div><dt>{t("profile.identity.id")}</dt><dd>{projection.publicProfile.elfieId}</dd></div>
        </>
      ) : null}
    </dl>
  )
}

type PortraitProps = {
  readonly name: string
  readonly portraitUrl: string
  readonly t: TFunction<"chat">
}

function Portrait({ name, portraitUrl, t }: PortraitProps) {
  const initial = name.trim().slice(0, 1) || "精"
  return (
    <span className="profile-dossier__portrait" aria-label={t("profile.identity.portrait", { name })}>
      {portraitUrl.trim() ? <img alt="" src={portraitUrl} /> : initial}
    </span>
  )
}

function speciesLabel(speciesId: string, t: TFunction<"chat">): string {
  switch (speciesId) {
    case "dog": return t("profile.identity.species.dog")
    case "fox": return t("profile.identity.species.fox")
    case "cat": return t("profile.identity.species.cat")
    default: return speciesId
  }
}

function speciesIcon(speciesId: string): string {
  switch (speciesId) {
    case "dog": return "🐶"
    case "fox": return "🦊"
    case "cat": return "🐱"
    default: return "🐾"
  }
}

function displayFallback(value: string, t: TFunction<"chat">): string {
  return value === "未登记" ? t("profile.identity.notRegistered") : value
}

function localizedAge(value: string, t: TFunction<"chat">): string {
  const months = /^(\d+) 个月$/.exec(value)
  if (months?.[1] !== undefined) return t("profile.identity.months", { count: Number(months[1]) })
  const years = /^(\d+) 岁$/.exec(value)
  if (years?.[1] !== undefined) return t("profile.identity.years", { count: Number(years[1]) })
  return displayFallback(value, t)
}

type GenderMarker = {
  readonly label: string
  readonly symbol: "♂" | "♀"
  readonly tone: "female" | "male"
}

function normalizedGender(gender: string | null, t: TFunction<"chat">): GenderMarker | null {
  switch ((gender?.trim() ?? "").toLowerCase()) {
    case "男":
    case "男性":
    case "male":
    case "m":
    case "♂":
      return { label: t("profile.identity.gender.male"), symbol: "♂", tone: "male" }
    case "女":
    case "女性":
    case "female":
    case "f":
    case "♀":
      return { label: t("profile.identity.gender.female"), symbol: "♀", tone: "female" }
    default:
      return null
  }
}
