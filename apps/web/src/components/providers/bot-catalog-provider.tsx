"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import {
  getBotCatalog,
  getBotDisplayMap,
  setBotCatalog,
  type BotDisplay,
} from "@/lib/bot-constants";

type BotCatalogContextValue = {
  bots: BotDisplay[];
  botDisplayMap: Record<string, BotDisplay>;
};

const BotCatalogContext = createContext<BotCatalogContextValue>({
  bots: [],
  botDisplayMap: {},
});

export function BotCatalogProvider({
  initialBots,
  children,
}: {
  initialBots: BotDisplay[];
  children: ReactNode;
}) {
  const bots = initialBots.length > 0 ? initialBots : getBotCatalog();
  setBotCatalog(bots);

  const value = useMemo(
    () => ({
      bots,
      botDisplayMap: getBotDisplayMap(),
    }),
    [bots]
  );

  return <BotCatalogContext.Provider value={value}>{children}</BotCatalogContext.Provider>;
}

export function useBotCatalog() {
  return useContext(BotCatalogContext);
}
