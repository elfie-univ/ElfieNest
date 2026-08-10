import type { AdminElfie, ElfieFoodPolicy, EmbodimentSession, NestBed, NestRoom } from "../api/client"

export type ManagedElfie = AdminElfie & {
  readonly embodiment: EmbodimentSession
  readonly foodPolicy: ElfieFoodPolicy
  readonly nestBed: NestBed | null
}

export function composeManagedElfies(
  elfies: readonly AdminElfie[],
  policies: ReadonlyMap<string, ElfieFoodPolicy>,
  sessions: readonly EmbodimentSession[],
  rooms: readonly NestRoom[],
): readonly ManagedElfie[] {
  const sessionsByElfie = new Map(sessions.map((session) => [session.elfie_id, session]))
  const bedsByElfie = new Map(
    rooms.flatMap((room) => room.beds)
      .flatMap((bed) => bed.occupant_id === null ? [] : [[bed.occupant_id, bed] as const]),
  )
  return elfies.flatMap((elfie) => {
    const elfieId = elfie.profile.elfie_id
    const foodPolicy = policies.get(elfieId)
    const embodiment = sessionsByElfie.get(elfieId)
    if (foodPolicy === undefined || embodiment === undefined) return []
    return [{
      ...elfie,
      embodiment,
      foodPolicy,
      nestBed: bedsByElfie.get(elfieId) ?? null,
    }]
  })
}
