import type { AccountRole } from "../../api/roles"
import type { CareSettings, PrivateCognition, PublicProfile } from "../../components/elfie-profile/model"
import type { ElfieProfileProjection } from "../../components/elfie-profile/projection"

export type ViewerFixture = {
  readonly accountId: string
  readonly role: AccountRole
  readonly displayName: string
}

export type ElfieExperienceFixture = {
  readonly adopter: {
    readonly accountId: string
    readonly displayName: string
  }
  readonly adoption: {
    readonly adoptedAt: string
    readonly ageLabel: string
  }
  readonly publicProfile: PublicProfile
  readonly privateCognition: PrivateCognition
  readonly careSettings: CareSettings
}

export function defineViewer(fixture: ViewerFixture): ViewerFixture {
  return fixture
}

export function defineElfieExperience(
  fixture: ElfieExperienceFixture,
): ElfieExperienceFixture {
  return fixture
}

export function projectElfieProfile(
  viewer: ViewerFixture,
  experience: ElfieExperienceFixture,
): ElfieProfileProjection {
  if (viewer.accountId === experience.adopter.accountId) {
    return {
      adoption: experience.adoption,
      kind: "adopter",
      ownerDisplayName: experience.adopter.displayName,
      publicProfile: experience.publicProfile,
      privateCognition: experience.privateCognition,
      careSettings: experience.careSettings,
    }
  }
  return {
    ageLabel: experience.adoption.ageLabel,
    kind: "visitor",
    ownerDisplayName: experience.adopter.displayName,
    publicProfile: experience.publicProfile,
  }
}
