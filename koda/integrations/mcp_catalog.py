"""Canonical per-MCP-server catalog.

Each entry declares:

- Stdio command OR remote HTTP URL.
- ConnectionProfile — which sub-form the UI should render.
- Runtime constraints applicable to this server.
- Tool inventory with read/write/destructive classification.

This is the SSoT consumed by:

- `koda/services/mcp_bootstrap.py` (reads command + env for process launch)
- `scripts/generate_integration_docs.py` (emits `docs/ai/integrations/mcp/*.md`)
- `cp_mcp_server_catalog` seed (upserted on boot)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from koda.agent_contract import ConnectionField, ConnectionProfile


@dataclass(frozen=True, slots=True)
class McpTool:
    """One tool the MCP server exposes."""

    name: str
    description: str
    classification: str  # "read" | "write" | "destructive"


@dataclass(frozen=True, slots=True)
class McpServerSpec:
    """One MCP server entry in the canonical catalog."""

    server_key: str
    display_name: str
    tagline: str
    description: str
    category: str  # "general" | "development" | "productivity" | "data" | "cloud"
    documentation_url: str
    logo_key: str
    transport_type: str  # "stdio" | "http_sse"
    command_template: tuple[str, ...] = ()
    remote_url: str | None = None
    connection_profile: ConnectionProfile = field(default_factory=lambda: ConnectionProfile(strategy="none"))
    runtime_constraints: tuple[str, ...] = ()
    tools: tuple[McpTool, ...] = ()
    tier: str = "recommended"  # "mandatory" | "recommended" | "high_impact" | "verticals"


_PINNED_SUPABASE = "@supabase/mcp-server-supabase@0.7.0"
_PINNED_STRIPE = "@stripe/mcp@0.3.3"
_PINNED_SENTRY = "@sentry/mcp-server@0.31.0"
_PINNED_REMOTE_BRIDGE = "mcp-remote@0.1.38"


def _r(name: str, desc: str) -> McpTool:
    return McpTool(name=name, description=desc, classification="read")


def _w(name: str, desc: str) -> McpTool:
    return McpTool(name=name, description=desc, classification="write")


def _d(name: str, desc: str) -> McpTool:
    return McpTool(name=name, description=desc, classification="destructive")


MCP_CATALOG: tuple[McpServerSpec, ...] = (
    # ------------------------------------------------------------- Mandatory
    McpServerSpec(
        server_key="supabase",
        display_name="Supabase",
        tagline="Backend completo com banco, auth e edge functions",
        description=(
            "Connect to Supabase to run SQL queries, manage tables, list functions, "
            "and inspect project configuration directly from the chat."
        ),
        category="cloud",
        documentation_url="https://supabase.com/docs/guides/getting-started/mcp",
        logo_key="supabase",
        transport_type="stdio",
        command_template=("npx", "-y", _PINNED_SUPABASE),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="SUPABASE_ACCESS_TOKEN",
                    label="Personal Access Token",
                    input_type="password",
                ),
            ),
            scope_fields=(
                ConnectionField(
                    key="SUPABASE_PROJECT_REF",
                    label="Project Reference (escopo)",
                    required=False,
                    input_type="text",
                    help="Optional: restricts access to a single Supabase project.",
                ),
            ),
        ),
        runtime_constraints=("allowed_db_envs", "read_only_mode"),
        tools=(
            _r("list_tables", "Listar todas as tabelas do projeto"),
            _r("get_table_schema", "Inspecionar schema de uma tabela"),
            _d("execute_sql", "Run SQL queries on the database"),
            _r("list_functions", "List Postgres functions"),
            _r("get_project_info", "Retrieve project configuration"),
            _d("apply_migration", "Apply a migration on the database"),
            _r("list_extensions", "List installed extensions"),
            _r("list_migrations", "List applied migrations"),
        ),
        tier="mandatory",
    ),
    McpServerSpec(
        server_key="stripe",
        display_name="Stripe",
        tagline="Pagamentos, assinaturas e faturamento",
        description=(
            "Manage customers, charges, subscriptions, and refunds on Stripe. Create "
            "payment links, inspect invoices, and query the API documentation."
        ),
        category="data",
        documentation_url="https://docs.stripe.com/mcp",
        logo_key="stripe",
        transport_type="stdio",
        command_template=("npx", "-y", _PINNED_STRIPE),
        remote_url="https://mcp.stripe.com",
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="stripe",
            oauth_scopes=("read_write",),
            fields=(
                ConnectionField(
                    key="STRIPE_SECRET_KEY",
                    label="Secret API Key (fallback)",
                    required=False,
                    input_type="password",
                    help="Use preferencialmente OAuth; a API Key fica apenas como fallback.",
                ),
            ),
        ),
        tools=(
            _w("create_customer", "Criar novo cliente"),
            _r("list_customers", "Listar clientes"),
            _w("create_invoice", "Criar fatura"),
            _d("finalize_invoice", "Finalizar fatura para pagamento"),
            _w("create_payment_link", "Create payment link"),
            _r("list_payment_intents", "List payment intents"),
            _r("list_subscriptions", "List subscriptions"),
            _d("cancel_subscription", "Cancelar assinatura"),
            _d("create_refund", "Process refund"),
            _r("search_stripe_documentation", "Search the Stripe documentation"),
        ),
        tier="mandatory",
    ),
    McpServerSpec(
        server_key="excalidraw",
        display_name="Excalidraw",
        tagline="Diagramas e whiteboarding colaborativo",
        description=(
            "Crie e edite diagramas, fluxogramas e wireframes no Excalidraw. "
            "Exporte como imagem, manipule elementos e gerencie cenas."
        ),
        category="productivity",
        documentation_url="https://github.com/excalidraw/excalidraw-mcp",
        logo_key="excalidraw",
        transport_type="stdio",
        command_template=("npx", "-y", "excalidraw-mcp"),
        connection_profile=ConnectionProfile(strategy="none"),
        tools=(
            _w("create_diagram", "Criar novo diagrama"),
            _r("export_to_image", "Exportar diagrama como PNG/SVG"),
            _r("export_scene", "Exportar cena completa"),
            _w("import_scene", "Importar cena de arquivo"),
            _r("describe_scene", "Descrever elementos do diagrama"),
            _d("clear_canvas", "Limpar canvas"),
            _r("snapshot_scene", "Create diagram snapshot"),
            _w("set_viewport", "Adjust viewport"),
        ),
        tier="mandatory",
    ),
    McpServerSpec(
        server_key="vercel",
        display_name="Vercel",
        tagline="Deploy, logs e preview deployments",
        description=(
            "Manage deployments, inspect build and runtime logs, check domains, and monitor project status on Vercel."
        ),
        category="development",
        documentation_url="https://vercel.com/docs/mcp",
        logo_key="vercel",
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://mcp.vercel.com"),
        remote_url="https://mcp.vercel.com",
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(ConnectionField(key="VERCEL_TOKEN", label="Vercel API Token", input_type="password"),),
        ),
        tools=(
            _r("list_projects", "Listar projetos"),
            _r("get_project", "Detalhes de um projeto"),
            _r("list_deployments", "Listar deployments"),
            _r("get_deployment", "Detalhes de um deployment"),
            _r("get_deployment_build_logs", "Logs de build"),
            _r("get_runtime_logs", "Logs de runtime"),
            _w("deploy_to_vercel", "Create new deployment"),
            _r("check_domain_availability_and_price", "Check domain availability"),
        ),
        tier="mandatory",
    ),
    McpServerSpec(
        server_key="granola",
        display_name="Granola",
        tagline="Meeting notes and transcripts",
        description=("Access meeting notes, transcripts, and calendar events captured by Granola."),
        category="productivity",
        documentation_url="https://github.com/btn0s/granola-mcp",
        logo_key="granola",
        transport_type="stdio",
        command_template=("npx", "-y", "granola-mcp-server"),
        connection_profile=ConnectionProfile(
            strategy="local_app",
            local_app_name="Granola",
            local_app_detection_hint=(
                "Install the Granola app and log in. The MCP reads credentials from "
                "`~/Library/Application Support/Granola/supabase.json`."
            ),
        ),
        tools=(
            _r("list_meetings", "List recent meetings"),
            _r("get_meeting_transcript", "Get meeting transcript"),
            _r("query_granola_meetings", "Search meetings by criteria"),
            _r("list_meeting_folders", "List meeting folders"),
            _r("get_meetings", "Get meeting details"),
        ),
        tier="mandatory",
    ),
    # ----------------------------------------------------------- Recommended
    McpServerSpec(
        server_key="sentry",
        display_name="Sentry",
        tagline="Monitoramento de erros e stack traces",
        description=(
            "Investigate production errors, analyze stack traces, search issues, and "
            "monitor project health with direct Sentry integration."
        ),
        category="development",
        documentation_url="https://docs.sentry.io/product/sentry-mcp/",
        logo_key="sentry",
        transport_type="stdio",
        command_template=("npx", "-y", _PINNED_SENTRY),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(ConnectionField(key="SENTRY_ACCESS_TOKEN", label="Auth Token", input_type="password"),),
            scope_fields=(
                ConnectionField(
                    key="SENTRY_HOST",
                    label="Host self-hosted (opcional)",
                    required=False,
                    input_type="text",
                    help="Deixe em branco para usar sentry.io.",
                ),
            ),
        ),
        tools=(
            _r("get_issues", "Recuperar issues de erro"),
            _r("get_issue_details", "Detalhes completos de uma issue"),
            _r("search_issues", "Search issues com filtros"),
            _r("list_projects", "List monitored projects"),
            _r("get_project_info", "Project configuration"),
            _w("create_issue", "Create new issue"),
            _w("update_issue", "Atualizar status de issue"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="linear",
        display_name="Linear",
        tagline="Project and issue management",
        description=(
            "Manage issues, projects, and cycles on Linear. Create tickets, update "
            "status, add comments, and track team progress."
        ),
        category="productivity",
        documentation_url="https://linear.app/docs/mcp",
        logo_key="linear",
        transport_type="http_sse",
        command_template=(
            "npx",
            "-y",
            _PINNED_REMOTE_BRIDGE,
            "https://mcp.linear.app/mcp",
        ),
        remote_url="https://mcp.linear.app/mcp",
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="linear",
            oauth_scopes=("read", "write"),
            fields=(
                ConnectionField(
                    key="LINEAR_API_KEY",
                    label="Personal API Key (fallback)",
                    required=False,
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _r("get_ticket", "Retrieve ticket details"),
            _r("get_my_issues", "Issues assigned to the current user"),
            _r("search_issues", "Search issues"),
            _w("create_issue", "Create new issue"),
            _w("update_issue", "Update issue properties"),
            _w("add_comment", "Add comment"),
            _r("get_teams", "List teams"),
            _r("list_projects", "Listar projetos"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="brave_search",
        display_name="Brave Search",
        tagline="Busca web com privacidade",
        description=("Search the web, news, images, and videos using the Brave Search API with a privacy-first focus."),
        category="data",
        documentation_url="https://brave.com/search/api/",
        logo_key="brave",
        transport_type="stdio",
        command_template=("npx", "-y", "@brave/brave-search-mcp-server"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(ConnectionField(key="BRAVE_API_KEY", label="Brave Search API Key", input_type="password"),),
        ),
        tools=(
            _r("brave_web_search", "General web search"),
            _r("brave_local_search", "Local business search"),
            _r("brave_news_search", "Recent news"),
            _r("brave_image_search", "Image search"),
            _r("brave_video_search", "Video search"),
            _r("brave_summarizer", "AI-generated results summary"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="slack",
        display_name="Slack",
        tagline="Mensagens, canais e threads",
        description=(
            "Send messages, read channel history, reply in threads, and look up user profiles in your Slack workspace."
        ),
        category="productivity",
        documentation_url="https://docs.slack.dev/ai/slack-mcp-server/",
        logo_key="slack",
        transport_type="http_sse",
        command_template=(
            "npx",
            "-y",
            _PINNED_REMOTE_BRIDGE,
            "https://mcp.slack.com/mcp",
        ),
        remote_url="https://mcp.slack.com/mcp",
        connection_profile=ConnectionProfile(
            strategy="oauth_only",
            oauth_provider="slack",
            oauth_scopes=("channels:read", "chat:write", "users:read"),
            fields=(
                ConnectionField(
                    key="SLACK_BOT_TOKEN",
                    label="Bot Token (fallback legado)",
                    required=False,
                    input_type="password",
                ),
                ConnectionField(
                    key="SLACK_TEAM_ID",
                    label="Team ID (fallback)",
                    required=False,
                    input_type="text",
                ),
            ),
        ),
        tools=(
            _r("slack_list_channels", "List available channels"),
            _w("slack_post_message", "Send message to channel"),
            _w("slack_reply_to_thread", "Reply in thread"),
            _w("slack_add_reaction", "Add emoji reaction"),
            _r("slack_get_channel_history", "Message history"),
            _r("slack_get_thread_replies", "Replies of a thread"),
            _r("slack_get_users", "List workspace users"),
            _r("slack_get_user_profile", "User profile"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="notion",
        display_name="Notion",
        tagline="Pages, data sources, and knowledge base",
        description=(
            "Search, create, and edit pages and data sources on Notion. Read content, "
            "add blocks, and manage your knowledge base."
        ),
        category="productivity",
        documentation_url="https://github.com/makenotion/notion-mcp-server",
        logo_key="notion",
        transport_type="stdio",
        command_template=("npx", "-y", "@notionhq/notion-mcp-server"),
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="notion",
            fields=(
                ConnectionField(
                    key="NOTION_TOKEN",
                    label="Notion Integration Token (fallback)",
                    required=False,
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _r("search_notion", "Busca full-text no workspace"),
            _r("query_data_source", "Query data source (v2)"),
            _r("get_page", "Retrieve page content"),
            _w("create_page", "Create new page"),
            _w("update_page", "Update page properties"),
            _w("append_block", "Append content to page"),
            _r("get_data_source", "Schema de um data source"),
            _r("list_pages", "List workspace pages"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="cloudflare",
        display_name="Cloudflare",
        tagline="DNS, Workers, and cloud security",
        description=(
            "Gerencie zonas DNS, deploy de Workers, configure regras de firewall e "
            "monitore a infraestrutura Cloudflare."
        ),
        category="cloud",
        documentation_url="https://github.com/cloudflare/mcp-server-cloudflare",
        logo_key="cloudflare",
        transport_type="stdio",
        command_template=("npx", "-y", "@cloudflare/mcp-server-cloudflare"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="CLOUDFLARE_API_TOKEN",
                    label="Cloudflare API Token",
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _r("list_zones", "List domains/zones"),
            _r("get_zone_details", "Zone configuration details"),
            _r("list_dns_records", "Listar registros DNS"),
            _w("create_dns_record", "Criar registro DNS"),
            _w("update_dns_record", "Atualizar registro DNS"),
            _d("delete_dns_record", "Remover registro DNS"),
            _r("list_workers", "Listar Workers"),
            _d("deploy_worker", "Deploy de Worker"),
        ),
        tier="recommended",
    ),
    # ----------------------------------------------------------- High impact
    McpServerSpec(
        server_key="google_maps",
        display_name="Google Maps",
        tagline="Geocoding, rotas e Places API",
        description=(
            "Consult Google Maps Platform documentation and generate integrated code "
            "com Maps, Places, Directions e Geocoding."
        ),
        category="cloud",
        documentation_url="https://developers.google.com/maps/ai/mcp",
        logo_key="google_maps",
        transport_type="stdio",
        command_template=("npx", "-y", "@googlemaps/code-assist-mcp"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="GOOGLE_MAPS_API_KEY",
                    label="Google Maps API Key",
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _r("retrieve-google-maps-platform-docs", "Consult official documentation"),
            _r("retrieve-instructions", "Instruction guide for the agent"),
        ),
        tier="high_impact",
    ),
    McpServerSpec(
        server_key="todoist",
        display_name="Todoist",
        tagline="Tarefas e projetos pessoais",
        description=(
            "Manage tasks, projects, sections, and labels on Todoist. Create, complete, reopen, and organize tasks."
        ),
        category="productivity",
        documentation_url="https://developer.todoist.com/",
        logo_key="todoist",
        transport_type="stdio",
        command_template=("npx", "-y", "todoist-mcp-server"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="TODOIST_API_TOKEN",
                    label="Todoist API Token",
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _r("listTasks", "Listar tarefas com filtros"),
            _w("createTask", "Criar nova tarefa"),
            _w("updateTask", "Update task properties"),
            _w("completeTask", "Mark task as completed"),
            _w("reopenTask", "Reopen completed task"),
            _d("deleteTask", "Remove task permanently"),
            _r("listProjects", "Listar projetos"),
            _w("createProject", "Create new project"),
            _r("listSections", "List sections of a project"),
            _w("createSection", "Create section in project"),
            _w("createLabel", "Create new label"),
            _w("addComment", "Add comment a tarefa"),
        ),
        tier="high_impact",
    ),
    McpServerSpec(
        server_key="obsidian",
        display_name="Obsidian",
        tagline="Second brain e knowledge management local",
        description=(
            "Access, search, and edit notes in your Obsidian vault. Read frontmatter, "
            "list tags, and search content across the vault."
        ),
        category="productivity",
        documentation_url="https://www.npmjs.com/package/@mauricio.wolff/mcp-obsidian",
        logo_key="obsidian",
        transport_type="stdio",
        command_template=("npx", "-y", "@mauricio.wolff/mcp-obsidian"),
        connection_profile=ConnectionProfile(
            strategy="local_path",
            path_argument=ConnectionField(
                key="VAULT_PATH",
                label="Caminho do vault Obsidian",
                input_type="text",
                help="Ex.: ~/Documents/MeuVault (caminho absoluto ao seu vault)",
            ),
        ),
        runtime_constraints=("allowed_paths",),
        tools=(
            _r("readFile", "Read note content"),
            _w("writeFile", "Create or update note"),
            _d("deleteFile", "Remover nota do vault"),
            _r("listVault", "Navegar estrutura do vault"),
            _r("searchVault", "Busca full-text no vault"),
            _r("readFrontmatter", "Ler metadados YAML da nota"),
            _r("listTags", "Listar todas as tags do vault"),
        ),
        tier="high_impact",
    ),
    McpServerSpec(
        server_key="mongodb",
        display_name="MongoDB",
        tagline="Banco de dados NoSQL e Atlas",
        description=(
            "Run queries, manage collections and indexes on MongoDB. Supports MongoDB "
            "Atlas para provisionamento de clusters."
        ),
        category="data",
        documentation_url="https://www.mongodb.com/docs/mcp-server/",
        logo_key="mongodb",
        transport_type="stdio",
        command_template=("npx", "-y", "mongodb-mcp-server"),
        connection_profile=ConnectionProfile(
            strategy="connection_string",
            fields=(
                ConnectionField(
                    key="MDB_MCP_CONNECTION_STRING",
                    label="Connection URI",
                    input_type="password",
                    help="Format: mongodb+srv://user:password@host/database",
                ),
            ),
            read_only_toggle=ConnectionField(
                key="MDB_MCP_READ_ONLY",
                label="Modo somente leitura",
                required=False,
                input_type="switch",
            ),
        ),
        runtime_constraints=("allowed_db_envs", "read_only_mode"),
        tools=(
            _r("find", "Query documents with filters"),
            _r("listCollections", "List available collections"),
            _w("insertOne", "Insert document"),
            _w("updateOne", "Atualizar documento"),
            _d("deleteOne", "Remove document"),
            _w("createIndex", "Create index"),
            _d("dropIndex", "Remove index"),
            _r("indexes", "List existing indexes"),
            _r("atlas-list-clusters", "List Atlas clusters"),
            _r("atlas-list-projects", "Listar projetos Atlas"),
            _r("atlas-inspect-cluster", "Detalhes do cluster"),
            _d("atlas-create-free-cluster", "Provision free cluster"),
            _r("atlas-list-db-users", "List database users"),
            _w("atlas-create-db-user", "Create database user"),
        ),
        tier="high_impact",
    ),
    # ------------------------------------------------------------ Verticals
    McpServerSpec(
        server_key="hubspot",
        display_name="HubSpot",
        tagline="CRM, contatos, deals e tickets",
        description=("Acesse e gerencie contatos, empresas, deals, tickets e faturas no HubSpot."),
        category="cloud",
        documentation_url="https://developers.hubspot.com/mcp",
        logo_key="hubspot",
        transport_type="stdio",
        command_template=("npx", "-y", "@hubspot/mcp-server"),
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="hubspot",
            oauth_scopes=(
                "crm.objects.contacts.read",
                "crm.objects.contacts.write",
            ),
            fields=(
                ConnectionField(
                    key="PRIVATE_APP_ACCESS_TOKEN",
                    label="Private App Access Token (fallback)",
                    required=False,
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _r("getContact", "Recuperar contato por ID"),
            _r("searchContacts", "Buscar contatos"),
            _w("createContact", "Criar novo contato"),
            _w("updateContact", "Atualizar contato"),
            _r("getCompany", "Recuperar empresa"),
            _r("searchCompanies", "Buscar empresas"),
            _r("getDeal", "Detalhes de um deal"),
            _r("searchDeals", "Buscar deals"),
            _r("getTicket", "Recuperar ticket de suporte"),
            _r("searchTickets", "Buscar tickets"),
            _r("getInvoice", "Invoice details"),
            _r("getProduct", "Product information"),
            _r("getLineItem", "Line item details"),
            _r("getQuote", "Quote details"),
            _r("getOrder", "Order details"),
        ),
        tier="verticals",
    ),
    McpServerSpec(
        server_key="figma",
        display_name="Figma",
        tagline="Design-to-code e design tokens",
        description=(
            "Acesse arquivos de design, inspecione componentes, extraia design tokens e exporte assets do Figma."
        ),
        category="development",
        documentation_url="https://developers.figma.com/docs/figma-mcp-server/",
        logo_key="figma",
        transport_type="stdio",
        command_template=("npx", "-y", "figma-developer-mcp", "--stdio"),
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="figma",
            oauth_scopes=("files:read",),
            fields=(
                ConnectionField(
                    key="FIGMA_API_KEY",
                    label="Personal Access Token (fallback)",
                    required=False,
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _r("getFileNodes", "Recuperar estrutura do arquivo de design"),
            _r("getComponentInfo", "Detalhes e propriedades de componentes"),
            _r("downloadImages", "Exportar assets de design"),
            _r("getVariables", "Extrair design tokens"),
            _r("getStyles", "Retrieve design system styles"),
            _r("analyzeComponents", "Component analysis for code generation"),
            _r("extractAssets", "Export all assets from the file"),
        ),
        tier="verticals",
    ),
    McpServerSpec(
        server_key="twilio",
        display_name="Twilio",
        tagline="SMS, voice, and programmable communication",
        description=(
            "Send SMS, make voice calls, and manage Twilio communication resources "
            "including messaging, chat, and serverless functions."
        ),
        category="cloud",
        documentation_url="https://github.com/twilio-labs/mcp",
        logo_key="twilio",
        transport_type="stdio",
        command_template=("npx", "-y", "@twilio-alpha/mcp"),
        connection_profile=ConnectionProfile(
            strategy="dual_token",
            fields=(
                ConnectionField(
                    key="TWILIO_ACCOUNT_SID",
                    label="Account SID",
                    input_type="text",
                ),
                ConnectionField(
                    key="TWILIO_AUTH_TOKEN",
                    label="Auth Token",
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _w("sendSms", "Enviar mensagem SMS"),
            _w("makeCall", "Iniciar chamada de voz"),
            _r("listMessages", "List sent/received messages"),
            _r("getAccount", "Twilio account information"),
            _r("listPhoneNumbers", "List phone numbers"),
            _w("createMessagingService", "Create messaging service"),
        ),
        tier="verticals",
    ),
    McpServerSpec(
        server_key="postgres_mcp",
        display_name="PostgreSQL (MCP)",
        tagline="SQL queries and schema inspection",
        description=(
            "Conecte a qualquer banco PostgreSQL externo para executar queries e inspecionar schema via protocolo MCP."
        ),
        category="data",
        documentation_url="https://www.npmjs.com/package/@henkey/postgres-mcp-server",
        logo_key="postgresql",
        transport_type="stdio",
        command_template=("npx", "-y", "@henkey/postgres-mcp-server"),
        connection_profile=ConnectionProfile(
            strategy="connection_string",
            fields=(
                ConnectionField(
                    key="DATABASE_URL",
                    label="PostgreSQL Connection String",
                    input_type="password",
                    help="Format: postgresql://user:password@host:5432/database",
                ),
            ),
            read_only_toggle=ConnectionField(
                key="POSTGRES_MCP_READ_ONLY",
                label="Modo somente leitura",
                required=False,
                input_type="switch",
            ),
        ),
        runtime_constraints=("allowed_db_envs", "read_only_mode"),
        tools=(
            _r("queryDatabase", "Executar queries SQL"),
            _r("inspectSchema", "Inspecionar schema do banco"),
            _r("listTables", "Listar todas as tabelas"),
            _r("getTableInfo", "Column and constraint details"),
            _r("list_schemas", "List available schemas"),
            _r("list_objects", "Browse tables, views, sequences"),
            _r("get_object_details", "Column and constraint details"),
            _r("execute_sql", "Execute SQL (respecting read-only mode)"),
            _r("explain_query", "Analyze execution plan"),
            _r("get_top_queries", "Identify slowest queries"),
            _r("analyze_workload_indexes", "Recommend indexes for the workload"),
            _r("analyze_query_indexes", "Optimize indexes for a query"),
            _r("analyze_db_health", "Check database health"),
        ),
        tier="verticals",
    ),
)


MCP_CATALOG_BY_KEY: dict[str, McpServerSpec] = {spec.server_key: spec for spec in MCP_CATALOG}
