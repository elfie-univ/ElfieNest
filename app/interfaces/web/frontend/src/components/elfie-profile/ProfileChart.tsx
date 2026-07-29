import type { EChartsCoreOption, EChartsType } from "echarts/core"
import { useEffect, useId, useRef, useState, type ReactNode } from "react"

export type ProfileChartRuntime = {
  readonly init: (element: HTMLElement) => Pick<EChartsType, "dispose" | "resize" | "setOption">
}

type ProfileChartProps = {
  readonly chartKey: string
  readonly label: string
  readonly loadRuntime?: () => Promise<ProfileChartRuntime>
  readonly option: EChartsCoreOption
  readonly summary: ReactNode
}

type LoadState = "loading" | "ready" | "error"

export function ProfileChart({
  chartKey,
  label,
  loadRuntime = loadProfileChartRuntime,
  option,
  summary,
}: ProfileChartProps) {
  const summaryId = useId()
  const hostRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<Pick<EChartsType, "dispose" | "resize" | "setOption"> | null>(null)
  const optionRef = useRef(option)
  const [state, setState] = useState<LoadState>("loading")
  optionRef.current = option

  useEffect(() => {
    let active = true
    let observer: ResizeObserver | null = null
    let chart: Pick<EChartsType, "dispose" | "resize" | "setOption"> | null = null
    setState("loading")

    void loadRuntime().then((runtime) => {
      const host = hostRef.current
      if (!active || host === null) return
      chart = runtime.init(host)
      chartRef.current = chart
      chart.setOption(optionRef.current)
      observer = new ResizeObserver(() => chart?.resize())
      observer.observe(host)
      setState("ready")
    }).catch(() => {
      if (active) setState("error")
    })

    return () => {
      active = false
      observer?.disconnect()
      chart?.dispose()
      if (chartRef.current === chart) chartRef.current = null
    }
  }, [chartKey, loadRuntime])

  useEffect(() => {
    chartRef.current?.setOption(option)
  }, [option])

  return (
    <div className="profile-chart">
      <div
        aria-describedby={summaryId}
        aria-label={label}
        className="profile-chart__canvas"
        ref={hostRef}
        role="img"
      />
      {state === "loading" && <p className="profile-chart__status" role="status">图表加载中…</p>}
      {state === "error" && (
        <p className="profile-chart__status" role="alert">图表暂时无法显示，请参考下方数值。</p>
      )}
      <div className="profile-chart__text-alternative" id={summaryId}>{summary}</div>
    </div>
  )
}

export async function loadProfileChartRuntime(): Promise<ProfileChartRuntime> {
  const { profileChartRuntime } = await import("./profile-chart-runtime")
  return profileChartRuntime
}
