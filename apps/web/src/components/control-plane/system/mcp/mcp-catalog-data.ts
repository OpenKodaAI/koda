/* ------------------------------------------------------------------ */
/*  MCP server catalog – suggested entries and category labels         */
/*                                                                    */
/*  SSoT (runtime) is the backend catalog.                            */
/*  This file mirrors koda/integrations/mcp_catalog.py for the        */
/*  suggested-servers marketplace + SSR fallback.                     */
/* ------------------------------------------------------------------ */

import type {
  ConnectionProfile,
  McpServerCatalogEntry,
  RuntimeConstraintKey,
} from "@/lib/control-plane";

export type McpCategory = "general" | "development" | "productivity" | "data" | "cloud";

export const MCP_CATEGORY_LABELS: Record<McpCategory, string> = {
  general: "Geral",
  development: "Desenvolvimento",
  productivity: "Produtividade",
  data: "Dados",
  cloud: "Cloud",
};

export type McpSuggestedEnvField = {
  key: string;
  label: string;
  required: boolean;
};

export type McpExpectedTool = {
  name: string;
  description: string;
  read_only_hint?: boolean;
  destructive_hint?: boolean;
};

export type McpSuggestedServer = {
  server_key: string;
  display_name: string;
  description: string;
  tagline: string;
  transport_type: "stdio" | "http_sse";
  command_template: string[];
  env_fields: McpSuggestedEnvField[];
  category: McpCategory;
  documentation_url?: string;
  logo_key?: string;
  expected_tools: McpExpectedTool[];
  oauth_supported?: boolean;
  connection_profile?: ConnectionProfile;
  runtime_constraints?: RuntimeConstraintKey[];
  remote_url?: string;
};

const PINNED_SUPABASE_MCP_PACKAGE = "@supabase/mcp-server-supabase@0.7.0";
const PINNED_STRIPE_MCP_PACKAGE = "@stripe/mcp@0.3.3";
const PINNED_SENTRY_MCP_PACKAGE = "@sentry/mcp-server@0.31.0";
const PINNED_REMOTE_MCP_BRIDGE = "mcp-remote@0.1.38";

export const MCP_RESERVED_SERVER_KEYS = new Set([
  "docker",
  "filesystem",
  "github",
  "gitlab",
  "memory",
  "puppeteer",
]);

export function normalizeMcpServerKey(serverKey: string) {
  return serverKey.trim().toLowerCase();
}

export function isReservedMcpServerKey(serverKey: string) {
  return MCP_RESERVED_SERVER_KEYS.has(normalizeMcpServerKey(serverKey));
}

export function filterAllowedMcpCatalogEntries<T extends { server_key: string }>(
  entries: T[],
) {
  return entries.filter((entry) => !isReservedMcpServerKey(entry.server_key));
}

