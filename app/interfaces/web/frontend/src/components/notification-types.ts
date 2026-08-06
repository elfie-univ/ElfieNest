export const NOTIFICATION_KINDS = ["success", "info", "warning", "error"] as const

export type NotificationKind = (typeof NOTIFICATION_KINDS)[number]

export const NOTIFICATION_DURATIONS = {
  error: 10000,
  info: 5000,
  success: 4000,
  warning: 8000,
} as const satisfies Record<NotificationKind, number>

export type ToastAction = {
  readonly label: string
  readonly onSelect: () => void
}

export type ToastOptions = {
  readonly action?: ToastAction
  readonly dedupeKey?: string
  readonly duration?: number
  readonly kind: NotificationKind
  readonly message: string
  readonly title?: string
}
