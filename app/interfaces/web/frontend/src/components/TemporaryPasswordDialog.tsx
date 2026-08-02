import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"

export function TemporaryPasswordDialog({
  onClose,
  password,
}: {
  readonly onClose: () => void
  readonly password: string | null
}) {
  const { t } = useTranslation("manage")
  const [copyResult, setCopyResult] = useState<"success" | "failure" | null>(null)

  const close = (): void => {
    setCopyResult(null)
    onClose()
  }

  const copy = async (): Promise<void> => {
    if (password === null) return
    try {
      await navigator.clipboard.writeText(password)
      setCopyResult("success")
    } catch (reason: unknown) {
      if (!(reason instanceof Error) && !(reason instanceof DOMException)) throw reason
      setCopyResult("failure")
    }
  }

  return <ManageDialog description={t("users.reset.resultDescription")} onOpenChange={(open) => { if (!open) close() }} open={password !== null} title={t("users.reset.resultTitle")}>
    {password === null ? null : <output>{password}</output>}
    {copyResult === "success" ? <Notice message={t("users.reset.copySuccess")} /> : null}
    {copyResult === "failure" ? <Notice kind="error" message={t("users.reset.copyFailure")} /> : null}
    <div className="manage-actions">
      <Button onClick={() => { void copy() }} type="button">{t("users.actions.copyPassword")}</Button>
      <Button onClick={close} type="button" variant="outline">{t("users.actions.close")}</Button>
    </div>
  </ManageDialog>
}
