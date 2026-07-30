import type { FoodPackage } from "../api/owner-foods"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table"

export function FoodRoleTable({ food }: { readonly food: FoodPackage }) {
  const roles = [
    ["Primary", food.roles.primary?.model ?? ""],
    ["Reasoning", food.roles.reasoning?.model ?? ""],
    ["Vision", food.roles.vision?.model ?? ""],
    ["Tool", food.roles.tool?.model ?? ""],
    ["Fallback", food.roles.fallback.map((item) => item.model).join(" → ")],
  ]
  return <Table aria-label={`${food.display_name}角色配置`} className="food-role-table">
    <TableHeader><TableRow><TableHead>角色</TableHead><TableHead>连接 / 模型</TableHead><TableHead>状态</TableHead></TableRow></TableHeader>
    <TableBody>{roles.map(([role, model]) => <TableRow key={role}>
      <TableHead scope="row">{role}</TableHead>
      <TableCell>{model || "未配置"}</TableCell>
      <TableCell>{model ? "可用模型候选" : "未配置"}</TableCell>
    </TableRow>)}</TableBody>
  </Table>
}
