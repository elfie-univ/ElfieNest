import { Button } from "@/components/ui/button"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Activity, Blocks, Bot, Box, Boxes, BrainCircuit, Cable, Castle, ChartNoAxesCombined,
  CircleUserRound, ContactRound, CookingPot, Cuboid, FileText, Gauge, House, KeyRound,
  LibraryBig, Logs, MessageCircle, MessagesSquare, Network, PanelsTopLeft, Plug, QrCode,
  ScanLine, ScrollText, Send, Settings, ShieldCheck, SlidersHorizontal, Smartphone,
  Sparkles, Trees, UsersRound, UserRoundCog, Utensils, WandSparkles, Wheat, Wrench
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

import {
  iconCatalog,
  type CatalogIconName,
  type IconCatalogGroupId,
} from "./iconCatalog"

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

function selectionSummary(
  selected: ChoiceState,
  groupLabel: (id: IconCatalogGroupId) => string,
): string {
  return iconCatalog.map((group) => {
    const choice = selected[group.id] ?? group.choices[0].id
    return `${groupLabel(group.id)}=${choice}`
  }).join("\n")
}

export function IconCatalogPage() {
  const { t } = useTranslation("manage")
  const [selected, setSelected] = useState<ChoiceState>({})
  const [copyNotice, setCopyNotice] = useState("")
  const copySelection = async (): Promise<void> => {
    await navigator.clipboard.writeText(selectionSummary(
      selected,
      (id) => t(`iconCatalog.groups.${id}`),
    ))
    setCopyNotice(t("iconCatalog.noticeCopied"))
  }
  return <main className="icon-catalog-page">
    <header className="icon-catalog-head">
      <div>
        <p className="brand">{t("iconCatalog.brand")}</p>
        <h1>{t("iconCatalog.title")}</h1>
        <p>{t("iconCatalog.description")}</p>
      </div>
      <div className="icon-catalog-actions">
        <Button asChild variant="outline"><a href="https://lucide.dev/icons/" rel="noreferrer" target="_blank">{t("iconCatalog.actions.browse")}</a></Button>
        <Button onClick={() => { void copySelection() }} type="button">{t("iconCatalog.actions.copy")}</Button>
      </div>
      {copyNotice && <p className="icon-catalog-notice">{copyNotice}</p>}
    </header>
    <section aria-label={t("iconCatalog.gridLabel")} className="icon-catalog-grid">
      {iconCatalog.map((group) => <section className="icon-catalog-group" key={group.id}>
        <h2>{t(`iconCatalog.groups.${group.id}`)}</h2>
        <div className="icon-catalog-choices">
          {group.choices.map((choice, index) => {
            const Icon = iconComponents[choice.id]
            const isSelected = (selected[group.id] ?? group.choices[0].id) === choice.id
            return <article className={`icon-catalog-choice${isSelected ? " icon-catalog-choice--selected" : ""}`} key={choice.id}>
              <button aria-pressed={isSelected} className="icon-catalog-choice__select" data-slot="button" data-variant="outline" onClick={() => { setSelected((current) => ({ ...current, [group.id]: choice.id })); setCopyNotice("") }} type="button">
              <span className="icon-catalog-choice__letter">{String.fromCharCode(65 + index)}</span>
              <Icon aria-hidden="true" size={34} strokeWidth={1.75} />
              <strong>{choice.label}</strong>
              </button>
              <a data-slot="button" data-variant="link" href={choice.url} rel="noreferrer" target="_blank">{t("iconCatalog.actions.source")}</a>
            </article>
          })}
        </div>
      </section>)}
    </section>
  </main>
}
