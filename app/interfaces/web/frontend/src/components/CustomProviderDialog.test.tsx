import { fireEvent, render, screen, within } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import { ApiError } from "../api/http"
import { createI18n } from "../i18n/config"
import { CustomProviderDialog } from "./CustomProviderDialog"

describe("CustomProviderDialog", () => {
  it("renders a save failure inside the active dialog", async () => {
    const onSave = vi.fn().mockRejectedValue(new ApiError(400, "后端拒绝了自定义连接"))
    render(<I18nextProvider i18n={createI18n()}><CustomProviderDialog onOpenChange={vi.fn()} onSave={onSave} open /></I18nextProvider>)
    const dialog = screen.getByRole("dialog", { name: "配置 OpenAI 接口" })

    fireEvent.change(within(dialog).getByRole("textbox", { name: "显示名称" }), { target: { value: "Custom" } })
    fireEvent.change(within(dialog).getByRole("textbox", { name: "API Base URL" }), { target: { value: "https://host.example/v1" } })
    fireEvent.change(within(dialog).getByLabelText("API 密钥", { selector: "input" }), { target: { value: "secret" } })
    expect(within(dialog).getByLabelText("API 密钥", { selector: "input" })).toHaveAttribute("type", "text")
    expect(within(dialog).getByLabelText("API 密钥", { selector: "input" })).toHaveAttribute("autocomplete", "off")
    fireEvent.click(within(dialog).getByRole("button", { name: "保存配置" }))

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("后端拒绝了自定义连接")
    expect(onSave).toHaveBeenCalledOnce()
  }, 10_000)
})
