import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import type { AppearanceCapture } from "./appearance-capture"
import { ProfileCaptureDialog } from "./ProfileCaptureDialog"

createI18n()

const captureBlob = new Blob(["same-png"], { type: "image/png" })
const capture: AppearanceCapture = {
  blob: captureBlob,
  previewUrl: "blob:preview",
}

type FixtureProps = {
  readonly onAvatar: (value: AppearanceCapture) => void
  readonly onDownload?: (value: AppearanceCapture, filename: string) => void
  readonly onRecapture: () => void
}

function DialogFixture({ onAvatar, onDownload, onRecapture }: FixtureProps) {
  const [open, setOpen] = useState(false)
  return (
    <ProfileCaptureDialog
      capture={capture}
      elfieName="Happy"
      onAvatar={onAvatar}
      onDownload={onDownload}
      onOpenChange={setOpen}
      onRecapture={onRecapture}
      open={open}
      trigger={<button type="button">拍照</button>}
    />
  )
}

describe("ProfileCaptureDialog", () => {
  it("uses one PNG capture for preview, avatar, and download", async () => {
    // Given: a completed stage capture.
    const user = userEvent.setup()
    const onAvatar = vi.fn()
    const onDownload = vi.fn()
    const onRecapture = vi.fn()
    render(
      <DialogFixture
        onAvatar={onAvatar}
        onDownload={onDownload}
        onRecapture={onRecapture}
      />,
    )

    // When: the dialog opens and each persistent action is chosen.
    const trigger = screen.getByRole("button", { name: "拍照" })
    await user.click(trigger)
    expect(screen.getByRole("img", { name: "Happy 的拍照预览" })).toHaveAttribute(
      "src",
      capture.previewUrl,
    )
    await user.click(screen.getByRole("button", { name: "下载图片" }))

    // Then: download receives the exact capture object and keeps the dialog usable.
    expect(onDownload).toHaveBeenCalledWith(capture, "Happy-elfie.png")
    expect(onDownload.mock.calls[0]?.[0].blob).toBe(captureBlob)
    await user.click(screen.getByRole("button", { name: "设为头像" }))
    expect(onAvatar).toHaveBeenCalledWith(capture)
    expect(onAvatar.mock.calls[0]?.[0].blob).toBe(captureBlob)
    expect(trigger).toHaveFocus()
  })

  it("supports recapture, cancel, Escape, and focus return", async () => {
    // Given: an openable Radix capture dialog.
    const user = userEvent.setup()
    const onRecapture = vi.fn()
    render(
      <DialogFixture
        onAvatar={vi.fn()}
        onRecapture={onRecapture}
      />,
    )
    const trigger = screen.getByRole("button", { name: "拍照" })

    // When: recapture is requested.
    await user.click(trigger)
    expect(screen.getByRole("dialog", { name: "确认这张照片" })).toBeVisible()
    await user.click(screen.getByRole("button", { name: "重新拍摄" }))

    // Then: recapture keeps the current decision surface while work proceeds.
    expect(onRecapture).toHaveBeenCalledOnce()
    expect(screen.getByRole("dialog", { name: "确认这张照片" })).toBeVisible()
    expect(screen.getByRole("button", { name: "重新拍摄" })).toHaveFocus()

    // When: the still-open dialog is cancelled.
    await user.click(screen.getByRole("button", { name: "取消" }))

    // Then: no dialog remains and trigger focus is restored.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()

    // When: it is reopened and dismissed with Escape.
    await user.click(trigger)
    await user.keyboard("{Escape}")

    // Then: Radix restores the same trigger focus.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it("reports a download failure without closing the decision dialog", async () => {
    // Given: a download adapter that reports failure.
    const user = userEvent.setup()
    render(
      <DialogFixture
        onAvatar={vi.fn()}
        onDownload={() => {
          throw new DOMException("blocked", "NotAllowedError")
        }}
        onRecapture={vi.fn()}
      />,
    )

    // When: download fails at the browser boundary.
    await user.click(screen.getByRole("button", { name: "拍照" }))
    await user.click(screen.getByRole("button", { name: "下载图片" }))

    // Then: recovery copy is announced and the other decisions remain available.
    expect(screen.getByRole("alert")).toHaveTextContent("下载没有开始")
    expect(screen.getByRole("button", { name: "重新拍摄" })).toBeInTheDocument()
  })

  it("downloads the PNG through a disposable object URL", async () => {
    // Given: browser URL APIs and the dialog's default download adapter.
    const user = userEvent.setup()
    const createObjectURL = vi.fn(() => "blob:download")
    const revokeObjectURL = vi.fn()
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined)
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL })
    render(<DialogFixture onAvatar={vi.fn()} onRecapture={vi.fn()} />)

    // When: the PNG download is requested.
    await user.click(screen.getByRole("button", { name: "拍照" }))
    await user.click(screen.getByRole("button", { name: "下载图片" }))

    // Then: the same Blob is downloaded and its disposable URL is immediately revoked.
    expect(createObjectURL).toHaveBeenCalledWith(captureBlob)
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:download")
    anchorClick.mockRestore()
    Reflect.deleteProperty(URL, "createObjectURL")
    Reflect.deleteProperty(URL, "revokeObjectURL")
  })

  it("revokes the disposable URL when the browser click throws", async () => {
    // Given: the default adapter allocated a URL before the browser blocks navigation.
    const user = userEvent.setup()
    const createObjectURL = vi.fn(() => "blob:blocked-download")
    const revokeObjectURL = vi.fn()
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {
      throw new DOMException("blocked", "NotAllowedError")
    })
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL })
    render(<DialogFixture onAvatar={vi.fn()} onRecapture={vi.fn()} />)

    // When: the default download action fails after URL allocation.
    await user.click(screen.getByRole("button", { name: "拍照" }))
    await user.click(screen.getByRole("button", { name: "下载图片" }))

    // Then: recovery is visible and the allocated URL is still revoked.
    expect(screen.getByRole("alert")).toHaveTextContent("下载没有开始")
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:blocked-download")
    anchorClick.mockRestore()
    Reflect.deleteProperty(URL, "createObjectURL")
    Reflect.deleteProperty(URL, "revokeObjectURL")
  })
})
