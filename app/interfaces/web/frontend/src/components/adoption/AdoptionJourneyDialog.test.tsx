import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"
import { AdoptionJourneyDialog } from "./AdoptionJourneyDialog"

const api = vi.hoisted(() => ({
  adoptionCandidates: vi.fn(),
  adoptionInfo: vi.fn(),
  adoptionReplies: vi.fn(),
  commitAdoption: vi.fn(),
}))

vi.mock("../../api/client", () => api)

function candidate(index: number) {
  return {
    candidate_id: `candidate-${index}`,
    original_name: `Aro ${index}`,
    suggested_name: `Roro ${index}`,
    species_id: "fox" as const,
    life_stage: "young_adult",
    gender: index % 2 === 0 ? "male" as const : "female" as const,
    image_url: "/adoption/fox.svg",
    appearance_tags: ["Balanced", "Soft"],
    personality_tags: ["Curious", "Warm"],
    introduction: "I would like to get to know your Nest.",
    compatibility: "Your answers sounded familiar.",
  }
}

describe("AdoptionJourneyDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    api.adoptionInfo.mockResolvedValue({
      personality_styles: ["好奇探索"],
      species_ids: ["fox", "dog"],
      heights: ["short", "standard", "tall"],
      builds: ["slim", "standard", "plump"],
      quota: { used: 0, max: 3, remaining: 3, can_adopt: true },
    })
    api.adoptionCandidates.mockResolvedValue({ candidate_set_id: "set-1", candidates: [0, 1, 2, 3, 4].map(candidate) })
    api.adoptionReplies.mockResolvedValue({ candidate_set_id: "set-1", replies: [candidate(0), candidate(1)].map((item, index) => ({ ...item, status: "accepted", message: `Reply ${index}` })) })
    api.commitAdoption.mockResolvedValue({ elfie_id: "00000001", name: "Aro 0", species_id: "fox" })
  })

  it("keeps the approved story flow from welcome through candidate generation", async () => {
    const user = userEvent.setup()
    const onAdopted = vi.fn(async () => undefined)
    render(<I18nextProvider i18n={createI18n()}><AdoptionJourneyDialog accountId="owner" csrfToken="csrf" onAdopted={onAdopted} onOpenChange={vi.fn()} open /></I18nextProvider>)

    expect(screen.getByRole("heading", { name: "认识一位来自 Elfaria 的朋友" })).toBeInTheDocument()
    expect(await screen.findByRole("heading", { name: "邀请一位精灵，从 Elfaria 到地球与你相遇" })).toBeInTheDocument()
    expect(screen.getByRole("img", { name: "来自 Elfaria、正在前往地球的 Elfie" })).toHaveAttribute("src", expect.stringContaining("elfaria-arrival-square.png"))
    expect(screen.getByRole("img", { name: "来自 Elfaria、正在前往地球的 Elfie" })).not.toHaveAttribute("src", "/adoption/elfaria-arrival-square.png")
    expect(screen.getByRole("checkbox", { name: "以后不再显示" })).not.toBeChecked()
    expect(screen.getByRole("checkbox", { name: "以后不再显示" })).toHaveClass("adoption-welcome__checkbox")
    expect(screen.queryByText("你提交的是愿意认识怎样的朋友；候选精灵也会阅读这份意向。")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "写下邀请" }))
    expect(await screen.findByRole("heading", { name: "你希望先认识怎样的 Elfie？" })).toBeInTheDocument()
    expect(screen.queryByText("第一步 · 基本意向")).not.toBeInTheDocument()
    expect(screen.queryByText("先确定物种、生命阶段和性别倾向。选择的是愿意见见的范围，不是在设置某一位精灵的身份。")).not.toBeInTheDocument()
    expect(screen.queryByText("看看狐狸报名者")).not.toBeInTheDocument()
    const speciesChoices = screen.getAllByRole("button", { name: /狐狸|小狗/ })
    expect(speciesChoices).toHaveLength(2)
    expect(speciesChoices[0]).toHaveTextContent("狐狸")
    expect(speciesChoices[0]).toHaveAttribute("aria-pressed", "false")
    expect(speciesChoices.every((choice) => choice.querySelector("img")?.getAttribute("src")?.includes("/adoption/") === false)).toBe(true)
    await user.click(screen.getByRole("button", { name: /狐狸/ }))
    await user.click(screen.getByRole("button", { name: /继续：外貌倾向/ }))
    expect(screen.queryByText("第二步 · 外貌倾向")).not.toBeInTheDocument()
    expect(screen.queryByText("用容易理解的视觉印象表达偏好。每项都可以交给缘分，实际候选仍会保留自己的特点。")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /继续：相处期待/ }))
    expect(screen.queryByText("第三步 · 相处期待")).not.toBeInTheDocument()
    expect(screen.queryByText("一次回答一个生活情景。候选 Elfie 也会阅读这些答案，判断这样的 Nest 是否适合自己。")).not.toBeInTheDocument()
    expect(screen.queryByText("生活情景 1 · 忙碌时")).not.toBeInTheDocument()

    for (let index = 0; index < 5; index += 1) {
      await user.click(screen.getByRole("button", { name: "都可以" }))
      if (index < 4) expect(screen.getByText(`问题 ${index + 2} / 5`)).toBeInTheDocument()
    }

    expect(screen.getByRole("heading", { name: "如果未来一起生活……" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "继续：确认意向" })).toBeEnabled()
    await user.click(screen.getByRole("button", { name: "继续：确认意向" }))
    expect(await screen.findByRole("heading", { name: "确认你的邀请意向" })).toBeInTheDocument()
    expect(screen.queryByText("发送后，系统会根据这些范围现场生成 5 位可能合适的报名者。这里仍然可以返回修改。")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "确认意向" }))
    expect(screen.getByRole("alertdialog")).toHaveTextContent("确认开始匹配")
    expect(api.adoptionCandidates).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "开始匹配" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "开始匹配" }))
    expect(await screen.findByRole("heading", { name: "找到 5 位可能与你合拍的报名者" })).toBeInTheDocument()
    expect(screen.queryByText("选择 1–3 位发送认识邀请。这里使用静态报名照，不同时加载多个 3D 形象。")).not.toBeInTheDocument()
    expect(api.adoptionCandidates).toHaveBeenCalledWith(expect.objectContaining({ species_id: "fox" }), "csrf")
  }, 15000)

  it("requires every companionship answer before opening the review", async () => {
    const user = userEvent.setup()
    render(<I18nextProvider i18n={createI18n()}><AdoptionJourneyDialog accountId="owner" csrfToken="csrf" onAdopted={vi.fn(async () => undefined)} onOpenChange={vi.fn()} open /></I18nextProvider>)

    await user.click(await screen.findByRole("button", { name: "写下邀请" }))
    await user.click(screen.getByRole("button", { name: /狐狸/ }))
    await user.click(screen.getByRole("button", { name: /继续：外貌倾向/ }))
    await user.click(screen.getByRole("button", { name: /继续：相处期待/ }))
    await user.click(screen.getByRole("button", { name: /生活节奏/ }))
    await user.click(screen.getByRole("button", { name: "都可以" }))

    expect(screen.getByRole("heading", { name: "如果未来一起生活……" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "继续：确认意向" })).toBeDisabled()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()

    for (const label of ["忙碌时", "新鲜事", "计划变化", "有分歧"]) {
      await user.click(screen.getByRole("button", { name: new RegExp(label) }))
      await user.click(screen.getByRole("button", { name: "都可以" }))
    }
    await user.click(screen.getByRole("button", { name: /生活节奏/ }))
    await user.click(screen.getByRole("button", { name: "都可以" }))
    expect(screen.getByRole("button", { name: "继续：确认意向" })).toBeEnabled()
    await user.click(screen.getByRole("button", { name: "继续：确认意向" }))
    expect(await screen.findByRole("heading", { name: "确认你的邀请意向" })).toBeInTheDocument()
  })

  it("allows editing earlier stages before confirmation and locks them after confirmation", async () => {
    const user = userEvent.setup()
    render(<I18nextProvider i18n={createI18n()}><AdoptionJourneyDialog accountId="owner" csrfToken="csrf" onAdopted={vi.fn(async () => undefined)} onOpenChange={vi.fn()} open /></I18nextProvider>)

    await user.click(await screen.findByRole("button", { name: "写下邀请" }))
    await user.click(screen.getByRole("button", { name: /狐狸/ }))
    await user.click(screen.getByRole("button", { name: /继续：外貌倾向/ }))
    await user.click(screen.getByRole("button", { name: /继续：相处期待/ }))
    for (let index = 0; index < 5; index += 1) await user.click(screen.getByRole("button", { name: "都可以" }))
    await user.click(screen.getByRole("button", { name: "继续：确认意向" }))

    await user.click(screen.getByRole("button", { name: "基本意向" }))
    expect(screen.getByRole("heading", { name: "你希望先认识怎样的 Elfie？" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "双向确认" }))
    expect(screen.getByRole("heading", { name: "确认你的邀请意向" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "确认意向" }))
    await user.click(screen.getByRole("button", { name: "开始匹配" }))
    expect(await screen.findByRole("heading", { name: "找到 5 位可能与你合拍的报名者" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "基本意向" })).toBeDisabled()
    expect(screen.queryByRole("button", { name: "返回" })).not.toBeInTheDocument()
  }, 15000)

  it("shows the welcome page again until the user explicitly skips it", async () => {
    const user = userEvent.setup()
    const props = { accountId: "owner", csrfToken: "csrf", onAdopted: vi.fn(async () => undefined), onOpenChange: vi.fn() }
    const first = render(<I18nextProvider i18n={createI18n()}><AdoptionJourneyDialog {...props} open /></I18nextProvider>)
    const checkbox = await screen.findByRole("checkbox", { name: "以后不再显示" })

    expect(checkbox).not.toBeChecked()
    await user.click(screen.getByRole("button", { name: "写下邀请" }))
    first.unmount()

    const second = render(<I18nextProvider i18n={createI18n()}><AdoptionJourneyDialog {...props} open /></I18nextProvider>)
    expect(await screen.findByRole("heading", { name: "邀请一位精灵，从 Elfaria 到地球与你相遇" })).toBeInTheDocument()
    await user.click(screen.getByRole("checkbox", { name: "以后不再显示" }))
    expect(screen.getByRole("checkbox", { name: "以后不再显示" })).toBeChecked()
    await user.click(screen.getByRole("button", { name: "写下邀请" }))
    second.unmount()

    render(<I18nextProvider i18n={createI18n()}><AdoptionJourneyDialog {...props} open /></I18nextProvider>)
    expect(await screen.findByRole("heading", { name: "你希望先认识怎样的 Elfie？" })).toBeInTheDocument()
  })

  it("allows selecting up to three candidates and keeps the selected snapshot", async () => {
    const user = userEvent.setup()
    render(<I18nextProvider i18n={createI18n()}><AdoptionJourneyDialog accountId="owner" csrfToken="csrf" onAdopted={vi.fn(async () => undefined)} onOpenChange={vi.fn()} open /></I18nextProvider>)
    await user.click(await screen.findByRole("button", { name: "写下邀请" }))
    await user.click(screen.getByRole("button", { name: /狐狸/ }))
    await user.click(screen.getByRole("button", { name: /继续：外貌倾向/ }))
    await user.click(screen.getByRole("button", { name: /继续：相处期待/ }))
    for (let index = 0; index < 5; index += 1) {
      await user.click(screen.getByRole("button", { name: "都可以" }))
    }
    await user.click(screen.getByRole("button", { name: "继续：确认意向" }))
    await user.click(screen.getByRole("button", { name: "确认意向" }))
    await user.click(screen.getByRole("button", { name: "开始匹配" }))
    await screen.findByRole("heading", { name: "找到 5 位可能与你合拍的报名者" })
    await user.click(screen.getByRole("button", { name: /Aro 0/ }))
    await user.click(screen.getByRole("button", { name: /Aro 1/ }))
    await user.click(screen.getByRole("button", { name: /发送认识邀请/ }))
    await waitFor(() => expect(api.adoptionReplies).toHaveBeenCalledWith("set-1", ["candidate-0", "candidate-1"], "csrf"))
    expect(await screen.findByRole("heading", { name: "你收到了 2 封愿意继续认识的回信" })).toBeInTheDocument()
    expect(screen.queryByText("来自 Elfaria 的回信")).not.toBeInTheDocument()
    expect(screen.queryByText("选择一封愿意继续认识的回信。")).not.toBeInTheDocument()
    expect(screen.queryByText("Your answers sounded familiar.")).not.toBeInTheDocument()
    expect(screen.queryByText("从愿意继续认识的 Elfie 中选择一位。打开回信时只展示静态形象和一小段自我表达。")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /Aro 0/ }))
    await user.click(screen.getByRole("button", { name: /选择 TA 继续/ }))
    expect(await screen.findByRole("heading", { name: "约定在地球上的称呼" })).toBeInTheDocument()
    expect(screen.queryByText("Elfie 已经有自己的原名。你们可以保留原名、使用 TA 提议的地球昵称，或者提出一个新称呼。")).not.toBeInTheDocument()
    expect(screen.queryByText("Reply 0")).not.toBeInTheDocument()
    expect(screen.getByRole("radiogroup", { name: "地球称呼" })).toBeInTheDocument()
    expect(screen.getByRole("radio", { name: /保留原名/ })).toBeChecked()
    expect(document.querySelectorAll(".adoption-name-option__radio")).toHaveLength(3)
    const customNameInput = screen.getByRole("textbox", { name: "新称呼" })
    expect(customNameInput.parentElement).toHaveAttribute("data-selected", "false")
    await user.click(customNameInput)
    expect(screen.getByRole("radio", { name: /提出一个新称呼/ })).toBeChecked()
    expect(customNameInput.parentElement).toHaveAttribute("data-selected", "true")
    await user.click(screen.getByRole("button", { name: "返回" }))
    expect(await screen.findByRole("heading", { name: "你收到了 2 封愿意继续认识的回信" })).toBeInTheDocument()
  }, 15000)

  it("lets the welcome checkbox label toggle the library checkbox", async () => {
    const user = userEvent.setup()
    render(<I18nextProvider i18n={createI18n()}><AdoptionJourneyDialog accountId="owner" csrfToken="csrf" onAdopted={vi.fn(async () => undefined)} onOpenChange={vi.fn()} open /></I18nextProvider>)

    const checkbox = await screen.findByRole("checkbox", { name: "以后不再显示" })
    await user.click(screen.getByText("以后不再显示"))
    expect(checkbox).toBeChecked()
    await user.click(screen.getByText("以后不再显示"))
    expect(checkbox).not.toBeChecked()
  })

  it("keeps the arrival page to its main title without the old helper copy", async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(<I18nextProvider i18n={createI18n()}><AdoptionJourneyDialog accountId="owner" csrfToken="csrf" onAdopted={vi.fn(async () => undefined)} onOpenChange={onOpenChange} open /></I18nextProvider>)

    await user.click(await screen.findByRole("button", { name: "写下邀请" }))
    await user.click(screen.getByRole("button", { name: /狐狸/ }))
    await user.click(screen.getByRole("button", { name: /继续：外貌倾向/ }))
    await user.click(screen.getByRole("button", { name: /继续：相处期待/ }))
    for (let index = 0; index < 5; index += 1) await user.click(screen.getByRole("button", { name: "都可以" }))
    await user.click(screen.getByRole("button", { name: "继续：确认意向" }))
    await user.click(screen.getByRole("button", { name: "确认意向" }))
    await user.click(screen.getByRole("button", { name: "开始匹配" }))
    await screen.findByRole("heading", { name: "找到 5 位可能与你合拍的报名者" })
    for (const index of [0, 1]) await user.click(screen.getByRole("button", { name: new RegExp(`Aro ${index}`) }))
    await user.click(screen.getByRole("button", { name: /发送认识邀请/ }))
    await screen.findByRole("heading", { name: "你收到了 2 封愿意继续认识的回信" })
    await user.click(screen.getByRole("button", { name: /Aro 0/ }))
    await user.click(screen.getByRole("button", { name: /选择 TA 继续/ }))
    await user.click(screen.getByRole("button", { name: /确认迎接/ }))
    expect(screen.getByRole("alertdialog")).toHaveTextContent("确认迎接")
    expect(api.commitAdoption).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: /确认迎接/ }))
    expect(await screen.findByRole("heading", { name: "Aro 0 来到 Nest 了" })).toBeInTheDocument()
    expect(screen.queryByText("Elfaria 通道已稳定")).not.toBeInTheDocument()
    expect(screen.queryByText("从这一刻起，Aro 0 会以自己的外貌和性格与你一起生活。")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "去 Nest 见 TA" }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(screen.queryByRole("heading", { name: "你希望先认识怎样的 Elfie？" })).not.toBeInTheDocument()
  }, 15000)

  it("offers at most three candidate batches and removes the old stability note", async () => {
    const user = userEvent.setup()
    api.adoptionCandidates
      .mockResolvedValueOnce({ candidate_set_id: "set-1", candidates: [0, 1, 2, 3, 4].map(candidate) })
      .mockResolvedValueOnce({ candidate_set_id: "set-2", candidates: [5, 6, 7, 8, 9].map(candidate) })
      .mockResolvedValueOnce({ candidate_set_id: "set-3", candidates: [10, 11, 12, 13, 14].map(candidate) })

    render(<I18nextProvider i18n={createI18n()}><AdoptionJourneyDialog accountId="owner" csrfToken="csrf" onAdopted={vi.fn(async () => undefined)} onOpenChange={vi.fn()} open /></I18nextProvider>)
    await user.click(await screen.findByRole("button", { name: "写下邀请" }))
    await user.click(screen.getByRole("button", { name: /狐狸/ }))
    await user.click(screen.getByRole("button", { name: /继续：外貌倾向/ }))
    await user.click(screen.getByRole("button", { name: /继续：相处期待/ }))
    for (let index = 0; index < 5; index += 1) await user.click(screen.getByRole("button", { name: "都可以" }))
    await user.click(screen.getByRole("button", { name: "继续：确认意向" }))
    await user.click(screen.getByRole("button", { name: "确认意向" }))
    await user.click(screen.getByRole("button", { name: "开始匹配" }))
    await screen.findByRole("heading", { name: "找到 5 位可能与你合拍的报名者" })
    expect(screen.getByText("第 1 / 3 批")).toBeInTheDocument()
    expect(screen.queryByText("选中后仍可取消；候选档案不会重新随机。")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "再找一批" }))
    await screen.findByText("第 2 / 3 批")
    await user.click(screen.getByRole("button", { name: "再找一批" }))
    await screen.findByText("第 3 / 3 批")
    expect(screen.getByRole("button", { name: "已看完 3 批" })).toBeDisabled()
    expect(api.adoptionCandidates).toHaveBeenCalledTimes(3)
  }, 15000)
})
