import { useMemo } from "react"

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
  const theme = useProfileChartTheme()
  const preview = projectGraph(module.graph, "preview")
  const detail = projectGraph(module.graph, "detail")
  const previewOption = useMemo(() => buildGraphOption(preview, theme), [preview, theme])
  const detailOption = useMemo(() => buildGraphOption(detail, theme), [detail, theme])

  return (
    <section className="profile-graph" aria-label={`${module.title}图谱`}>
      <header className="profile-graph__header">
        <div>
          <strong>{graphLabel(module.title)}</strong>
          <span>{module.graph.nodes.length} 个节点 · {module.graph.edges.length} 条连接</span>
        </div>
        <Dialog>
          <DialogTrigger asChild>
            <Button
              aria-label={`查看${module.title}详情`}
              className="profile-graph__detail-trigger"
              type="button"
              variant="outline"
            >
              查看详情
            </Button>
          </DialogTrigger>
          <DialogContent className="profile-graph-dialog" showCloseButton={false}>
            <DialogHeader>
              <DialogTitle>{module.title}详情</DialogTitle>
              <DialogDescription>详情最多展示 50 个节点，并保留可阅读的连接说明。</DialogDescription>
            </DialogHeader>
            <GraphView
              chartKey={`${elfieId}-${module.title}-detail`}
              graph={detail}
              label={`${module.title}详情图`}
              loadChartRuntime={loadChartRuntime}
              option={detailOption}
              title={module.title}
              variant="detail"
            />
            <DialogFooter>
              <DialogClose asChild><Button type="button" variant="outline">关闭详情</Button></DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </header>
      <GraphView
        chartKey={`${elfieId}-${module.title}-preview`}
        graph={preview}
        label={`${module.title}预览图`}
        loadChartRuntime={loadChartRuntime}
        option={previewOption}
        title={module.title}
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
  readonly title: GraphModule["title"]
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
  readonly title: GraphModule["title"]
}) {
  const labels = new Map(graph.nodes.map((node) => [node.id, node.label]))
  return (
    <div className="profile-graph__summary">
      {graph.nodes.length === 0 && <p>暂无可呈现的{title}节点。</p>}
      {graph.truncatedNodeCount > 0 && (
        <p className="profile-graph__truncation">
          已显示前 {graph.nodes.length} 个节点，另有 {graph.truncatedNodeCount} 个未显示。
        </p>
      )}
      {graph.edges.length > 0 ? (
        <ul aria-label={`${title}连接说明`} className="profile-graph__edges">
          {graph.edges.map((edge, index) => (
            <li key={`${edge.source}-${edge.target}-${index}`}>
              <span>{labels.get(edge.source) ?? edge.source}</span>
              <b aria-label={edge.directed ? "指向" : "连接"}>{edge.directed ? "→" : "—"}</b>
              <span>{labels.get(edge.target) ?? edge.target}</span>
              <small>：{edge.label}</small>
            </li>
          ))}
        </ul>
      ) : (
        <p>暂无连接说明。</p>
      )}
    </div>
  )
}

function graphLabel(title: GraphModule["title"]): string {
  switch (title) {
    case "关系认知":
      return "关系网络"
    case "知识与信念":
      return "有向知识网络"
    case "世界理解":
      return "世界理解地图"
    default:
      return assertNever(title)
  }
}

function assertNever(value: never): never {
  throw new RangeError(`Unexpected graph module: ${String(value)}`)
}
