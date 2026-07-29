import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  HAPPY_EXPERIENCE,
  LONG_BIOGRAPHY_EXPERIENCE,
  MISSING_PUBLIC_FIELDS_EXPERIENCE,
} from "./mock-data"
import { ProfileAppearanceStage } from "./ProfileAppearanceStage"

const profileStyles = readFileSync(resolve(import.meta.dirname, "../../shared/chat-profile.css"), "utf8")

describe("ProfileAppearanceStage", () => {
  it("activates the local 3D mock and supports direct pointer, wheel, and keyboard control", async () => {
    // Given: an adopter viewing Happy's appearance stage.
    const user = userEvent.setup()
    render(
      <ProfileAppearanceStage
        canCapture
        profile={HAPPY_EXPERIENCE.publicProfile}
      />,
    )

    // When: the visitor activates 3D and manipulates the model directly.
    await user.click(screen.getByRole("button", { name: "打开3D" }))
    const stage = screen.getByRole("application", { name: "Happy 的可交互 3D 外观" })
    const model = screen.getByTestId("appearance-model")
    const setPointerCapture = vi.fn()
    Object.defineProperty(stage, "setPointerCapture", { configurable: true, value: setPointerCapture })
    fireEvent.pointerDown(stage, { clientX: 20, clientY: 20, pointerId: 1, pointerType: "mouse" })
    fireEvent.pointerMove(stage, { clientX: 60, clientY: 20, pointerId: 1, pointerType: "mouse" })
    fireEvent.pointerUp(stage, { pointerId: 1, pointerType: "mouse" })
    fireEvent.wheel(stage, { deltaY: -100 })
    fireEvent.keyDown(stage, { key: "ArrowLeft" })
    fireEvent.keyDown(stage, { key: "+" })

    // Then: yaw and zoom visibly change without a bottom rotation toolbar.
    expect(setPointerCapture).toHaveBeenCalledWith(1)
    expect(model).not.toHaveAttribute("data-yaw", "0")
    expect(Number(model.getAttribute("data-scale"))).toBeGreaterThan(1)
    expect(screen.queryByRole("button", { name: /左转|右转|放大|缩小/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/Observer|本地 3D 观察/)).not.toBeInTheDocument()
  })

  it("supports two-pointer pinch, Home reset, and the compact reset action", async () => {
    // Given: an active local 3D stage.
    const user = userEvent.setup()
    render(
      <ProfileAppearanceStage
        canCapture
        profile={HAPPY_EXPERIENCE.publicProfile}
      />,
    )
    await user.click(screen.getByRole("button", { name: "打开3D" }))
    const stage = screen.getByRole("application", { name: "Happy 的可交互 3D 外观" })
    const model = screen.getByTestId("appearance-model")

    // When: two touch pointers pinch outward and the view is reset twice.
    fireEvent.pointerDown(stage, { clientX: 20, clientY: 20, pointerId: 1, pointerType: "touch" })
    fireEvent.pointerDown(stage, { clientX: 40, clientY: 20, pointerId: 2, pointerType: "touch" })
    fireEvent.pointerMove(stage, { clientX: 70, clientY: 20, pointerId: 2, pointerType: "touch" })
    expect(Number(model.getAttribute("data-scale"))).toBeGreaterThan(1)
    fireEvent.keyDown(stage, { key: "Home" })
    expect(model).toHaveAttribute("data-yaw", "0")
    expect(model).toHaveAttribute("data-scale", "1")
    fireEvent.keyDown(stage, { key: "ArrowRight" })
    await user.click(screen.getByRole("button", { name: "复位视角" }))

    // Then: reset returns the deterministic initial composition.
    expect(model).toHaveAttribute("data-yaw", "0")
    expect(model).toHaveAttribute("data-scale", "1")
  })

  it("clears lost and deactivated pointer gestures before a fresh drag", async () => {
    // Given: an active stage with one interrupted pointer.
    const user = userEvent.setup()
    render(<ProfileAppearanceStage canCapture profile={HAPPY_EXPERIENCE.publicProfile} />)
    await user.click(screen.getByRole("button", { name: "打开3D" }))
    const stage = screen.getByRole("application")
    const model = screen.getByTestId("appearance-model")
    fireEvent.pointerDown(stage, { clientX: 10, clientY: 10, pointerId: 1, pointerType: "touch" })

    // When: pointer capture is lost and a new pointer begins.
    fireEvent.lostPointerCapture(stage, { pointerId: 1, pointerType: "touch" })
    fireEvent.pointerDown(stage, { clientX: 20, clientY: 10, pointerId: 2, pointerType: "touch" })
    fireEvent.pointerMove(stage, { clientX: 50, clientY: 10, pointerId: 2, pointerType: "touch" })

    // Then: the new gesture is orbit, not a stale two-pointer pinch.
    expect(model).not.toHaveAttribute("data-yaw", "0")
    expect(model).toHaveAttribute("data-scale", "1")

    // When: another gesture is interrupted by deactivation.
    fireEvent.pointerDown(stage, { clientX: 10, clientY: 10, pointerId: 3, pointerType: "touch" })
    await user.click(screen.getByRole("button", { name: "关闭3D" }))
    await user.click(screen.getByRole("button", { name: "打开3D" }))
    fireEvent.pointerDown(stage, { clientX: 20, clientY: 10, pointerId: 4, pointerType: "touch" })
    fireEvent.pointerMove(stage, { clientX: 45, clientY: 10, pointerId: 4, pointerType: "touch" })

    // Then: deactivation also cleared the abandoned pointer bookkeeping.
    expect(Number(model.getAttribute("data-yaw"))).toBeGreaterThan(12)
    expect(model).toHaveAttribute("data-scale", "1")
  })

  it("bounds wheel zoom and disables model animation for reduced motion", async () => {
    // Given: an active appearance stage and the profile stylesheet.
    const user = userEvent.setup()
    render(<ProfileAppearanceStage canCapture profile={HAPPY_EXPERIENCE.publicProfile} />)
    await user.click(screen.getByRole("button", { name: "打开3D" }))
    const stage = screen.getByRole("application")
    const model = screen.getByTestId("appearance-model")

    // When: zoom is repeatedly driven beyond both supported limits.
    for (let step = 0; step < 30; step += 1) {
      fireEvent.wheel(stage, { deltaY: -100 })
    }

    // Then: the upper bound and reduced-motion contract remain explicit.
    expect(model).toHaveAttribute("data-scale", "1.8")
    for (let step = 0; step < 40; step += 1) {
      fireEvent.wheel(stage, { deltaY: 100 })
    }
    expect(model).toHaveAttribute("data-scale", "0.72")
    expect(profileStyles).toMatch(
      /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.profile-appearance__model\s*\{\s*transition: none;/,
    )
  })

  it("keeps capture adopter-only and uses an immediate initial fallback", () => {
    // Given: a visitor projection and a profile without a portrait.
    const { rerender } = render(
      <ProfileAppearanceStage
        canCapture={false}
        profile={MISSING_PUBLIC_FIELDS_EXPERIENCE.publicProfile}
      />,
    )

    // When: the fallback stage is displayed.
    // Then: the initial is immediate and capture is absent from the DOM.
    expect(screen.getByText("M", { selector: ".profile-appearance__fallback" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "拍照" })).not.toBeInTheDocument()

    // When: the Elfie changes after the stage has been opened.
    rerender(
      <ProfileAppearanceStage
        canCapture={false}
        profile={HAPPY_EXPERIENCE.publicProfile}
      />,
    )

    // Then: the stage resets to portrait mode for the new Elfie.
    expect(screen.getByRole("button", { name: "打开3D" })).toBeInTheDocument()
  })

  it("opens capture with the current stage composition and applies a local avatar preview", async () => {
    // Given: a deterministic capture adapter for the active stage.
    const user = userEvent.setup()
    document.documentElement.style.setProperty("--accent", "accent-token")
    document.documentElement.style.setProperty("--field-bg", "background-token")
    document.documentElement.style.setProperty("--surface-raised", "surface-token")
    document.documentElement.style.setProperty("--text", "foreground-token")
    const blob = new Blob(["png"], { type: "image/png" })
    const capture = vi.fn().mockResolvedValue({ blob, previewUrl: "blob:stage-preview" })
    render(
      <ProfileAppearanceStage
        canCapture
        capture={capture}
        profile={HAPPY_EXPERIENCE.publicProfile}
      />,
    )
    await user.click(screen.getByRole("button", { name: "打开3D" }))
    fireEvent.keyDown(screen.getByRole("application"), { key: "ArrowRight" })

    // When: the adopter captures and selects the preview as avatar.
    await user.click(screen.getByRole("button", { name: "拍照" }))
    await user.click(await screen.findByRole("button", { name: "设为头像" }))

    // Then: capture receives the current transform and the local-only notice is announced.
    expect(capture).toHaveBeenCalledWith(expect.objectContaining({
      accent: "accent-token",
      background: "background-token",
      foreground: "foreground-token",
      name: "Happy",
      portraitUrl: HAPPY_EXPERIENCE.publicProfile.portraitUrl,
      yaw: 8,
      scale: 1,
      surface: "surface-token",
    }))
    expect(screen.getByRole("status")).toHaveTextContent("仅更新本地预览，刷新页面后会恢复")
    expect(screen.getByRole("img", { name: "Happy 的本地头像预览" })).toHaveAttribute(
      "src",
      "blob:stage-preview",
    )
    document.documentElement.removeAttribute("style")
  })

  it("announces capture failure and leaves the stage recoverable", async () => {
    // Given: a browser capture adapter that rejects the PNG operation.
    const user = userEvent.setup()
    const capture = vi.fn().mockRejectedValue(new DOMException("blocked", "NotAllowedError"))
    render(
      <ProfileAppearanceStage
        canCapture
        capture={capture}
        profile={HAPPY_EXPERIENCE.publicProfile}
      />,
    )

    // When: the adopter requests a photo.
    await user.click(screen.getByRole("button", { name: "拍照" }))

    // Then: a clear failure state appears without removing the reset/open controls.
    expect(await screen.findByRole("alert")).toHaveTextContent("照片生成失败")
    expect(screen.getByRole("button", { name: "打开3D" })).toBeInTheDocument()
  })

  it("preserves the current preview and dialog when recapture fails", async () => {
    // Given: one successful capture followed by a rejected recapture.
    const user = userEvent.setup()
    const first = { blob: new Blob(["first"], { type: "image/png" }), previewUrl: "blob:first" }
    const capture = vi.fn()
      .mockResolvedValueOnce(first)
      .mockRejectedValueOnce(new DOMException("blocked", "NotAllowedError"))
    render(<ProfileAppearanceStage canCapture capture={capture} profile={HAPPY_EXPERIENCE.publicProfile} />)
    await user.click(screen.getByRole("button", { name: "拍照" }))
    expect(await screen.findByRole("img", { name: "Happy 的拍照预览" })).toHaveAttribute("src", "blob:first")

    // When: recapture fails.
    await user.click(screen.getByRole("button", { name: "重新拍摄" }))

    // Then: the current decision dialog and valid preview remain with recovery copy.
    expect(await screen.findByRole("alert")).toHaveTextContent("照片生成失败")
    expect(screen.getByRole("dialog", { name: "确认这张照片" })).toBeVisible()
    expect(screen.getByRole("img", { name: "Happy 的拍照预览" })).toHaveAttribute("src", "blob:first")
  })

  it("resets stage and capture state across Elfies and discards a stale in-flight result", async () => {
    // Given: Happy has an applied local capture plus a second capture still in flight.
    const user = userEvent.setup()
    let resolveStale = (captureValue: { readonly blob: Blob; readonly previewUrl: string }): void => {
      void captureValue
    }
    const stalePromise = new Promise<{ readonly blob: Blob; readonly previewUrl: string }>((resolve) => {
      resolveStale = resolve
    })
    const first = { blob: new Blob(["first"], { type: "image/png" }), previewUrl: "blob:first" }
    const stale = { blob: new Blob(["stale"], { type: "image/png" }), previewUrl: "blob:stale" }
    const capture = vi.fn().mockResolvedValueOnce(first).mockReturnValueOnce(stalePromise)
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL })
    const { rerender } = render(
      <ProfileAppearanceStage canCapture capture={capture} profile={HAPPY_EXPERIENCE.publicProfile} />,
    )
    await user.click(screen.getByRole("button", { name: "打开3D" }))
    fireEvent.keyDown(screen.getByRole("application"), { key: "ArrowRight" })
    await user.click(screen.getByRole("button", { name: "拍照" }))
    await user.click(await screen.findByRole("button", { name: "设为头像" }))
    await user.click(screen.getByRole("button", { name: "拍照" }))

    // When: the profile switches before the second capture resolves.
    rerender(
      <ProfileAppearanceStage
        canCapture
        capture={capture}
        profile={LONG_BIOGRAPHY_EXPERIENCE.publicProfile}
      />,
    )

    // Then: stage, dialog, and local-avatar state reset immediately.
    expect(screen.getByRole("button", { name: "打开3D" })).toBeInTheDocument()
    expect(screen.getByTestId("appearance-model")).toHaveAttribute("data-yaw", "0")
    expect(screen.getByTestId("appearance-model")).toHaveAttribute("data-scale", "1")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.queryByText("仅更新本地预览")).not.toBeInTheDocument()
    expect(screen.getByText("K", { selector: ".profile-appearance__fallback" })).toBeInTheDocument()

    // When: Happy's stale asynchronous capture finally resolves.
    resolveStale(stale)

    // Then: it is revoked instead of being applied to the new Elfie.
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:stale"))
    expect(screen.queryByRole("img", { name: /本地头像预览|拍照预览/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    Reflect.deleteProperty(URL, "revokeObjectURL")
  })
})