export const MCP_SUGGESTED_SERVERS: McpSuggestedServer[] = [
  // --- Obrigatórias (5) ---
  {
    server_key: "supabase",
    display_name: "Supabase",
    tagline: "Backend completo com banco, auth e edge functions",
    description:
      "Conecte ao Supabase para executar queries SQL, gerenciar tabelas, listar funções e inspecionar a configuração do projeto.",
    transport_type: "stdio",
    command_template: ["npx", "-y", PINNED_SUPABASE_MCP_PACKAGE],
    env_fields: [
      { key: "SUPABASE_ACCESS_TOKEN", label: "Personal Access Token", required: true },
      { key: "SUPABASE_PROJECT_REF", label: "Project Reference", required: false },
    ],
    category: "cloud",
    logo_key: "supabase",
    documentation_url: "https://supabase.com/docs/guides/getting-started/mcp",
    connection_profile: {
      strategy: "api_key",
      fields: [{ key: "SUPABASE_ACCESS_TOKEN", label: "Personal Access Token", input_type: "password" }],
      scope_fields: [
        {
          key: "SUPABASE_PROJECT_REF",
          label: "Project Reference (escopo)",
          required: false,
          input_type: "text",
          help: "Opcional: limita o acesso a um único projeto Supabase.",
        },
      ],
    },
    runtime_constraints: ["allowed_db_envs", "read_only_mode"],
    expected_tools: [
      { name: "list_tables", description: "Listar todas as tabelas do projeto", read_only_hint: true },
      { name: "get_table_schema", description: "Inspecionar schema de uma tabela", read_only_hint: true },
      { name: "execute_sql", description: "Executar queries SQL no banco", destructive_hint: true },
      { name: "list_functions", description: "Listar funções Postgres", read_only_hint: true },
      { name: "get_project_info", description: "Recuperar configuração do projeto", read_only_hint: true },
      { name: "apply_migration", description: "Aplicar migration no banco", destructive_hint: true },
      { name: "list_extensions", description: "Listar extensões instaladas", read_only_hint: true },
      { name: "list_migrations", description: "Listar migrations aplicadas", read_only_hint: true },
    ],
  },
  {
    server_key: "stripe",
    display_name: "Stripe",
    tagline: "Pagamentos, assinaturas e faturamento",
    description:
      "Gerencie clientes, cobranças, assinaturas e reembolsos no Stripe. Crie payment links, inspecione invoices e consulte a documentação da API.",
    transport_type: "stdio",
    command_template: ["npx", "-y", PINNED_STRIPE_MCP_PACKAGE],
    env_fields: [{ key: "STRIPE_SECRET_KEY", label: "Secret API Key", required: true }],
    category: "data",
    logo_key: "stripe",
    documentation_url: "https://docs.stripe.com/mcp",
    oauth_supported: true,
    remote_url: "https://mcp.stripe.com",
    connection_profile: {
      strategy: "oauth_preferred",
      oauth_provider: "stripe",
      oauth_scopes: ["read_write"],
      fields: [
        {
          key: "STRIPE_SECRET_KEY",
          label: "Secret API Key (fallback)",
          required: false,
          input_type: "password",
          help: "Use preferencialmente OAuth; a API Key fica apenas como fallback.",
        },
      ],
    },
    expected_tools: [
      { name: "create_customer", description: "Criar novo cliente" , destructive_hint: false },
      { name: "list_customers", description: "Listar clientes", read_only_hint: true },
      { name: "create_invoice", description: "Criar fatura" , destructive_hint: false },
      { name: "finalize_invoice", description: "Finalizar fatura para pagamento", destructive_hint: true },
      { name: "create_payment_link", description: "Gerar link de pagamento" , destructive_hint: false },
      { name: "list_payment_intents", description: "Listar intenções de pagamento", read_only_hint: true },
      { name: "list_subscriptions", description: "Listar assinaturas", read_only_hint: true },
      { name: "cancel_subscription", description: "Cancelar assinatura", destructive_hint: true },
      { name: "create_refund", description: "Processar reembolso", destructive_hint: true },
      { name: "search_stripe_documentation", description: "Buscar na documentação Stripe", read_only_hint: true },
    ],
  },
  {
    server_key: "excalidraw",
    display_name: "Excalidraw",
    tagline: "Diagramas e whiteboarding colaborativo",
    description:
      "Crie e edite diagramas, fluxogramas e wireframes no Excalidraw. Exporte como imagem e gerencie cenas.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "excalidraw-mcp"],
    env_fields: [],
    category: "productivity",
    logo_key: "excalidraw",
    documentation_url: "https://github.com/excalidraw/excalidraw-mcp",
    connection_profile: { strategy: "none" },
    expected_tools: [
      { name: "create_diagram", description: "Criar novo diagrama" , destructive_hint: false },
      { name: "export_to_image", description: "Exportar diagrama como PNG/SVG", read_only_hint: true },
      { name: "export_scene", description: "Exportar cena completa", read_only_hint: true },
      { name: "import_scene", description: "Importar cena de arquivo" , destructive_hint: false },
      { name: "describe_scene", description: "Descrever elementos do diagrama", read_only_hint: true },
      { name: "clear_canvas", description: "Limpar canvas", destructive_hint: true },
      { name: "snapshot_scene", description: "Criar snapshot do diagrama", read_only_hint: true },
      { name: "set_viewport", description: "Ajustar área de visualização" , destructive_hint: false },
    ],
  },
  {
    server_key: "vercel",
    display_name: "Vercel",
    tagline: "Deploy, logs e preview deployments",
    description:
      "Gerencie deployments, consulte logs de build e runtime, verifique domínios e monitore status dos projetos na Vercel.",
    transport_type: "http_sse",
    command_template: ["npx", "-y", PINNED_REMOTE_MCP_BRIDGE, "https://mcp.vercel.com"],
    env_fields: [{ key: "VERCEL_TOKEN", label: "Vercel API Token", required: true }],
    category: "development",
    logo_key: "vercel",
    documentation_url: "https://vercel.com/docs/mcp",
    remote_url: "https://mcp.vercel.com",
    connection_profile: {
      strategy: "api_key",
      fields: [{ key: "VERCEL_TOKEN", label: "Vercel API Token", input_type: "password" }],
    },
    expected_tools: [
      { name: "list_projects", description: "Listar projetos", read_only_hint: true },
      { name: "get_project", description: "Detalhes de um projeto", read_only_hint: true },
      { name: "list_deployments", description: "Listar deployments", read_only_hint: true },
      { name: "get_deployment", description: "Detalhes de um deployment", read_only_hint: true },
      { name: "get_deployment_build_logs", description: "Logs de build", read_only_hint: true },
      { name: "get_runtime_logs", description: "Logs de runtime", read_only_hint: true },
      { name: "deploy_to_vercel", description: "Criar novo deployment" , destructive_hint: false },
      { name: "check_domain_availability_and_price", description: "Verificar disponibilidade de domínio", read_only_hint: true },
    ],
  },
  {
    server_key: "granola",
    display_name: "Granola",
    tagline: "Meeting notes e transcrições",
    description:
      "Acesse notas de reuniões, transcrições e eventos de calendário capturados pelo Granola.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "granola-mcp-server"],
    env_fields: [],
    category: "productivity",
    logo_key: "granola",
    documentation_url: "https://github.com/btn0s/granola-mcp",
    connection_profile: {
      strategy: "local_app",
      local_app_name: "Granola",
      local_app_detection_hint:
        "Instale o app Granola e faça login. O MCP lê as credenciais de ~/Library/Application Support/Granola/supabase.json.",
    },
    expected_tools: [
      { name: "list_meetings", description: "Listar reuniões recentes", read_only_hint: true },
      { name: "get_meeting_transcript", description: "Obter transcrição de reunião", read_only_hint: true },
      { name: "query_granola_meetings", description: "Buscar reuniões por critérios", read_only_hint: true },
      { name: "list_meeting_folders", description: "Listar pastas de reuniões", read_only_hint: true },
      { name: "get_meetings", description: "Obter detalhes de reuniões", read_only_hint: true },
    ],
  },

  // --- Recomendadas (6) ---
  {
    server_key: "sentry",
    display_name: "Sentry",
    tagline: "Monitoramento de erros e stack traces",
    description:
      "Investigue erros em produção, analise stack traces, busque issues e monitore a saúde dos projetos com integração direta ao Sentry.",
    transport_type: "stdio",
    command_template: ["npx", "-y", PINNED_SENTRY_MCP_PACKAGE],
    env_fields: [
      { key: "SENTRY_ACCESS_TOKEN", label: "Auth Token", required: true },
      { key: "SENTRY_HOST", label: "Self-hosted URL (opcional)", required: false },
    ],
    category: "development",
    logo_key: "sentry",
    documentation_url: "https://docs.sentry.io/product/sentry-mcp/",
    connection_profile: {
      strategy: "api_key",
      fields: [{ key: "SENTRY_ACCESS_TOKEN", label: "Auth Token", input_type: "password" }],
      scope_fields: [
        {
          key: "SENTRY_HOST",
          label: "Host self-hosted (opcional)",
          required: false,
          input_type: "text",
          help: "Deixe em branco para usar sentry.io.",
        },
      ],
    },
    expected_tools: [
      { name: "get_issues", description: "Recuperar issues de erro", read_only_hint: true },
      { name: "get_issue_details", description: "Detalhes completos de uma issue", read_only_hint: true },
      { name: "search_issues", description: "Buscar issues com filtros", read_only_hint: true },
      { name: "list_projects", description: "Listar projetos monitorados", read_only_hint: true },
      { name: "get_project_info", description: "Configuração do projeto", read_only_hint: true },
      { name: "create_issue", description: "Criar nova issue" , destructive_hint: false },
      { name: "update_issue", description: "Atualizar status de issue" , destructive_hint: false },
    ],
  },
  {
    server_key: "linear",
    display_name: "Linear",
    tagline: "Gestão de projetos e issues",
    description:
      "Gerencie issues, projetos e ciclos no Linear. Crie tickets, atualize status, adicione comentários e acompanhe o progresso.",
    transport_type: "http_sse",
    command_template: ["npx", "-y", PINNED_REMOTE_MCP_BRIDGE, "https://mcp.linear.app/mcp"],
    env_fields: [{ key: "LINEAR_API_KEY", label: "Personal API Key (fallback)", required: false }],
    category: "productivity",
    logo_key: "linear",
    documentation_url: "https://linear.app/docs/mcp",
    oauth_supported: true,
    remote_url: "https://mcp.linear.app/mcp",
    connection_profile: {
      strategy: "oauth_preferred",
      oauth_provider: "linear",
      oauth_scopes: ["read", "write"],
      fields: [
        {
          key: "LINEAR_API_KEY",
          label: "Personal API Key (fallback)",
          required: false,
          input_type: "password",
        },
      ],
    },
    expected_tools: [
      { name: "get_ticket", description: "Recuperar detalhes de um ticket", read_only_hint: true },
      { name: "get_my_issues", description: "Issues atribuídas ao usuário atual", read_only_hint: true },
      { name: "search_issues", description: "Buscar issues", read_only_hint: true },
      { name: "create_issue", description: "Criar nova issue" , destructive_hint: false },
      { name: "update_issue", description: "Atualizar propriedades de issue" , destructive_hint: false },
      { name: "add_comment", description: "Adicionar comentário" , destructive_hint: false },
      { name: "get_teams", description: "Listar equipes", read_only_hint: true },
      { name: "list_projects", description: "Listar projetos", read_only_hint: true },
    ],
  },
  {
    server_key: "brave_search",
    display_name: "Brave Search",
    tagline: "Busca web com privacidade",
    description:
      "Realize buscas na web, notícias, imagens e vídeos usando a API do Brave Search com foco em privacidade.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "@brave/brave-search-mcp-server"],
    env_fields: [{ key: "BRAVE_API_KEY", label: "Brave Search API Key", required: true }],
    category: "data",
    logo_key: "brave",
    documentation_url: "https://brave.com/search/api/",
    connection_profile: {
      strategy: "api_key",
      fields: [{ key: "BRAVE_API_KEY", label: "Brave Search API Key", input_type: "password" }],
    },
    expected_tools: [
      { name: "brave_web_search", description: "Busca geral na web", read_only_hint: true },
      { name: "brave_local_search", description: "Busca de negócios locais", read_only_hint: true },
      { name: "brave_news_search", description: "Notícias recentes", read_only_hint: true },
      { name: "brave_image_search", description: "Busca de imagens", read_only_hint: true },
      { name: "brave_video_search", description: "Busca de vídeos", read_only_hint: true },
      { name: "brave_summarizer", description: "Resumo de resultados gerado por IA", read_only_hint: true },
    ],
  },
  {
    server_key: "slack",
    display_name: "Slack",
    tagline: "Mensagens, canais e threads",
    description:
      "Envie mensagens, leia histórico de canais, responda em threads e consulte perfis de usuários no Slack do seu workspace.",
    transport_type: "http_sse",
    command_template: ["npx", "-y", PINNED_REMOTE_MCP_BRIDGE, "https://mcp.slack.com/mcp"],
    env_fields: [
      { key: "SLACK_BOT_TOKEN", label: "Agent User OAuth Token (fallback legado)", required: false },
      { key: "SLACK_TEAM_ID", label: "Workspace ID (fallback)", required: false },
    ],
    category: "productivity",
    logo_key: "slack",
    documentation_url: "https://docs.slack.dev/ai/slack-mcp-server/",
    oauth_supported: true,
    remote_url: "https://mcp.slack.com/mcp",
    connection_profile: {
      strategy: "oauth_only",
      oauth_provider: "slack",
      oauth_scopes: ["channels:read", "chat:write", "users:read"],
      fields: [
        { key: "SLACK_BOT_TOKEN", label: "Bot Token (fallback legado)", required: false, input_type: "password" },
        { key: "SLACK_TEAM_ID", label: "Team ID (fallback)", required: false, input_type: "text" },
      ],
    },
    expected_tools: [
      { name: "slack_list_channels", description: "Listar canais disponíveis", read_only_hint: true },
      { name: "slack_post_message", description: "Enviar mensagem no canal" , destructive_hint: false },
      { name: "slack_reply_to_thread", description: "Responder em thread" , destructive_hint: false },
      { name: "slack_add_reaction", description: "Adicionar reação com emoji" , destructive_hint: false },
      { name: "slack_get_channel_history", description: "Histórico de mensagens", read_only_hint: true },
      { name: "slack_get_thread_replies", description: "Respostas de uma thread", read_only_hint: true },
      { name: "slack_get_users", description: "Listar usuários do workspace", read_only_hint: true },
      { name: "slack_get_user_profile", description: "Perfil de um usuário", read_only_hint: true },
    ],
  },
  {
    server_key: "notion",
    display_name: "Notion",
    tagline: "Páginas, data sources e knowledge base",
    description:
      "Busque, crie e edite páginas e data sources no Notion. Consulte conteúdo, adicione blocos e gerencie sua base de conhecimento.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "@notionhq/notion-mcp-server"],
    env_fields: [{ key: "NOTION_TOKEN", label: "Notion Integration Token", required: true }],
    category: "productivity",
    logo_key: "notion",
    documentation_url: "https://github.com/makenotion/notion-mcp-server",
    oauth_supported: true,
    connection_profile: {
      strategy: "oauth_preferred",
      oauth_provider: "notion",
      fields: [
        {
          key: "NOTION_TOKEN",
          label: "Notion Integration Token (fallback)",
          required: false,
          input_type: "password",
        },
      ],
    },
    expected_tools: [
      { name: "search_notion", description: "Busca full-text no workspace", read_only_hint: true },
      { name: "query_data_source", description: "Consultar data source (v2.0)", read_only_hint: true },
      { name: "get_page", description: "Recuperar conteúdo de página", read_only_hint: true },
      { name: "create_page", description: "Criar nova página" , destructive_hint: false },
      { name: "update_page", description: "Atualizar propriedades de página" , destructive_hint: false },
      { name: "append_block", description: "Adicionar conteúdo a página" , destructive_hint: false },
      { name: "get_data_source", description: "Schema de um data source", read_only_hint: true },
      { name: "list_pages", description: "Listar páginas do workspace", read_only_hint: true },
    ],
  },
  {
    server_key: "cloudflare",
    display_name: "Cloudflare",
    tagline: "DNS, Workers e segurança cloud",
    description:
      "Gerencie zonas DNS, deploy de Workers, configure regras de firewall e monitore a infraestrutura Cloudflare.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "@cloudflare/mcp-server-cloudflare"],
    env_fields: [{ key: "CLOUDFLARE_API_TOKEN", label: "Cloudflare API Token", required: true }],
    category: "cloud",
    logo_key: "cloudflare",
    documentation_url: "https://github.com/cloudflare/mcp-server-cloudflare",
    connection_profile: {
      strategy: "api_key",
      fields: [{ key: "CLOUDFLARE_API_TOKEN", label: "Cloudflare API Token", input_type: "password" }],
    },
    expected_tools: [
      { name: "list_zones", description: "Listar domínios/zonas", read_only_hint: true },
      { name: "get_zone_details", description: "Detalhes de configuração da zona", read_only_hint: true },
      { name: "list_dns_records", description: "Listar registros DNS", read_only_hint: true },
      { name: "create_dns_record", description: "Criar registro DNS" , destructive_hint: false },
      { name: "update_dns_record", description: "Atualizar registro DNS" , destructive_hint: false },
      { name: "delete_dns_record", description: "Remover registro DNS", destructive_hint: true },
      { name: "list_workers", description: "Listar Workers", read_only_hint: true },
      { name: "deploy_worker", description: "Deploy de Worker", destructive_hint: true },
    ],
  },

  // --- Alto impacto (4) ---
  {
    server_key: "google_maps",
    display_name: "Google Maps",
    tagline: "Geocoding, rotas e Places API",
    description:
      "Consulte a documentação do Google Maps Platform e gere código integrado com Maps, Places, Directions e Geocoding.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "@googlemaps/code-assist-mcp"],
    env_fields: [{ key: "GOOGLE_MAPS_API_KEY", label: "Google Maps API Key", required: true }],
    category: "cloud",
    logo_key: "google_maps",
    documentation_url: "https://developers.google.com/maps/ai/mcp",
    connection_profile: {
      strategy: "api_key",
      fields: [{ key: "GOOGLE_MAPS_API_KEY", label: "Google Maps API Key", input_type: "password" }],
    },
    expected_tools: [
      { name: "retrieve-google-maps-platform-docs", description: "Consultar documentação oficial", read_only_hint: true },
      { name: "retrieve-instructions", description: "Guia de instruções para o agente", read_only_hint: true },
    ],
  },
  {
    server_key: "todoist",
    display_name: "Todoist",
    tagline: "Gestão de tarefas e projetos pessoais",
    description:
      "Gerencie tarefas, projetos, seções e labels no Todoist. Crie, complete, reabra e organize tarefas.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "todoist-mcp-server"],
    env_fields: [{ key: "TODOIST_API_TOKEN", label: "Todoist API Token", required: true }],
    category: "productivity",
    logo_key: "todoist",
    documentation_url: "https://developer.todoist.com/",
    connection_profile: {
      strategy: "api_key",
      fields: [{ key: "TODOIST_API_TOKEN", label: "Todoist API Token", input_type: "password" }],
    },
    expected_tools: [
      { name: "listTasks", description: "Listar tarefas com filtros", read_only_hint: true },
      { name: "createTask", description: "Criar nova tarefa" , destructive_hint: false },
      { name: "updateTask", description: "Atualizar propriedades da tarefa" , destructive_hint: false },
      { name: "completeTask", description: "Marcar tarefa como concluída" , destructive_hint: false },
      { name: "reopenTask", description: "Reabrir tarefa concluída" , destructive_hint: false },
      { name: "deleteTask", description: "Remover tarefa permanentemente", destructive_hint: true },
      { name: "listProjects", description: "Listar projetos", read_only_hint: true },
      { name: "createProject", description: "Criar novo projeto" , destructive_hint: false },
      { name: "listSections", description: "Listar seções de um projeto", read_only_hint: true },
      { name: "createSection", description: "Criar seção em projeto" , destructive_hint: false },
      { name: "createLabel", description: "Criar nova label" , destructive_hint: false },
      { name: "addComment", description: "Adicionar comentário a tarefa" , destructive_hint: false },
    ],
  },
  {
    server_key: "obsidian",
    display_name: "Obsidian",
    tagline: "Second brain e knowledge management local",
    description:
      "Acesse, busque e edite notas do seu vault Obsidian. Leia frontmatter, liste tags e pesquise conteúdo.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "@mauricio.wolff/mcp-obsidian"],
    env_fields: [],
    category: "productivity",
    logo_key: "obsidian",
    documentation_url: "https://www.npmjs.com/package/@mauricio.wolff/mcp-obsidian",
    connection_profile: {
      strategy: "local_path",
      path_argument: {
        key: "VAULT_PATH",
        label: "Caminho do vault Obsidian",
        input_type: "text",
        help: "Ex.: ~/Documents/MeuVault (caminho absoluto ao seu vault)",
      },
    },
    runtime_constraints: ["allowed_paths"],
    expected_tools: [
      { name: "readFile", description: "Ler conteúdo de uma nota", read_only_hint: true },
      { name: "writeFile", description: "Criar ou atualizar nota" , destructive_hint: false },
      { name: "deleteFile", description: "Remover nota do vault", destructive_hint: true },
      { name: "listVault", description: "Navegar estrutura do vault", read_only_hint: true },
      { name: "searchVault", description: "Busca full-text no vault", read_only_hint: true },
      { name: "readFrontmatter", description: "Ler metadados YAML da nota", read_only_hint: true },
      { name: "listTags", description: "Listar todas as tags do vault", read_only_hint: true },
    ],
  },
  {
    server_key: "mongodb",
    display_name: "MongoDB",
    tagline: "Banco de dados NoSQL e Atlas cloud",
    description:
      "Execute queries, gerencie coleções e índices no MongoDB. Suporta MongoDB Atlas para provisionamento de clusters.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "mongodb-mcp-server"],
    env_fields: [
      { key: "MDB_MCP_CONNECTION_STRING", label: "MongoDB Connection URI", required: true },
      { key: "MDB_MCP_READ_ONLY", label: "Modo somente leitura (true/false)", required: false },
    ],
    category: "data",
    logo_key: "mongodb",
    documentation_url: "https://www.mongodb.com/docs/mcp-server/",
    connection_profile: {
      strategy: "connection_string",
      fields: [
        {
          key: "MDB_MCP_CONNECTION_STRING",
          label: "Connection URI",
          input_type: "password",
          help: "Formato: mongodb+srv://usuário:senha@host/banco",
        },
      ],
      read_only_toggle: {
        key: "MDB_MCP_READ_ONLY",
        label: "Modo somente leitura",
        required: false,
        input_type: "switch",
      },
    },
    runtime_constraints: ["allowed_db_envs", "read_only_mode"],
    expected_tools: [
      { name: "find", description: "Consultar documentos com filtros", read_only_hint: true },
      { name: "listCollections", description: "Listar coleções disponíveis", read_only_hint: true },
      { name: "insertOne", description: "Inserir documento" , destructive_hint: false },
      { name: "updateOne", description: "Atualizar documento" , destructive_hint: false },
      { name: "deleteOne", description: "Remover documento", destructive_hint: true },
      { name: "createIndex", description: "Criar índice" , destructive_hint: false },
      { name: "dropIndex", description: "Remover índice", destructive_hint: true },
      { name: "indexes", description: "Listar índices existentes", read_only_hint: true },
      { name: "atlas-list-clusters", description: "Listar clusters Atlas", read_only_hint: true },
      { name: "atlas-list-projects", description: "Listar projetos Atlas", read_only_hint: true },
      { name: "atlas-inspect-cluster", description: "Detalhes do cluster", read_only_hint: true },
      { name: "atlas-create-free-cluster", description: "Provisionar cluster gratuito", destructive_hint: true },
      { name: "atlas-list-db-users", description: "Listar usuários do banco", read_only_hint: true },
      { name: "atlas-create-db-user", description: "Criar usuário do banco", destructive_hint: true },
    ],
  },

  // --- Verticals (4) ---
  {
    server_key: "hubspot",
    display_name: "HubSpot",
    tagline: "CRM, contatos, deals e tickets",
    description:
      "Acesse e gerencie contatos, empresas, deals, tickets e faturas no HubSpot.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "@hubspot/mcp-server"],
    env_fields: [{ key: "PRIVATE_APP_ACCESS_TOKEN", label: "Private App Access Token", required: true }],
    category: "cloud",
    logo_key: "hubspot",
    documentation_url: "https://developers.hubspot.com/mcp",
    oauth_supported: true,
    connection_profile: {
      strategy: "oauth_preferred",
      oauth_provider: "hubspot",
      oauth_scopes: ["crm.objects.contacts.read", "crm.objects.contacts.write"],
      fields: [
        {
          key: "PRIVATE_APP_ACCESS_TOKEN",
          label: "Private App Access Token (fallback)",
          required: false,
          input_type: "password",
        },
      ],
    },
    expected_tools: [
      { name: "getContact", description: "Recuperar contato por ID", read_only_hint: true },
      { name: "searchContacts", description: "Buscar contatos", read_only_hint: true },
      { name: "createContact", description: "Criar novo contato" , destructive_hint: false },
      { name: "updateContact", description: "Atualizar contato" , destructive_hint: false },
      { name: "getCompany", description: "Recuperar empresa", read_only_hint: true },
      { name: "searchCompanies", description: "Buscar empresas", read_only_hint: true },
      { name: "getDeal", description: "Detalhes de um deal", read_only_hint: true },
      { name: "searchDeals", description: "Buscar deals", read_only_hint: true },
      { name: "getTicket", description: "Recuperar ticket de suporte", read_only_hint: true },
      { name: "searchTickets", description: "Buscar tickets", read_only_hint: true },
      { name: "getInvoice", description: "Detalhes de fatura", read_only_hint: true },
      { name: "getProduct", description: "Informações de produto", read_only_hint: true },
      { name: "getLineItem", description: "Detalhes de item", read_only_hint: true },
      { name: "getQuote", description: "Detalhes de cotação", read_only_hint: true },
      { name: "getOrder", description: "Detalhes de pedido", read_only_hint: true },
    ],
  },
  {
    server_key: "figma",
    display_name: "Figma",
    tagline: "Design-to-code e design tokens",
    description:
      "Acesse arquivos de design, inspecione componentes, extraia design tokens e exporte assets do Figma.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "figma-developer-mcp", "--stdio"],
    env_fields: [{ key: "FIGMA_API_KEY", label: "Figma Personal Access Token", required: true }],
    category: "development",
    logo_key: "figma",
    documentation_url: "https://developers.figma.com/docs/figma-mcp-server/",
    oauth_supported: true,
    connection_profile: {
      strategy: "oauth_preferred",
      oauth_provider: "figma",
      oauth_scopes: ["files:read"],
      fields: [
        {
          key: "FIGMA_API_KEY",
          label: "Personal Access Token (fallback)",
          required: false,
          input_type: "password",
        },
      ],
    },
    expected_tools: [
      { name: "getFileNodes", description: "Recuperar estrutura do arquivo de design", read_only_hint: true },
      { name: "getComponentInfo", description: "Detalhes e propriedades de componentes", read_only_hint: true },
      { name: "downloadImages", description: "Exportar assets de design", read_only_hint: true },
      { name: "getVariables", description: "Extrair design tokens", read_only_hint: true },
      { name: "getStyles", description: "Recuperar estilos do design system", read_only_hint: true },
      { name: "analyzeComponents", description: "Análise de componentes para code generation", read_only_hint: true },
      { name: "extractAssets", description: "Exportar todos os assets do arquivo", read_only_hint: true },
    ],
  },
  {
    server_key: "twilio",
    display_name: "Twilio",
    tagline: "SMS, voz e comunicação programática",
    description:
      "Envie SMS, faça chamadas de voz e gerencie recursos de comunicação do Twilio.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "@twilio-alpha/mcp"],
    env_fields: [
      { key: "TWILIO_ACCOUNT_SID", label: "Account SID", required: true },
      { key: "TWILIO_AUTH_TOKEN", label: "Auth Token", required: true },
    ],
    category: "cloud",
    logo_key: "twilio",
    documentation_url: "https://github.com/twilio-labs/mcp",
    connection_profile: {
      strategy: "dual_token",
      fields: [
        { key: "TWILIO_ACCOUNT_SID", label: "Account SID", input_type: "text" },
        { key: "TWILIO_AUTH_TOKEN", label: "Auth Token", input_type: "password" },
      ],
    },
    expected_tools: [
      { name: "sendSms", description: "Enviar mensagem SMS" , destructive_hint: false },
      { name: "makeCall", description: "Iniciar chamada de voz" , destructive_hint: false },
      { name: "listMessages", description: "Listar mensagens enviadas/recebidas", read_only_hint: true },
      { name: "getAccount", description: "Informações da conta Twilio", read_only_hint: true },
      { name: "listPhoneNumbers", description: "Listar números de telefone", read_only_hint: true },
      { name: "createMessagingService", description: "Criar serviço de messaging" , destructive_hint: false },
    ],
  },
  {
    server_key: "postgres_mcp",
    display_name: "PostgreSQL (MCP)",
    tagline: "Queries SQL e inspeção de schema via MCP",
    description:
      "Conecte a qualquer banco PostgreSQL externo para executar queries e inspecionar schema via protocolo MCP.",
    transport_type: "stdio",
    command_template: ["npx", "-y", "@henkey/postgres-mcp-server"],
    env_fields: [{ key: "DATABASE_URL", label: "PostgreSQL Connection String", required: true }],
    category: "data",
    logo_key: "postgresql",
    documentation_url: "https://www.npmjs.com/package/@henkey/postgres-mcp-server",
    connection_profile: {
      strategy: "connection_string",
      fields: [
        {
          key: "DATABASE_URL",
          label: "PostgreSQL Connection String",
          input_type: "password",
          help: "Formato: postgresql://usuário:senha@host:5432/banco",
        },
      ],
      read_only_toggle: {
        key: "POSTGRES_MCP_READ_ONLY",
        label: "Modo somente leitura",
        required: false,
        input_type: "switch",
      },
    },
    runtime_constraints: ["allowed_db_envs", "read_only_mode"],
    expected_tools: [
      { name: "queryDatabase", description: "Executar queries SQL", read_only_hint: true },
      { name: "inspectSchema", description: "Inspecionar schema do banco", read_only_hint: true },
      { name: "listTables", description: "Listar todas as tabelas", read_only_hint: true },
      { name: "getTableInfo", description: "Detalhes de colunas e constraints", read_only_hint: true },
      { name: "list_schemas", description: "Listar schemas disponíveis", read_only_hint: true },
      { name: "list_objects", description: "Navegar tabelas, views, sequences", read_only_hint: true },
      { name: "get_object_details", description: "Detalhes de colunas e constraints", read_only_hint: true },
      { name: "execute_sql", description: "Executar SQL (respeitando modo read-only)", read_only_hint: true },
      { name: "explain_query", description: "Analisar plano de execução", read_only_hint: true },
      { name: "get_top_queries", description: "Identificar queries mais lentas", read_only_hint: true },
      { name: "analyze_workload_indexes", description: "Recomendar índices para a carga", read_only_hint: true },
      { name: "analyze_query_indexes", description: "Otimizar índices de uma query", read_only_hint: true },
      { name: "analyze_db_health", description: "Checar health do banco", read_only_hint: true },
    ],
  },
];

