import type { ReactElement } from "react"
import { useEffect, useRef, useState } from "react"
import {
  Download,
  Move,
  RectangleHorizontal,
  RectangleVertical,
  Square,
  UserRound,
} from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

import type { AppearanceCapture } from "./appearance-capture"
import {
  CROP_ASPECTS,
  clampCropRect,
  cropAspectRatio,
  cropCapture,
  defaultCropRect,
  fitCropRectToAspect,
  inspectCapture,
  squareCropRect,
  type CropAspect,
  type CropImageInfo,
  type CropRect,
} from "./profile-capture-crop"

type ProfileCaptureDialogProps = {
  readonly capture: AppearanceCapture | null
  readonly captureError?: string | undefined
  readonly capturePending?: boolean | undefined
  readonly elfieName: string
  readonly onAvatar: (capture: AppearanceCapture) => boolean | void | Promise<boolean | void>
  readonly onDownload?: ((capture: AppearanceCapture, filename: string) => void | Promise<void>) | undefined
  readonly onOpenChange: (open: boolean) => void
  readonly open: boolean
  readonly trigger: ReactElement
}

type ViewportLayout = {
  readonly offsetX: number
  readonly offsetY: number
  readonly scale: number
}

type CropInteraction = {
  readonly mode: "move" | "resize"
  readonly pointerId: number
  readonly startCrop: CropRect
  readonly startX: number
  readonly startY: number
}

