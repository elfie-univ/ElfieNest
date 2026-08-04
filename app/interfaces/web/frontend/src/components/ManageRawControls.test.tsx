import { render, screen, within } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import "../styles.css"
import { Button } from "@/components/ui/button"
import { SelectGroup, SelectLabel } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ClientUser } from "../api/client"
import { createI18n } from "../i18n/config"
import { initializeLocale } from "../i18n/locale"
import { ownerProviderConnections } from "../api/owner-providers"
import { ownerUsers } from "../api/owner-users"
import {
  ownerFoods,
  type FoodCatalog,
  type FoodPackage,
} from "../api/owner-foods"
import { ManageSidebar } from "./ManageSidebar"
import { OwnerFoodPanel } from "./OwnerFoodPanel"

vi.mock("../api/owner-foods", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-foods")>()
  return {
    ...original,
    ownerFoods: vi.fn(),
  }
})

vi.mock("../api/owner-providers", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-providers")>()
  return {
    ...original,
    ownerProviderConnections: vi.fn(),
  }
})

vi.mock("../api/owner-users", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-users")>()
  return {
    ...original,
    ownerUsers: vi.fn(),
  }
})

const food = {
  key: "standard",
  display_name: "标准粮",
  system_role: "common",
  enabled: true,
  archived: false,
  visibility_mode: "global",
  visible_user_ids: [],
  roles: { primary: { model: "ollama/primary" }, reasoning: null, vision: null, tool: null, fallback: null },
  health: "passed",
  locality: "local",
  latest_evidence_at: null,
} satisfies FoodPackage

const catalog = {
  version: 2,
  global_default_food_id: "standard",
  global_emergency_food_id: "emergency",
  packages: [food],
  eligible_models: [],
} satisfies FoodCatalog

const ownerUser = {
  account_id: "owner",
  display_name: "Owner",
  role: "owner",
  csrf_token: "csrf",
  avatar_url: null,
  theme_key: "warm-paper",
  default_landing_page: "manage",
  user_id: 1,
} satisfies ClientUser

describe("Manage shared controls", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    vi.mocked(ownerFoods).mockResolvedValue(catalog)
    vi.mocked(ownerProviderConnections).mockResolvedValue([])
    vi.mocked(ownerUsers).mockResolvedValue([])
  })

  it("renders small shared actions and select group labels as accessible controls", () => {
    render(
      <div>
        <Button size="xs" type="button">紧凑动作</Button>
        <Button size="sm" type="button">小号动作</Button>
        <SelectGroup>
          <SelectLabel>本地模型</SelectLabel>
        </SelectGroup>
      </div>,
    )

    expect(screen.getByRole("button", { name: "紧凑动作" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "小号动作" })).toBeEnabled()
    expect(screen.getByText("本地模型")).toBeVisible()
  })

  it("exposes sidebar actions as named buttons and navigation links", () => {
    const instance = createI18n()
    initializeLocale(instance, {
      browserLanguages: ["zh-CN"],
      documentElement: document.documentElement,
      storage: localStorage,
    })
    render(<I18nextProvider i18n={instance}><ManageSidebar activeTab="providers" onSelect={() => undefined} onUserUpdated={async () => undefined} user={ownerUser} /></I18nextProvider>)

    expect(screen.getByRole("button", { name: "模型订阅" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "用手机打开管理台" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "Owner管理员" })).toHaveAttribute("aria-haspopup", "dialog")
    expect(screen.getByRole("link", { name: "进入聊天" })).toHaveAttribute("href", "/chat")
  })

  it("composes operational tables from the shared Table primitive while keeping native roles", () => {
    render(
      <Table aria-label="运行数据表">
        <TableHeader>
          <TableRow>
            <TableHead scope="col">名称</TableHead>
            <TableHead scope="col">状态</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableHead scope="row">标准粮</TableHead>
            <TableCell>通过</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    )

    const table = screen.getByRole("table", { name: "运行数据表" })
    expect(within(table).getAllByRole("columnheader")).toHaveLength(2)
    expect(within(table).getByRole("rowheader", { name: "标准粮" })).toBeInstanceOf(HTMLTableCellElement)
    const passingCell = within(table).getByRole("cell", { name: "通过" })
    expect(passingCell).toBeInstanceOf(HTMLTableCellElement)
    if (passingCell instanceof HTMLTableCellElement) {
      expect(getComputedStyle(passingCell).display).toBe("table-cell")
    }
  })

  it("renders the food catalog as the flat shared table", async () => {
    const instance = createI18n()
    document.documentElement.lang = "zh-CN"
    render(
      <I18nextProvider i18n={instance}>
        <OwnerFoodPanel csrfToken="csrf" />
      </I18nextProvider>,
    )

    const foodTable = await screen.findByRole("table", { name: "粮食套餐" })
    expect(within(foodTable).getAllByRole("columnheader")).toHaveLength(9)
    expect(screen.queryByRole("table", { name: "标准粮角色配置" })).not.toBeInTheDocument()
  })
})
