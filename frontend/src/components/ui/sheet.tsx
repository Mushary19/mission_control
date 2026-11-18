import * as React from "react";
import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";

/** Right-side panel (shadcn "Sheet"). */
export function Sheet({ open, onOpenChange, title, description, children }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: string; children: React.ReactNode }) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-zinc-900/10" />
        <D.Content className="fixed right-0 top-0 z-50 flex h-full w-[440px] max-w-[92vw] flex-col border-l border-zinc-200 bg-white focus:outline-none">
          <div className="flex items-start justify-between gap-3 border-b border-zinc-200 px-5 py-4">
            <div>
              <D.Title className="text-[15px] font-semibold">{title}</D.Title>
              {description && <D.Description className="mt-0.5 text-xs text-zinc-500">{description}</D.Description>}
            </div>
            <D.Close className="rounded-md p-1 text-zinc-500 hover:bg-zinc-100" aria-label="Close"><X className="size-4" /></D.Close>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
