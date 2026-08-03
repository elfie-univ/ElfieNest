import type { ReactNode } from "react"

import type { ToolKey } from "../../api/owner-tools"
import { Icon } from "../Icon"

type ToolSettingsRowProps = {
  readonly details: ReactNode
  readonly disabledLabel: string
  readonly enabled: boolean
  readonly enabledLabel: string
  readonly collapseLabel: string
  readonly collapseText: string
  readonly expandLabel: string
  readonly expandText: string
  readonly expanded: boolean
  readonly onToggle: (enabled: boolean) => void
  readonly onToggleDetails: () => void
  readonly pending: boolean
  readonly statusLabel: string
  readonly switchLabel: string
  readonly title: string
  readonly description: string
  readonly toolKey: ToolKey
  readonly unsavedLabel: string
}

export function ToolSettingsRow({
  details,
  disabledLabel,
  collapseLabel,
  collapseText,
  enabled,
  enabledLabel,
  expandLabel,
  expandText,
  expanded,
  onToggle,
  onToggleDetails,
  pending,
  statusLabel,
  switchLabel,
  title,
  description,
  toolKey,
  unsavedLabel,
}: ToolSettingsRowProps) {
  const detailsId = `tool-${toolKey}-details`
  const titleId = `tool-${toolKey}-title`
  const currentStatus = enabled ? enabledLabel : disabledLabel

  return <article className="tool-settings-row" data-tool-key={toolKey}>
    <div className="tool-settings-row__header">
      <div className="tool-settings-row__copy">
        <strong id={titleId}>{title}</strong>
        <small>{description}</small>
        <span className="tool-settings-row__status-line">
          <span className="tool-settings-row__status">{statusLabel || currentStatus}</span>
          {unsavedLabel ? <span className="tool-settings-row__unsaved">{unsavedLabel}</span> : null}
        </span>
      </div>
      <div className="tool-settings-row__actions">
        <button
          aria-checked={enabled}
          aria-label={switchLabel}
          className="tool-settings-row__switch"
          data-state={enabled ? "checked" : "unchecked"}
          disabled={pending}
          onClick={() => onToggle(!enabled)}
          role="switch"
          type="button"
        >
          <span>{currentStatus}</span>
          <span aria-hidden="true" className="tool-settings-row__switch-track"><span /></span>
        </button>
        <button
          aria-controls={detailsId}
          aria-expanded={expanded}
          aria-label={expanded ? collapseLabel : expandLabel}
          className="tool-settings-row__disclosure"
          onClick={onToggleDetails}
          type="button"
        >
          <span>{expanded ? collapseText : expandText}</span>
          <Icon name={expanded ? "chevron-up" : "chevron-down"} size={15} />
        </button>
      </div>
    </div>
    <div
      aria-labelledby={titleId}
      className="tool-settings-row__details"
      hidden={!expanded}
      id={detailsId}
      role="region"
    >
      {details}
    </div>
  </article>
}
