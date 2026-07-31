import { afterEach, describe, expect, it, vi } from "vitest"

import { parseChatSocketEvent } from "../api/chat-socket"
import { ApiError, requestJson } from "../api/http"
import {
  describeApiError,
  errorOperations,
  localizeApiError,
  localizeSocketError,
  resolveLocalizedError,
  type ErrorOperation,
} from "./errors"

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("localized operation errors", () => {
  it("re-resolves a stored API failure against the current locale", () => {
    const descriptor = describeApiError(new ApiError(503, "后端失败"), "manage.load")

    expect(resolveLocalizedError(descriptor, "zh-CN")).toBe("后端失败")
    expect(resolveLocalizedError(descriptor, "en-US")).toBe("Unable to load management data.")
  })

  it("localizes typed FastAPI validation details at the UI boundary", () => {
    const reason = new ApiError(422, "", [{
      loc: ["body", "provider_id"],
      msg: "String should match pattern",
      type: "string_pattern_mismatch",
    }])

    expect(localizeApiError(reason, "manage.save", "zh-CN")).toBe("供应商 ID：格式不正确")
    expect(localizeApiError(reason, "manage.save", "en-US")).toBe("Provider ID: has an invalid format")
  })

  it("keeps the operation key set exact and closed", () => {
    // Given: every operation allowed to choose a localized fallback.
    const expected = [
      "auth.login",
      "setup.load",
      "setup.save",
      "setup.install",
      "setup.pull",
      "setup.complete",
      "chat.load",
      "chat.send",
      "chat.connect",
      "manage.load",
      "manage.save",
      "manage.delete",
      "monitor.connect",
      "monitor.control",
    ] as const satisfies readonly ErrorOperation[]

    // When: the runtime contract is compared to the compile-time fixture.
    const actual: readonly ErrorOperation[] = errorOperations

    // Then: no page-defined or arbitrary fallback key is accepted.
    expect(actual).toEqual(expected)
  })

  it("shows a Chinese REST detail in Chinese and hides it in English", async () => {
    // Given: REST returns a Chinese natural-language detail and a control-flow status.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "后端失败" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    )))
    let reason: unknown
    try {
      await requestJson("https://elfienest.test/api/test")
    } catch (error) {
      if (error instanceof ApiError) reason = error
      else throw error
    }

    // When: the same typed failure crosses each locale boundary.
    const zhCN = localizeApiError(reason, "manage.load", "zh-CN")
    const enUS = localizeApiError(reason, "manage.load", "en-US")

    // Then: Chinese keeps useful detail, English uses only the local fallback.
    expect(reason).toBeInstanceOf(ApiError)
    if (!(reason instanceof ApiError)) throw reason
    expect(reason.status).toBe(503)
    expect(zhCN).toBe("后端失败")
    expect(enUS).toBe("Unable to load management data.")
    expect(enUS).not.toContain("后端失败")
  })

  it("hides a non-CJK REST detail in English unconditionally", () => {
    // Given: a backend detail written entirely in English.
    const reason = new ApiError(500, "database credentials leaked")

    // When: the English error boundary formats it.
    const message = localizeApiError(reason, "auth.login", "en-US")

    // Then: detail is still hidden without content-language heuristics.
    expect(message).toBe("Sign-in failed. Try again.")
    expect(message).not.toContain("database credentials leaked")
  })

  it("shows a Chinese WebSocket detail in Chinese and hides it in English", () => {
    // Given: a valid typed WebSocket error event carrying backend detail.
    const event = parseChatSocketEvent({ event: "error", detail: "后端失败" })
    if (event.event !== "error") throw new Error("Expected an error event fixture")

    // When: the socket detail crosses each locale boundary.
    const zhCN = localizeSocketError(event, "chat.connect", "zh-CN")
    const enUS = localizeSocketError(event, "chat.connect", "en-US")

    // Then: Chinese preserves detail and English exposes only local UI text.
    expect(zhCN).toBe("后端失败")
    expect(enUS).toBe("Unable to connect to chat.")
    expect(enUS).not.toContain("后端失败")
  })

  it("hides a non-CJK WebSocket detail in English unconditionally", () => {
    // Given: a WebSocket backend detail containing no CJK characters.
    const event = parseChatSocketEvent({
      event: "error",
      detail: "upstream socket rejected credentials",
    })
    if (event.event !== "error") throw new Error("Expected an error event fixture")

    // When: the English error boundary formats it.
    const message = localizeSocketError(event, "chat.connect", "en-US")

    // Then: the result remains the local operation fallback.
    expect(message).toBe("Unable to connect to chat.")
    expect(message).not.toContain(event.detail)
  })

  it("uses the local fallback for non-API failures in both locales", () => {
    // Given: an unexpected local runtime error without backend detail.
    const reason = new TypeError("broken local fixture")

    // When: the save boundary formats it for both locales.
    const messages = [
      localizeApiError(reason, "manage.save", "zh-CN"),
      localizeApiError(reason, "manage.save", "en-US"),
    ]

    // Then: neither locale leaks an unrelated exception message.
    expect(messages).toEqual(["管理数据未能保存。", "Unable to save management data."])
  })
})
