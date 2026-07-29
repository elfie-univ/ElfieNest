import { Button } from "@/components/ui/button"

import { Icon } from "../Icon"
import type { ElfieProfileProjection } from "./projection"

type PersonalIdentityFrameProps = {
  readonly onBack: () => void
  readonly onChat: () => void
  readonly portraitOverride?: string
  readonly projection: ElfieProfileProjection
}

const SPECIES_LABELS: Readonly<Record<string, string>> = {
  dog: "小狗精灵",
  fox: "狐狸精灵",
}

const MISSING_BIOGRAPHY = "这只精灵还没有留下自我介绍。"

export function PersonalIdentityFrame({
  onBack,
  onChat,
  portraitOverride = "",
  projection,
}: PersonalIdentityFrameProps) {
  const profile = projection.publicProfile
  const species = SPECIES_LABELS[profile.speciesId] ?? profile.speciesId
  const gender = normalizedGender(profile.gender)

  return (
    <header className="profile-dossier__identity">
      <Button
        aria-label="返回我的精灵"
        className="profile-dossier__back"
        onClick={onBack}
        size="icon-sm"
        type="button"
        variant="ghost"
      >
        <Icon name="chevron-down" />
      </Button>

      <Portrait name={profile.name} portraitUrl={portraitOverride || profile.portraitUrl} />

      <div className="profile-dossier__identity-copy">
        <p className="profile-dossier__eyebrow">
          {projection.kind === "adopter" ? "你的精灵" : "精灵资料"}
        </p>
        <h1>{profile.name}</h1>
        <div className="profile-dossier__attributes" aria-label="公开属性">
          <span>{species}</span>
          {gender === null ? null : <span>{gender}</span>}
        </div>
        <IdentityMetadata projection={projection} />
      </div>

      <Button className="profile-dossier__chat" onClick={onChat} type="button">
        <Icon name="messages-square" />
        进入聊天
      </Button>

      <div className="profile-dossier__biography">
        <span>关于我</span>
        <p>{profile.biography.trim() || MISSING_BIOGRAPHY}</p>
      </div>
    </header>
  )
}

function IdentityMetadata({ projection }: { readonly projection: ElfieProfileProjection }) {
  return (
    <dl className="profile-dossier__metadata">
      <div><dt>领养人</dt><dd>{projection.kind === "adopter" ? <strong>我</strong> : projection.ownerDisplayName}</dd></div>
      {projection.kind === "adopter" ? (
        <>
          <div><dt>领养日期</dt><dd>{projection.adoption.adoptedAt}</dd></div>
          <div><dt>年龄</dt><dd>{projection.adoption.ageLabel}</dd></div>
          <div><dt>ID</dt><dd>{projection.publicProfile.elfieId}</dd></div>
        </>
      ) : null}
    </dl>
  )
}

type PortraitProps = {
  readonly name: string
  readonly portraitUrl: string
}

function Portrait({ name, portraitUrl }: PortraitProps) {
  const initial = name.trim().slice(0, 1) || "精"
  return (
    <span className="profile-dossier__portrait" aria-label={`${name} 的头像`}>
      {portraitUrl.trim() ? <img alt="" src={portraitUrl} /> : initial}
    </span>
  )
}

function normalizedGender(gender: string | null): string | null {
  const value = gender?.trim() ?? ""
  return value && value !== "未登记" ? value : null
}
