export type ChannelStatus = "disconnected" | "pending" | "connected";

export type ChannelDefinition = {
  key: string;
  labelKey: string;
  taglineKey: string;
  logoKey: string;
  gradientFrom: string;
  gradientTo: string;
  isOfficial: boolean;
  helpUrl?: string;
  fields: {
    key: string;
    labelKey: string;
    type: "secret" | "text" | "tags";
    required: boolean;
    helpTextKey?: string;
  }[];
};

export const CHANNEL_CATALOG: ChannelDefinition[] = [
  {
    key: "telegram",
    labelKey: "controlPlane.channelCatalog.entries.telegram.label",
    taglineKey: "controlPlane.channelCatalog.entries.telegram.tagline",
    logoKey: "telegram",
    gradientFrom: "#0088cc",
    gradientTo: "#0077b5",
    isOfficial: true,
    fields: [
      {
        key: "AGENT_TOKEN",
        labelKey: "controlPlane.channelCatalog.entries.telegram.fields.AGENT_TOKEN.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.telegram.fields.AGENT_TOKEN.helpText",
      },
      {
        key: "ALLOWED_USER_IDS",
        labelKey: "controlPlane.channelCatalog.entries.telegram.fields.ALLOWED_USER_IDS.label",
        type: "tags",
        required: false,
        helpTextKey: "controlPlane.channelCatalog.entries.telegram.fields.ALLOWED_USER_IDS.helpText",
      },
    ],
  },
  {
    key: "whatsapp",
    labelKey: "controlPlane.channelCatalog.entries.whatsapp.label",
    taglineKey: "controlPlane.channelCatalog.entries.whatsapp.tagline",
    logoKey: "whatsapp",
    gradientFrom: "#25D366",
    gradientTo: "#128C7E",
    isOfficial: true,
    fields: [
      {
        key: "WHATSAPP_ACCESS_TOKEN",
        labelKey: "controlPlane.channelCatalog.entries.whatsapp.fields.WHATSAPP_ACCESS_TOKEN.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.whatsapp.fields.WHATSAPP_ACCESS_TOKEN.helpText",
      },
      {
        key: "WHATSAPP_PHONE_NUMBER_ID",
        labelKey: "controlPlane.channelCatalog.entries.whatsapp.fields.WHATSAPP_PHONE_NUMBER_ID.label",
        type: "text",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.whatsapp.fields.WHATSAPP_PHONE_NUMBER_ID.helpText",
      },
      {
        key: "WHATSAPP_VERIFY_TOKEN",
        labelKey: "controlPlane.channelCatalog.entries.whatsapp.fields.WHATSAPP_VERIFY_TOKEN.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.whatsapp.fields.WHATSAPP_VERIFY_TOKEN.helpText",
      },
      {
        key: "WHATSAPP_APP_SECRET",
        labelKey: "controlPlane.channelCatalog.entries.whatsapp.fields.WHATSAPP_APP_SECRET.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.whatsapp.fields.WHATSAPP_APP_SECRET.helpText",
      },
    ],
  },
  {
    key: "discord",
    labelKey: "controlPlane.channelCatalog.entries.discord.label",
    taglineKey: "controlPlane.channelCatalog.entries.discord.tagline",
    logoKey: "discord",
    gradientFrom: "#5865F2",
    gradientTo: "#4752C4",
    isOfficial: true,
    fields: [
      {
        key: "DISCORD_BOT_TOKEN",
        labelKey: "controlPlane.channelCatalog.entries.discord.fields.DISCORD_BOT_TOKEN.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.discord.fields.DISCORD_BOT_TOKEN.helpText",
      },
    ],
  },
  {
    key: "slack",
    labelKey: "controlPlane.channelCatalog.entries.slack.label",
    taglineKey: "controlPlane.channelCatalog.entries.slack.tagline",
    logoKey: "slack",
    gradientFrom: "#4A154B",
    gradientTo: "#611F69",
    isOfficial: true,
    fields: [
      {
        key: "SLACK_BOT_TOKEN",
        labelKey: "controlPlane.channelCatalog.entries.slack.fields.SLACK_BOT_TOKEN.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.slack.fields.SLACK_BOT_TOKEN.helpText",
      },
      {
        key: "SLACK_APP_TOKEN",
        labelKey: "controlPlane.channelCatalog.entries.slack.fields.SLACK_APP_TOKEN.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.slack.fields.SLACK_APP_TOKEN.helpText",
      },
      {
        key: "SLACK_SIGNING_SECRET",
        labelKey: "controlPlane.channelCatalog.entries.slack.fields.SLACK_SIGNING_SECRET.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.slack.fields.SLACK_SIGNING_SECRET.helpText",
      },
    ],
  },
  {
    key: "teams",
    labelKey: "controlPlane.channelCatalog.entries.teams.label",
    taglineKey: "controlPlane.channelCatalog.entries.teams.tagline",
    logoKey: "teams",
    gradientFrom: "#6264A7",
    gradientTo: "#464EB8",
    isOfficial: true,
    fields: [
      {
        key: "TEAMS_APP_ID",
        labelKey: "controlPlane.channelCatalog.entries.teams.fields.TEAMS_APP_ID.label",
        type: "text",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.teams.fields.TEAMS_APP_ID.helpText",
      },
      {
        key: "TEAMS_APP_PASSWORD",
        labelKey: "controlPlane.channelCatalog.entries.teams.fields.TEAMS_APP_PASSWORD.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.teams.fields.TEAMS_APP_PASSWORD.helpText",
      },
    ],
  },
  {
    key: "line",
    labelKey: "controlPlane.channelCatalog.entries.line.label",
    taglineKey: "controlPlane.channelCatalog.entries.line.tagline",
    logoKey: "line",
    gradientFrom: "#06C755",
    gradientTo: "#00B900",
    isOfficial: true,
    fields: [
      {
        key: "LINE_CHANNEL_SECRET",
        labelKey: "controlPlane.channelCatalog.entries.line.fields.LINE_CHANNEL_SECRET.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.line.fields.LINE_CHANNEL_SECRET.helpText",
      },
      {
        key: "LINE_CHANNEL_ACCESS_TOKEN",
        labelKey: "controlPlane.channelCatalog.entries.line.fields.LINE_CHANNEL_ACCESS_TOKEN.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.line.fields.LINE_CHANNEL_ACCESS_TOKEN.helpText",
      },
    ],
  },
  {
    key: "messenger",
    labelKey: "controlPlane.channelCatalog.entries.messenger.label",
    taglineKey: "controlPlane.channelCatalog.entries.messenger.tagline",
    logoKey: "messenger",
    gradientFrom: "#0099FF",
    gradientTo: "#0077CC",
    isOfficial: true,
    fields: [
      {
        key: "MESSENGER_PAGE_ACCESS_TOKEN",
        labelKey: "controlPlane.channelCatalog.entries.messenger.fields.MESSENGER_PAGE_ACCESS_TOKEN.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.messenger.fields.MESSENGER_PAGE_ACCESS_TOKEN.helpText",
      },
      {
        key: "MESSENGER_VERIFY_TOKEN",
        labelKey: "controlPlane.channelCatalog.entries.messenger.fields.MESSENGER_VERIFY_TOKEN.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.messenger.fields.MESSENGER_VERIFY_TOKEN.helpText",
      },
      {
        key: "MESSENGER_APP_SECRET",
        labelKey: "controlPlane.channelCatalog.entries.messenger.fields.MESSENGER_APP_SECRET.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.messenger.fields.MESSENGER_APP_SECRET.helpText",
      },
    ],
  },
  {
    key: "signal",
    labelKey: "controlPlane.channelCatalog.entries.signal.label",
    taglineKey: "controlPlane.channelCatalog.entries.signal.tagline",
    logoKey: "signal",
    gradientFrom: "#3A76F0",
    gradientTo: "#2E5FBF",
    isOfficial: false,
    fields: [
      {
        key: "SIGNAL_PHONE_NUMBER",
        labelKey: "controlPlane.channelCatalog.entries.signal.fields.SIGNAL_PHONE_NUMBER.label",
        type: "text",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.signal.fields.SIGNAL_PHONE_NUMBER.helpText",
      },
      {
        key: "SIGNAL_CLI_URL",
        labelKey: "controlPlane.channelCatalog.entries.signal.fields.SIGNAL_CLI_URL.label",
        type: "text",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.signal.fields.SIGNAL_CLI_URL.helpText",
      },
    ],
  },
  {
    key: "instagram",
    labelKey: "controlPlane.channelCatalog.entries.instagram.label",
    taglineKey: "controlPlane.channelCatalog.entries.instagram.tagline",
    logoKey: "instagram",
    gradientFrom: "#E4405F",
    gradientTo: "#C13584",
    isOfficial: false,
    fields: [
      {
        key: "INSTAGRAM_PAGE_ACCESS_TOKEN",
        labelKey: "controlPlane.channelCatalog.entries.instagram.fields.INSTAGRAM_PAGE_ACCESS_TOKEN.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.instagram.fields.INSTAGRAM_PAGE_ACCESS_TOKEN.helpText",
      },
      {
        key: "INSTAGRAM_APP_SECRET",
        labelKey: "controlPlane.channelCatalog.entries.instagram.fields.INSTAGRAM_APP_SECRET.label",
        type: "secret",
        required: true,
        helpTextKey: "controlPlane.channelCatalog.entries.instagram.fields.INSTAGRAM_APP_SECRET.helpText",
      },
    ],
  },
];
