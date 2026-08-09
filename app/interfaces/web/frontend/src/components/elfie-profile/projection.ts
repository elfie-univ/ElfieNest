import type { CareSettings, PublicProfile, PrivateCognition } from "./model"

export type AdoptionMetadata = {
  readonly adoptedAt: string
  readonly ageLabel: string
}

export type VisitorProfileProjection = {
  readonly ageLabel: string
  readonly kind: "visitor"
  readonly ownerDisplayName: string
  readonly publicProfile: PublicProfile
}

export type AdopterProfileProjection = {
  readonly adoption: AdoptionMetadata
  readonly kind: "adopter"
  readonly ownerDisplayName: string
  readonly publicProfile: PublicProfile
  readonly privateCognition: PrivateCognition
  readonly careSettings: CareSettings
}

export type ElfieProfileProjection = VisitorProfileProjection | AdopterProfileProjection

export function isAdopterAccount(viewerAccountId: string, adopterAccountId: string): boolean {
  return viewerAccountId === adopterAccountId
}