export function ProfileCaptureDialog({
  capture,
  captureError = "",
  capturePending = false,
  elfieName,
  onAvatar,
  onDownload = downloadCapture,
  onOpenChange,
  open,
  trigger,
}: ProfileCaptureDialogProps) {
  const { t } = useTranslation("chat")
  const viewportRef = useRef<HTMLDivElement>(null)
  const interactionRef = useRef<CropInteraction | null>(null)
  const [downloadError, setDownloadError] = useState("")
  const [cropError, setCropError] = useState("")
  const [cropPending, setCropPending] = useState(false)
  const [aspect, setAspect] = useState<CropAspect>("square")
  const [imageInfo, setImageInfo] = useState<CropImageInfo | null>(null)
  const [crop, setCrop] = useState<CropRect | null>(null)
  const [viewportSize, setViewportSize] = useState({ height: 0, width: 0 })

  useEffect(() => {
    let active = true
    setAspect("square")
    setImageInfo(null)
    setCrop(null)
    setCropError("")
    if (capture === null) return () => { active = false }
    void inspectCapture(capture)
      .then((info) => {
        if (!active) return
        setImageInfo(info)
        setCrop(defaultCropRect(info.width, info.height, "square", info.visibleBounds))
      })
      .catch(() => {
        if (active) setCropError(t("profile.captureDialog.cropError"))
      })
    return () => { active = false }
  }, [capture, t])

  useEffect(() => {
    const viewport = viewportRef.current
    if (viewport === null || typeof ResizeObserver === "undefined") return undefined
    const update = (): void => {
      const bounds = viewport.getBoundingClientRect()
      setViewportSize({ height: bounds.height, width: bounds.width })
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(viewport)
    return () => observer.disconnect()
  }, [imageInfo])

  function changeAspect(nextAspect: CropAspect): void {
    setAspect(nextAspect)
    if (imageInfo === null) return
    setCrop((current) => fitCropRectToAspect(
      current ?? defaultCropRect(imageInfo.width, imageInfo.height, nextAspect, imageInfo.visibleBounds),
      imageInfo.width,
      imageInfo.height,
      nextAspect,
    ))
  }

  function layout(): ViewportLayout {
    if (imageInfo === null || viewportSize.width <= 0 || viewportSize.height <= 0) {
      return { offsetX: 0, offsetY: 0, scale: 1 }
    }
    const scale = Math.min(viewportSize.width / imageInfo.width, viewportSize.height / imageInfo.height)
    return {
      offsetX: (viewportSize.width - imageInfo.width * scale) * 0.5,
      offsetY: (viewportSize.height - imageInfo.height * scale) * 0.5,
      scale,
    }
  }

  function updateFromKeyboard(event: React.KeyboardEvent<HTMLDivElement>): void {
    if (imageInfo === null || crop === null) return
    const step = event.shiftKey ? 32 : 12
    const currentLayout = layout()
    const imageStep = step / Math.max(currentLayout.scale, 0.01)
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
      event.preventDefault()
      const deltaX = event.key === "ArrowLeft" ? -imageStep : event.key === "ArrowRight" ? imageStep : 0
      const deltaY = event.key === "ArrowUp" ? -imageStep : event.key === "ArrowDown" ? imageStep : 0
      setCrop(clampCropRect({ ...crop, x: crop.x + deltaX, y: crop.y + deltaY }, imageInfo.width, imageInfo.height, cropAspectRatio(aspect)))
      return
    }
    if (event.key !== "+" && event.key !== "=" && event.key !== "-" && event.key !== "_") return
    event.preventDefault()
    const ratio = cropAspectRatio(aspect)
    const change = event.key === "-" || event.key === "_" ? -imageStep : imageStep
    const nextWidth = Math.max(1, crop.width + change)
    const nextHeight = nextWidth / ratio
    setCrop(clampCropRect({
      height: nextHeight,
      width: nextWidth,
      x: crop.x - (nextWidth - crop.width) * 0.5,
      y: crop.y - (nextHeight - crop.height) * 0.5,
    }, imageInfo.width, imageInfo.height, ratio))
  }

  function pointerDown(event: React.PointerEvent<HTMLDivElement>): void {
    if (crop === null || imageInfo === null) return
    const target = event.target as HTMLElement
    const mode = target.closest("[data-crop-handle]") === null ? "move" : "resize"
    interactionRef.current = {
      mode,
      pointerId: event.pointerId,
      startCrop: crop,
      startX: event.clientX,
      startY: event.clientY,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
    event.preventDefault()
  }

  function pointerMove(event: React.PointerEvent<HTMLDivElement>): void {
    const interaction = interactionRef.current
    if (interaction === null || interaction.pointerId !== event.pointerId || imageInfo === null) return
    const currentLayout = layout()
    const deltaX = (event.clientX - interaction.startX) / Math.max(currentLayout.scale, 0.01)
    const deltaY = (event.clientY - interaction.startY) / Math.max(currentLayout.scale, 0.01)
    if (interaction.mode === "move") {
      setCrop(clampCropRect({
        ...interaction.startCrop,
        x: interaction.startCrop.x + deltaX,
        y: interaction.startCrop.y + deltaY,
      }, imageInfo.width, imageInfo.height, cropAspectRatio(aspect)))
      return
    }
    const ratio = cropAspectRatio(aspect)
    const widthFromX = interaction.startCrop.width + deltaX
    const widthFromY = (interaction.startCrop.height + deltaY) * ratio
    const nextWidth = Math.max(48, Math.max(widthFromX, widthFromY))
    setCrop(clampCropRect({
      height: nextWidth / ratio,
      width: nextWidth,
      x: interaction.startCrop.x,
      y: interaction.startCrop.y,
    }, imageInfo.width, imageInfo.height, ratio))
  }

  function pointerEnd(event: React.PointerEvent<HTMLDivElement>): void {
    if (interactionRef.current?.pointerId === event.pointerId) interactionRef.current = null
  }

  async function selectedCapture(forAvatar: boolean): Promise<AppearanceCapture> {
    if (capture === null || imageInfo === null || crop === null) throw new Error("crop_not_ready")
    const selected = forAvatar
      ? squareCropRect(crop, imageInfo.width, imageInfo.height)
      : crop
    return cropCapture(capture, selected)
  }

  async function chooseAvatar(): Promise<void> {
    if (capture === null || cropPending) return
    setCropPending(true)
    setCropError("")
    let selected: AppearanceCapture | null = null
    try {
      selected = await selectedCapture(true)
      const saved = await onAvatar(selected)
      if (saved === false) return
      onOpenChange(false)
    } catch {
      setCropError(t("profile.captureDialog.cropError"))
    } finally {
      revokeDerivedCapture(capture, selected)
      setCropPending(false)
    }
  }

  async function download(): Promise<void> {
    if (capture === null || cropPending) return
    setDownloadError("")
    setCropPending(true)
    let selected: AppearanceCapture | null = null
    try {
      selected = await selectedCapture(false)
      await onDownload(selected, `${elfieName}-elfie.png`)
    } catch (error) {
      if (error instanceof DOMException) {
        setDownloadError(t("profile.captureDialog.downloadError"))
      } else {
        setCropError(t("profile.captureDialog.cropError"))
      }
    } finally {
      revokeDerivedCapture(capture, selected)
      setCropPending(false)
    }
  }

  const isDisabled = capture === null || imageInfo === null || crop === null || capturePending || cropPending
  const currentLayout = layout()
  const cropStyle = crop === null ? undefined : {
    height: `${crop.height * currentLayout.scale}px`,
    left: `${currentLayout.offsetX + crop.x * currentLayout.scale}px`,
    top: `${currentLayout.offsetY + crop.y * currentLayout.scale}px`,
    width: `${crop.width * currentLayout.scale}px`,
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
        </DialogHeader>
        {capture === null ? (
          <p className="profile-capture__loading" role="status">{t("profile.captureDialog.loading")}</p>
        ) : (
          <div
            aria-label={t("profile.captureDialog.cropArea")}
            className="profile-capture__workspace"
            data-testid="capture-crop-workspace"
            onLostPointerCapture={pointerEnd}
            onPointerCancel={pointerEnd}
            onPointerDown={pointerDown}
            onPointerMove={pointerMove}
            onPointerUp={pointerEnd}
            ref={viewportRef}
            role="application"
            tabIndex={0}
          >
            <img
              alt={t("profile.captureDialog.preview", { name: elfieName })}
              className="profile-capture__preview"
              draggable={false}
              src={capture.previewUrl}
            />
            {cropStyle !== undefined ? (
              <div
                aria-label={t("profile.captureDialog.cropBox")}
                className="profile-capture__crop-box"
                data-testid="capture-crop-box"
                onKeyDown={updateFromKeyboard}
                style={cropStyle}
                tabIndex={0}
              >
                <span aria-hidden="true" className="profile-capture__crop-guide profile-capture__crop-guide--vertical" />
                <span aria-hidden="true" className="profile-capture__crop-guide profile-capture__crop-guide--horizontal" />
                <span aria-hidden="true" className="profile-capture__crop-handle" data-crop-handle="true" />
              </div>
            ) : null}
            <p className="profile-capture__format-hint profile-capture__format-hint--overlay">
              <Move aria-hidden="true" />{t("profile.captureDialog.cropHint")}
            </p>
            {imageInfo === null && <p className="profile-capture__loading-overlay" role="status">{t("profile.captureDialog.loading")}</p>}
          </div>
        )}
        {downloadError.length > 0 && <p className="profile-capture__error" role="alert">{downloadError}</p>}
        {captureError.length > 0 && <p className="profile-capture__error" role="alert">{captureError}</p>}
        {cropError.length > 0 && <p className="profile-capture__error" role="alert">{cropError}</p>}
        <DialogFooter className="profile-capture__actions">
          <div className="profile-capture__aspect-control">
            {aspectIcon(aspect)}
            <Select onValueChange={(value) => changeAspect(value as CropAspect)} value={aspect}>
              <SelectTrigger aria-label={t("profile.captureDialog.aspectLabel")} className="profile-capture__aspect-select" size="sm">
                <SelectValue>{CROP_ASPECTS[aspect].label}</SelectValue>
              </SelectTrigger>
              <SelectContent align="start" position="popper">
                {(Object.entries(CROP_ASPECTS) as readonly [CropAspect, (typeof CROP_ASPECTS)[CropAspect]][]).map(([key, preset]) => (
                  <SelectItem key={key} value={key}>
                    <span className="profile-capture__aspect-option">{aspectIcon(key)}{preset.label}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="profile-capture__action-buttons">
            <DialogClose asChild>
              <Button type="button" variant="ghost">{t("profile.captureDialog.cancel")}</Button>
            </DialogClose>
            <Button disabled={isDisabled} onClick={() => { void download() }} type="button" variant="outline">
              <Download aria-hidden="true" />{t("profile.captureDialog.download")}
            </Button>
            <Button disabled={isDisabled} onClick={() => { void chooseAvatar() }} type="button">
              <UserRound aria-hidden="true" />{t("profile.captureDialog.avatar")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function aspectIcon(aspect: CropAspect): ReactElement {
  if (aspect === "landscape") return <RectangleHorizontal aria-hidden="true" />
  if (aspect === "portrait") return <RectangleVertical aria-hidden="true" />
  return <Square aria-hidden="true" />
}

function revokeDerivedCapture(source: AppearanceCapture, selected: AppearanceCapture | null): void {
  if (selected === null || selected.previewUrl === source.previewUrl) return
  if (typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(selected.previewUrl)
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
