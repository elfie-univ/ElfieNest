import type { OwnerElfie } from "../api/client"
import { Icon } from "./Icon"

type ElfieIdentityCardProps = {
  readonly elfie: OwnerElfie
  readonly onEdit: () => void
}

export function ElfieIdentityCard({ elfie, onEdit }: ElfieIdentityCardProps) {
  const profile = elfie.profile
  const statusLabel = profile.online_status === "online"
    ? "在线"
    : profile.online_status === "offline" ? "离线" : "状态未知"
  return <article className="elfie-id-card">
    <div aria-label={`${profile.name} 的头像`} className="elfie-id-card__portrait">
      {profile.portrait_url
        ? <img alt={`${profile.name} 的头像`} src={profile.portrait_url} />
        : <span>{profile.name.slice(0, 1)}</span>}
    </div>
    <div className="elfie-id-card__body">
      <span
        className={`status-dot status-dot--${profile.online_status}`}
        title={`在线状态：${statusLabel}`}
      />
      <dl className="elfie-id-card__identity">
        <IdentityField label="姓名" value={profile.name} />
        <IdentityField label="主人" value={elfie.owner.username || "未分配"} />
        <IdentityField label="物种" value={profile.species_id} />
        <IdentityField label="性别" value={profile.gender ?? "未登记"} />
        <IdentityField label="出生日期" value={profile.birth_date ?? "未登记"} />
        <IdentityField label="床位号" value={profile.nest.bed_name ?? "未分配"} />
        <IdentityField className="elfie-id-card__wide" label="唯一 ID" value={elfie.elfie_id} />
        <IdentityField
          className="elfie-id-card__wide elfie-id-card__summary"
          label="简介"
          value={profile.summary ?? "暂无简介"}
        />
      </dl>
      <div className="elfie-id-card__food">
        <div>
          <span>粮食策略：<strong>{elfie.food_policy.default_food}</strong></span>
          <small>回退粮：{elfie.food_policy.fallback_food}</small>
        </div>
        <button
          aria-label={`编辑 ${profile.name} 的粮食策略`}
          className="icon-button"
          onClick={onEdit}
          type="button"
        ><Icon name="pencil" size={16} /></button>
      </div>
    </div>
  </article>
}

function IdentityField({ className, label, value }: {
  readonly className?: string
  readonly label: string
  readonly value: string
}) {
  return <div className={className}><dt>{label}</dt><dd>{value}</dd></div>
}
