import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "../i18n/config"
import { MobileAccessDialog } from "./MobileAccessDialog"

const mobileAccessMock = vi.hoisted(() => vi.fn())
const toDataURLMock = vi.hoisted(() => vi.fn())

vi.mock("../api/admin/runtime", () => ({ mobileAccess: mobileAccessMock }))
vi.mock("qrcode", () => ({ default: { toDataURL: toDataURLMock } }))

describe("MobileAccessDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    toDataURLMock.mockResolvedValue("data:image/png;base64,qr")
  })

  it.each([
    ["/chat" as const, "/chat"],
    ["/manage" as const, "/manage"],
    ["/monitor" as const, "/monitor"],
  ])("shows the two-step instructions for %s", async (targetPath, expectedPath) => {
    mobileAccessMock.mockResolvedValue({
      available: true,
      network_name: "Elfie Home",
      urls: ["http://192.168.1.8:15212/"],
    })
    const instance = createI18n()

    render(
      <I18nextProvider i18n={instance}>
        <MobileAccessDialog onClose={vi.fn()} targetPath={targetPath} />
      </I18nextProvider>,
    )

    const firstStep = await screen.findByRole("heading", { name: "第一步　手机连接无线网" })
    const network = screen.getByText("Elfie Home")
    const secondStep = screen.getByRole("heading", { name: "第二步　用手机扫描二维码" })
    const qr = await screen.findByRole("img", { name: /二维码/ })

    expect(firstStep.compareDocumentPosition(network) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(network.compareDocumentPosition(secondStep) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(secondStep.compareDocumentPosition(qr) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(network.compareDocumentPosition(qr) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.queryByText("用手机打开 ElfieNest")).not.toBeInTheDocument()
    expect(screen.getByText(`http://192.168.1.8:15212${expectedPath}`)).toBeInTheDocument()
    expect(toDataURLMock).toHaveBeenCalledWith(
      `http://192.168.1.8:15212${expectedPath}`,
      expect.any(Object),
    )
  })

  it("tells the phone to use the same Wi-Fi when the name cannot be read", async () => {
    mobileAccessMock.mockResolvedValue({
      available: true,
      network_name: null,
      urls: ["http://192.168.1.8:15212/"],
    })

    render(
      <I18nextProvider i18n={createI18n()}>
        <MobileAccessDialog onClose={vi.fn()} />
      </I18nextProvider>,
    )

    expect(await screen.findByRole("heading", { name: "第一步　手机连接同一无线网" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "第二步　用手机扫描二维码" })).toBeInTheDocument()
    expect(screen.queryByText("无线网名称未识别")).not.toBeInTheDocument()
  })
})
