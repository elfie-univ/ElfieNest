import type { ReactElement } from "react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

import type { AppearanceCapture } from "./appearance-capture"

type ProfileCaptureDialogProps = {
  readonly capture: AppearanceCapture | null
  readonly captureError?: string | undefined
  readonly capturePending?: boolean | undefined
  readonly elfieName: string
  readonly onAvatar: (capture: AppearanceCapture) => void
  readonly onDownload?: ((capture: AppearanceCapture, filename: string) => void) | undefined
  readonly onOpenChange: (open: boolean) => void
  readonly onRecapture: () => void
  readonly open: boolean
  readonly trigger: ReactElement
}

export function ProfileCaptureDialog({
  capture,
  captureError = "",
  capturePending = false,
  elfieName,
  onAvatar,
  onDownload = downloadCapture,
  onOpenChange,
  onRecapture,
  open,
  trigger,
}: ProfileCaptureDialogProps) {
  const { t } = useTranslation("chat")
  const [downloadError, setDownloadError] = useState("")

  function chooseAvatar(): void {
    if (capture === null) {
      return
    }
    onAvatar(capture)
    onOpenChange(false)
  }

  function download(): void {
    if (capture === null) {
      return
    }
    setDownloadError("")
    try {
      onDownload(capture, `${elfieName}-elfie.png`)
    } catch (error) {
      if (error instanceof DOMException) {
        setDownloadError(t("profile.captureDialog.downloadError"))
        return
      }
      throw error
    }
  }

  function recapture(): void {
    onRecapture()
  }

  return (
    <Dialog
      onOpenChange={(nextOpen) => {
        setDownloadError("")
        onOpenChange(nextOpen)
      }}
      open={open}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="profile-capture" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("profile.captureDialog.title")}</DialogTitle>
          <DialogDescription>
            {t("profile.captureDialog.description")}
          </DialogDescription>
        </DialogHeader>
        {capture === null ? (
          <p className="profile-capture__loading" role="status">{t("profile.captureDialog.loading")}</p>
        ) : (
          <img
            alt={t("profile.captureDialog.preview", { name: elfieName })}
            className="profile-capture__preview"
            src={capture.previewUrl}
          />
        )}
        {downloadError.length > 0 && <p className="profile-capture__error" role="alert">{downloadError}</p>}
        {captureError.length > 0 && <p className="profile-capture__error" role="alert">{captureError}</p>}
        <DialogFooter className="profile-capture__actions">
          <DialogClose asChild>
            <Button type="button" variant="ghost">{t("profile.captureDialog.cancel")}</Button>
          </DialogClose>
          <Button disabled={capturePending} onClick={recapture} type="button" variant="outline">
            {capturePending ? t("profile.captureDialog.recapturing") : t("profile.captureDialog.recapture")}
          </Button>
          <Button disabled={capture === null || capturePending} onClick={download} type="button" variant="outline">
            {t("profile.captureDialog.download")}
          </Button>
          <Button disabled={capture === null || capturePending} onClick={chooseAvatar} type="button">
            {t("profile.captureDialog.avatar")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function downloadCapture(capture: AppearanceCapture, filename: string): void {
  const downloadUrl = URL.createObjectURL(capture.blob)
  try {
    const anchor = document.createElement("a")
    anchor.download = filename
    anchor.href = downloadUrl
    anchor.click()
  } finally {
    URL.revokeObjectURL(downloadUrl)
  }
}
