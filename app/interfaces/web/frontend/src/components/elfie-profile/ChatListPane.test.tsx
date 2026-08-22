import { render, screen, within } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"
import { ChatListPane } from "./ChatListPane"

describe("ChatListPane layout", () => {
  it("keeps a list error and the scrollable list in one body track", () => {
    const instance = createI18n()
    void instance.changeLanguage("zh-CN")

    render(
      <I18nextProvider i18n={instance}>
        <ChatListPane
          activePane="elfies"
          conversations={[]}
          elfieFilter="all"
          elfieItems={[{
            adopterAccountId: "owner",
            profile: { elfie_id: "00000001", name: "小羽", portrait_url: "", species_id: "fox" },
          }]}
          elfieQuery=""
          error="精灵列表加载失败"
          hiddenOnMobile={false}
          onAdopt={vi.fn()}
          onChat={vi.fn()}
          onElfieFilterChange={vi.fn()}
          onElfieProfile={vi.fn()}
          onElfieQueryChange={vi.fn()}
          selectedId={null}
          viewerAccountId="owner"
        />
      </I18nextProvider>,
    )

    const body = document.querySelector(".chat-list-pane__body")
    if (!(body instanceof HTMLElement)) throw new TypeError("Expected list body")
    expect(body).toHaveClass("chat-list-pane__body--with-error")
    expect(within(body).getByRole("alert")).toHaveTextContent("精灵列表加载失败")
    expect(within(body).getByRole("button", { name: "查看 小羽 的个人档案" })).toBeInTheDocument()
  })
})
