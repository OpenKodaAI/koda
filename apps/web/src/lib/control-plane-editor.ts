import { translateLiteral } from "@/lib/i18n";

export function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export function parseJsonObject(
  label: string,
  value: string,
): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) {
    return {};
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : translateLiteral("JSON invalido");
    throw new Error(`${label}: ${message}`);
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label}: ${translateLiteral("o valor precisa ser um objeto JSON")}`);
  }

  return parsed as Record<string, unknown>;
}

export function parseJsonArray(
  label: string,
  value: string,
): Array<Record<string, unknown>> {
  const trimmed = value.trim();
  if (!trimmed) {
    return [];
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : translateLiteral("JSON invalido");
    throw new Error(`${label}: ${message}`);
  }

  if (!Array.isArray(parsed)) {
    throw new Error(`${label}: ${translateLiteral("o valor precisa ser um array JSON")}`);
  }

  const invalidIndex = parsed.findIndex(
    (item) => !item || typeof item !== "object" || Array.isArray(item),
  );
  if (invalidIndex >= 0) {
    throw new Error(
      `${label}: ${translateLiteral("cada item precisa ser um objeto JSON (indice {{index}})", { index: invalidIndex })}`,
    );
  }

  return parsed as Array<Record<string, unknown>>;
}

export function parseHealthPort(value: string): number {
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error(translateLiteral("Health port e obrigatorio."));
  }

  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
    throw new Error(translateLiteral("Health port precisa ser um inteiro entre 1 e 65535."));
  }

  return parsed;
}

export function buildBotMetadataPayload(input: {
  displayName: string;
  status: string;
  storageNamespace: string;
  workspaceId: string;
  squadId: string;
  color: string;
  colorRgb: string;
  healthPort: string;
  healthUrl: string;
  runtimeBaseUrl: string;
  appearanceJson: string;
  runtimeEndpointJson: string;
  metadataJson: string;
}) {
  const appearance = parseJsonObject("Appearance JSON", input.appearanceJson);
  const runtimeEndpoint = parseJsonObject(
    "Runtime endpoint JSON",
    input.runtimeEndpointJson,
  );
  const metadata = parseJsonObject("Metadata JSON", input.metadataJson);

  const displayName = input.displayName.trim();
  const storageNamespace = input.storageNamespace.trim();
  if (!displayName) {
    throw new Error(translateLiteral("Display name e obrigatorio."));
  }
  if (!storageNamespace) {
    throw new Error(translateLiteral("Storage namespace e obrigatorio."));
  }

  appearance.label = displayName;
  if (input.color.trim()) {
    appearance.color = input.color.trim();
  } else {
    delete appearance.color;
  }
  if (input.colorRgb.trim()) {
    appearance.color_rgb = input.colorRgb.trim();
  } else {
    delete appearance.color_rgb;
  }

  runtimeEndpoint.health_port = parseHealthPort(input.healthPort);
  if (input.healthUrl.trim()) {
    runtimeEndpoint.health_url = input.healthUrl.trim();
  } else {
    delete runtimeEndpoint.health_url;
  }
  if (input.runtimeBaseUrl.trim()) {
    runtimeEndpoint.runtime_base_url = input.runtimeBaseUrl.trim();
  } else {
    delete runtimeEndpoint.runtime_base_url;
  }

  return {
    display_name: displayName,
    status: input.status,
    storage_namespace: storageNamespace,
    appearance,
    runtime_endpoint: runtimeEndpoint,
    metadata,
    organization: {
      workspace_id: input.workspaceId.trim() || null,
      squad_id: input.workspaceId.trim()
        ? input.squadId.trim() || null
        : null,
    },
  };
}

export function buildAgentSpecPayload(input: {
  missionProfileJson: string;
  interactionStyleJson: string;
  operatingInstructionsJson: string;
  hardRulesJson: string;
  responsePolicyJson: string;
  modelPolicyJson: string;
  toolPolicyJson: string;
  memoryPolicyJson: string;
  knowledgePolicyJson: string;
  autonomyPolicyJson: string;
  resourceAccessPolicyJson: string;
  voicePolicyJson: string;
  imageAnalysisPolicyJson: string;
  memoryExtractionSchemaJson: string;
}) {
  return {
    mission_profile: parseJsonObject(
      "Mission profile JSON",
      input.missionProfileJson,
    ),
    interaction_style: parseJsonObject(
      "Interaction style JSON",
      input.interactionStyleJson,
    ),
    operating_instructions: parseJsonObject(
      "Operating instructions JSON",
      input.operatingInstructionsJson,
    ),
    hard_rules: parseJsonObject("Hard rules JSON", input.hardRulesJson),
    response_policy: parseJsonObject(
      "Response policy JSON",
      input.responsePolicyJson,
    ),
    model_policy: parseJsonObject("Model policy JSON", input.modelPolicyJson),
    tool_policy: parseJsonObject("Tool policy JSON", input.toolPolicyJson),
    memory_policy: parseJsonObject(
      "Memory policy JSON",
      input.memoryPolicyJson,
    ),
    knowledge_policy: parseJsonObject(
      "Knowledge policy JSON",
      input.knowledgePolicyJson,
    ),
    autonomy_policy: parseJsonObject(
      "Autonomy policy JSON",
      input.autonomyPolicyJson,
    ),
    resource_access_policy: parseJsonObject(
      "Resource access policy JSON",
      input.resourceAccessPolicyJson,
    ),
    voice_policy: parseJsonObject("Voice policy JSON", input.voicePolicyJson),
    image_analysis_policy: parseJsonObject(
      "Image analysis policy JSON",
      input.imageAnalysisPolicyJson,
    ),
    memory_extraction_schema: parseJsonObject(
      "Memory extraction schema JSON",
      input.memoryExtractionSchemaJson,
    ),
  };
}

export function validateColor(hex: string): boolean {
  return /^#[0-9a-fA-F]{6}$/.test(hex);
}

export function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const match = /^#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/.exec(hex);
  if (!match) return null;
  return {
    r: parseInt(match[1], 16),
    g: parseInt(match[2], 16),
    b: parseInt(match[3], 16),
  };
}

export function rgbToHex(r: number, g: number, b: number): string {
  const clamp = (n: number) => Math.max(0, Math.min(255, Math.round(n)));
  return `#${[r, g, b].map((c) => clamp(c).toString(16).padStart(2, "0")).join("")}`;
}

export function rgbStringToComponents(rgb: string): { r: number; g: number; b: number } | null {
  const parts = rgb.split(",").map((s) => parseInt(s.trim(), 10));
  if (parts.length !== 3 || parts.some(isNaN)) return null;
  return { r: parts[0], g: parts[1], b: parts[2] };
}

export function componentsToRgbString(r: number, g: number, b: number): string {
  return `${r}, ${g}, ${b}`;
}
