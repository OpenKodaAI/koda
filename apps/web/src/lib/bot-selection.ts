import type { BotDisplay } from "@/lib/bot-constants";
import { translate } from "@/lib/i18n";

export function resolveBotSelection(
  selectedBotIds: string[] | undefined,
  availableBotIds: string[],
): string[] {
  if (availableBotIds.length === 0) return [];

  const selectedSet = new Set(selectedBotIds ?? []);
  const resolved = availableBotIds.filter((botId) => selectedSet.has(botId));
  return resolved.length > 0 ? resolved : [...availableBotIds];
}

export function toggleBotSelection(
  selectedBotIds: string[] | undefined,
  botId: string,
  availableBotIds: string[],
): string[] {
  const current = resolveBotSelection(selectedBotIds, availableBotIds);
  const next = current.includes(botId)
    ? current.filter((value) => value !== botId)
    : [...current, botId];

  if (next.length === 0 || next.length === availableBotIds.length) {
    return [];
  }

  const nextSet = new Set(next);
  return availableBotIds.filter((value) => nextSet.has(value));
}

export function formatBotSelectionLabel(
  resolvedBotIds: string[],
  bots: BotDisplay[],
): string {
  if (
    bots.length === 0 ||
    resolvedBotIds.length === 0 ||
    resolvedBotIds.length === bots.length
  ) {
    return translate("botSwitcher.allBots");
  }

  if (resolvedBotIds.length === 1) {
    const matchedBot = bots.find((bot) => bot.id === resolvedBotIds[0]);
    return matchedBot?.label ?? resolvedBotIds[0];
  }

  return translate("botSwitcher.botsSelected", { count: resolvedBotIds.length });
}
