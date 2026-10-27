import * as React from "react"
import { cn } from "cn"

function Field({
  className,
  orientation = "vertical",
  ...props
}: React.ComponentProps<"div"> & {
  orientation?: "vertical" | "horizontal"
}) {
  return (
    <div
      role="group"
      data-slot="field"
      data-orientation={orientation}
      className={cn(
        "group/field flex w-full gap-2 data-[orientation=horizontal]:flex-row data-[orientation=horizontal]:items-center data-[orientation=vertical]:flex-col",
        className
      )}
      {...props}
    />
  )
}

function FieldLabel({
  className,
  ...props
}: React.ComponentProps<"label">) {
  return (
    <label
      data-slot="field-label"
      className={cn(
        "text-sm font-medium text-foreground group-data-[orientation=horizontal]/field:whitespace-nowrap",
        className
      )}
      {...props}
    />
  )
}

export { Field, FieldLabel }
