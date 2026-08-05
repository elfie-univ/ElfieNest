import type { NotificationKind } from "./notification-types"

type NoticeProps = { readonly message: string; readonly kind?: NotificationKind }

function assertNever(value: never): never {
  throw new Error(`Unsupported notification kind: ${String(value)}`)
}

function noticeRole(kind: NotificationKind): "alert" | "status" {
  switch (kind) {
    case "error":
    case "warning":
      return "alert"
    case "info":
    case "success":
      return "status"
    default:
      return assertNever(kind)
  }
}

export function Notice({ message, kind = "info" }: NoticeProps) {
  return <p className={`notice notice--${kind}`} data-kind={kind} role={noticeRole(kind)}>{message}</p>
}
