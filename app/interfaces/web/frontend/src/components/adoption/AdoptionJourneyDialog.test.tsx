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

    expect(await screen.findByRole("heading", { name: "不是挑选一只精灵，而是遇见一位朋友" })).toBeInTheDocument()
    expect(screen.queryByText("你提交的是愿意认识怎样的朋友；候选精灵也会阅读这份意向。")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "开始填写意向" }))
    expect(await screen.findByRole("heading", { name: "你希望先认识怎样的 Elfie？" })).toBeInTheDocument()
    expect(screen.queryByText("第一步 · 基本意向")).not.toBeInTheDocument()
    expect(screen.queryByText("先确定物种、生命阶段和性别倾向。选择的是愿意见见的范围，不是在设置某一位精灵的身份。")).not.toBeInTheDocument()
    expect(screen.queryByText("看看狐狸报名者")).not.toBeInTheDocument()
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
      await user.click(screen.getByRole("button", { name: index === 4 ? /查看意向摘要/ : /下一题/ }))
    }

    expect(await screen.findByRole("heading", { name: "把这份地球意向发送给 Elfaria" })).toBeInTheDocument()
    expect(screen.queryByText("发送后，系统会根据这些范围现场生成 5 位可能合适的报名者。这里仍然可以返回修改。")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /现场生成候选/ }))
    expect(await screen.findByRole("heading", { name: "找到 5 位可能与你合拍的报名者" })).toBeInTheDocument()
    expect(screen.queryByText("选择 1–3 位发送认识邀请。这里使用静态报名照，不同时加载多个 3D 形象。")).not.toBeInTheDocument()
    expect(api.adoptionCandidates).toHaveBeenCalledWith(expect.objectContaining({ species_id: "fox" }), "csrf")
  }, 15000)

  it("allows selecting up to three candidates and keeps the selected snapshot", async () => {
    const user = userEvent.setup()
    render(<I18nextProvider i18n={createI18n()}><AdoptionJourneyDialog accountId="owner" csrfToken="csrf" onAdopted={vi.fn(async () => undefined)} onOpenChange={vi.fn()} open /></I18nextProvider>)
    await user.click(await screen.findByRole("button", { name: "开始填写意向" }))
    await user.click(screen.getByRole("button", { name: /狐狸/ }))
    await user.click(screen.getByRole("button", { name: /继续：外貌倾向/ }))
    await user.click(screen.getByRole("button", { name: /继续：相处期待/ }))
    for (let index = 0; index < 5; index += 1) {
      await user.click(screen.getByRole("button", { name: "都可以" }))
      await user.click(screen.getByRole("button", { name: index === 4 ? /查看意向摘要/ : /下一题/ }))
    }
    await user.click(screen.getByRole("button", { name: /现场生成候选/ }))
    await screen.findByRole("heading", { name: "找到 5 位可能与你合拍的报名者" })
    await user.click(screen.getByRole("button", { name: /Aro 0/ }))
    await user.click(screen.getByRole("button", { name: /Aro 1/ }))
    await user.click(screen.getByRole("button", { name: /发送认识邀请/ }))
    await waitFor(() => expect(api.adoptionReplies).toHaveBeenCalledWith("set-1", ["candidate-0", "candidate-1"], "csrf"))
    expect(await screen.findByRole("heading", { name: "你收到了 2 封愿意继续认识的回信" })).toBeInTheDocument()
    expect(screen.queryByText("从愿意继续认识的 Elfie 中选择一位。打开回信时只展示静态形象和一小段自我表达。")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /Aro 0/ }))
    await user.click(screen.getByRole("button", { name: /选择 TA 继续/ }))
    expect(await screen.findByRole("heading", { name: "约定在地球上的称呼" })).toBeInTheDocument()
    expect(screen.queryByText("Elfie 已经有自己的原名。你们可以保留原名、使用 TA 提议的地球昵称，或者提出一个新称呼。")).not.toBeInTheDocument()
  }, 15000)
})
