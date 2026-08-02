import { Button } from "@/components/ui/button"
import { DropdownMenu } from "radix-ui"
import { useTranslation } from "react-i18next"

import { Icon } from "./Icon"

export type ProviderLifecycleAction = "enable" | "disable" | "archive" | "restore"

type ProviderLifecycleMenuProps = {
  readonly archived: boolean
  readonly busy: boolean
  readonly enabled: boolean
  readonly onDelete: () => void
  readonly onLifecycle: (action: ProviderLifecycleAction) => void
}

export function ProviderLifecycleMenu({ archived, busy, enabled, onDelete, onLifecycle }: ProviderLifecycleMenuProps) {
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
        {archived
          ? <DropdownMenu.Item className="provider-lifecycle-menu__item" onSelect={() => onLifecycle("restore")}>{t("providerConnections.actions.restore")}</DropdownMenu.Item>
          : enabled
            ? <DropdownMenu.Item className="provider-lifecycle-menu__item" onSelect={() => onLifecycle("disable")}>{t("providerConnections.actions.disable")}</DropdownMenu.Item>
            : <DropdownMenu.Item className="provider-lifecycle-menu__item" onSelect={() => onLifecycle("enable")}>{t("providerConnections.actions.enable")}</DropdownMenu.Item>}
        {!archived ? <DropdownMenu.Item className="provider-lifecycle-menu__item" onSelect={() => onLifecycle("archive")}>{t("providerConnections.actions.archive")}</DropdownMenu.Item> : null}
        <DropdownMenu.Item className="provider-lifecycle-menu__item provider-lifecycle-menu__item--danger" disabled={!archived} onSelect={onDelete}>{t("providerConnections.actions.delete")}</DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Portal>
  </DropdownMenu.Root>
}
