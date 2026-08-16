import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError } from "../../api/http"
import { createI18n } from "../../i18n/config"
import { AdoptionJourneyDialog } from "./AdoptionJourneyDialog"

const api = vi.hoisted(() => ({
  adoptionCandidates: vi.fn(),
  adoptionInfo: vi.fn(),
  adoptionReplies: vi.fn(),
  commitAdoption: vi.fn(),
}))

vi.mock("../../api/me/adoption", () => api)

vi.mock("../elfie-profile/profile-godot-preview", () => ({
  ProfileGodotPreviewError: class ProfileGodotPreviewError extends Error {
    public readonly reason: string

    public constructor(reason: string) {
      super(reason)
      this.reason = reason
    }
  },
  createProfileGodotPreview: ({ onEvent }: { readonly onEvent: (event: { readonly kind: "ready" | "completed"; readonly action?: string; readonly requestId?: string }) => void }) => {
    queueMicrotask(() => onEvent({ kind: "ready" }))
    return {
      capture: () => {
        queueMicrotask(() => onEvent({ kind: "completed", action: "capture", requestId: "test-capture" }))
        return Promise.resolve({ blob: new Blob(["png"], { type: "image/png" }), previewUrl: "preview://test" })
      },
      dispose: vi.fn(),
      send: (action: string) => queueMicrotask(() => onEvent({ kind: "completed", action, requestId: "test-action" })),
    }
  },
}))

function candidate(index: number) {
  return {
    candidate_id: `candidate-${index}`,
    species_id: "fox" as const,
    life_stage: "young_adult" as const,
    age_months: 36,
    gender: index % 2 === 0 ? "male" as const : "female" as const,
    full_body_image_url: `data:image/png;base64,full-${index}`,
    headshot_image_url: `data:image/png;base64,head-${index}`,
    appearance_tags: ["Balanced", "Soft"],
    personality_tags: ["Curious", "Warm"],
    runtime_appearance: { species_id: "fox" },
  }
}

function reply(index: number) {
  return {
    ...candidate(index),
    status: "accepted" as const,
    message: "",
    reveal: {
      original_name: `Aro ${index}`,
      suggested_name: `阿洛 ${index}`,
      personal_story: `我是 Aro ${index}，很高兴来到 Nest。`,
    },
  }
}

const species = [
  {
    species_id: "fox",
    canon_id: "saevi",
    display_name: "Saevi",
    display_name_zh: "灵狐",
    earth_shape_label: "fox-like",
    scene_id: "fox",
    sort_order: 0,
    presentation_images: {
      headshot_url: "/api/v1/me/adoption/species/fox/images/headshot",
      full_body_url: "/api/v1/me/adoption/species/fox/images/full-body",
    },
  },
  {
    species_id: "dog",
    canon_id: "tovren",
    display_name: "Tovren",
    display_name_zh: "灵犬",
    earth_shape_label: "dog-like",
    scene_id: "dog",
    sort_order: 1,
    presentation_images: {
      headshot_url: "/api/v1/me/adoption/species/dog/images/headshot",
      full_body_url: "/api/v1/me/adoption/species/dog/images/full-body",
    },
  },
] as const

function renderJourney(options: {
  readonly accountId?: string
  readonly onAdopted?: (elfieId: string) => Promise<void>
  readonly onOpenChange?: (open: boolean) => void
} = {}) {
  return render(
    <I18nextProvider i18n={createI18n()}>
      <AdoptionJourneyDialog
        accountId={options.accountId ?? "owner"}
        csrfToken="csrf"
        onAdopted={options.onAdopted ?? (async () => undefined)}
        onOpenChange={options.onOpenChange ?? vi.fn()}
        open
      />
    </I18nextProvider>,
  )
}

async function openBasic(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "开始寻找" }))
  expect(await screen.findByRole("heading", { name: "先选一个基础方向" })).toBeInTheDocument()
}

async function reachShortlist(user: ReturnType<typeof userEvent.setup>) {
  await openBasic(user)
  await user.click(screen.getByRole("button", { name: "灵狐" }))
  await user.click(screen.getByRole("button", { name: "开始寻找候选" }))
  expect(await screen.findByRole("heading", { name: "选一位你最喜欢的 Elfie" })).toBeInTheDocument()
  expect(screen.getByText("第 1 / 3 批")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "再找一批" })).toBeInTheDocument()
}

