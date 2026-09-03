import { Button } from "@/components/ui/button"
import { DropdownMenu } from "radix-ui"
import { useTranslation } from "react-i18next"

import { Icon } from "./Icon"

export type ProviderLifecycleAction = "enable" | "disable" | "archive" | "restore"

type ProviderLifecycleMenuProps = {
  readonly archived: boolean
  readonly busy: boolean
  readonly canDelete: boolean
  readonly enabled: boolean
  readonly onDelete: () => void
  readonly onForceFull: () => void
  readonly onLifecycle: (action: ProviderLifecycleAction) => void
}

export function ProviderLifecycleMenu({ archived, busy, canDelete, enabled, onDelete, onForceFull, onLifecycle }: ProviderLifecycleMenuProps) {
  const { t } = useTranslation("manage")

  return <DropdownMenu.Root>
    <DropdownMenu.Trigger asChild>
      <Button aria-label={t("providerConnections.actions.more")} disabled={busy} type="button" variant="outline">
        {t("providerConnections.actions.more")}
        <Icon name="chevron-down" size={15} />
      </Button>
    </DropdownMenu.Trigger>
    <DropdownMenu.Portal>
      <DropdownMenu.Content align="end" className="provider-lifecycle-menu" sideOffset={6}>
        <DropdownMenu.Item className="provider-lifecycle-menu__item" onSelect={onForceFull}>{t("providerConnections.actions.forceFullValidate")}</DropdownMenu.Item>
        {archived
          ? <DropdownMenu.Item className="provider-lifecycle-menu__item" onSelect={() => onLifecycle("restore")}>{t("providerConnections.actions.restore")}</DropdownMenu.Item>
          : enabled
            ? <DropdownMenu.Item className="provider-lifecycle-menu__item" onSelect={() => onLifecycle("disable")}>{t("providerConnections.actions.disable")}</DropdownMenu.Item>
            : <DropdownMenu.Item className="provider-lifecycle-menu__item" onSelect={() => onLifecycle("enable")}>{t("providerConnections.actions.enable")}</DropdownMenu.Item>}
        {!archived ? <DropdownMenu.Item className="provider-lifecycle-menu__item" onSelect={() => onLifecycle("archive")}>{t("providerConnections.actions.archive")}</DropdownMenu.Item> : null}
        <DropdownMenu.Item className="provider-lifecycle-menu__item provider-lifecycle-menu__item--danger" disabled={!canDelete} onSelect={onDelete} title={!canDelete ? t("providerConnections.actions.deleteRequiresArchive") : undefined}>{t("providerConnections.actions.delete")}</DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Portal>
  </DropdownMenu.Root>
}
