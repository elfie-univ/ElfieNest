import { useEffect, useMemo, useState } from "react"

import { resolveChartTheme, type ChartTheme } from "./chart-options"

export function useProfileChartTheme(): ChartTheme {
  const root = document.documentElement
  const readTheme = () => root.dataset["theme"] ?? ""
  const [theme, setTheme] = useState(readTheme)

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()))
    observer.observe(root, { attributeFilter: ["data-theme"], attributes: true })
    setTheme(readTheme())
    return () => observer.disconnect()
  }, [root])

  return useMemo(
    () => resolveChartTheme(window.getComputedStyle(root)),
    [root, theme],
  )
}
