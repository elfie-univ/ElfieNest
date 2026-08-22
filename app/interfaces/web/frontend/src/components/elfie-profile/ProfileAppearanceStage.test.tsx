import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import { HAPPY_EXPERIENCE, MISSING_PUBLIC_FIELDS_EXPERIENCE } from "../../test/fixtures/elfie-profile"
import type { AppearanceCapture } from "./appearance-capture"
import type { GodotAppearance } from "./model"
import { ProfileAppearanceStage } from "./ProfileAppearanceStage"

vi.mock("./profile-godot-preview", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./profile-godot-preview")>()
  return { ...actual, measureVisibleFrame: vi.fn().mockResolvedValue(null) }
})

vi.mock("./profile-capture-crop", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./profile-capture-crop")>()
  return {
    ...actual,
    cropCapture: vi.fn(async (value: AppearanceCapture) => value),
    inspectCapture: vi.fn(async () => ({ height: 600, visibleBounds: null, width: 1000 })),
  }
})

createI18n()

Object.defineProperty(URL, "createObjectURL", { configurable: true, value: () => "blob:godot-capture" })
Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: () => undefined })

Object.defineProperties(HTMLElement.prototype, {
  hasPointerCapture: { configurable: true, value: () => false },
  setPointerCapture: { configurable: true, value: () => undefined },
  releasePointerCapture: { configurable: true, value: () => undefined },
  scrollIntoView: { configurable: true, value: () => undefined },
})

const profileStyles = readFileSync(resolve(import.meta.dirname, "../../shared/chat-profile.css"), "utf8")

const RUNTIME_APPEARANCE = {
  species_id: "fox",
  profile_version: 1,
  height_scale: 1,
  build_scale: 1,
  height_label: "standard",
  build_label: "standard",
  bone_scales: {},
  blend_shapes: {},
  material_parameters: { palette_id: "amber" },
  species_traits: {},
} satisfies GodotAppearance

