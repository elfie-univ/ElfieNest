type StatusTone = "active" | "inactive" | "transition" | "resting" | "unknown"

type StatusIndicatorProps = {
  readonly label: string
  readonly tone: StatusTone | string
}

export function StatusIndicator({ label, tone }: StatusIndicatorProps) {
  const { t } = useTranslation("common")
  const normalizedTone = normalizeTone(tone)
  return (
    <span className={`status-indicator status-indicator--${normalizedTone}`}>
      <i aria-hidden="true" />
      {label || t("status.unknown")}
    </span>
  )
}

function normalizeTone(tone: string): StatusTone {
  switch (tone) {
    case "active":
    case "inactive":
    case "transition":
    case "resting":
    case "unknown":
      return tone
    default:
      return "unknown"
  }
}
import { useTranslation } from "react-i18next"
