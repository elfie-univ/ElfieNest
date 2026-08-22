import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import type { AppearanceCapture } from "./appearance-capture"
import { ProfileCaptureDialog } from "./ProfileCaptureDialog"
import { cropCapture } from "./profile-capture-crop"

vi.mock("./profile-capture-crop", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./profile-capture-crop")>()
  return {
    ...actual,
    cropCapture: vi.fn(async (value: AppearanceCapture) => value),
    inspectCapture: vi.fn(async () => ({ height: 600, visibleBounds: null, width: 1000 })),
  }
})

createI18n()

Object.defineProperties(HTMLElement.prototype, {
  hasPointerCapture: { configurable: true, value: () => false },
  setPointerCapture: { configurable: true, value: () => undefined },
  releasePointerCapture: { configurable: true, value: () => undefined },
  scrollIntoView: { configurable: true, value: () => undefined },
})

const captureBlob = new Blob(["same-png"], { type: "image/png" })
const capture: AppearanceCapture = {
  blob: captureBlob,
  previewUrl: "blob:preview",
}

type FixtureProps = {
  readonly onAvatar: (value: AppearanceCapture) => void
  readonly onDownload?: (value: AppearanceCapture, filename: string) => void
}

function DialogFixture({ onAvatar, onDownload }: FixtureProps) {
  const [open, setOpen] = useState(false)
  return (
    <ProfileCaptureDialog
      capture={capture}
      elfieName="Happy"
      onAvatar={onAvatar}
      onDownload={onDownload}
      onOpenChange={setOpen}
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
    render(
      <DialogFixture
        onAvatar={onAvatar}
        onDownload={onDownload}
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
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it("supports crop controls, cancel, Escape, and focus return", async () => {
    // Given: an openable Radix capture dialog.
    const user = userEvent.setup()
    render(<DialogFixture onAvatar={vi.fn()} />)
    const trigger = screen.getByRole("button", { name: "拍照" })

    // When: the crop workspace is opened.
    await user.click(trigger)
    expect(screen.getByRole("dialog", { name: "确认这张照片" })).toBeVisible()
    expect(screen.getByTestId("capture-crop-box")).toBeInTheDocument()
    const aspectSelect = screen.getByRole("combobox", { name: "照片比例" })
    expect(aspectSelect).toHaveTextContent("1:1")
    expect(screen.getByRole("button", { name: "取消" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "下载图片" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "设为头像" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "重新拍摄" })).not.toBeInTheDocument()
    await user.click(aspectSelect)
    await user.click(screen.getByRole("option", { name: "16:9" }))
    expect(aspectSelect).toHaveTextContent("16:9")
    expect(screen.queryByText("你可以先设为本地头像预览，或下载 PNG 图片保存。"))
      .not.toBeInTheDocument()

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
      />,
    )

    // When: download fails at the browser boundary.
    await user.click(screen.getByRole("button", { name: "拍照" }))
    await user.click(screen.getByRole("button", { name: "下载图片" }))

    // Then: recovery copy is announced and the other decisions remain available.
    expect(screen.getByRole("alert")).toHaveTextContent("下载没有开始")
    expect(screen.getByRole("button", { name: "设为头像" })).toBeInTheDocument()
  })

  it("downloads the PNG through a disposable object URL", async () => {
    // Given: browser URL APIs and the dialog's default download adapter.
    const user = userEvent.setup()
    const createObjectURL = vi.fn(() => "blob:download")
    const revokeObjectURL = vi.fn()
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined)
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL })
    render(<DialogFixture onAvatar={vi.fn()} />)

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
    render(<DialogFixture onAvatar={vi.fn()} />)

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

  it("releases the derived crop URL after saving an avatar", async () => {
    const user = userEvent.setup()
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL })
    vi.mocked(cropCapture).mockResolvedValueOnce({ blob: captureBlob, previewUrl: "blob:avatar-crop" })
    render(<DialogFixture onAvatar={vi.fn()} />)

    await user.click(screen.getByRole("button", { name: "拍照" }))
    await user.click(screen.getByRole("button", { name: "设为头像" }))

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:avatar-crop")
    Reflect.deleteProperty(URL, "revokeObjectURL")
  })
})
