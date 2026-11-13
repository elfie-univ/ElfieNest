import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { environmentSettings, updateEnvironmentSettings, type EnvironmentSettings } from "../api/admin/settings"
import { createI18n } from "../i18n/config"
import { EnvironmentSettingsSection } from "./EnvironmentSettingsSection"

vi.mock("../api/admin/settings", () => ({ environmentSettings: vi.fn(), updateEnvironmentSettings: vi.fn() }))
const value: EnvironmentSettings = {
  settings: { daylight_source: "manual", sunrise_time: "06:00", sunset_time: "18:00", rest_time: "00:00", latitude: null, longitude: null },
  today: { date: "2026-11-03", timezone: "UTC+08:00", sunrise_time: "06:00", sunset_time: "18:00", condition: "normal" },
}
const originalLocation = Object.getOwnPropertyDescriptor(navigator, "geolocation")
afterEach(() => {
  if (originalLocation) Object.defineProperty(navigator, "geolocation", originalLocation)
  else Reflect.deleteProperty(navigator, "geolocation")
})
beforeEach(() => {
  vi.clearAllMocks()
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.setPointerCapture = vi.fn()
  Element.prototype.releasePointerCapture = vi.fn()
  Element.prototype.scrollIntoView = vi.fn()
  vi.mocked(environmentSettings).mockResolvedValue(value)
  vi.mocked(updateEnvironmentSettings).mockImplementation(async settings => ({ ...value, settings }))
})
function show() {
  const i18n = createI18n()
  void i18n.changeLanguage("zh-CN")
  render(<I18nextProvider i18n={i18n}><EnvironmentSettingsSection csrfToken="csrf" /></I18nextProvider>)
}

describe("environment settings", () => {
  it("saves three independent clock points with the original location and CSRF", async () => {
    const user = userEvent.setup()
    show()
    fireEvent.change(await screen.findByLabelText("休息时间", { selector: "input" }), { target: { value: "22:30" } })
    expect(screen.getByLabelText("日出时间", { selector: "input" })).toHaveValue("06:00")
    expect(screen.getByLabelText("日落时间", { selector: "input" })).toHaveValue("18:00")
    await user.click(screen.getByRole("button", { name: "保存环境设置" }))
    await waitFor(() => expect(updateEnvironmentSettings).toHaveBeenCalledWith({ ...value.settings, rest_time: "22:30" }, "csrf"))
    expect(await screen.findByText(/环境设置已保存/)).toBeInTheDocument()
  })
  it("requests location only on an explicit click and keeps rest time editable", async () => {
    const locate = vi.fn((success: PositionCallback) => success({
      coords: { latitude: 39.9042, longitude: 116.4074, accuracy: 100, altitude: null, altitudeAccuracy: null, heading: null, speed: null, toJSON: () => ({}) },
      timestamp: 0, toJSON: () => ({}),
    }))
    Object.defineProperty(navigator, "geolocation", { configurable: true, value: { getCurrentPosition: locate } })
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole("combobox", { name: "日照来源" }))
    await user.click(screen.getByRole("option", { name: "跟随本地" }))
    expect(locate).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "保存环境设置" })).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "使用电脑位置" }))
    expect(screen.getByLabelText("日出时间", { selector: "input" })).toHaveAttribute("readonly")
    expect(screen.getByLabelText("休息时间", { selector: "input" })).not.toHaveAttribute("readonly")
    await user.click(screen.getByRole("button", { name: "保存环境设置" }))
    await waitFor(() => expect(updateEnvironmentSettings).toHaveBeenCalledWith({ ...value.settings, daylight_source: "local", latitude: 39.9, longitude: 116.41 }, "csrf"))
  })
  it("explains a denied location permission without submitting incomplete settings", async () => {
    Object.defineProperty(navigator, "geolocation", { configurable: true, value: {
      getCurrentPosition: (_success: PositionCallback, failure: PositionErrorCallback) => failure({ code: 1, message: "denied", PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 }),
    } })
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole("combobox", { name: "日照来源" }))
    await user.click(screen.getByRole("option", { name: "跟随本地" }))
    await user.click(screen.getByRole("button", { name: "使用电脑位置" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("无法获取位置")
    expect(screen.getByRole("button", { name: "保存环境设置" })).toBeDisabled()
  })
})
