import { useTranslation } from "react-i18next"

import type { ExecutionProfile, FoodRecipe } from "../api/owner-foods"
import { currentLocale, formatNumber } from "../i18n/format"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table"

export function FoodRoleTable({ food }: { readonly food: FoodRecipe }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const roles: readonly (readonly [string, ExecutionProfile | null])[] = [
    [t("foods.roles.primary"), food.primary],
    [t("foods.roles.deep"), food.deep],
    [t("foods.roles.verifier"), food.verifier],
    ...food.technical_fallbacks.map((profile, index) => [t("foods.roles.fallback", { number: index + 1 }), profile] as const),
  ]
  return <div className="food-role-table-wrap"><Table aria-label={t("foods.labels.roleTable", { name: food.display_name })} className="food-role-table">
    <TableHeader><TableRow><TableHead scope="col">{t("foods.roles.role")}</TableHead><TableHead scope="col">{t("executionProfile.fields.model", { label: "" }).trim()}</TableHead><TableHead scope="col">{t("executionProfile.fields.reasoning", { label: "" }).trim()}</TableHead><TableHead scope="col">{t("executionProfile.fields.maxTokens", { label: "" }).trim()} / {t("executionProfile.fields.temperature", { label: "" }).trim()}</TableHead><TableHead scope="col">{t("executionProfile.fields.tools", { label: "" }).trim()}</TableHead><TableHead scope="col">{t("executionProfile.fields.providerOptions")}</TableHead></TableRow></TableHeader>
    <TableBody>{roles.map(([role, profile]) => <TableRow key={role}>
      <TableHead scope="row">{role}</TableHead>
      <TableCell>{profile?.model || t("foods.values.notConfigured")}</TableCell>
      <TableCell>{profile?.reasoning_profile ?? t("foods.values.notConfigured")}</TableCell>
      <TableCell>{profile ? `${formatNumber(profile.max_tokens, locale)} / ${formatNumber(profile.temperature, locale)}` : t("foods.values.notConfigured")}</TableCell>
      <TableCell>{profile?.tools.length ? profile.tools.join(t("foods.values.toolSeparator")) : t("foods.values.none")}</TableCell>
      <TableCell>{profile && Object.keys(profile.provider_options).length > 0
        ? Object.entries(profile.provider_options).map(([key, value]) => `${key}: ${String(value)}`).join(t("foods.values.providerOptionsSeparator"))
        : t("foods.values.none")}</TableCell>
    </TableRow>)}</TableBody>
  </Table>
}
