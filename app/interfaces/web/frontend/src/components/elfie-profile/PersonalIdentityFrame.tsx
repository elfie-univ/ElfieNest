import { Button } from "@/components/ui/button"
import type { TFunction } from "i18next"
import { useTranslation } from "react-i18next"

import type { AdoptionSpecies } from "../../api/me/adoption"
import { Icon } from "../Icon"
import { strongestBigFiveDescriptors } from "./chart-options"
import type { ElfieProfileProjection } from "./projection"

type SpeciesPresentation = Pick<AdoptionSpecies, "display_name" | "display_name_zh">

type PersonalIdentityFrameProps = {
  readonly onBack: () => void
  readonly onChat: () => void
  readonly portraitOverride?: string
  readonly projection: ElfieProfileProjection
  readonly speciesDefinition?: SpeciesPresentation | undefined
}

export function PersonalIdentityFrame({
  onBack,
  onChat,
  portraitOverride = "",
  projection,
  speciesDefinition,
}: PersonalIdentityFrameProps) {
  const { i18n, t } = useTranslation("chat")
  const profile = projection.publicProfile
  const species = speciesLabel(profile.speciesId, speciesDefinition, i18n.resolvedLanguage ?? i18n.language)
  const gender = normalizedGender(profile.gender ?? "male", t)
  const biography = profile.biography.trim()
  const showBiography = biography.toLowerCase() !== "genesis"
  const personalityLabels = {
    openness: t("profile.bigFive.traits.openness.label"),
    conscientiousness: t("profile.bigFive.traits.conscientiousness.label"),
    extraversion: t("profile.bigFive.traits.extraversion.label"),
    agreeableness: t("profile.bigFive.traits.agreeableness.label"),
    neuroticism: t("profile.bigFive.traits.neuroticism.label"),
  } as const
  const personalitySummary = strongestBigFiveDescriptors(profile.bigFive)
    .map(({ trait }) => personalityLabels[trait])
    .join("、")

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
              {species}
            </span>
          </div>
        </div>
        <IdentityMetadata projection={projection} t={t} />
        {personalitySummary ? <div className="profile-dossier__personality">
          <span>{t("profile.identity.personality")}</span>
          <p>{personalitySummary}</p>
        </div> : null}
        {showBiography ? <div className="profile-dossier__biography">
          <span>{t("profile.identity.biographyLabel")}</span>
          <p>{biography || t("profile.identity.missingBiography")}</p>
        </div> : null}
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
      <div><dt><span>{t("profile.identity.age")}</span>：</dt><dd>{localizedAge(ageLabel, t)}</dd></div>
      <div><dt><span>{t("profile.identity.owner")}</span>：</dt><dd>{projection.kind === "adopter" ? <strong>{t("profile.identity.me")}</strong> : projection.ownerDisplayName}</dd></div>
      {projection.kind === "adopter" ? <>
        <div><dt><span>{t("profile.identity.adoptedAt")}</span>：</dt><dd>{displayFallback(formatDateOnly(projection.adoption.adoptedAt), t)}</dd></div>
        <div><dt><span>{t("profile.identity.id")}</span>：</dt><dd>{projection.publicProfile.elfieId}</dd></div>
      </> : null}
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

function speciesLabel(
  speciesId: string,
  definition: SpeciesPresentation | undefined,
  language: string,
): string {
  if (definition !== undefined) {
    return language.startsWith("zh") ? definition.display_name_zh : definition.display_name
  }
  return speciesId
}

function formatDateOnly(value: string | undefined): string {
  return value === undefined ? "未登记" : value.split(/[ T]/)[0] ?? value
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