describe("ProfileAppearanceStage", () => {
  it("keeps the appearance stage inside the profile width", () => {
    const stageRule = profileStyles.match(/\.profile-appearance__stage\s*\{[^}]+\}/)?.[0] ?? ""

    expect(stageRule).toContain("width: 100%")
    expect(stageRule).toContain("max-width: 100%")
    expect(stageRule).toContain("min-width: 0")
    expect(stageRule).toContain("min-height: 0")
  })

  it("mounts the real Godot preview only after opening 3D", async () => {
    const user = userEvent.setup()
    const enqueue = vi.fn<(payload: string) => void>()
    const profile = { ...HAPPY_EXPERIENCE.publicProfile, runtimeAppearance: RUNTIME_APPEARANCE }
    render(<ProfileAppearanceStage canCapture={false} profile={profile} />)

    expect(screen.getByRole("button", { name: "打开3D" })).toBeInTheDocument()
    expect(screen.queryByTitle("Happy 的可交互 3D 外观")).not.toBeInTheDocument()
    expect(screen.getByTestId("appearance-idle-placeholder")).toBeInTheDocument()
    expect(screen.getByRole("img", { name: "Happy 的外观" })).toHaveAttribute("src", profile.fullBodyUrl)

    await user.click(screen.getByRole("button", { name: "打开3D" }))
    const frame = getFrame()
    defineEnqueue(frame, enqueue)
    sendGodotEvent(frame, { channel: "elfie-lab", event: "ready" })

    await waitFor(() => expect(enqueue).toHaveBeenCalledOnce())
    const rawCommand = enqueue.mock.calls[0]?.[0]
    if (rawCommand === undefined) throw new TypeError("Expected a Godot configure command")
    expect(JSON.parse(rawCommand)).toEqual(expect.objectContaining({
      action: "configure",
      payload: expect.objectContaining({
        appearance: RUNTIME_APPEARANCE,
        elfie_id: "12345678",
        species_id: "fox",
      }),
    }))
    expect(frame).toHaveAttribute("src", "/runtime/godot/elfienest.html?mode=elfie_lab")
    expect(screen.queryByTestId("appearance-model")).not.toBeInTheDocument()
    expect(screen.queryByRole("img", { name: /Happy 的外观/ })).not.toBeInTheDocument()

    await completeConfigureAndCalibration(frame, enqueue)
    await user.click(screen.getByRole("button", { name: "复位视角" }))
    expect(enqueue).toHaveBeenCalledTimes(3)
    expect(JSON.parse(String(enqueue.mock.calls[2]?.[0]))).toEqual(expect.objectContaining({ action: "reset" }))

    await user.click(screen.getByRole("combobox", { name: "选择姿势" }))
    await user.click(screen.getByRole("option", { name: "挥手" }))
    expect(JSON.parse(String(enqueue.mock.calls[3]?.[0]))).toEqual(expect.objectContaining({
      action: "preview_intent",
      payload: { intent: expect.objectContaining({ motion: "pose_waving", type: "motion" }) },
    }))

    fireEvent.keyDown(screen.getByRole("application"), { key: "ArrowLeft" })
    expect(JSON.parse(String(enqueue.mock.calls[4]?.[0]))).toEqual(expect.objectContaining({ action: "orbit" }))
    fireEvent.keyDown(screen.getByRole("application"), { key: "ArrowUp" })
    expect(JSON.parse(String(enqueue.mock.calls[5]?.[0]))).toEqual(expect.objectContaining({
      action: "orbit",
      payload: { delta: { x: 0, y: -0.18 } },
    }))

    await user.click(screen.getByRole("button", { name: "关闭3D" }))
    expect(screen.queryByTitle("Happy 的可交互 3D 外观")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "打开3D" })).toBeInTheDocument()
  })

  it("falls back to the stored headshot when the full-body portrait is unavailable", async () => {
    const profile = {
      ...HAPPY_EXPERIENCE.publicProfile,
      fullBodyUrl: "data:image/png;base64,full-body",
      portraitUrl: "data:image/png;base64,headshot",
      runtimeAppearance: RUNTIME_APPEARANCE,
    }
    render(<ProfileAppearanceStage canCapture={false} profile={profile} />)

    const portrait = screen.getByRole("img", { name: "Happy 的外观" })
    fireEvent.error(portrait)

    await waitFor(() => expect(screen.getByRole("img", { name: "Happy 的外观" })).toHaveAttribute("src", profile.portraitUrl))
  })

  it("keeps the real viewport honest when resolved appearance data is unavailable", async () => {
    const user = userEvent.setup()
    render(<ProfileAppearanceStage canCapture={false} profile={MISSING_PUBLIC_FIELDS_EXPERIENCE.publicProfile} />)

    expect(screen.queryByTitle("Missing Fields Happy 的可交互 3D 外观")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "打开3D" }))
    expect(getFrame()).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent("正在连接 3D 角色…")
    expect(screen.queryByTestId("appearance-model")).not.toBeInTheDocument()
  })

  it("keeps adopter capture available after the real preview is loaded", async () => {
    const user = userEvent.setup()
    const blob = new Blob(["png"], { type: "image/png" })
    const capture = vi.fn().mockResolvedValue({ blob, previewUrl: "blob:stage-preview" })
    const profile = { ...HAPPY_EXPERIENCE.publicProfile, runtimeAppearance: RUNTIME_APPEARANCE }
    const onAvatarSave = vi.fn().mockResolvedValue("/api/v1/elfies/12345678/portrait")
    const onAvatarSaved = vi.fn()
    const { container } = render(
      <ProfileAppearanceStage
        canCapture
        capture={capture}
        onAvatarSave={onAvatarSave}
        onAvatarSaved={onAvatarSaved}
        profile={profile}
      />,
    )
    await user.click(screen.getByRole("button", { name: "打开3D" }))
    const frame = getFrame()
    const enqueue = vi.fn<(payload: string) => void>()
    defineEnqueue(frame, enqueue)
    sendGodotEvent(frame, { channel: "elfie-lab", event: "ready" })
    await completeConfigureAndCalibration(frame, enqueue)

    await user.click(screen.getByRole("button", { name: "拍照" }))
    await waitFor(() => expect(capture).toHaveBeenCalledOnce())
    await user.click(await screen.findByRole("button", { name: "设为头像" }))

    const notice = container.querySelector(".profile-appearance__notice")
    if (notice === null) throw new TypeError("Expected the saved avatar notice")
    expect(notice).toHaveTextContent("头像已保存")
    expect(onAvatarSave).toHaveBeenCalledWith(expect.objectContaining({ blob }))
    expect(onAvatarSaved).toHaveBeenCalledWith(expect.stringContaining("/api/v1/elfies/12345678/portrait?v="))

    await user.click(screen.getByRole("button", { name: "关闭3D" }))
    expect(screen.getByRole("img", { name: "Happy 的外观" })).toHaveAttribute("src", profile.fullBodyUrl)
  })

  it("keeps the crop dialog open when avatar persistence fails", async () => {
    const user = userEvent.setup()
    const blob = new Blob(["png"], { type: "image/png" })
    const capture = vi.fn().mockResolvedValue({ blob, previewUrl: "blob:stage-preview" })
    const profile = { ...HAPPY_EXPERIENCE.publicProfile, runtimeAppearance: RUNTIME_APPEARANCE }
    const onAvatarSave = vi.fn().mockRejectedValue(new Error("persist failed"))
    render(
      <ProfileAppearanceStage
        canCapture
        capture={capture}
        onAvatarSave={onAvatarSave}
        profile={profile}
      />,
    )
    await user.click(screen.getByRole("button", { name: "打开3D" }))
    const frame = getFrame()
    const enqueue = vi.fn<(payload: string) => void>()
    defineEnqueue(frame, enqueue)
    sendGodotEvent(frame, { channel: "elfie-lab", event: "ready" })
    await completeConfigureAndCalibration(frame, enqueue)

    await user.click(screen.getByRole("button", { name: "拍照" }))
    await waitFor(() => expect(capture).toHaveBeenCalledOnce())
    await user.click(await screen.findByRole("button", { name: "设为头像" }))

    expect(onAvatarSave).toHaveBeenCalledOnce()
    expect(screen.getByRole("dialog", { name: "确认这张照片" })).toBeVisible()
    expect(screen.getByRole("alert")).toHaveTextContent("头像保存失败，请重试。")
  })
})

