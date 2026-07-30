import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import {
  HAPPY_EXPERIENCE,
  KETTLE_EXPERIENCE,
  PRIVATE_MODULE_TITLES,
  SIGNED_IN_ADMIN,
} from "./mock-data"
import { parseViewer } from "./model"
import { ProfilePrivateModules } from "./ProfilePrivateModules"
import type { ProfileChartRuntime } from "./ProfileChart"
import type { ElfieProfileProjection } from "./projection"
import { projectElfieProfile } from "./projection"

const kettleAdopter = parseViewer({
  accountId: "user123",
  role: "user",
  displayName: "Kettle 的领养人",
})

const pendingRuntime = () => new Promise<ProfileChartRuntime>(() => undefined)

describe("ProfilePrivateModules", () => {
  it("renders exactly six adopter headings, all collapsed by default", () => {
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)

    const { container } = render(<ProfilePrivateModules projection={projection} />)

    const buttons = screen.getAllByRole("button")
    expect(buttons).toHaveLength(6)
    expect(buttons.map((button) => button.textContent?.trim())).toEqual(PRIVATE_MODULE_TITLES)
    for (const button of buttons) {
      expect(button).toHaveAttribute("aria-expanded", "false")
      expect(button).toHaveAttribute("aria-controls")
      expect(button.querySelector(".lucide-chevron-down")).not.toBeNull()
    }
    expect(container).not.toHaveTextContent("晨间巡游")
    expect(container.querySelector('[role="region"]')).toBeNull()
  })

  it("keeps multiple modules open and mounts heavy bodies only on demand", async () => {
    const user = userEvent.setup()
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    render(<ProfilePrivateModules loadChartRuntime={pendingRuntime} projection={projection} />)

    const memoryButton = screen.getByRole("button", { name: "记忆与认知" })
    const graphButton = screen.getByRole("button", { name: "关系认知" })
    await user.click(memoryButton)
    await user.click(graphButton)

    expect(memoryButton).toHaveAttribute("aria-expanded", "true")
    expect(graphButton).toHaveAttribute("aria-expanded", "true")
    expect(memoryButton.querySelector(".lucide-chevron-up")).not.toBeNull()
    expect(screen.getByRole("region", { name: "记忆与认知" })).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "关系认知" })).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "知识与信念" })).not.toBeInTheDocument()
  })

  it("supports keyboard activation and resets every panel when the Elfie changes", async () => {
    const user = userEvent.setup()
    const happyProjection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    const kettleProjection = projectElfieProfile(kettleAdopter, KETTLE_EXPERIENCE)
    const happyVisitorProjection: ElfieProfileProjection = {
      kind: "visitor",
      ownerDisplayName: "管理员",
      publicProfile: happyProjection.publicProfile,
    }
    const { container, rerender } = render(<ProfilePrivateModules projection={happyProjection} />)

    const experienceButton = screen.getByRole("button", { name: "重要经历" })
    experienceButton.focus()
    await user.keyboard("{Enter}")
    expect(experienceButton).toHaveAttribute("aria-expanded", "true")

    rerender(<ProfilePrivateModules projection={kettleProjection} />)

    for (const button of screen.getAllByRole("button")) {
      expect(button).toHaveAttribute("aria-expanded", "false")
    }
    expect(document.querySelector('[role="region"]')).toBeNull()

    rerender(<ProfilePrivateModules projection={happyProjection} />)

    for (const button of screen.getAllByRole("button")) {
      expect(button).toHaveAttribute("aria-expanded", "false")
    }
    expect(container.querySelector('[role="region"]')).toBeNull()
    expect(container).not.toHaveTextContent("第一次回头")

    await user.click(screen.getByRole("button", { name: "记忆与认知" }))
    expect(screen.getByText("晨间巡游")).toBeInTheDocument()

    rerender(<ProfilePrivateModules projection={happyVisitorProjection} />)
    expect(container).toBeEmptyDOMElement()

    rerender(<ProfilePrivateModules projection={happyProjection} />)
    expect(screen.getByRole("button", { name: "记忆与认知" })).toHaveAttribute(
      "aria-expanded",
      "false",
    )
    expect(container.querySelector('[role="region"]')).toBeNull()
    expect(container).not.toHaveTextContent("晨间巡游")
  })

  it("uses semantic topic, timeline, graph, and food strategy surfaces", async () => {
    const user = userEvent.setup()
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    render(<ProfilePrivateModules loadChartRuntime={pendingRuntime} projection={projection} />)

    await user.click(screen.getByRole("button", { name: "记忆与认知" }))
    const memory = screen.getByRole("region", { name: "记忆与认知" })
    expect(within(memory).getByRole("list")).toBeInTheDocument()
    expect(within(memory).getByText("47 条经历")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "重要经历" }))
    const timeline = screen.getByRole("region", { name: "重要经历" })
    expect(within(timeline).getByRole("list")).toBeInTheDocument()
    expect(timeline.querySelector("time[datetime='2026-06-30']")).not.toBeNull()

    await user.click(screen.getByRole("button", { name: "知识与信念" }))
    expect(screen.getByRole("img", { name: "知识与信念预览图" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "查看知识与信念详情" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "粮食策略" }))
    const foodStrategy = screen.getByRole("region", { name: "粮食策略" })
    expect(within(foodStrategy).getByRole("combobox", { name: "主粮" })).toHaveTextContent("food_common")
    expect(within(foodStrategy).queryByRole("combobox", { name: "备用粮" })).not.toBeInTheDocument()
    expect(within(foodStrategy).getByText("可选粮食由管理员维护，此处不能增删。")).toBeInTheDocument()
    expect(within(foodStrategy).queryByText(/模型|温度|提供方/)).not.toBeInTheDocument()
  })

  it("renders nothing for visitors without private headings or payload strings", () => {
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, KETTLE_EXPERIENCE)

    const { container } = render(<ProfilePrivateModules projection={projection} />)

    expect(container).toBeEmptyDOMElement()
    expect(container).not.toHaveTextContent(PRIVATE_MODULE_TITLES.join("|"))
    expect(container).not.toHaveTextContent("铜壶窗边观察")
    expect(container).not.toHaveTextContent("qwen3-8b-calm")
  })

  it("keeps empty topics and long CJK timeline copy explicit", async () => {
    const user = userEvent.setup()
    const source = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    expect(source.kind).toBe("adopter")
    if (source.kind !== "adopter") {
      return
    }
    const [memory, timeline, relationships, knowledge, world, config] = source.privateCognition.modules
    const longDetail = "这是一段用于验证长内容换行的经历说明，它会保留完整语义，并在窄屏幕中自然换行，不依赖截断、隐藏文本或仅靠图表位置传达含义。"
    const projection: ElfieProfileProjection = {
      ...source,
      privateCognition: {
        modules: [
          { ...memory, topics: [] },
          { ...timeline, entries: [{ date: "2026-07-28", title: "长内容记录", detail: longDetail }] },
          relationships,
          knowledge,
          world,
          config,
        ],
      },
    }
    render(<ProfilePrivateModules projection={projection} />)

    await user.click(screen.getByRole("button", { name: "记忆与认知" }))
    await user.click(screen.getByRole("button", { name: "重要经历" }))

    expect(screen.getByText("尚未形成记忆主题。")).toBeInTheDocument()
    expect(screen.getByText(longDetail)).toBeInTheDocument()
  })
})
