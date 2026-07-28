import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "min-h-24 w-full min-w-0 resize-y rounded-lg border border-[var(--border)] bg-[var(--surface-field)] px-3 py-2 text-base text-[var(--text)] outline-none transition-colors placeholder:text-[var(--text-muted)] hover:border-[var(--border-strong)] focus-visible:border-[var(--focus-ring)] focus-visible:ring-3 focus-visible:ring-[color-mix(in_srgb,var(--focus-ring)_28%,transparent)] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
