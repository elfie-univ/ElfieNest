import { useEffect, useRef, useState } from "react"
import { Camera, RotateCcw, Scan } from "lucide-react"

import { Button } from "@/components/ui/button"

import type { PublicProfile } from "./model"
import {
  AppearanceCaptureError,
  captureAppearance,
  type AppearanceCapture,
  type AppearanceCaptureAdapter,
  type AppearanceCaptureInput,
} from "./appearance-capture"
import { ProfileCaptureDialog } from "./ProfileCaptureDialog"
import { useAppearanceInteraction } from "./use-appearance-interaction"

type ProfileAppearanceStageProps = {
  readonly canCapture: boolean
  readonly capture?: AppearanceCaptureAdapter | undefined
  readonly onAvatarPreview?: (previewUrl: string) => void
  readonly profile: PublicProfile
}

type CaptureRequestKind = "initial" | "recapture"

export function ProfileAppearanceStage({
  canCapture,
  capture = captureAppearance,
  onAvatarPreview,
  profile,
}: ProfileAppearanceStageProps) {
  const [active, setActive] = useState(false)
  const [captureOpen, setCaptureOpen] = useState(false)
  const [captureError, setCaptureError] = useState("")
  const [capturePending, setCapturePending] = useState(false)
  const [currentCapture, setCurrentCapture] = useState<AppearanceCapture | null>(null)
  const [localAvatar, setLocalAvatar] = useState("")
  const [notice, setNotice] = useState("")
  const interaction = useAppearanceInteraction(active)
  const stageRef = useRef<HTMLDivElement>(null)
  const objectUrlsRef = useRef(new Set<string>())
  const captureGenerationRef = useRef(0)
  const fallback = profile.name.slice(0, 1).toUpperCase()

  useEffect(() => {
    captureGenerationRef.current += 1
    setActive(false)
    setCaptureOpen(false)
    setCaptureError("")
    setCapturePending(false)
    setCurrentCapture(null)
    setLocalAvatar("")
    setNotice("")
    interaction.reset()
    revokeCapturedUrls(objectUrlsRef.current)
  }, [profile.elfieId])

  useEffect(() => () => {
    captureGenerationRef.current += 1
    revokeCapturedUrls(objectUrlsRef.current)
  }, [])

  async function captureStage(kind: CaptureRequestKind): Promise<boolean> {
    const stage = stageRef.current
    if (stage === null) {
      return false
    }
    const generation = captureGenerationRef.current + 1
    captureGenerationRef.current = generation
    setCaptureError("")
    setCapturePending(true)
    try {
      const nextCapture = await capture(buildCaptureInput(
        stage,
        profile,
        localAvatar,
        interaction.yaw,
        interaction.scale,
      ))
      if (generation !== captureGenerationRef.current) {
        revokeCaptureUrl(nextCapture.previewUrl)
        return false
      }
      objectUrlsRef.current.add(nextCapture.previewUrl)
      setCurrentCapture(nextCapture)
      setCapturePending(false)
      return true
    } catch (error) {
      if (generation !== captureGenerationRef.current) {
        return false
      }
      if (error instanceof AppearanceCaptureError || error instanceof DOMException) {
        setCapturePending(false)
        if (kind === "initial") {
          setCaptureOpen(false)
        }
        setCaptureError("照片生成失败，请重试。")
        return false
      }
      throw error
    }
  }

  async function recapture(): Promise<void> {
    await captureStage("recapture")
  }

  function changeCaptureOpen(open: boolean): void {
    if (!open && capturePending) {
      captureGenerationRef.current += 1
      setCapturePending(false)
    }
    setCaptureOpen(open)
  }

  const visiblePortrait = localAvatar || profile.portraitUrl

  return (
    <section className="profile-appearance profile-dossier__section" aria-labelledby={`appearance-${profile.elfieId}`}>
      <header className="profile-appearance__header">
        <div>
          <span>外观</span>
          <h2 id={`appearance-${profile.elfieId}`}>3D 个体视图</h2>
        </div>
        <div className="profile-appearance__actions">
          <Button onClick={() => setActive((current) => !current)} size="sm" type="button" variant="outline">
            <Scan aria-hidden="true" />{active ? "关闭3D" : "打开3D"}
          </Button>
          <Button disabled={!active} onClick={interaction.reset} size="sm" type="button" variant="ghost">
            <RotateCcw aria-hidden="true" />复位视角
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
                setNotice("仅更新本地预览，刷新页面后会恢复。")
                setCaptureOpen(false)
              }}
              onOpenChange={changeCaptureOpen}
              onRecapture={recapture}
              open={captureOpen}
              trigger={(
                <Button onClick={() => { void captureStage("initial") }} size="sm" type="button">
                  <Camera aria-hidden="true" />拍照
                </Button>
              )}
            />
          )}
        </div>
      </header>
      <div
        aria-label={`${profile.name} 的可交互 3D 外观`}
        className={`profile-appearance__stage${active ? " profile-appearance__stage--active" : ""}`}
        onKeyDown={interaction.onKeyDown}
        onLostPointerCapture={interaction.onPointerLost}
        onPointerCancel={interaction.onPointerEnd}
        onPointerDown={interaction.onPointerDown}
        onPointerMove={interaction.onPointerMove}
        onPointerUp={interaction.onPointerEnd}
        onWheel={interaction.onWheel}
        ref={stageRef}
        role="application"
        tabIndex={active ? 0 : -1}
      >
        <div
          className="profile-appearance__model"
          data-scale={interaction.scale}
          data-testid="appearance-model"
          data-yaw={interaction.yaw}
          style={{ transform: `rotateY(${interaction.yaw}deg) scale(${interaction.scale})` }}
        >
          {visiblePortrait.length > 0 ? (
            <img
              alt={localAvatar.length > 0 ? `${profile.name} 的本地头像预览` : `${profile.name} 的外观`}
              draggable={false}
              src={visiblePortrait}
            />
          ) : (
            <span className="profile-appearance__fallback">{fallback}</span>
          )}
          {active && <i aria-hidden="true" className="profile-appearance__model-body" />}
        </div>
        <div aria-hidden="true" className="profile-appearance__platform" />
        <p className="profile-appearance__hint">
          {active ? "拖拽旋转，滚轮或双指缩放；键盘方向键、加减键与 Home 也可操作。" : "打开 3D 后可直接拖拽查看。"}
        </p>
      </div>
      {!captureOpen && captureError.length > 0 && <p className="profile-appearance__error" role="alert">{captureError}</p>}
      {notice.length > 0 && <p className="profile-appearance__notice" role="status">{notice}</p>}
    </section>
  )
}

function buildCaptureInput(
  stage: HTMLDivElement,
  profile: PublicProfile,
  localAvatar: string,
  yaw: number,
  scale: number,
): AppearanceCaptureInput {
  const styles = getComputedStyle(stage)
  return {
    accent: styles.getPropertyValue("--accent").trim(),
    background: styles.getPropertyValue("--field-bg").trim(),
    fallback: profile.name.slice(0, 1).toUpperCase(),
    foreground: styles.getPropertyValue("--text").trim(),
    name: profile.name,
    portraitUrl: localAvatar || profile.portraitUrl,
    scale,
    surface: styles.getPropertyValue("--surface-raised").trim(),
    yaw,
  }
}

function revokeCapturedUrls(urls: Set<string>): void {
  for (const url of urls) {
    if (typeof URL.revokeObjectURL === "function") {
      URL.revokeObjectURL(url)
    }
  }
  urls.clear()
}

function revokeCaptureUrl(url: string): void {
  if (typeof URL.revokeObjectURL === "function") {
    URL.revokeObjectURL(url)
  }
}
