import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import { ProfileRecentFocus } from "./ProfileRecentFocus"
import type { RecentFocus } from "./model"

type MockDatum = {
  readonly text: string
  readonly value: number
}

type MockWord = MockDatum & {
  readonly x: number
  readonly y: number
  readonly rotate: number
  readonly size: number
}

type MockWordcloudProps = {
  readonly words: readonly MockDatum[]
  readonly children: (words: readonly MockWord[]) => ReactNode
}

vi.mock("@visx/wordcloud", () => ({
  Wordcloud: ({ words, children }: MockWordcloudProps) => (
    <svg data-testid="mock-wordcloud-svg">
      {children(words.map((word, index) => ({
        ...word,
        rotate: index % 7 === 0 ? 90 : 0,
        size: 18 + word.value * 40,
        x: 160,
        y: 24 + index * 18,
      })))}
    </svg>
  ),
}))

function focusWithTopics(count: number): RecentFocus {
  return {
    topics: Array.from({ length: count }, (_, index) => ({
      category: index % 2 === 0 ? "activity" : "place",
      id: `topic:${index}`,
      label: `主题${index}`,
      weight: index / Math.max(1, count - 1),
    })),
  }
}

describe("ProfileRecentFocus", () => {
  it("uses the real word-cloud host and preserves visible weight differences", () => {
    render(
      <I18nextProvider i18n={createI18n()}>
        <ProfileRecentFocus focus={focusWithTopics(50)} status="ready" />
      </I18nextProvider>,
    )

    expect(screen.getByTestId("recent-focus-wordcloud")).toBeInTheDocument()
    expect(screen.getAllByTestId("recent-focus-topic")).toHaveLength(50)
    const sizes = screen.getAllByTestId("recent-focus-topic").map((node) => Number(node.getAttribute("font-size")))
    expect(Math.max(...sizes)).toBeGreaterThan(Math.min(...sizes))
    expect(screen.getAllByTestId("recent-focus-topic").some((node) => node.getAttribute("data-rotation") === "90")).toBe(true)
    expect(screen.queryByRole("list")).not.toBeInTheDocument()
  })
})
