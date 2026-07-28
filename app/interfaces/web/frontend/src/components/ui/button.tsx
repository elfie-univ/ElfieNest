import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-semibold whitespace-nowrap transition-colors outline-none select-none focus-visible:border-[var(--focus-ring)] focus-visible:ring-3 focus-visible:ring-[color-mix(in_srgb,var(--focus-ring)_28%,transparent)] active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-[var(--error-text)] [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--accent)] text-[var(--surface)] hover:bg-[var(--accent-hover)] hover:text-[var(--surface)]",
        outline:
          "border-[var(--border-strong)] bg-[var(--surface-field)] text-[var(--text)] hover:border-[var(--accent)] hover:bg-[var(--surface-hover)] hover:text-[var(--text)] aria-expanded:bg-[var(--surface-hover)] aria-expanded:text-[var(--text)]",
        secondary:
          "bg-[var(--surface-field)] text-[var(--text)] hover:bg-[var(--surface-hover)] hover:text-[var(--text)] aria-expanded:bg-[var(--surface-hover)]",
        ghost:
          "bg-transparent text-[var(--text)] hover:bg-[var(--surface-hover)] hover:text-[var(--text)] aria-expanded:bg-[var(--surface-hover)]",
        destructive:
          "bg-[var(--error-bg)] text-[var(--error-text)] hover:bg-[color-mix(in_srgb,var(--error-bg)_72%,var(--error-text))] hover:text-[var(--surface-raised)]",
        link: "text-[var(--accent-hover)] underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-10 gap-2 px-4 has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        xs: "h-7 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-sm in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        sm: "h-8 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-sm in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-11 gap-2 px-5 has-data-[icon=inline-end]:pr-4 has-data-[icon=inline-start]:pl-4",
        icon: "size-10",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
