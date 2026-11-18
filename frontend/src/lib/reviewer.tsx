import * as React from "react";
import { storageGet, storageSet } from "./utils";

const Ctx = React.createContext<{ user: string; setUser: (u: string) => void }>({ user: "Hana Pemberton", setUser: () => {} });

/** "Reviewing as" (no auth). Remembered per browser when storage is available. */
export function ReviewerProvider({ children }: { children: React.ReactNode }) {
  const [user, setU] = React.useState(() => storageGet("mc.reviewer") || "Hana Pemberton");
  const setUser = (u: string) => { setU(u); storageSet("mc.reviewer", u); };
  return <Ctx.Provider value={{ user, setUser }}>{children}</Ctx.Provider>;
}
export const useReviewer = () => React.useContext(Ctx);