export function buildSuggestedMcpCatalogEntry(
  suggested: McpSuggestedServer,
): McpServerCatalogEntry {
  const metadata: Record<string, unknown> = {};
  if (suggested.connection_profile) {
    metadata.connection_profile = suggested.connection_profile;
  }
  if (suggested.runtime_constraints) {
    metadata.runtime_constraints = suggested.runtime_constraints;
  }
  if (suggested.remote_url) {
    metadata.remote_url = suggested.remote_url;
  }
  return {
    server_key: suggested.server_key,
    display_name: suggested.display_name,
    description: suggested.description,
    transport_type: suggested.transport_type,
    command_json: JSON.stringify(suggested.command_template),
    url: suggested.remote_url ?? null,
    env_schema_json: JSON.stringify(
      suggested.env_fields.map((field) => ({
        key: field.key,
        label: field.label,
        required: field.required,
        input_type: "password",
      })),
    ),
    documentation_url: suggested.documentation_url ?? null,
    logo_key: suggested.logo_key ?? null,
    category: suggested.category,
    enabled: true,
    metadata_json: JSON.stringify(metadata),
    connection_profile: suggested.connection_profile ?? null,
    runtime_constraints: suggested.runtime_constraints ?? undefined,
    created_at: "",
    updated_at: "",
  };
}
