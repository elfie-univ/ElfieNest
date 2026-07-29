import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("./pages/ChatPage", () => ({ ChatPage: () => <div data-testid="chat-page" /> }))
vi.mock("./pages/LoginPage", () => ({ LoginPage: () => <div data-testid="login-page" /> }))
vi.mock("./pages/ManagePage", () => ({ ManagePage: () => <div data-testid="manage-page" /> }))
vi.mock("./pages/MonitorPage", () => ({ MonitorPage: () => <div data-testid="monitor-page" /> }))
vi.mock("./pages/SetupPage", () => ({ SetupPage: () => <div data-testid="setup-page" /> }))
vi.mock("./stores/history", () => ({ useAppLocation: vi.fn() }))

import { App } from "./App"
import { useAppLocation } from "./stores/history"

describe("App routing", () => {
  it("renders the shared monitor page at the monitor route", () => {
    vi.mocked(useAppLocation).mockReturnValue({ pathname: "/monitor", search: "" })

    render(<App />)

    expect(screen.getByTestId("monitor-page")).toBeInTheDocument()
  })
})
