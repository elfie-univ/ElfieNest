import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import { HAPPY_EXPERIENCE } from "./mock-data"
import type { Graph } from "./model"
import { ProfileGraphSection } from "./ProfileGraphSection"
import type { ProfileChartRuntime } from "./ProfileChart"

createI18n()

const pendingRuntime = () => new Promise<ProfileChartRuntime>(() => undefined)

describe("ProfileGraphSection", () => {
  it("pairs visible labels with a textual directed-edge list", () => {
    const module = HAPPY_EXPERIENCE.privateCognition.modules[3]

    render(
      <ProfileGraphSection
        elfieId={HAPPY_EXPERIENCE.publicProfile.elfieId}
        loadChartRuntime={pendingRuntime}
        module={module}
      />,
    )

    expect(screen.getByRole("img", { name: "知识与信念预览图" })).toBeInTheDocument()
    expect(screen.getByRole("list", { name: "知识与信念连接说明" })).toBeInTheDocument()
    const edgeList = screen.getByRole("list", { name: "知识与信念连接说明" })
    expect(within(edgeList).getAllByRole("listitem")[0]).toHaveTextContent(
      "happy-belief 1→happy-belief 2：指向",
    )
    expect(screen.getByText("已显示前 20 个节点，另有 31 个未显示。")).toBeInTheDocument()
  })

  it("opens a 50-node detail dialog and returns focus when closed", async () => {
    const user = userEvent.setup()
    const module = HAPPY_EXPERIENCE.privateCognition.modules[3]
    render(
      <ProfileGraphSection
        elfieId={HAPPY_EXPERIENCE.publicProfile.elfieId}
        loadChartRuntime={pendingRuntime}
        module={module}
      />,
    )
    const trigger = screen.getByRole("button", { name: "查看知识与信念详情" })

    trigger.focus()
    await user.click(trigger)

    const dialog = screen.getByRole("dialog", { name: "知识与信念详情" })
    expect(within(dialog).getByText("已显示前 50 个节点，另有 1 个未显示。")).toBeInTheDocument()
    expect(within(dialog).getByRole("img", { name: "知识与信念详情图" })).toBeInTheDocument()

    await user.click(within(dialog).getByRole("button", { name: "关闭详情" }))
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it("shows safe empty and edge-free alternatives without mounting a canvas", () => {
    const source = HAPPY_EXPERIENCE.privateCognition.modules[2]
    const emptyModule = { ...source, graph: { nodes: [], edges: [] } satisfies Graph }

    render(
      <ProfileGraphSection
        elfieId={HAPPY_EXPERIENCE.publicProfile.elfieId}
        loadChartRuntime={pendingRuntime}
        module={emptyModule}
      />,
    )

    expect(screen.getByText("暂无可呈现的关系认知节点。")).toBeInTheDocument()
    expect(screen.getByText("暂无连接说明。")).toBeInTheDocument()
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("keeps semantic graph content when the lazy chart runtime fails", async () => {
    const module = HAPPY_EXPERIENCE.privateCognition.modules[4]
    const loadChartRuntime = vi.fn(() => Promise.reject(new Error("blocked")))

    render(
      <ProfileGraphSection
        elfieId={HAPPY_EXPERIENCE.publicProfile.elfieId}
        loadChartRuntime={loadChartRuntime}
        module={module}
      />,
    )

    expect(await screen.findByRole("alert")).toHaveTextContent("图表暂时无法显示")
    expect(screen.getByRole("list", { name: "世界理解连接说明" })).toBeInTheDocument()
    const edgeList = screen.getByRole("list", { name: "世界理解连接说明" })
    expect(within(edgeList).getAllByRole("listitem")[0]).toHaveTextContent(
      "happy-world 1—happy-world 2：关联",
    )
  })
})
