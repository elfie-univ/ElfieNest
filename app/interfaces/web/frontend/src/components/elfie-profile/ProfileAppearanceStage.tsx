import { useCallback, useEffect, useRef, useState } from "react"
import { Camera, RotateCcw, Scan } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"

import type { AppearanceCapture, AppearanceCaptureAdapter, AppearanceCaptureInput } from "./appearance-capture"
import { AppearanceCaptureError } from "./appearance-capture"
import { ProfileCaptureDialog } from "./ProfileCaptureDialog"
import { ProfileGodotViewport, type PreviewStatus } from "./ProfileGodotViewport"
import { ProfileGodotPreviewError, type ProfileGodotPreview } from "./profile-godot-preview"
import type { PublicProfile } from "./model"

type ProfileAppearanceStageProps = {
  readonly canCapture: boolean
  readonly capture?: AppearanceCaptureAdapter | undefined
  readonly onAvatarPreview?: (previewUrl: string) => void
  readonly profile: PublicProfile
}

type CaptureRequestKind = "initial" | "recapture"

export function ProfileAppearanceStage({
  canCapture,
  capture,
  onAvatarPreview,
  profile,
}: ProfileAppearanceStageProps) {
  const { t } = useTranslation("chat")
  const previewRef = useRef<ProfileGodotPreview | null>(null)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const objectUrlsRef = useRef(new Set<string>())
  const captureGenerationRef = useRef(0)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewStatus, setPreviewStatus] = useState<PreviewStatus>("idle")
  const [captureOpen, setCaptureOpen] = useState(false)
  const [captureError, setCaptureError] = useState("")
  const [capturePending, setCapturePending] = useState(false)
  const [currentCapture, setCurrentCapture] = useState<AppearanceCapture | null>(null)
  const [localAvatar, setLocalAvatar] = useState("")
  const [notice, setNotice] = useState("")

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
    setPreviewOpen(false)
    setPreviewStatus("idle")
    setCaptureOpen(false)
    setCaptureError("")
    setCapturePending(false)
    setCurrentCapture(null)
    setLocalAvatar("")
    setNotice("")
    revokeCapturedUrls(objectUrlsRef.current)
  }, [profile.elfieId])

  useEffect(() => () => {
    captureGenerationRef.current += 1
    revokeCapturedUrls(objectUrlsRef.current)
  }, [])

  async function captureStage(kind: CaptureRequestKind): Promise<boolean> {
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
        if (kind === "initial") setCaptureOpen(false)
        setCaptureError(t("profile.appearance.captureError"))
        return false
      }
      throw error
    }
  }

  async function captureWithGodot(): Promise<AppearanceCapture> {
    const preview = previewRef.current
    if (preview === null) throw new ProfileGodotPreviewError("preview_not_ready")
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
    }
    setPreviewOpen(open)
  }

  function resetPreview(): void {
    previewRef.current?.send("reset")
  }

  const fallback = profile.name.slice(0, 1).toUpperCase()
  const visiblePortrait = localAvatar || profile.portraitUrl

  return (
    <section aria-labelledby={`appearance-${profile.elfieId}`} className="profile-appearance profile-dossier__section">
      <header className="profile-appearance__header">
        <div>
          <span>{t("profile.appearance.eyebrow")}</span>
          <p className="profile-appearance__title" id={`appearance-${profile.elfieId}`}>
            {t("profile.appearance.title")}
          </p>
        </div>
        <div className="profile-appearance__actions">
          <Button onClick={() => changePreviewOpen(!previewOpen)} size="sm" type="button" variant="outline">
            <Scan aria-hidden="true" />{previewOpen ? t("profile.appearance.close") : t("profile.appearance.open")}
          </Button>
          <Button disabled={!previewOpen || previewStatus !== "ready"} onClick={resetPreview} size="sm" type="button" variant="ghost">
            <RotateCcw aria-hidden="true" />{t("profile.appearance.reset")}
          </Button>
          {canCapture && (
            <ProfileCaptureDialog
              capture={currentCapture}
              captureError={captureError}
              capturePending={capturePending}
              elfieName={profile.name}
              onAvatar={(nextCapture) => {
                setLocalAvatar(nextCapture.previewUrl)
                onAvatarPreview?.(nextCapture.previewUrl)
                setNotice(t("profile.appearance.localNotice"))
                setCaptureOpen(false)
              }}
              onOpenChange={changeCaptureOpen}
              onRecapture={() => { void captureStage("recapture") }}
              open={captureOpen}
              trigger={(
                <Button disabled={previewStatus !== "ready"} onClick={() => { void captureStage("initial") }} size="sm" type="button">
                  <Camera aria-hidden="true" />{t("profile.appearance.capture")}
                </Button>
              )}
            />
          )}
        </div>
      </header>
      {previewOpen ? (
        <ProfileGodotViewport
          onPreviewChange={onPreviewChange}
          onStageChange={onStageChange}
          onStatusChange={onStatusChange}
          profile={profile}
        />
      ) : (
        <div
          aria-label={t("profile.appearance.stage", { name: profile.name })}
          className="profile-appearance__stage profile-appearance__stage--idle"
          data-testid="appearance-idle-placeholder"
          ref={onStageChange}
          role="img"
        >
          <div className="profile-appearance__idle-card">
            {visiblePortrait.length > 0 ? (
              <img
                alt={t("profile.appearance.appearanceAlt", { name: profile.name })}
                className="profile-appearance__idle-portrait"
                draggable={false}
                src={visiblePortrait}
              />
            ) : (
              <span className="profile-appearance__idle-fallback">{fallback}</span>
            )}
          </div>
          <p className="profile-appearance__hint">{t("profile.appearance.inactiveHint")}</p>
        </div>
      )}
      {!captureOpen && captureError.length > 0 && <p className="profile-appearance__error" role="alert">{captureError}</p>}
      {notice.length > 0 && <p className="profile-appearance__notice" role="status">{notice}</p>}
    </section>
  )
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
