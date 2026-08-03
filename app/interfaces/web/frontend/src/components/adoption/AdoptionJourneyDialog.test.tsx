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
    await user.click(screen.getByRole("button", { name: "开始填写意向" }))
    await user.click(screen.getByRole("button", { name: /狐狸/ }))
    await user.click(screen.getByRole("button", { name: /继续：外貌倾向/ }))
    await user.click(screen.getByRole("button", { name: /继续：相处期待/ }))

    for (let index = 0; index < 5; index += 1) {
      await user.click(screen.getByRole("button", { name: "都可以" }))
      await user.click(screen.getByRole("button", { name: index === 4 ? /查看意向摘要/ : /下一题/ }))
    }

    expect(await screen.findByRole("heading", { name: "把这份地球意向发送给 Elfaria" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /现场生成候选/ }))
    expect(await screen.findByRole("heading", { name: "找到 5 位可能与你合拍的报名者" })).toBeInTheDocument()
    expect(api.adoptionCandidates).toHaveBeenCalledWith(expect.objectContaining({ species_id: "fox" }), "csrf")
  })

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
  })
})