describe("AdoptionJourneyDialog", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() })
    window.localStorage.clear()
    api.adoptionInfo.mockResolvedValue({
      personality_styles: ["好奇探索"],
      species,
      heights: ["short", "standard", "tall"],
      builds: ["slim", "standard", "plump"],
      quota: { used: 0, max: 3, remaining: 3, can_adopt: true },
      nest_capacity: { used: 0, max: 4, remaining: 4 },
      availability: "available",
    })
    api.adoptionCandidates.mockResolvedValue({
      candidate_set_id: "set-1",
      adoption_session_id: "session-1",
      batch_number: 1,
      candidates: [0, 1, 2, 3, 4].map(candidate),
    })
    api.adoptionReplies.mockImplementation(async (_setId: string, candidateIds: readonly string[]) => ({
      candidate_set_id: "set-1",
      replies: candidateIds.map((candidateId) => reply(Number(candidateId.replace("candidate-", "")))),
    }))
    api.commitAdoption.mockResolvedValue({ elfie_id: "00000001", name: "Aro 0", species_id: "fox" })
  })

  it("blocks entry when the adoption quota is full", async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    api.adoptionInfo.mockResolvedValueOnce({
      personality_styles: ["好奇探索"],
      species,
      heights: ["short", "standard", "tall"],
      builds: ["slim", "standard", "plump"],
      quota: { used: 3, max: 3, remaining: 0, can_adopt: false },
      nest_capacity: { used: 4, max: 4, remaining: 0 },
      availability: "nest_full",
    })

    renderJourney({ onOpenChange })

    const dialog = await screen.findByRole("alertdialog")
    expect(dialog).toHaveTextContent("领养名额已满")
    expect(dialog).toHaveTextContent("当前 Nest 暂时没有新的领养名额")
    await user.click(screen.getByRole("button", { name: "知道了" }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it("keeps the welcome copy compact and hides the explanation by default", async () => {
    renderJourney()

    expect(await screen.findByRole("heading", { name: "一位来自遥远星球 Elfaria 的朋友，正在等你相遇" })).toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: "以后跳过这段介绍" })).toBeChecked()
    expect(screen.queryByText("先选一个方向，马上看看适合你的 Elfie。")).not.toBeInTheDocument()
    expect(screen.getByText("不确定的地方会交给缘分；想让匹配更贴合，也可以展开详细匹配")).not.toBeVisible()
    expect(screen.getByRole("button", { name: "开始寻找" })).toBeInTheDocument()
  })

  it("advances the candidate-search story while candidate profiles are in transit", async () => {
    api.adoptionCandidates.mockImplementationOnce(() => new Promise<never>(() => undefined))
    renderJourney()
    expect(await screen.findByRole("heading", { name: "一位来自遥远星球 Elfaria 的朋友，正在等你相遇" })).toBeInTheDocument()

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole("button", { name: "开始寻找" }))
    fireEvent.click(screen.getByRole("button", { name: "灵狐" }))
    fireEvent.click(screen.getByRole("button", { name: "开始寻找候选" }))

    expect(screen.getByRole("heading", { name: "正在穿过星海，为你寻找合拍的 Elfie" })).toBeInTheDocument()
    expect(screen.getByText("正在将你的期待传往 Elfaria")).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(4_000) })
    expect(screen.getByText("来自 Elfaria 的候选资料正在传回地球")).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(6_000) })
    expect(screen.getByText("Elfaria 离地球很远，候选资料仍在传回途中")).toBeInTheDocument()
  })

  it("advances the selected Elfie's departure story while waiting", async () => {
    const user = userEvent.setup()
    renderJourney()
    await reachShortlist(user)
    await user.click(screen.getByRole("button", { name: "候选者 1" }))
    api.adoptionReplies.mockImplementationOnce(() => new Promise<never>(() => undefined))

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole("button", { name: "迎接 TA" }))

    expect(screen.getByRole("heading", { name: "TA 正在从遥远的 Elfaria 赶往地球" })).toBeInTheDocument()
    expect(screen.getByText("TA 正在收拾行李，准备出发")).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(4_000) })
    expect(screen.getByText("TA 已经离开 Elfaria，正在穿越星海")).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(6_000) })
    expect(screen.getByText("Elfaria 离地球很远，TA 还在路上")).toBeInTheDocument()
  })

  it("runs the quick three-step flow and welcomes one selected Elfie", async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    const onAdopted = vi.fn(async () => undefined)
    renderJourney({ onOpenChange, onAdopted })

    await openBasic(user)
    const progress = screen.getByRole("list", { name: "领养阶段" })
    expect(progress).toHaveTextContent("1基础匹配2选择 Elfie3欢迎 TA")
    expect(screen.getAllByRole("button", { name: "不限" })).toHaveLength(2)
    expect(screen.queryByText("约 1 分钟")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "开始寻找候选" })).toBeDisabled()

    await user.click(screen.getByRole("button", { name: "灵狐" }))
    expect(screen.getByRole("button", { name: "开始寻找候选" })).toBeEnabled()
    await user.click(screen.getByRole("button", { name: "开始寻找候选" }))
    expect(await screen.findByRole("heading", { name: "选一位你最喜欢的 Elfie" })).toBeInTheDocument()
    expect(api.adoptionCandidates).toHaveBeenCalledWith(expect.objectContaining({
      species_id: "fox",
      life_stage: "any",
      gender: "any",
      answers: ["any", "any", "any", "any", "any"],
    }), "csrf")

    const first = screen.getByRole("button", { name: "候选者 1" })
    const second = screen.getByRole("button", { name: "候选者 2" })
    await user.click(first)
    expect(first).toHaveAttribute("aria-pressed", "true")
    expect(screen.queryByText("选一位你最想迎接的 Elfie")).not.toBeInTheDocument()
    expect(screen.queryByText("已选择 1 位")).not.toBeInTheDocument()
    await user.click(second)
    expect(first).toHaveAttribute("aria-pressed", "false")
    expect(second).toHaveAttribute("aria-pressed", "true")
    expect(screen.queryByRole("button", { name: /拒绝|写信|回信/ })).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "迎接 TA" }))
    expect(await screen.findByRole("heading", { name: "欢迎来到 Nest，Aro 1" })).toBeInTheDocument()
    expect(api.adoptionReplies).toHaveBeenCalledWith("set-1", ["candidate-1"], "", "csrf")
    expect(screen.queryByText("TA 的自我介绍")).not.toBeInTheDocument()
    expect(screen.getByText("3 岁 · 女性")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "返回" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /拒绝|写信|回信/ })).not.toBeInTheDocument()

    const nameInput = screen.getByRole("textbox", { name: "给 TA 一个称呼" })
    await user.clear(nameInput)
    await user.type(nameInput, "洛洛")
    expect(screen.getByRole("heading", { name: "欢迎来到 Nest，洛洛" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "和 TA 聊聊" }))
    expect(api.commitAdoption).toHaveBeenCalledWith("set-1", "candidate-1", "洛洛", "csrf", expect.any(Object))
    expect(onAdopted).toHaveBeenCalledWith("00000001")
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(screen.queryByRole("heading", { name: "TA 正在从遥远的 Elfaria 赶往地球" })).not.toBeInTheDocument()
  }, 15000)

  it("keeps detailed matching optional while reusing the same candidate page", async () => {
    const user = userEvent.setup()
    renderJourney()

    await openBasic(user)
    await user.click(screen.getByRole("button", { name: "灵狐" }))
    await user.click(screen.getByRole("button", { name: "展开详细匹配" }))
    expect(await screen.findByRole("heading", { name: "再告诉我们你的外貌偏好" })).toBeInTheDocument()
    expect(screen.getByText("详细匹配：1/2")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "继续：相处期待" }))
    expect(await screen.findByRole("heading", { name: "如果未来一起生活……" })).toBeInTheDocument()
    expect(screen.getByText("详细匹配：2/2")).toBeInTheDocument()
    expect(screen.queryByText("问题 1 / 5")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "开始寻找候选" }))
    expect(await screen.findByRole("heading", { name: "选一位你最喜欢的 Elfie" })).toBeInTheDocument()

    expect(api.adoptionCandidates).toHaveBeenCalledWith(expect.objectContaining({
      appearance: { stature: "any", build: "any", face: "any", signature: "any", priority: "face" },
    }), "csrf")
  }, 15000)

  it("keeps one-candidate invitation failures recoverable", async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    api.adoptionReplies.mockRejectedValue(new Error("signal unavailable"))
    renderJourney({ onOpenChange })

    await reachShortlist(user)
    await user.click(screen.getByRole("button", { name: "候选者 3" }))
    await user.click(screen.getByRole("button", { name: "迎接 TA" }))

    const failureDialog = await screen.findByRole("alertdialog")
    expect(failureDialog).toHaveTextContent("TA 暂时还没到达")
    expect(screen.getByRole("heading", { name: "TA 正在从遥远的 Elfaria 赶往地球" })).toBeInTheDocument()
    expect(api.adoptionReplies).toHaveBeenCalledWith("set-1", ["candidate-2"], "", "csrf")
    await user.click(screen.getByRole("button", { name: "稍后再说" }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  }, 15000)

  it("restarts when the candidate session has expired", async () => {
    const user = userEvent.setup()
    api.adoptionReplies.mockRejectedValueOnce(new ApiError(410, "gone", [], "adoption_candidate_set_expired"))
    renderJourney()

    await reachShortlist(user)
    await user.click(screen.getByRole("button", { name: "候选者 1" }))
    await user.click(screen.getByRole("button", { name: "迎接 TA" }))

    expect(await screen.findByRole("heading", { name: "先选一个基础方向" })).toBeInTheDocument()
    expect(screen.getByText("本次领养已失效，请重新开始")).toBeInTheDocument()
  }, 15000)
})
