import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex h-6 shrink-0 items-center gap-1 rounded-md px-2 text-sm font-medium whitespace-nowrap", {
  variants: {
    variant: {
      solid: "bg-zinc-900 text-white",
      outline: "border border-zinc-300 text-zinc-700",
      dashed: "border border-dashed border-zinc-400 text-zinc-600",
      muted: "bg-zinc-100 text-zinc-600",
      accent: "bg-indigo-50 text-indigo-700",
      green: "bg-emerald-50 text-emerald-700",
      amber: "bg-amber-50 text-amber-800",
      red: "bg-red-50 text-red-700",
    },
  },
  defaultVariants: { variant: "muted" },
});
export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}
export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(({ className, variant, ...props }, ref) => (
  <span ref={ref} className={cn(badgeVariants({ variant }), className)} {...props} />
));
Badge.displayName = "Badge";
