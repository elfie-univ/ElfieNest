import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { saveElfiePortrait } from "../api/elfies/profiles"
import type { DiscordAccount, TelegramAccount } from "../api/client"
import type { AdoptionSpecies } from "../api/me/adoption"
import type { AppearanceCapture, AppearanceCaptureAdapter } from "./elfie-profile/appearance-capture"
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
  readonly onAvatarSaved?: (elfieId: string, portraitUrl: string) => void | Promise<void>
  readonly onFoodSaved?: (() => Promise<void>) | undefined
  readonly onTelegramAccountChange?: ((account: TelegramAccount) => void) | undefined
  readonly onTelegramRefresh?: (() => Promise<void>) | undefined
  readonly onDiscordAccountChange?: ((account: DiscordAccount) => void) | undefined
  readonly onDiscordRefresh?: (() => Promise<void>) | undefined
  readonly projection: ElfieProfileProjection | null
  readonly speciesDefinition?: Pick<AdoptionSpecies, "display_name" | "display_name_zh"> | undefined
  readonly telegramAccount?: TelegramAccount | null
  readonly telegramAccountError?: string | null
  readonly telegramAccountLoading?: boolean
  readonly discordAccount?: DiscordAccount | null
  readonly discordAccountError?: string | null
  readonly discordAccountLoading?: boolean
}

type LocalAvatar = {
  readonly elfieId: string
  readonly portraitUrl: string
}

export function ElfieProfilePanel({
  appearanceCapture,
  csrfToken,
  onBack,
  onChat,
  onAvatarSaved,
  onFoodSaved,
  onTelegramAccountChange,
  onTelegramRefresh,
  onDiscordAccountChange,
  onDiscordRefresh,
  projection,
  speciesDefinition,
  telegramAccount = null,
  telegramAccountError = null,
  telegramAccountLoading = false,
  discordAccount = null,
  discordAccountError = null,
  discordAccountLoading = false,
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
    ? localAvatar.portraitUrl
    : ""
  const isAdopter = projection.kind === "adopter"
  const saveAvatar = async (capture: AppearanceCapture): Promise<string> => {
    return saveElfiePortrait(profile.elfieId, capture.blob, csrfToken ?? "")
  }
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
              onAvatarSave={saveAvatar}
              onAvatarSaved={(portraitUrl) => {
                setLocalAvatar({ elfieId: profile.elfieId, portraitUrl })
                void onAvatarSaved?.(profile.elfieId, portraitUrl)
              }}
              profile={profile}
            />
            <ProfileBigFive elfieId={profile.elfieId} values={profile.bigFive} />
            <ProfilePrivateModules
              csrfToken={csrfToken}
              onFoodSaved={onFoodSaved}
              onTelegramAccountChange={onTelegramAccountChange}
              onTelegramRefresh={onTelegramRefresh}
              onDiscordAccountChange={onDiscordAccountChange}
              onDiscordRefresh={onDiscordRefresh}
              projection={projection}
              section="archive"
              telegramAccount={telegramAccount}
              telegramAccountError={telegramAccountError}
              telegramAccountLoading={telegramAccountLoading}
              discordAccount={discordAccount}
              discordAccountError={discordAccountError}
              discordAccountLoading={discordAccountLoading}
            />
          </>
        ) : null}
        {isAdopter && activeSection === "manage" ? (
          <ProfilePrivateModules
            csrfToken={csrfToken}
            onFoodSaved={onFoodSaved}
            onTelegramAccountChange={onTelegramAccountChange}
            onTelegramRefresh={onTelegramRefresh}
            onDiscordAccountChange={onDiscordAccountChange}
            onDiscordRefresh={onDiscordRefresh}
            projection={projection}
            section="manage"
            telegramAccount={telegramAccount}
            telegramAccountError={telegramAccountError}
            telegramAccountLoading={telegramAccountLoading}
            discordAccount={discordAccount}
            discordAccountError={discordAccountError}
            discordAccountLoading={discordAccountLoading}
          />
        ) : null}
      </div>
    </article>
  )
}