function getFrame(): HTMLIFrameElement {
  const frame = screen.queryByTitle("Happy 的可交互 3D 外观")
    ?? screen.getByTitle("Missing Fields Happy 的可交互 3D 外观")
  if (!(frame instanceof HTMLIFrameElement)) throw new TypeError("Expected the embedded Godot preview")
  return frame
}

function defineEnqueue(frame: HTMLIFrameElement, enqueue: (payload: string) => void): void {
  if (frame.contentWindow === null) throw new TypeError("Expected the Godot frame window")
  Object.defineProperty(frame.contentWindow, "elfieLabEnqueue", {
    configurable: true,
    value: enqueue,
  })
}

function sendGodotEvent(frame: HTMLIFrameElement, data: Readonly<Record<string, unknown>>): void {
  if (frame.contentWindow === null) throw new TypeError("Expected the Godot frame window")
  window.dispatchEvent(new MessageEvent("message", {
    data,
    origin: window.location.origin,
    source: frame.contentWindow,
  }))
}

async function completeConfigureAndCalibration(
  frame: HTMLIFrameElement,
  enqueue: ReturnType<typeof vi.fn<(payload: string) => void>>,
): Promise<void> {
  sendGodotEvent(frame, { channel: "elfie-lab", event: "completed", action: "configure", request_id: "configure" })
  await waitFor(() => expect(enqueue).toHaveBeenCalledTimes(2))
  const rawCaptureCommand = enqueue.mock.calls[1]?.[0]
  if (rawCaptureCommand === undefined) throw new TypeError("Expected a calibration capture command")
  const captureRequestId = String(JSON.parse(rawCaptureCommand).request_id)
  sendGodotEvent(frame, { channel: "elfie-lab", event: "completed", action: "capture", request_id: captureRequestId })
  sendGodotEvent(frame, {
    channel: "elfie-lab",
    data_url: `data:image/png;base64,${btoa("png")}`,
    event: "portrait",
    request_id: captureRequestId,
  })
  await waitFor(() => expect(screen.getByText("角色已装载 · 可交互")).toBeInTheDocument())
}
