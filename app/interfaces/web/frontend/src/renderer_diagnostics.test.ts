import { afterEach, describe, expect, it, vi } from "vitest"

import {
  installGlobalRendererDiagnostics,
  reportRendererError,
  resetRendererDiagnosticSamplingForTests,
} from "./renderer_diagnostics"

describe("Desktop renderer diagnostics", () => {
  afterEach(() => {
    delete window.elfienestDesktop
    resetRendererDiagnosticSamplingForTests()
  })

  it("sends only bounded redacted error context through the Desktop bridge", () => {
    const report = vi.fn()
    window.elfienestDesktop = {
      readCurrentWifiName: vi.fn(),
      openLocationSettings: vi.fn(),
      reportRendererError: report,
    }

    reportRendererError(
      "react_uncaught",
      new Error(`token=visible ${"x".repeat(3_000)}`),
      `https://example.test/app.js?nonce=visible ${"s".repeat(10_000)}`,
    )

    expect(report).toHaveBeenCalledOnce()
    const payload = report.mock.calls[0]?.[0] as Record<string, string>
    expect(payload["origin"]).toBe("react_uncaught")
    expect(payload["message"]).toHaveLength(2_048)
    expect(payload["stack"]?.length).toBeLessThanOrEqual(8_192)
    expect(JSON.stringify(payload)).not.toMatch(/visible/u)
    expect(payload["occurrences"]).toBe(1)
    expect(payload["suppressed_count"]).toBe(0)
  })

  it("redacts OAuth credentials and authorization headers", () => {
    const report = vi.fn()
    window.elfienestDesktop = {
      readCurrentWifiName: vi.fn(),
      openLocationSettings: vi.fn(),
      reportRendererError: report,
    }

    reportRendererError(
      "react_uncaught",
      new Error(
        "access_token=sample-access "
        + "refresh_token='sample-refresh' "
        + '"client_secret": "sample-client" '
        + "Authorization: Bearer sample-bearer "
        + "Bearer sample-standalone",
      ),
    )

    const encoded = JSON.stringify(report.mock.calls[0]?.[0])
    expect(encoded).not.toMatch(
      /sample-access|sample-refresh|sample-client|sample-bearer|sample-standalone/u,
    )
  })

  it("captures global errors without suppressing normal browser handling", () => {
    const report = vi.fn()
    window.elfienestDesktop = {
      readCurrentWifiName: vi.fn(),
      openLocationSettings: vi.fn(),
      reportRendererError: report,
    }
    const remove = installGlobalRendererDiagnostics()
    try {
      const event = new ErrorEvent("error", { error: new TypeError("render failed") })
      expect(window.dispatchEvent(event)).toBe(true)
    } finally {
      remove()
    }

    expect(report).toHaveBeenCalledWith(
      expect.objectContaining({
        origin: "window_error",
        error_type: "TypeError",
        message: "render failed",
      }),
    )
  })

  it("exponentially samples one repeated renderer error signature", () => {
    const report = vi.fn()
    window.elfienestDesktop = {
      readCurrentWifiName: vi.fn(),
      openLocationSettings: vi.fn(),
      reportRendererError: report,
    }

    for (let occurrence = 0; occurrence < 8; occurrence += 1) {
      reportRendererError("react_recoverable", new Error("render retry"))
    }

    expect(report).toHaveBeenCalledTimes(4)
    expect(report.mock.calls.map((call) => call[0].occurrences)).toEqual([
      1, 2, 4, 8,
    ])
    expect(report.mock.calls.at(-1)?.[0].suppressed_count).toBe(3)
  })
})
