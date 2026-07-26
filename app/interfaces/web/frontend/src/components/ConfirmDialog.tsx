import * as AlertDialog from "@radix-ui/react-alert-dialog"
import { useRef, type ReactElement } from "react"

import "./manager-controls.css"

type ConfirmDialogProps = {
  readonly cancelLabel?: string
  readonly confirmLabel?: string
  readonly danger?: boolean
  readonly description: string
  readonly onConfirm: () => void
  readonly onOpenChange: (open: boolean) => void
  readonly open: boolean
  readonly pending?: boolean
  readonly title: string
  readonly trigger?: ReactElement
}

export function ConfirmDialog({
  cancelLabel = "取消",
  confirmLabel = "确认",
  danger = false,
  description,
  onConfirm,
  onOpenChange,
  open,
  pending = false,
  title,
  trigger,
}: ConfirmDialogProps) {
  const openerRef = useRef<HTMLElement | null>(null)
  return <AlertDialog.Root onOpenChange={onOpenChange} open={open}>
    {trigger ? <AlertDialog.Trigger asChild>{trigger}</AlertDialog.Trigger> : null}
    <AlertDialog.Portal>
      <AlertDialog.Overlay className="manager-dialog-backdrop" />
      <AlertDialog.Content
        className="manager-dialog manager-confirm-dialog"
        onCloseAutoFocus={(event) => {
          if (!openerRef.current) return
          event.preventDefault()
          openerRef.current.focus()
          openerRef.current = null
        }}
        onOpenAutoFocus={() => {
          openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
        }}
      >
        <AlertDialog.Title>{title}</AlertDialog.Title>
        <AlertDialog.Description>{description}</AlertDialog.Description>
        <div className="manager-dialog__actions">
          <AlertDialog.Cancel className="button button--quiet" disabled={pending}>{cancelLabel}</AlertDialog.Cancel>
          <button
            className={danger ? "button manager-confirm-dialog__danger" : "button"}
            disabled={pending}
            onClick={onConfirm}
            type="button"
          >
            {pending ? "处理中…" : confirmLabel}
          </button>
        </div>
      </AlertDialog.Content>
    </AlertDialog.Portal>
  </AlertDialog.Root>
}
