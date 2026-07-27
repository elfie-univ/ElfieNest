import type { ElfieProfile } from "../api/client"
import { Avatar } from "./Avatar"
import { ObserverSurface } from "./ObserverSurface"

type ElfieProfilePanelProps = {
  readonly profile: ElfieProfile | null
}

const BIG_FIVE_LABELS: Readonly<Record<string, string>> = {
  openness: "开放",
  conscientiousness: "尽责",
  extraversion: "外向",
  agreeableness: "亲和",
  neuroticism: "敏感",
}

const SPECIES_LABELS: Readonly<Record<string, string>> = {
  fox: "狐狸精灵",
  dog: "小狗精灵",
}

const EMBODIMENT_LABELS: Readonly<Record<string, string>> = {
  at_nest: "在精灵巢",
  switching_to_hosted: "正在连接外部身体",
  hosted: "外部身体在线",
  returning_to_nest: "正在返回精灵巢",
  offline: "暂时离线",
}

const APPEARANCE_LABELS: Readonly<Record<string, string>> = {
  short: "娇小",
  standard: "匀称",
  tall: "高挑",
  slim: "轻盈",
  plump: "圆润",
}

const POSTURE_LABELS: Readonly<Record<string, string>> = {
  resting: "休息中",
  active: "活动中",
  sleeping: "睡眠中",
  away: "外出中",
}

const APPEARANCE_FIELDS = [
  ["height_label", "身高"],
  ["build_label", "体型"],
] as const

function formatAppearance(profile: ElfieProfile): string {
  const summary = APPEARANCE_FIELDS.flatMap(([key, label]) => {
    const value = profile.appearance[key]
    return typeof value === "string" && value.trim()
      ? [`${label}：${APPEARANCE_LABELS[value] ?? "待补全"}`]
      : []
  }).join(" · ")
  return summary || "外貌资料正在生成"
}

function archiveLabel(elfieId: string): string {
  const shortId = elfieId.replace(/^elfie[-_]/, "").toUpperCase()
  return `档案编号：${shortId || "待分配"}`
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

export function ElfieProfilePanel({ profile }: ElfieProfilePanelProps) {
  if (profile === null) {
    return (
      <section className="elfie-passport elfie-passport--empty">
        <p className="empty">选择一只精灵，右侧会显示身份证、3D 外貌、人格和认知摘要。</p>
      </section>
    )
  }

  const bigFive = Object.entries(profile.big_five)
  const room = profile.nest.room_name ?? "尚未进入精灵巢"
  const bed = profile.nest.bed_name ?? "未设置家位"
  const species = SPECIES_LABELS[profile.species_id] ?? "未知物种"
  const embodiment = EMBODIMENT_LABELS[profile.embodiment.state] ?? "状态待同步"
  const posture = POSTURE_LABELS[profile.nest.posture] ?? "状态待同步"

  return (
    <section className="elfie-passport">
      <header className="passport-identity">
        <Avatar name={profile.name} />
        <div>
          <p className="brand">精灵身份证</p>
          <h1>{profile.name}</h1>
          <p>{species} · {embodiment}</p>
          <div className="passport-tags">
            <span>{archiveLabel(profile.elfie_id)}</span>
            {profile.personality_tags.map((tag) => (
              <span key={tag}>{BIG_FIVE_LABELS[tag] ?? tag}</span>
            ))}
          </div>
        </div>
        <span className="passport-tags"><span>本地 3D 观察</span></span>
      </header>

      <section className="passport-section">
        <div className="section-title">
          <span>外貌</span>
          <strong>3D 个体视图</strong>
          <small>角色已装载 · 可交互</small>
        </div>
        <div className="avatar-stage">
          <Avatar name={profile.name} />
          <p>{formatAppearance(profile)}</p>
        </div>
        <ObserverSurface elfieId={profile.elfie_id} kind="elfie" title={`${profile.name} 的 3D 观察`} />
      </section>

      <section className="passport-section">
        <div className="section-title section-title--row">
          <div><span>内在画像</span><strong>大五人格</strong></div>
          <button className="button button--quiet" type="button">修改</button>
        </div>
        <div className="personality-bars">
          {bigFive.length === 0 ? <p className="empty">人格数据正在补全。</p> : bigFive.map(([key, value]) => (
            <div className="personality-row" key={key}>
              <span>{BIG_FIVE_LABELS[key] ?? key}</span>
              <div><i style={{ inlineSize: percent(value) }} /></div>
              <strong>{percent(value)}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="passport-grid">
        <article><span>记忆与认知</span><strong>0 条经历</strong><p>关键经历、长期记忆与自我叙事会在这里汇总。</p></article>
        <article><span>重要经历</span><strong>待记录</strong><p>保留影响性格与关系变化的事件。</p></article>
        <article><span>关系认知</span><strong>你与家庭</strong><p>展示它对家人、主人和其他精灵的关系理解。</p></article>
        <article><span>知识与信念</span><strong>成长中</strong><p>沉淀它学到的规则、偏好、世界观和边界。</p></article>
        <article><span>世界理解</span><strong>{room}</strong><p>{bed} · 姿态 {posture}</p></article>
        <article><span>配置</span><strong>粮食与模型</strong><p>后续在这里配置这只精灵可用的粮食、模型组和能力边界。</p></article>
      </section>
    </section>
  )
}
