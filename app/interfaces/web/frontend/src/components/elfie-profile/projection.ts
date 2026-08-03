import type { ExperienceFixture, PublicProfile, PrivateCognition, Viewer } from "./model"

export type VisitorProfileProjection = {
  readonly ageLabel: ExperienceFixture["adoption"]["ageLabel"]
  readonly kind: "visitor"
  readonly ownerDisplayName: string
  readonly publicProfile: PublicProfile
}

export type AdopterProfileProjection = {
  readonly adoption: ExperienceFixture["adoption"]
  readonly kind: "adopter"
  readonly ownerDisplayName: string
  readonly publicProfile: PublicProfile
  readonly privateCognition: PrivateCognition
}

export type ElfieProfileProjection = VisitorProfileProjection | AdopterProfileProjection

export function isAdopterAccount(viewerAccountId: string, adopterAccountId: string): boolean {
  return viewerAccountId === adopterAccountId
}

export function projectElfieProfile(
  viewer: Viewer,
  experience: ExperienceFixture,
): ElfieProfileProjection {
  if (isAdopterAccount(viewer.accountId, experience.adopter.accountId)) {
    return {
      adoption: experience.adoption,
      kind: "adopter",
      ownerDisplayName: experience.adopter.displayName,
      publicProfile: experience.publicProfile,
      privateCognition: experience.privateCognition,
    }
  }
  return {
    ageLabel: experience.adoption.ageLabel,
    kind: "visitor",
    ownerDisplayName: experience.adopter.displayName,
    publicProfile: experience.publicProfile,
  }
}
