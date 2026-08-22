import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react"
import { Camera, PersonStanding, RotateCcw, Scan } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

import type { AppearanceCapture, AppearanceCaptureAdapter, AppearanceCaptureInput } from "./appearance-capture"
import { AppearanceCaptureError } from "./appearance-capture"
import { ProfileCaptureDialog } from "./ProfileCaptureDialog"
import { ProfileGodotViewport, type PreviewStatus } from "./ProfileGodotViewport"
import {
  calculateVisibleFrameBounds,
  ProfileGodotPreviewError,
  type ProfileGodotPreview,
} from "./profile-godot-preview"
import type { PublicProfile } from "./model"
import { calculateIdlePortraitFrame, type IdlePortraitFrame } from "./profile-idle-portrait"

type ProfileAppearanceStageProps = {
  readonly canCapture: boolean
  readonly capture?: AppearanceCaptureAdapter | undefined
  readonly interactive?: boolean
  readonly onAvatarSave?: (capture: AppearanceCapture) => Promise<string>
  readonly onAvatarSaved?: (portraitUrl: string) => void
  readonly profile: PublicProfile
}

type PosePreset = "default" | "thinking" | "waving" | "victory" | "thumbsUp" | "handsOnHips"

const POSE_PRESETS: readonly { readonly motion: string; readonly value: PosePreset }[] = [
  { motion: "pose_default", value: "default" },
  { motion: "pose_thinking", value: "thinking" },
  { motion: "pose_waving", value: "waving" },
  { motion: "pose_victory", value: "victory" },
  { motion: "pose_thumbs_up", value: "thumbsUp" },
  { motion: "pose_hands_on_hips", value: "handsOnHips" },
]

