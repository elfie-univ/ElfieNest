import { render, screen, within } from "@testing-library/react"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import "../styles.css"
import { Button } from "@/components/ui/button"
import { SelectGroup, SelectLabel } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ClientUser } from "../api/client"
import { ownerProviders } from "../api/owner-providers"
import {
  ownerFoods,
  type FoodCatalog,
  type FoodRecipe,
} from "../api/owner-foods"
import { FoodRoleTable } from "./FoodRoleTable"
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
    ownerProviders: vi.fn(),
  }
})

const profile = {
  model: "ollama/primary",
  reasoning_profile: "balanced",
  max_tokens: 1500,
  temperature: 0.7,
  tools: [],
  provider_options: {},
}

const food = {
  key: "standard",
  display_name: "标准粮",
  description: "日常默认",
  primary: profile,
  deep: null,
  verifier: null,
  technical_fallbacks: [],
  validation_status: "passed",
  source: "manual",
  locked_fields: [],
} satisfies FoodRecipe

const catalog = {
  version: 2,
  source_fingerprint: "current",
  generated_at: "2026-07-26T00:00:00Z",
  generation_sources: ["manual"],
  generation_note: "",
  foods: { standard: food },
} satisfies FoodCatalog

const ownerUser = {
  account_id: "owner",
  username: "owner",
  nickname: "Owner",
  role: "owner",
  csrf_token: "csrf",
  avatar_url: null,
  theme_key: "warm-paper",
  default_landing_page: "manage",
} satisfies ClientUser

describe("Manage shared controls", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    vi.mocked(ownerFoods).mockResolvedValue(catalog)
    vi.mocked(ownerProviders).mockResolvedValue([])
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
    render(<ManageSidebar activeTab="providers" onSelect={() => undefined} onUserUpdated={async () => undefined} user={ownerUser} />)

    expect(screen.getByRole("button", { name: "模型订阅" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "用手机打开管理台" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "OwnerOwner" })).toHaveAttribute("aria-haspopup", "dialog")
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

  it("renders food catalog and role tables through the shared Table primitive", async () => {
    render(<OwnerFoodPanel csrfToken="csrf" />)

    const foodTable = await screen.findByRole("table", { name: "粮食策略" })
    expect(within(foodTable).getByRole("columnheader", { name: "验证状态" })).toBeInTheDocument()

    render(<FoodRoleTable food={food} />)
    const roleTable = screen.getByRole("table", { name: "标准粮角色配置" })
    expect(within(roleTable).getByRole("rowheader", { name: "主模型" })).toBeInTheDocument()
  })
})
