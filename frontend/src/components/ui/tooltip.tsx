import * as React from "react";
import * as T from "@radix-ui/react-tooltip";

export const TooltipProvider = T.Provider;
export function Tip({ content, children }: { content: React.ReactNode; children: React.ReactNode }) {
  if (!content) return <>{children}</>;
  return (
    <T.Root delayDuration={200}>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content sideOffset={4} className="z-50 max-w-xs rounded-md bg-zinc-900 px-2 py-1.5 text-xs leading-snug text-white">
          {content}
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
