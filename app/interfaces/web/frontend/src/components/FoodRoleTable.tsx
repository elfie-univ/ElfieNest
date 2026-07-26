import type { ExecutionProfile, FoodRecipe } from "../api/owner-foods"

export function FoodRoleTable({ food }: { readonly food: FoodRecipe }) {
  const roles: readonly (readonly [string, ExecutionProfile | null])[] = [
    ["主模型", food.primary],
    ["深度模型", food.deep],
    ["校验模型", food.verifier],
    ...food.technical_fallbacks.map((profile, index) => [`技术回退 ${index + 1}`, profile] as const),
  ]
  return <div className="food-role-table-wrap"><table aria-label={`${food.display_name}角色配置`} className="food-role-table">
    <thead><tr><th>角色</th><th>模型</th><th>推理档位</th><th>Tokens / 温度</th><th>工具</th><th>Provider 参数</th></tr></thead>
    <tbody>{roles.map(([role, profile]) => <tr key={role}>
      <th scope="row">{role}</th>
      <td>{profile?.model || "未配置"}</td>
      <td>{profile?.reasoning_profile ?? "未配置"}</td>
      <td>{profile ? `${profile.max_tokens} / ${profile.temperature}` : "未配置"}</td>
      <td>{profile?.tools.length ? profile.tools.join("、") : "无"}</td>
      <td>{profile && Object.keys(profile.provider_options).length > 0
        ? Object.entries(profile.provider_options).map(([key, value]) => `${key}: ${String(value)}`).join("；")
        : "无"}</td>
    </tr>)}</tbody>
  </table></div>
}
