import { useState } from "react"
import {
  Activity, Blocks, Bot, Box, Boxes, BrainCircuit, Cable, Castle, ChartNoAxesCombined,
  CircleUserRound, ContactRound, CookingPot, Cuboid, FileText, Gauge, House, KeyRound,
  LibraryBig, Logs, MessageCircle, MessagesSquare, Network, PanelsTopLeft, Plug, QrCode,
  ScanLine, ScrollText, Send, Settings, ShieldCheck, SlidersHorizontal, Smartphone,
  Sparkles, Trees, UsersRound, UserRoundCog, Utensils, WandSparkles, Wheat, Wrench
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

import { iconCatalog, type CatalogIconName } from "./iconCatalog"

const iconComponents = {
  activity: Activity,
  gauge: Gauge,
  chart: ChartNoAxesCombined,
  scroll: ScrollText,
  logs: Logs,
  file: FileText,
  bot: Bot,
  sparkles: Sparkles,
  wand: WandSparkles,
  house: House,
  castle: Castle,
  trees: Trees,
  users: UsersRound,
  contact: ContactRound,
  "user-settings": UserRoundCog,
  plug: Plug,
  cable: Cable,
  network: Network,
  library: LibraryBig,
  boxes: Boxes,
  brain: BrainCircuit,
  utensils: Utensils,
  "cooking-pot": CookingPot,
  wheat: Wheat,
  wrench: Wrench,
  shield: ShieldCheck,
  key: KeyRound,
  settings: Settings,
  sliders: SlidersHorizontal,
  panels: PanelsTopLeft,
  cuboid: Cuboid,
  box: Box,
  blocks: Blocks,
  message: MessageCircle,
  messages: MessagesSquare,
  send: Send,
  qr: QrCode,
  scan: ScanLine,
  phone: Smartphone,
  profile: CircleUserRound
} satisfies Record<CatalogIconName, LucideIcon>

type ChoiceState = Readonly<Record<string, CatalogIconName>>

function selectionSummary(selected: ChoiceState): string {
  return iconCatalog.map((group) => {
    const choice = selected[group.id] ?? group.choices[0].id
    return `${group.label}=${choice}`
  }).join("，")
}

export function IconCatalogPage() {
  const [selected, setSelected] = useState<ChoiceState>({})
  const [copyNotice, setCopyNotice] = useState("")
  const copySelection = async (): Promise<void> => {
    await navigator.clipboard.writeText(selectionSummary(selected))
    setCopyNotice("已复制。直接粘贴回聊天即可。")
  }
  return <main className="icon-catalog-page">
    <header className="icon-catalog-head">
      <div>
        <p className="brand">ELFIENEST · DESKTOP REVIEW</p>
        <h1>图标挑选页</h1>
        <p>图标已内嵌在本页，不依赖外部图片加载。每项点击一个候选，最后复制结果给我即可。</p>
      </div>
      <div className="icon-catalog-actions">
        <a className="button button--quiet" href="https://lucide.dev/icons/" rel="noreferrer" target="_blank">浏览 Lucide 全部图标</a>
        <button className="button" onClick={() => { void copySelection() }} type="button">复制当前选择</button>
      </div>
      {copyNotice && <p className="icon-catalog-notice">{copyNotice}</p>}
    </header>
    <section aria-label="图标候选" className="icon-catalog-grid">
      {iconCatalog.map((group) => <section className="icon-catalog-group" key={group.id}>
        <h2>{group.label}</h2>
        <div className="icon-catalog-choices">
          {group.choices.map((choice, index) => {
            const Icon = iconComponents[choice.id]
            const isSelected = (selected[group.id] ?? group.choices[0].id) === choice.id
            return <article className={`icon-catalog-choice${isSelected ? " icon-catalog-choice--selected" : ""}`} key={choice.id}>
              <button aria-pressed={isSelected} className="icon-catalog-choice__select" onClick={() => { setSelected((current) => ({ ...current, [group.id]: choice.id })); setCopyNotice("") }} type="button">
              <span className="icon-catalog-choice__letter">{String.fromCharCode(65 + index)}</span>
              <Icon aria-hidden="true" size={34} strokeWidth={1.75} />
              <strong>{choice.label}</strong>
              </button>
              <a href={choice.url} rel="noreferrer" target="_blank">查看原图</a>
            </article>
          })}
        </div>
      </section>)}
    </section>
  </main>
}
