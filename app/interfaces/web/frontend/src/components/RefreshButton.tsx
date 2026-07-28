import type { ComponentProps } from "react"

import { Button } from "@/components/ui/button"
import { Icon } from "./Icon"

type RefreshButtonProps = Omit<ComponentProps<typeof Button>, "children" | "variant"> & {
  readonly label: string
}

export function RefreshButton({ label, ...props }: RefreshButtonProps) {
  return <Button {...props} type="button">
    <Icon name="rotate-cw" size={16} />
    {label}
  </Button>
}
