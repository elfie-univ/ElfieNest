import { useMemo } from "react"
import type { TFunction } from "i18next"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

import { buildGraphOption } from "./chart-options"
import type { ElfieId, GraphProjection, PrivateCognition } from "./model"
import { projectGraph } from "./model"
import {
  loadProfileChartRuntime,
  ProfileChart,
  type ProfileChartRuntime,
} from "./ProfileChart"
import { useProfileChartTheme } from "./use-profile-chart-theme"

type GraphModule = PrivateCognition["modules"][2 | 3 | 4]

type ProfileGraphSectionProps = {
  readonly elfieId: ElfieId
  readonly loadChartRuntime?: () => Promise<ProfileChartRuntime>
  readonly module: GraphModule
}

export function ProfileGraphSection({
  elfieId,
  loadChartRuntime = loadProfileChartRuntime,
  module,
}: ProfileGraphSectionProps) {
  const { t } = useTranslation("chat")
  const theme = useProfileChartTheme()
  const preview = projectGraph(module.graph, "preview")
  const detail = projectGraph(module.graph, "detail")
  const previewOption = useMemo(() => buildGraphOption(preview, theme), [preview, theme])
  const detailOption = useMemo(() => buildGraphOption(detail, theme), [detail, theme])

  const title = moduleTitle(module.title, t)
  return (
    <section className="profile-graph" aria-label={t("profile.graph.graphLabel", { title })}>
      <header className="profile-graph__header">
        <div>
          <strong>{graphLabel(module.title, t)}</strong>
          <span>{t("profile.graph.counts", { edges: module.graph.edges.length, nodes: module.graph.nodes.length })}</span>
        </div>
        <Dialog>
          <DialogTrigger asChild>
            <Button
              aria-label={t("profile.graph.viewDetails", { title })}
              className="profile-graph__detail-trigger"
              type="button"
              variant="outline"
            >
              {t("profile.graph.details")}
            </Button>
          </DialogTrigger>
          <DialogContent className="profile-graph-dialog" showCloseButton={false}>
            <DialogHeader>
              <DialogTitle>{t("profile.graph.detailTitle", { title })}</DialogTitle>
              <DialogDescription>{t("profile.graph.detailDescription")}</DialogDescription>
            </DialogHeader>
            <GraphView
              chartKey={`${elfieId}-${module.title}-detail`}
              graph={detail}
              label={t("profile.graph.detailChart", { title })}
              loadChartRuntime={loadChartRuntime}
              option={detailOption}
              title={title}
              variant="detail"
            />
            <DialogFooter>
              <DialogClose asChild><Button type="button" variant="outline">{t("profile.graph.closeDetails")}</Button></DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </header>
      <GraphView
        chartKey={`${elfieId}-${module.title}-preview`}
        graph={preview}
        label={t("profile.graph.previewChart", { title })}
        loadChartRuntime={loadChartRuntime}
        option={previewOption}
        title={title}
        variant="preview"
      />
    </section>
  )
}

type GraphViewProps = {
  readonly chartKey: string
  readonly graph: GraphProjection
  readonly label: string
  readonly loadChartRuntime: () => Promise<ProfileChartRuntime>
  readonly option: ReturnType<typeof buildGraphOption>
  readonly title: string
  readonly variant: "preview" | "detail"
}

function GraphView({
  chartKey,
  graph,
  label,
  loadChartRuntime,
  option,
  title,
  variant,
}: GraphViewProps) {
  const summary = <GraphSummary graph={graph} title={title} />
  return (
    <div className={`profile-graph__${variant}`}>
      {graph.nodes.length > 0 ? (
        <ProfileChart
          chartKey={chartKey}
          label={label}
          loadRuntime={loadChartRuntime}
          option={option}
          summary={summary}
        />
      ) : (
        summary
      )}
    </div>
  )
}

function GraphSummary({ graph, title }: {
  readonly graph: GraphProjection
  readonly title: string
}) {
  const { t } = useTranslation("chat")
  const labels = new Map(graph.nodes.map((node) => [node.id, node.label]))
  return (
    <div className="profile-graph__summary">
      {graph.nodes.length === 0 && <p>{t("profile.graph.emptyNodes", { title })}</p>}
      {graph.truncatedNodeCount > 0 && (
        <p className="profile-graph__truncation">
          {t("profile.graph.truncated", { hidden: graph.truncatedNodeCount, shown: graph.nodes.length })}
        </p>
      )}
      {graph.edges.length > 0 ? (
        <ul aria-label={t("profile.graph.edgeList", { title })} className="profile-graph__edges">
          {graph.edges.map((edge, index) => (
            <li key={`${edge.source}-${edge.target}-${index}`}>
              <span>{labels.get(edge.source) ?? edge.source}</span>
              <b aria-label={edge.directed ? t("profile.graph.directed") : t("profile.graph.connected")}>{edge.directed ? "→" : "—"}</b>
              <span>{labels.get(edge.target) ?? edge.target}</span>
              <small>：{edge.label}</small>
            </li>
          ))}
        </ul>
      ) : (
        <p>{t("profile.graph.noEdges")}</p>
      )}
    </div>
  )
}

function graphLabel(title: GraphModule["title"], t: TFunction<"chat">): string {
  switch (title) {
    case "关系认知":
      return t("profile.graph.labels.relationships")
    case "知识与信念":
      return t("profile.graph.labels.knowledge")
    case "世界理解":
      return t("profile.graph.labels.world")
    default:
      return assertNever(title)
  }
}

function moduleTitle(title: GraphModule["title"], t: TFunction<"chat">): string {
  switch (title) {
    case "关系认知": return t("profile.private.titles.relationships")
    case "知识与信念": return t("profile.private.titles.knowledge")
    case "世界理解": return t("profile.private.titles.world")
    default: return assertNever(title)
  }
}

function assertNever(value: never): never {
  throw new RangeError(`Unexpected graph module: ${String(value)}`)
}
