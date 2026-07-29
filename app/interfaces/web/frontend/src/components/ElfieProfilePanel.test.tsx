import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  HAPPY_EXPERIENCE,
  KETTLE_EXPERIENCE,
  LONG_BIOGRAPHY_EXPERIENCE,
  MISSING_PUBLIC_FIELDS_EXPERIENCE,
  PRIVATE_MODULE_TITLES,
  SIGNED_IN_ADMIN,
} from "./elfie-profile/mock-data"
import { parseViewer } from "./elfie-profile/model"
import { projectElfieProfile } from "./elfie-profile/projection"
import { ElfieProfilePanel } from "./ElfieProfilePanel"

const profileStyles = readFileSync(resolve(import.meta.dirname, "../shared/chat-profile.css"), "utf8")

vi.mock("./elfie-profile/ProfileChart", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("./elfie-profile/ProfileChart")>()
  return {
    ...original,
    loadProfileChartRuntime: () => Promise.resolve({
      init: vi.fn(() => ({ dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn() })),
    }),
  }
})

describe("ElfieProfilePanel", () => {
  it("keeps the desktop portrait track bound to the visible portrait width", () => {
    // Given: the responsive profile stylesheet.
    const identityRule = profileStyles.match(/\.profile-dossier__identity\s*\{[^}]+\}/)?.[0] ?? ""

    // When: the desktop identity grid contract is inspected.
    // Then: the track is capped with the portrait instead of adding an invisible 18vw gap.
    expect(identityRule).toContain(
      "grid-template-columns: clamp(128px, 14vw, 176px) minmax(0, 1fr) auto",
    )
    expect(identityRule).toContain("column-gap: clamp(18px, 2vw, 32px)")
    expect(identityRule).not.toContain("minmax(128px, 18vw)")
  })

  it("keeps the tablet identity readable beside the persistent Elfie list", () => {
    expect(profileStyles).toMatch(
      /@media \(max-width: 860px\)[\s\S]*\.profile-dossier__identity\s*\{[\s\S]*grid-template-columns: 108px minmax\(0, 1fr\)/,
    )
  })

  it("does not reserve mobile header space for the disabled reset action", () => {
    expect(profileStyles).toMatch(
      /@media \(max-width: 760px\)[\s\S]*\.profile-appearance__actions \[disabled\]\s*\{\s*display: none;/,
    )
    expect(profileStyles).toMatch(
      /@media \(max-width: 760px\)[\s\S]*\.profile-appearance__header h2\s*\{[^}]*white-space: nowrap;/,
    )
  })

  it("renders the adopter identity, public biography, and owner relationship metadata", () => {
    // Given: Happy projected for the account that adopted Happy.
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)

    // When: the personal dossier identity frame is rendered.
    render(<ElfieProfilePanel onBack={vi.fn()} onChat={vi.fn()} projection={projection} />)

    // Then: the reference-led public hierarchy and adopter relationship are visible.
    expect(screen.getByRole("heading", { level: 1, name: "Happy" })).toBeInTheDocument()
    expect(screen.getByText("狐狸精灵")).toBeInTheDocument()
    expect(screen.getByText(HAPPY_EXPERIENCE.publicProfile.biography)).toBeInTheDocument()
    expect(screen.getByText("我")).toBeInTheDocument()
    expect(screen.getByText("2026-06-30")).toBeInTheDocument()
    expect(screen.getByText("1 个月")).toBeInTheDocument()
    expect(screen.getByText("12345678")).toBeInTheDocument()
  })

  it("routes mobile back and chat actions through callbacks", async () => {
    // Given: a profile with route-owned action callbacks.
    const user = userEvent.setup()
    const onBack = vi.fn()
    const onChat = vi.fn()
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    render(<ElfieProfilePanel onBack={onBack} onChat={onChat} projection={projection} />)

    // When: each identity action is invoked.
    await user.click(screen.getByRole("button", { name: "返回我的精灵" }))
    await user.click(screen.getByRole("button", { name: "进入聊天" }))

    // Then: navigation remains owned by the caller.
    expect(onBack).toHaveBeenCalledOnce()
    expect(onChat).toHaveBeenCalledOnce()
    expect(screen.getByRole("button", { name: "返回我的精灵" })).toHaveClass("profile-dossier__back")
  })

  it("omits adopter-only metadata and all old admin passport surfaces for visitors", () => {
    // Given: Kettle projected for an unrelated account.
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, LONG_BIOGRAPHY_EXPERIENCE)

    // When: the visitor dossier is rendered.
    const { container } = render(
      <ElfieProfilePanel onBack={vi.fn()} onChat={vi.fn()} projection={projection} />,
    )

    // Then: only public relationship copy remains in the visitor DOM.
    expect(screen.getByText("用户示例")).toBeInTheDocument()
    expect(screen.getByText(LONG_BIOGRAPHY_EXPERIENCE.publicProfile.biography)).toBeInTheDocument()
    expect(screen.queryByText("领养日期")).not.toBeInTheDocument()
    expect(screen.queryByText("年龄")).not.toBeInTheDocument()
    expect(screen.queryByText("23456789")).not.toBeInTheDocument()
    expect(container).not.toHaveTextContent(/精灵身份证|档案编号|管理员|本地 3D 观察/)
    expect(container.querySelector("iframe")).toBeNull()
  })

  it("keeps missing portrait, gender, and biography concise and readable", () => {
    // Given: a fixture with all optional public fields absent.
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, MISSING_PUBLIC_FIELDS_EXPERIENCE)

    // When: the identity frame renders its fallbacks.
    render(<ElfieProfilePanel onBack={vi.fn()} onChat={vi.fn()} projection={projection} />)

    // Then: it uses a portrait initial and honest copy without fake gender.
    expect(screen.getByText("M", { selector: ".profile-dossier__portrait" })).toBeInTheDocument()
    expect(screen.getByText("这只精灵还没有留下自我介绍。")).toBeInTheDocument()
    expect(screen.queryByText(/性别/)).not.toBeInTheDocument()
  })

  it("composes the complete owner profile in the approved section order", () => {
    // Given: Happy projected for the account that adopted Happy.
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)

    // When: the complete profile experience renders.
    const { container } = render(
      <ElfieProfilePanel onBack={vi.fn()} onChat={vi.fn()} projection={projection} />,
    )

    // Then: identity, appearance, public personality, and private modules appear in order.
    expect(screen.getByRole("heading", { level: 2, name: "3D 个体视图" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 2, name: "大五人格" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "拍照" })).toBeInTheDocument()
    for (const title of PRIVATE_MODULE_TITLES) {
      expect(screen.getByRole("button", { name: title })).toBeInTheDocument()
    }
    const identity = container.querySelector(".profile-dossier__identity")
    const appearance = container.querySelector(".profile-appearance")
    const radar = container.querySelector(".profile-radar")
    const privateModules = container.querySelector(".profile-dossier__private-modules")
    if (identity === null || appearance === null || radar === null || privateModules === null) {
      throw new TypeError("Expected the complete profile composition")
    }
    expect(identity.compareDocumentPosition(appearance) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(appearance.compareDocumentPosition(radar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(radar.compareDocumentPosition(privateModules) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(container).not.toHaveTextContent(/精灵身份证|Observer|本地 3D 观察|修改/)
  })

  it("keeps capture and all six private payloads out of the visitor DOM", () => {
    // Given: Kettle projected for a platform owner who did not adopt Kettle.
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, KETTLE_EXPERIENCE)

    // When: the complete public profile renders.
    const { container } = render(
      <ElfieProfilePanel onBack={vi.fn()} onChat={vi.fn()} projection={projection} />,
    )

    // Then: public identity and Big Five remain, while capture and private data are omitted.
    expect(screen.getByRole("heading", { level: 1, name: "Kettle" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 2, name: "大五人格" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "拍照" })).not.toBeInTheDocument()
    for (const title of PRIVATE_MODULE_TITLES) {
      expect(screen.queryByRole("button", { name: title })).not.toBeInTheDocument()
    }
    expect(container).not.toHaveTextContent(/铜壶窗边观察|qwen3-8b-calm|第一次避让/)
  })

  it("applies a captured avatar to the visible identity and resets it on Elfie switch", async () => {
    // Given: an owner profile and a deterministic local capture.
    const user = userEvent.setup()
    const captured = {
      blob: new Blob(["happy"], { type: "image/png" }),
      previewUrl: "blob:happy-avatar",
    }
    const capture = vi.fn().mockResolvedValue(captured)
    const happyProjection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    const kettleViewer = parseViewer({
      accountId: "user123",
      displayName: "Kettle 的领养人",
      role: "user",
    })
    const kettleProjection = projectElfieProfile(kettleViewer, KETTLE_EXPERIENCE)
    const view = render(
      <ElfieProfilePanel
        appearanceCapture={capture}
        onBack={vi.fn()}
        onChat={vi.fn()}
        projection={happyProjection}
      />,
    )

    // When: the capture is selected as the session-local avatar.
    await user.click(screen.getByRole("button", { name: "拍照" }))
    const dialog = await screen.findByRole("dialog", { name: "确认这张照片" })
    await user.click(within(dialog).getByRole("button", { name: "设为头像" }))

    // Then: the identity portrait uses that exact preview.
    expect(document.querySelector(".profile-dossier__portrait img")).toHaveAttribute(
      "src",
      captured.previewUrl,
    )

    // When: the same panel switches to another Elfie.
    view.rerender(
      <ElfieProfilePanel
        appearanceCapture={capture}
        onBack={vi.fn()}
        onChat={vi.fn()}
        projection={kettleProjection}
      />,
    )

    // Then: the previous Elfie's session avatar is not reused.
    expect(document.querySelector(".profile-dossier__portrait img")).toBeNull()
    expect(screen.getByText("K", { selector: ".profile-dossier__portrait" })).toBeInTheDocument()

    // When: navigation returns to Happy within the same mounted panel.
    view.rerender(
      <ElfieProfilePanel
        appearanceCapture={capture}
        onBack={vi.fn()}
        onChat={vi.fn()}
        projection={happyProjection}
      />,
    )

    // Then: the old capture remains cleared instead of reappearing from an ID-keyed cache.
    expect(document.querySelector(".profile-dossier__portrait img")).toBeNull()
    expect(screen.getByText("H", { selector: ".profile-dossier__portrait" })).toBeInTheDocument()
  })
})
