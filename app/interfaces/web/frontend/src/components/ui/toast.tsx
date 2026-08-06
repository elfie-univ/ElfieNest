import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react"
import { Toast as ToastPrimitive } from "radix-ui"
import { useTranslation } from "react-i18next"
import { XIcon } from "lucide-react"

import { cn } from "@/lib/utils"

import { NOTIFICATION_DURATIONS, type ToastOptions } from "../notification-types"

const MAX_TOASTS = 3

type ToastRecord = ToastOptions & { readonly id: string }

type ToastContextValue = {
  readonly dismiss: (id: string) => void
  readonly show: (options: ToastOptions) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { readonly children: ReactNode }) {
  const [toasts, setToasts] = useState<readonly ToastRecord[]>([])
  const sequence = useRef(0)
  const dismiss = useCallback((id: string): void => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])
  const show = useCallback((options: ToastOptions): void => {
    sequence.current += 1
    const nextId = `toast-${sequence.current}`
    setToasts((current) => {
      const existing = options.dedupeKey === undefined
        ? undefined
        : current.find((toast) => toast.dedupeKey === options.dedupeKey)
      const nextToast: ToastRecord = { ...options, id: existing?.id ?? nextId }
      if (existing) return current.map((toast) => toast.id === existing.id ? nextToast : toast)
      return [...current, nextToast].slice(-MAX_TOASTS)
    })
  }, [])
  const context = useMemo<ToastContextValue>(() => ({ dismiss, show }), [dismiss, show])
  const { t } = useTranslation("common")

  return <ToastContext.Provider value={context}>
    <ToastPrimitive.Provider duration={NOTIFICATION_DURATIONS.info} label={t("aria.notifications")} swipeDirection="right">
      {children}
      {toasts.map((toast) => <ToastItem key={toast.id} onDismiss={dismiss} toast={toast} />)}
      <ToastPrimitive.Viewport className="toast-viewport" data-slot="toast-viewport" />
    </ToastPrimitive.Provider>
  </ToastContext.Provider>
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (context === null) throw new Error("useToast must be used within ToastProvider")
  return context
}

function ToastItem({ onDismiss, toast }: { readonly onDismiss: (id: string) => void; readonly toast: ToastRecord }) {
  const { t } = useTranslation("common")
  return <ToastPrimitive.Root
    className={cn("toast-root", `toast-root--${toast.kind}`)}
    data-kind={toast.kind}
    duration={toast.duration ?? NOTIFICATION_DURATIONS[toast.kind]}
    onOpenChange={(open) => { if (!open) onDismiss(toast.id) }}
    type="foreground"
  >
    {toast.title ? <ToastPrimitive.Title className="toast-root__title">{toast.title}</ToastPrimitive.Title> : null}
    <ToastPrimitive.Description className="toast-root__description">{toast.message}</ToastPrimitive.Description>
    {toast.action ? <ToastPrimitive.Action
      altText={toast.action.label}
      className="toast-root__action"
      onClick={() => { toast.action?.onSelect(); onDismiss(toast.id) }}
    >{toast.action.label}</ToastPrimitive.Action> : null}
    <ToastPrimitive.Close aria-label={t("actions.close")} className="toast-root__close">
      <XIcon aria-hidden="true" size={16} />
      <span className="sr-only">{t("actions.close")}</span>
    </ToastPrimitive.Close>
  </ToastPrimitive.Root>
}
