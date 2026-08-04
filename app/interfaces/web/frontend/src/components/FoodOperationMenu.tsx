import { Button } from "@/components/ui/button"
import { DropdownMenu } from "radix-ui"
import { useTranslation } from "react-i18next"

import { Icon } from "./Icon"

export type FoodLifecycleAction = "enable" | "disable" | "archive" | "restore"

type FoodOperationMenuProps = {
  readonly archived: boolean
  readonly busy: boolean
  readonly enabled: boolean
  readonly system: boolean
  readonly onDelete: () => void
  readonly onEdit: () => void
  readonly onGenerate: () => void
  readonly onLifecycle: (action: FoodLifecycleAction) => void
}

export function FoodOperationMenu({ archived, busy, enabled, system, onDelete, onEdit, onGenerate, onLifecycle }: FoodOperationMenuProps) {
  const { t } = useTranslation("manage")
  return <DropdownMenu.Root>
    <DropdownMenu.Trigger asChild>
      <Button aria-label={t("foodPackages.actions.more")} disabled={busy} type="button" variant="outline">
        {t("foodPackages.actions.more")}<Icon name="chevron-down" size={15} />
      </Button>
    </DropdownMenu.Trigger>
    <DropdownMenu.Portal>
      <DropdownMenu.Content align="end" className="food-operation-menu" sideOffset={6}>
        {!archived ? <>
          <DropdownMenu.Item className="food-operation-menu__item" onSelect={onGenerate}>{t("foodPackages.actions.generate")}</DropdownMenu.Item>
          <DropdownMenu.Item className="food-operation-menu__item" onSelect={onEdit}>{t("foodPackages.actions.edit")}</DropdownMenu.Item>
          <DropdownMenu.Item className="food-operation-menu__item" onSelect={() => onLifecycle(enabled ? "disable" : "enable")}>{t(enabled ? "foodPackages.actions.disable" : "foodPackages.actions.enable")}</DropdownMenu.Item>
          {!system ? <DropdownMenu.Item className="food-operation-menu__item" onSelect={() => onLifecycle("archive")}>{t("foodPackages.actions.archive")}</DropdownMenu.Item> : null}
        </> : <>
          <DropdownMenu.Item className="food-operation-menu__item" onSelect={() => onLifecycle("restore")}>{t("foodPackages.actions.restore")}</DropdownMenu.Item>
          {!system ? <DropdownMenu.Item className="food-operation-menu__item food-operation-menu__item--danger" onSelect={onDelete}>{t("foodPackages.actions.delete")}</DropdownMenu.Item> : null}
        </>}
      </DropdownMenu.Content>
    </DropdownMenu.Portal>
  </DropdownMenu.Root>
}