export function ProfileAppearanceStage({
  canCapture,
  capture,
  interactive = true,
  onAvatarSave,
  onAvatarSaved,
  profile,
}: ProfileAppearanceStageProps) {
  const { t } = useTranslation("chat")
  const previewRef = useRef<ProfileGodotPreview | null>(null)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const objectUrlsRef = useRef(new Set<string>())
  const captureGenerationRef = useRef(0)
  const poseIntentRef = useRef(0)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewStatus, setPreviewStatus] = useState<PreviewStatus>("idle")
  const [captureOpen, setCaptureOpen] = useState(false)
  const [captureError, setCaptureError] = useState("")
  const [capturePending, setCapturePending] = useState(false)
  const [currentCapture, setCurrentCapture] = useState<AppearanceCapture | null>(null)
  const [fullBodyUnavailable, setFullBodyUnavailable] = useState(false)
  const [localAvatar, setLocalAvatar] = useState("")
  const [notice, setNotice] = useState("")
  const [posePreset, setPosePreset] = useState<PosePreset>("default")
  const [idlePortraitSource, setIdlePortraitSource] = useState<{
    readonly bounds: ReturnType<typeof readVisiblePortraitBounds>
    readonly height: number
    readonly width: number
  } | null>(null)
  const [idleStageSize, setIdleStageSize] = useState({ height: 0, width: 0 })

  const onPreviewChange = useCallback((preview: ProfileGodotPreview | null): void => {
    previewRef.current = preview
  }, [])
  const onStageChange = useCallback((stage: HTMLDivElement | null): void => {
    stageRef.current = stage
  }, [])
  const onStatusChange = useCallback((status: PreviewStatus): void => {
    setPreviewStatus(status)
  }, [])

  useEffect(() => {
    captureGenerationRef.current += 1
    poseIntentRef.current = 0
    setPreviewOpen(false)
    setPreviewStatus("idle")
    setCaptureOpen(false)
    setCaptureError("")
    setCapturePending(false)
    setCurrentCapture(null)
    setFullBodyUnavailable(false)
    setLocalAvatar("")
    setNotice("")
    setPosePreset("default")
    revokeCapturedUrls(objectUrlsRef.current)
  }, [profile.elfieId])

  useEffect(() => () => {
    captureGenerationRef.current += 1
    revokeCapturedUrls(objectUrlsRef.current)
  }, [])

  useEffect(() => {
    const stage = stageRef.current
    if (stage === null || typeof ResizeObserver === "undefined") return undefined
    const update = (): void => {
      const bounds = stage.getBoundingClientRect()
      setIdleStageSize({ height: bounds.height, width: bounds.width })
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(stage)
    return () => observer.disconnect()
  }, [fullBodyUnavailable, localAvatar, previewOpen, profile.elfieId, profile.fullBodyUrl, profile.portraitUrl])

  useEffect(() => {
    setIdlePortraitSource(null)
    setIdleStageSize({ height: 0, width: 0 })
  }, [localAvatar, profile.elfieId, profile.fullBodyUrl, profile.portraitUrl])

  async function captureStage(): Promise<boolean> {
    const stage = stageRef.current
    if (stage === null) return false
    const generation = captureGenerationRef.current + 1
    captureGenerationRef.current = generation
    setCaptureError("")
    setCapturePending(true)
    try {
      const nextCapture = capture === undefined
        ? await captureWithGodot()
        : await capture(buildCaptureInput(stage, profile, localAvatar))
      if (generation !== captureGenerationRef.current) {
        revokeCaptureUrl(nextCapture.previewUrl)
        return false
      }
      objectUrlsRef.current.add(nextCapture.previewUrl)
      setCurrentCapture(nextCapture)
      setCapturePending(false)
      return true
    } catch (error) {
      if (generation !== captureGenerationRef.current) return false
      if (error instanceof AppearanceCaptureError
        || error instanceof DOMException
        || error instanceof ProfileGodotPreviewError) {
        setCapturePending(false)
        setCaptureOpen(false)
        setCaptureError(t("profile.appearance.captureError"))
        return false
      }
      throw error
    }
  }

  async function captureWithGodot(): Promise<AppearanceCapture> {
    const preview = previewRef.current
    if (preview === null) throw new ProfileGodotPreviewError("preview_not_ready")
    // Capture the camera, zoom, and pose the user is currently viewing. The
    // reset action belongs only to the explicit reset control, not to photo capture.
    await waitForBrowserFrames()
    return preview.capture()
  }

  function changeCaptureOpen(open: boolean): void {
    if (!open && capturePending) {
      captureGenerationRef.current += 1
      setCapturePending(false)
    }
    setCaptureOpen(open)
  }

  function changePreviewOpen(open: boolean): void {
    if (!open) {
      captureGenerationRef.current += 1
      setCaptureOpen(false)
      setCapturePending(false)
      setPreviewStatus("idle")
      setPosePreset("default")
    }
    setPreviewOpen(open)
  }

  function resetPreview(): void {
    const preview = previewRef.current
    if (preview === null || previewStatus !== "ready") return
    setCaptureError("")
    try {
      preview.send("reset")
    } catch (error) {
      if (error instanceof ProfileGodotPreviewError) {
        setCaptureError(t("profile.appearance.error"))
        return
      }
      throw error
    }
  }

  function applyPose(value: string): void {
    const preset = POSE_PRESETS.find((option) => option.value === value)
    const preview = previewRef.current
    if (preset === undefined || preview === null || previewStatus !== "ready") return
    setCaptureError("")
    try {
      poseIntentRef.current += 1
      preview.send("preview_intent", {
        intent: {
          intent_id: `pose-${poseIntentRef.current}`,
          motion: preset.motion,
          type: "motion",
        },
      })
      setPosePreset(preset.value)
    } catch (error) {
      if (error instanceof ProfileGodotPreviewError) {
        setCaptureError(t("profile.appearance.error"))
        return
      }
      throw error
    }
  }

  const fallback = profile.name.slice(0, 1).toUpperCase()
  // The closed appearance surface is deliberately a full-body presentation.
  // A locally selected headshot belongs to the profile avatar preview and must
  // not replace the calibrated full-body composition when 3D is closed.
  const isFullBodyPortrait = !fullBodyUnavailable && profile.fullBodyUrl.length > 0
  const visiblePortrait = isFullBodyPortrait ? profile.fullBodyUrl : localAvatar || profile.portraitUrl
  const idlePortraitFrame: IdlePortraitFrame | null = !isFullBodyPortrait
    ? null
    : calculateIdlePortraitFrame(
      idleStageSize.width,
      idleStageSize.height,
      idlePortraitSource?.width ?? 0,
      idlePortraitSource?.height ?? 0,
      idlePortraitSource?.bounds ?? null,
    )
  const idlePortraitStyle: CSSProperties = idlePortraitFrame === null
    ? { inset: 0 }
    : {
      height: `${idlePortraitFrame.height}px`,
      left: `${idlePortraitFrame.left}px`,
      top: `${idlePortraitFrame.top}px`,
      width: `${idlePortraitFrame.width}px`,
    }
  const showControls = interactive

  return (
    <section aria-labelledby={`appearance-${profile.elfieId}`} className="profile-appearance profile-dossier__section">
      <header className="profile-appearance__header">
        <div>
          <span>{t("profile.appearance.eyebrow")}</span>
          <p className="profile-appearance__title" id={`appearance-${profile.elfieId}`}>
            {t(showControls ? "profile.appearance.title" : "profile.appearance.photoTitle")}
          </p>
        </div>
        {showControls ? <div className="profile-appearance__actions">
          {previewOpen ? (
            <>
              {canCapture && (
                <ProfileCaptureDialog
                  capture={currentCapture}
                  captureError={captureError}
                  capturePending={capturePending}
                  elfieName={profile.name}
                  onAvatar={async (nextCapture): Promise<boolean> => {
                    if (onAvatarSave === undefined) {
                      setNotice(t("profile.appearance.saveError"))
                      setCaptureError(t("profile.appearance.saveError"))
                      return false
                    }
                    setCaptureError("")
                    try {
                      const portraitUrl = await onAvatarSave(nextCapture)
                      const versionedPortraitUrl = addCacheBust(portraitUrl)
                      setLocalAvatar(versionedPortraitUrl)
                      onAvatarSaved?.(versionedPortraitUrl)
                      setNotice(t("profile.appearance.savedNotice"))
                      setCaptureOpen(false)
                      return true
                    } catch {
                      setNotice(t("profile.appearance.saveError"))
                      setCaptureError(t("profile.appearance.saveError"))
                      return false
                    }
                  }}
                  onOpenChange={changeCaptureOpen}
                  open={captureOpen}
                  trigger={(
                    <Button disabled={previewStatus !== "ready"} onClick={() => { void captureStage() }} size="sm" type="button">
                      <Camera aria-hidden="true" />{t("profile.appearance.capture")}
                    </Button>
                  )}
                />
              )}
              <Button disabled={previewStatus !== "ready"} onClick={resetPreview} size="sm" type="button" variant="ghost">
                <RotateCcw aria-hidden="true" />{t("profile.appearance.reset")}
              </Button>
              <Select disabled={previewStatus !== "ready"} onValueChange={applyPose} value={posePreset}>
                <SelectTrigger aria-label={t("profile.appearance.poseLabel")} className="profile-appearance__pose" size="sm">
                  <PersonStanding aria-hidden="true" />
                  <SelectValue>{t(`profile.appearance.pose.${posePreset}`)}</SelectValue>
                </SelectTrigger>
                <SelectContent align="end" position="popper">
                  {POSE_PRESETS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {t(`profile.appearance.pose.${option.value}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button onClick={() => changePreviewOpen(false)} size="sm" type="button" variant="outline">
                <Scan aria-hidden="true" />{t("profile.appearance.close")}
              </Button>
            </>
          ) : (
            <Button onClick={() => changePreviewOpen(true)} size="sm" type="button" variant="outline">
              <Scan aria-hidden="true" />{t("profile.appearance.open")}
            </Button>
          )}
        </div> : null}
      </header>
      {showControls && previewOpen ? (
        <ProfileGodotViewport
          onPreviewChange={onPreviewChange}
          onStageChange={onStageChange}
          onStatusChange={onStatusChange}
          profile={profile}
        />
      ) : (
        <div
          aria-label={t(showControls ? "profile.appearance.stage" : "profile.appearance.photoStage", { name: profile.name })}
          className="profile-appearance__stage profile-appearance__stage--idle"
          data-testid="appearance-idle-placeholder"
          ref={onStageChange}
          role="img"
        >
          <div className="profile-appearance__idle-card">
            {visiblePortrait.length > 0 ? (
              <div
                className={`profile-appearance__idle-portrait-frame${idlePortraitFrame === null ? "" : " profile-appearance__idle-portrait-frame--framed"}`}
                style={idlePortraitStyle}
              >
                <img
                  alt={t("profile.appearance.appearanceAlt", { name: profile.name })}
                  className="profile-appearance__idle-portrait"
                  draggable={false}
                  onLoad={(event) => {
                    if (!isFullBodyPortrait) return
                    setIdlePortraitSource({
                      bounds: readVisiblePortraitBounds(event.currentTarget),
                      height: event.currentTarget.naturalHeight,
                      width: event.currentTarget.naturalWidth,
                    })
                  }}
                  onError={() => {
                    if (!isFullBodyPortrait) return
                    setFullBodyUnavailable(true)
                    setIdlePortraitSource(null)
                  }}
                  src={visiblePortrait}
                />
              </div>
            ) : (
              <span className="profile-appearance__idle-fallback">{fallback}</span>
            )}
          </div>
          {showControls ? <p className="profile-appearance__hint">{t("profile.appearance.inactiveHint")}</p> : null}
        </div>
      )}
      {showControls && !captureOpen && captureError.length > 0 && <p className="profile-appearance__error" role="alert">{captureError}</p>}
      {showControls && notice.length > 0 && <p className="profile-appearance__notice" role="status">{notice}</p>}
    </section>
  )
}

function readVisiblePortraitBounds(image: HTMLImageElement) {
  if (image.naturalWidth < 2 || image.naturalHeight < 2) return null
  const canvas = document.createElement("canvas")
  canvas.width = image.naturalWidth
  canvas.height = image.naturalHeight
  const context = canvas.getContext("2d")
  if (context === null) return null
  try {
    context.drawImage(image, 0, 0, image.naturalWidth, image.naturalHeight)
    return calculateVisibleFrameBounds(
      image.naturalWidth,
      image.naturalHeight,
      context.getImageData(0, 0, image.naturalWidth, image.naturalHeight).data,
    )
  } catch {
    return null
  }
}

async function waitForBrowserFrames(): Promise<void> {
  await new Promise<void>((resolve) => {
    if (typeof window.requestAnimationFrame !== "function") {
      window.setTimeout(resolve, 100)
      return
    }
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => resolve())
    })
  })
}

function buildCaptureInput(
  stage: HTMLDivElement,
  profile: PublicProfile,
  localAvatar: string,
): AppearanceCaptureInput {
  const styles = getComputedStyle(stage)
  return {
    accent: styles.getPropertyValue("--accent").trim(),
    background: styles.getPropertyValue("--field-bg").trim(),
    fallback: profile.name.slice(0, 1).toUpperCase(),
    foreground: styles.getPropertyValue("--text").trim(),
    name: profile.name,
    portraitUrl: localAvatar || profile.portraitUrl,
    scale: 1,
    surface: styles.getPropertyValue("--surface-raised").trim(),
    yaw: 0,
  }
}

function revokeCapturedUrls(urls: Set<string>): void {
  for (const url of urls) revokeCaptureUrl(url)
  urls.clear()
}

function revokeCaptureUrl(url: string): void {
  if (typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(url)
}

function addCacheBust(url: string): string {
  const separator = url.includes("?") ? "&" : "?"
  return `${url}${separator}v=${Date.now()}`
}
