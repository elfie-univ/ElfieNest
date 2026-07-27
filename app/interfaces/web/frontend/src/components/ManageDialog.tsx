import * as Dialog from "@radix-ui/react-dialog"
import { useRef, type ReactElement, type ReactNode } from "react"

import { Icon } from "./Icon"
import "./manage-controls.css"

type ManageDialogProps = {
  readonly children: ReactNode
  readonly contentClassName?: string
  readonly description?: string
  readonly onOpenChange: (open: boolean) => void
  readonly open: boolean
  readonly title: string
  readonly trigger?: ReactElement
}

export function ManageDialog({
  children,
  contentClassName,
  description,
  onOpenChange,
  open,
  title,
  trigger,
}: ManageDialogProps) {
  const openerRef = useRef<HTMLElement | null>(null)
  const contentClasses = ["manage-dialog", contentClassName].filter(Boolean).join(" ")
  return <Dialog.Root onOpenChange={onOpenChange} open={open}>
    {trigger ? <Dialog.Trigger asChild>{trigger}</Dialog.Trigger> : null}
    <Dialog.Portal>
      <Dialog.Overlay className="manage-dialog-backdrop" />
      <Dialog.Content
        className={contentClasses}
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
        <header className="manage-dialog__header">
          <div>
            <Dialog.Title>{title}</Dialog.Title>
            {description ? <Dialog.Description>{description}</Dialog.Description> : null}
          </div>
        </header>
        <div className="manage-dialog__body">{children}</div>
        <Dialog.Close aria-label={`关闭${title}`} className="manage-dialog__close">
          <Icon name="x" size={18} />
        </Dialog.Close>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
