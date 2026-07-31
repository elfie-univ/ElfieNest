import type { FoodPackage } from "../api/owner-foods"
import { useTranslation } from "react-i18next"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table"

export function FoodRoleTable({ food }: { readonly food: FoodPackage }) {
  const { t } = useTranslation("manage")
  const roles = [
    [t("foodPackages.roles.primary"), food.roles.primary?.model ?? ""],
    [t("foodPackages.roles.reasoning"), food.roles.reasoning?.model ?? ""],
    [t("foodPackages.roles.vision"), food.roles.vision?.model ?? ""],
    [t("foodPackages.roles.tool"), food.roles.tool?.model ?? ""],
    [t("foodPackages.roles.fallback"), food.roles.fallback.map((item) => item.model).join(" → ")],
  ]
  return <Table aria-label={t("foodPackages.labels.roleTable", { name: food.display_name })} className="food-role-table">
    <TableHeader><TableRow><TableHead>{t("foodPackages.roleTable.role")}</TableHead><TableHead>{t("foodPackages.roleTable.connectionModel")}</TableHead><TableHead>{t("foodPackages.roleTable.status")}</TableHead></TableRow></TableHeader>
    <TableBody>{roles.map(([role, model]) => <TableRow key={role}>
      <TableHead scope="row">{role}</TableHead>
      <TableCell>{model || t("foodPackages.values.notConfigured")}</TableCell>
      <TableCell>{model ? t("foodPackages.roleTable.available") : t("foodPackages.values.notConfigured")}</TableCell>
    </TableRow>)}</TableBody>
  </Table>
}
