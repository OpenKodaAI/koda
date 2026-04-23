export type ChannelStatus = "disconnected" | "pending" | "connected";

export type ChannelDefinition = {
  key: string;
  label: string;
  tagline: string;
  logoKey: string;
  gradientFrom: string;
  gradientTo: string;
  isOfficial: boolean;
  helpUrl?: string;
  fields: {
    key: string;
    label: string;
    type: "secret" | "text" | "tags";
    required: boolean;
    helpText?: string;
  }[];
};

export const CHANNEL_CATALOG: ChannelDefinition[] = [
  {
    key: "telegram",
    label: "Telegram",
    tagline: "Agent API",
    logoKey: "telegram",
    gradientFrom: "#0088cc",
    gradientTo: "#0077b5",
    isOfficial: true,
    fields: [
      {
        key: "AGENT_TOKEN",
        label: "Agent Token",
        type: "secret",
        required: true,
        helpText: "Token gerado pelo @AgentFather no Telegram.",
      },
      {
        key: "ALLOWED_USER_IDS",
        label: "User IDs permitidos",
        type: "tags",
        required: false,
        helpText: "IDs numericos do Telegram. Deixe vazio para permitir todos.",
      },
    ],
  },
  {
    key: "whatsapp",
    label: "WhatsApp Business",
    tagline: "Meta Cloud API",
    logoKey: "whatsapp",
    gradientFrom: "#25D366",
    gradientTo: "#128C7E",
    isOfficial: true,
    fields: [
      {
        key: "WHATSAPP_ACCESS_TOKEN",
        label: "Access Token",
        type: "secret",
        required: true,
        helpText: "Token de acesso da API Cloud",
      },
      {
        key: "WHATSAPP_PHONE_NUMBER_ID",
        label: "Phone Number ID",
        type: "text",
        required: true,
        helpText: "ID do número de telefone",
      },
      {
        key: "WHATSAPP_VERIFY_TOKEN",
        label: "Verify Token",
        type: "secret",
        required: true,
        helpText: "Token de verificação do webhook",
      },
      {
        key: "WHATSAPP_APP_SECRET",
        label: "App Secret",
        type: "secret",
        required: true,
        helpText: "App secret para verificação HMAC do webhook",
      },
    ],
  },
  {
    key: "discord",
    label: "Discord",
    tagline: "Agent API",
    logoKey: "discord",
    gradientFrom: "#5865F2",
    gradientTo: "#4752C4",
    isOfficial: true,
    fields: [
      {
        key: "DISCORD_BOT_TOKEN",
        label: "Agent Token",
        type: "secret",
        required: true,
        helpText: "Token do agent no Developer Portal",
      },
    ],
  },
  {
    key: "slack",
    label: "Slack",
    tagline: "Bolt API",
    logoKey: "slack",
    gradientFrom: "#4A154B",
    gradientTo: "#611F69",
    isOfficial: true,
    fields: [
      {
        key: "SLACK_BOT_TOKEN",
        label: "Agent Token",
        type: "secret",
        required: true,
        helpText: "Token do agent (xoxb-)",
      },
      {
        key: "SLACK_APP_TOKEN",
        label: "App Token",
        type: "secret",
        required: true,
        helpText: "Token do app (xapp-)",
      },
      {
        key: "SLACK_SIGNING_SECRET",
        label: "Signing Secret",
        type: "secret",
        required: true,
        helpText: "Signing secret do app",
      },
    ],
  },
  {
    key: "teams",
    label: "Microsoft Teams",
    tagline: "Agent Framework",
    logoKey: "teams",
    gradientFrom: "#6264A7",
    gradientTo: "#464EB8",
    isOfficial: true,
    fields: [
      {
        key: "TEAMS_APP_ID",
        label: "App ID",
        type: "text",
        required: true,
        helpText: "Application ID do Azure",
      },
      {
        key: "TEAMS_APP_PASSWORD",
        label: "App Password",
        type: "secret",
        required: true,
        helpText: "Client secret do Azure",
      },
    ],
  },
  {
    key: "line",
    label: "LINE",
    tagline: "Messaging API",
    logoKey: "line",
    gradientFrom: "#06C755",
    gradientTo: "#00B900",
    isOfficial: true,
    fields: [
      {
        key: "LINE_CHANNEL_SECRET",
        label: "Channel Secret",
        type: "secret",
        required: true,
        helpText: "Channel secret do console",
      },
      {
        key: "LINE_CHANNEL_ACCESS_TOKEN",
        label: "Channel Access Token",
        type: "secret",
        required: true,
        helpText: "Channel access token",
      },
    ],
  },
  {
    key: "messenger",
    label: "Messenger",
    tagline: "Graph API",
    logoKey: "messenger",
    gradientFrom: "#0099FF",
    gradientTo: "#0077CC",
    isOfficial: true,
    fields: [
      {
        key: "MESSENGER_PAGE_ACCESS_TOKEN",
        label: "Page Access Token",
        type: "secret",
        required: true,
        helpText: "Page access token",
      },
      {
        key: "MESSENGER_VERIFY_TOKEN",
        label: "Verify Token",
        type: "secret",
        required: true,
        helpText: "Token de verificação do webhook",
      },
      {
        key: "MESSENGER_APP_SECRET",
        label: "App Secret",
        type: "secret",
        required: true,
        helpText: "App secret",
      },
    ],
  },
  {
    key: "signal",
    label: "Signal",
    tagline: "signal-cli",
    logoKey: "signal",
    gradientFrom: "#3A76F0",
    gradientTo: "#2E5FBF",
    isOfficial: false,
    fields: [
      {
        key: "SIGNAL_PHONE_NUMBER",
        label: "Phone Number",
        type: "text",
        required: true,
        helpText: "Número de telefone registrado",
      },
      {
        key: "SIGNAL_CLI_URL",
        label: "CLI URL",
        type: "text",
        required: true,
        helpText: "URL da API signal-cli",
      },
    ],
  },
  {
    key: "instagram",
    label: "Instagram",
    tagline: "Graph API",
    logoKey: "instagram",
    gradientFrom: "#E4405F",
    gradientTo: "#C13584",
    isOfficial: false,
    fields: [
      {
        key: "INSTAGRAM_PAGE_ACCESS_TOKEN",
        label: "Page Access Token",
        type: "secret",
        required: true,
        helpText: "Page access token",
      },
      {
        key: "INSTAGRAM_APP_SECRET",
        label: "App Secret",
        type: "secret",
        required: true,
        helpText: "App secret",
      },
    ],
  },
];
