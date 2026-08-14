import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import type { AppearanceCaptureAdapter } from "./elfie-profile/appearance-capture"
import type { ElfieProfileProjection } from "./elfie-profile/projection"
import { PersonalIdentityFrame } from "./elfie-profile/PersonalIdentityFrame"
import { ProfileAppearanceStage } from "./elfie-profile/ProfileAppearanceStage"
import { ProfileBigFive } from "./elfie-profile/ProfileBigFive"
import { ProfilePrivateModules } from "./elfie-profile/ProfilePrivateModules"

type ElfieProfilePanelProps = {
  readonly appearanceCapture?: AppearanceCaptureAdapter
  readonly csrfToken?: string | undefined
  readonly onBack: () => void
  readonly onChat: () => void
  readonly onFoodSaved?: (() => Promise<void>) | undefined
  readonly projection: ElfieProfileProjection | null
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
}: ElfieProfilePanelProps) {
  const { t } = useTranslation("chat")
  const [localAvatar, setLocalAvatar] = useState<LocalAvatar | null>(null)

  useEffect(() => {
    setLocalAvatar(null)
  }, [projection?.publicProfile.elfieId])

  if (projection === null) {
    return (
      <section className="profile-dossier profile-dossier--empty">
        <p className="empty">{t("profile.empty")}</p>
      </section>
    )
  }

  const profile = projection.publicProfile
  const portraitOverride = localAvatar?.elfieId === profile.elfieId
    ? localAvatar.previewUrl
    : ""

  return (
    <article className="profile-dossier">
      <PersonalIdentityFrame
        onBack={onBack}
        onChat={onChat}
        portraitOverride={portraitOverride}
        projection={projection}
      />
      <ProfileAppearanceStage
        canCapture={projection.kind === "adopter"}
        capture={appearanceCapture}
        interactive={false}
        onAvatarPreview={(previewUrl) => {
          setLocalAvatar({ elfieId: profile.elfieId, previewUrl })
        }}
        profile={profile}
      />
      <ProfileBigFive elfieId={profile.elfieId} values={profile.bigFive} />
      <ProfilePrivateModules csrfToken={csrfToken} onFoodSaved={onFoodSaved} projection={projection} />
    </article>
  )
}
