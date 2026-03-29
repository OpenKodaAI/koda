import fs from "node:fs";
import path from "node:path";

function stripQuotes(value: string) {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }

  return value;
}

export function parseDotenv(content: string) {
  const result: Record<string, string> = {};

  for (const rawLine of content.split(/\r?\n/g)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    const normalized = line.startsWith("export ") ? line.slice(7).trim() : line;
    const separatorIndex = normalized.indexOf("=");
    if (separatorIndex <= 0) continue;

    const key = normalized.slice(0, separatorIndex).trim();
    const value = stripQuotes(normalized.slice(separatorIndex + 1).trim());

    if (!key) continue;
    result[key] = value;
  }

  return result;
}

export function loadProjectEnv(projectPath: string) {
  const envPath = path.join(projectPath, ".env");

  try {
    const content = fs.readFileSync(envPath, "utf8");
    return parseDotenv(content);
  } catch {
    return {} as Record<string, string>;
  }
}

export function resolveScopedEnvValue(
  values: Record<string, string>,
  botId: string,
  key: string
) {
  return values[`${botId}_${key}`] || values[key] || null;
}
