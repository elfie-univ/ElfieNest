import type { ExecutionProfile, FoodRecipe } from "../api/owner-foods"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table"

export function FoodRoleTable({ food }: { readonly food: FoodRecipe }) {
  const roles: readonly (readonly [string, ExecutionProfile | null])[] = [
    ["主模型", food.primary],
    ["深度模型", food.deep],
    ["校验模型", food.verifier],
    ...food.technical_fallbacks.map((profile, index) => [`技术回退 ${index + 1}`, profile] as const),
  ]
  return <div className="food-role-table-wrap"><Table aria-label={`${food.display_name}角色配置`} className="food-role-table">
    <TableHeader><TableRow><TableHead scope="col">角色</TableHead><TableHead scope="col">模型</TableHead><TableHead scope="col">推理档位</TableHead><TableHead scope="col">Tokens / 温度</TableHead><TableHead scope="col">工具</TableHead><TableHead scope="col">Provider 参数</TableHead></TableRow></TableHeader>
    <TableBody>{roles.map(([role, profile]) => <TableRow key={role}>
      <TableHead scope="row">{role}</TableHead>
      <TableCell>{profile?.model || "未配置"}</TableCell>
      <TableCell>{profile?.reasoning_profile ?? "未配置"}</TableCell>
      <TableCell>{profile ? `${profile.max_tokens} / ${profile.temperature}` : "未配置"}</TableCell>
      <TableCell>{profile?.tools.length ? profile.tools.join("、") : "无"}</TableCell>
      <TableCell>{profile && Object.keys(profile.provider_options).length > 0
        ? Object.entries(profile.provider_options).map(([key, value]) => `${key}: ${String(value)}`).join("；")
        : "无"}</TableCell>
    </TableRow>)}</TableBody>
  </Table></div>
}
