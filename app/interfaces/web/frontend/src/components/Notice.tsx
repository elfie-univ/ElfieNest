type NoticeProps = { readonly message: string; readonly kind?: "error" | "info" }

export function Notice({ message, kind = "info" }: NoticeProps) {
  return <p className={`notice notice--${kind}`} role={kind === "error" ? "alert" : "status"}>{message}</p>
}
