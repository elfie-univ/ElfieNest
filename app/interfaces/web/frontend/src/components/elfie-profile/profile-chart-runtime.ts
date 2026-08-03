import { RadarChart } from "echarts/charts"
import { AriaComponent, RadarComponent, TooltipComponent } from "echarts/components"
import { init, use } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"

import type { ProfileChartRuntime } from "./ProfileChart"

use([
  RadarChart,
  AriaComponent,
  RadarComponent,
  TooltipComponent,
  CanvasRenderer,
])

export const profileChartRuntime: ProfileChartRuntime = { init }
