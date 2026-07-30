import { useRef, type ReactElement } from "react"
import { useTranslation } from "react-i18next"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"

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
  cancelLabel,
  confirmLabel,
  danger = false,
  description,
  onConfirm,
  onOpenChange,
  open,
  pending = false,
  title,
  trigger,
}: ConfirmDialogProps) {
  const { t } = useTranslation("common")
  const openerRef = useRef<HTMLElement | null>(null)
  const localizedCancelLabel = cancelLabel ?? t("actions.cancel")
  const localizedConfirmLabel = confirmLabel ?? t("actions.confirm")
  return <AlertDialog onOpenChange={onOpenChange} open={open}>
    {trigger ? <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger> : null}
      <AlertDialogContent
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
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>{localizedCancelLabel}</AlertDialogCancel>
          <AlertDialogAction
            disabled={pending}
            onClick={onConfirm}
            variant={danger ? "destructive" : "default"}
          >
            {pending ? t("actions.processing") : localizedConfirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
  </AlertDialog>
}
