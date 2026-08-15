import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import type { AdoptionSpecies } from "../api/me/adoption"
import type { AppearanceCaptureAdapter } from "./elfie-profile/appearance-capture"
import type { ElfieProfileProjection } from "./elfie-profile/projection"
import { PersonalIdentityFrame } from "./elfie-profile/PersonalIdentityFrame"
import { ProfileAppearanceStage } from "./elfie-profile/ProfileAppearanceStage"
import { ProfileBigFive } from "./elfie-profile/ProfileBigFive"
import { ProfilePrivateModules, type ProfilePrivateModuleSection } from "./elfie-profile/ProfilePrivateModules"
import { Icon } from "./Icon"

type ProfileSection = Exclude<ProfilePrivateModuleSection, "all">
type MobileProfileSection = "card" | ProfileSection

type ElfieProfilePanelProps = {
  readonly appearanceCapture?: AppearanceCaptureAdapter
  readonly csrfToken?: string | undefined
  readonly onBack: () => void
  readonly onChat: () => void
  readonly onFoodSaved?: (() => Promise<void>) | undefined
  readonly projection: ElfieProfileProjection | null
  readonly speciesDefinition?: Pick<AdoptionSpecies, "display_name" | "display_name_zh"> | undefined
}

type LocalAvatar = {
  readonly elfieId: string
  readonly previewUrl: string
}

export function ElfieProfilePanel({
  appearanceCapture,
  csrfToken,
  onBack,
  onChat,
  onFoodSaved,
  projection,
  speciesDefinition,
}: ElfieProfilePanelProps) {
  const { t } = useTranslation("chat")
  const [activeSection, setActiveSection] = useState<ProfileSection>("archive")
  const [mobileSection, setMobileSection] = useState<MobileProfileSection>("card")
  const [localAvatar, setLocalAvatar] = useState<LocalAvatar | null>(null)

  useEffect(() => {
    setLocalAvatar(null)
    setActiveSection("archive")
    setMobileSection("card")
  }, [projection?.publicProfile.elfieId])

  if (projection === null) {
    return (
      <section className="profile-dossier profile-dossier--empty">
        <p className="empty" role="status">{t("profile.empty")}</p>
      </section>
    )
  }

  const profile = projection.publicProfile
  const portraitOverride = localAvatar?.elfieId === profile.elfieId
    ? localAvatar.previewUrl
    : ""
  const isAdopter = projection.kind === "adopter"
  const chooseSection = (section: ProfileSection): void => {
    setActiveSection(section)
    setMobileSection(section)
  }
  const backToCard = (): void => {
    setMobileSection("card")
  }
  const handleBack = (): void => {
    if (mobileSection !== "card") {
      backToCard()
      return
    }
    onBack()
  }

  return (
    <article className={`profile-dossier ${mobileSection === "card" ? "profile-dossier--mobile-card" : "profile-dossier--mobile-subpage"}`}>
      <PersonalIdentityFrame
        onBack={handleBack}
        onChat={onChat}
        portraitOverride={portraitOverride}
        projection={projection}
        speciesDefinition={speciesDefinition}
      />
      {isAdopter ? (
        <div className="profile-dossier__mobile-actions" aria-label={t("profile.mobile.actionsLabel")}>
          <Button onClick={() => chooseSection("archive")} type="button" variant="outline">
            {t("profile.tabs.archive")}
          </Button>
          <Button onClick={() => chooseSection("manage")} type="button" variant="outline">
            {t("profile.tabs.manage")}
          </Button>
        </div>
      ) : null}
      <div className="profile-dossier__mobile-subpage-head">
        <Button aria-label={t("profile.mobile.backToCard")} onClick={backToCard} size="icon-sm" type="button" variant="ghost">
          <Icon name="chevron-down" />
        </Button>
        <h2>{t(`profile.tabs.${activeSection}`)}</h2>
      </div>
      {isAdopter ? (
        <nav aria-label={t("profile.tabs.label")} className="profile-dossier__tabs" role="tablist">
          {(["archive", "manage"] as const).map((section) => (
            <button
              aria-selected={activeSection === section}
              className={activeSection === section ? "profile-dossier__tab profile-dossier__tab--active" : "profile-dossier__tab"}
              key={section}
              onClick={() => chooseSection(section)}
              role="tab"
              type="button"
            >
              {t(`profile.tabs.${section}`)}
            </button>
          ))}
        </nav>
      ) : null}
      <div className="profile-dossier__tab-content" role={isAdopter ? "tabpanel" : undefined}>
        {isAdopter && activeSection === "archive" ? (
          <>
            <ProfileAppearanceStage
              canCapture
              capture={appearanceCapture}
              interactive={false}
              onAvatarPreview={(previewUrl) => {
                setLocalAvatar({ elfieId: profile.elfieId, previewUrl })
              }}
              profile={profile}
            />
            <ProfileBigFive elfieId={profile.elfieId} values={profile.bigFive} />
            <ProfilePrivateModules
              csrfToken={csrfToken}
              onFoodSaved={onFoodSaved}
              projection={projection}
              section="archive"
            />
          </>
        ) : null}
        {isAdopter && activeSection === "manage" ? (
          <ProfilePrivateModules
            csrfToken={csrfToken}
            onFoodSaved={onFoodSaved}
            projection={projection}
            section="manage"
          />
        ) : null}
      </div>
    </article>
  )
}
