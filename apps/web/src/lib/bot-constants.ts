/** Client-safe dynamic bot catalog hydrated by the dashboard layout. */

export interface BotDisplay {
  id: string;
  label: string;
  color: string;
  colorRgb: string;
}

let botCatalog: BotDisplay[] = [];

function buildBotDisplayMap() {
  return Object.fromEntries(botCatalog.map((bot) => [bot.id, bot])) as Record<string, BotDisplay>;
}

export function setBotCatalog(items: BotDisplay[]) {
  botCatalog = [...items];
}

export function getBotCatalog() {
  return botCatalog;
}

export function getBotDisplayMap() {
  return buildBotDisplayMap();
}

export function getBotDisplay(botId: string) {
  return buildBotDisplayMap()[botId] ?? null;
}

export function getBotColor(botId: string): string {
  return getBotDisplay(botId)?.color ?? "#7A8799";
}

export function getBotChartColor(botId: string): string {
  return getBotColor(botId);
}

export function getBotLabel(botId: string): string {
  return getBotDisplay(botId)?.label ?? botId;
}
