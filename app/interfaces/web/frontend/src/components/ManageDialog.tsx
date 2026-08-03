import { useRef, type ReactElement, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
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
  const { t } = useTranslation("common")
  const openerRef = useRef<HTMLElement | null>(null)
  const contentClasses = ["max-w-[35rem] max-h-[min(47.5rem,calc(100vh-2rem))] overflow-y-auto p-6 sm:max-w-[35rem]", contentClassName].filter(Boolean).join(" ")
  return <Dialog onOpenChange={onOpenChange} open={open}>
    {trigger ? <DialogTrigger asChild>{trigger}</DialogTrigger> : null}
      <DialogContent
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
        showCloseButton={false}
      >
        <DialogHeader className="gap-2 pr-9">
          <DialogTitle className="text-[1.375rem] leading-tight">{title}</DialogTitle>
          {description ? <DialogDescription className="leading-relaxed">{description}</DialogDescription> : null}
        </DialogHeader>
        <div className="manage-dialog__fields">{children}</div>
        <DialogClose asChild>
          <Button aria-label={t("aria.closeDialog", { title })} className="absolute top-4 right-4" size="icon-sm" type="button" variant="ghost">
            <Icon name="x" size={18} />
          </Button>
        </DialogClose>
      </DialogContent>
  </Dialog>
}
