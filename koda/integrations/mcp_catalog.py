"""Canonical per-MCP-server catalog.

Each entry declares:

- Stdio command OR remote HTTP URL.
- ConnectionProfile — which sub-form the UI should render.
- Runtime constraints applicable to this server.
- Tool inventory with read/write/destructive classification.

This is the SSoT consumed by:

- `koda/services/mcp_bootstrap.py` (reads command + env for process launch)
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
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://mcp.supabase.com/mcp"),
        remote_url="https://mcp.supabase.com/mcp",
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="supabase",
            oauth_scopes=("read", "write"),
            fields=(
                ConnectionField(
                    key="SUPABASE_ACCESS_TOKEN",
                    label="Personal Access Token (fallback)",
                    required=False,
                    input_type="password",
                    help="Use preferencialmente OAuth; o PAT fica como fallback para CI.",
                ),
            ),
            scope_fields=(
                ConnectionField(
                    key="SUPABASE_PROJECT_REF",
                    label="Project Reference (escopo)",
                    required=False,
                    input_type="text",
                    help="Opcional: restringe acesso a um único projeto Supabase.",
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
            strategy="oauth_preferred",
            oauth_provider="vercel",
            oauth_scopes=("read", "write"),
            fields=(
                ConnectionField(
                    key="VERCEL_TOKEN",
                    label="Vercel API Token (fallback)",
                    required=False,
                    input_type="password",
                    help="Use preferencialmente OAuth; o token fica como fallback.",
                ),
            ),
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
            strategy="oauth_preferred",
            oauth_provider="sentry",
            oauth_scopes=("org:read", "project:read", "event:read"),
            fields=(
                ConnectionField(
                    key="SENTRY_ACCESS_TOKEN",
                    label="Auth Token (fallback)",
                    required=False,
                    input_type="password",
                    help="Use preferencialmente OAuth; o token fica como fallback.",
                ),
            ),
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
        documentation_url="https://developers.notion.com/guides/mcp/get-started-with-mcp",
        logo_key="notion",
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://mcp.notion.com/mcp"),
        remote_url="https://mcp.notion.com/mcp",
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="notion",
            fields=(
                ConnectionField(
                    key="NOTION_TOKEN",
                    label="Notion Integration Token (fallback)",
                    required=False,
                    input_type="password",
                    help="Use preferencialmente OAuth; o token fica como fallback.",
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
            strategy="oauth_preferred",
            oauth_provider="cloudflare",
            oauth_scopes=("zone:read", "dns:edit", "worker:edit"),
            fields=(
                ConnectionField(
                    key="CLOUDFLARE_API_TOKEN",
                    label="Cloudflare API Token (fallback)",
                    required=False,
                    input_type="password",
                    help="Use preferencialmente OAuth; o token fica como fallback.",
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
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://mcp.hubspot.com"),
        remote_url="https://mcp.hubspot.com",
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
                    help="Use preferencialmente OAuth; o private app token fica como fallback.",
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
                    help="Encontre no painel Twilio (formato AC...).",
                ),
                ConnectionField(
                    key="TWILIO_API_KEY",
                    label="API Key SID",
                    input_type="text",
                    help="Crie em Console → Account → API keys & tokens (formato SK...).",
                ),
                ConnectionField(
                    key="TWILIO_API_SECRET",
                    label="API Secret",
                    input_type="password",
                    help="Mostrado apenas uma vez ao criar a API Key.",
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
        display_name="PostgreSQL",
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
    McpServerSpec(
        server_key="atlassian",
        display_name="Atlassian",
        tagline="Jira issues, Confluence pages e Atlassian Cloud",
        description=(
            "Conecte ao Atlassian Cloud para gerenciar issues do Jira, páginas e spaces "
            "do Confluence. Suporta OAuth 2.1 via Rovo MCP server (mcp.atlassian.com) "
            "ou autenticação por email + API token quando o admin habilita."
        ),
        category="productivity",
        documentation_url="https://support.atlassian.com/atlassian-rovo-mcp-server/",
        logo_key="jira",
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://mcp.atlassian.com/v1/mcp"),
        remote_url="https://mcp.atlassian.com/v1/mcp",
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="atlassian",
            oauth_scopes=("read:jira-work", "write:jira-work", "read:confluence-content.all"),
            fields=(
                ConnectionField(
                    key="ATLASSIAN_SITE_URL",
                    label="Site URL (fallback)",
                    required=False,
                    input_type="text",
                    help="Ex.: https://yourorg.atlassian.net (apenas para autenticação por API token)",
                ),
                ConnectionField(
                    key="ATLASSIAN_USER_EMAIL",
                    label="Email da conta (fallback)",
                    required=False,
                    input_type="text",
                ),
                ConnectionField(
                    key="ATLASSIAN_API_TOKEN",
                    label="API Token (fallback)",
                    required=False,
                    input_type="password",
                    help=(
                        "Crie em id.atlassian.com/manage-profile/security/api-tokens. "
                        "Use preferencialmente OAuth — só preencha se o admin desabilitou o flow OAuth."
                    ),
                ),
            ),
        ),
        tools=(
            _r("get_issue", "Recuperar detalhes de um Jira issue"),
            _r("search_issues", "Buscar issues com JQL"),
            _w("create_issue", "Criar issue no Jira"),
            _w("update_issue", "Atualizar campos de issue"),
            _w("add_comment", "Adicionar comentário"),
            _r("get_page", "Recuperar página do Confluence"),
            _r("search_pages", "Buscar páginas do Confluence (CQL)"),
            _w("create_page", "Criar página no Confluence"),
            _w("update_page", "Atualizar página do Confluence"),
            _r("list_projects", "Listar projetos do Jira"),
            _r("list_spaces", "Listar spaces do Confluence"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="gitlab_mcp",
        display_name="GitLab",
        tagline="Repositórios, MRs, issues e CI/CD",
        description=(
            "Servidor MCP comunitário do GitLab: navega projetos, abre merge "
            "requests, lê issues e consulta pipelines. Auth via Personal "
            "Access Token (scope ``api`` ou ``read_api``)."
        ),
        category="development",
        documentation_url="https://github.com/zereight/gitlab-mcp",
        logo_key="gitlab",
        transport_type="stdio",
        command_template=("npx", "-y", "@zereight/mcp-gitlab"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="GITLAB_PERSONAL_ACCESS_TOKEN",
                    label="Personal Access Token",
                    input_type="password",
                    help="Crie em GitLab → User → Preferences → Access tokens com scope 'api' ou 'read_api'.",
                ),
                ConnectionField(
                    key="GITLAB_API_URL",
                    label="API URL (opcional)",
                    required=False,
                    input_type="text",
                    help="Padrão: https://gitlab.com/api/v4. Use sua URL self-hosted se aplicável.",
                ),
            ),
        ),
        tools=(
            _r("list_projects", "Listar projetos"),
            _r("get_project", "Detalhes do projeto"),
            _r("list_issues", "Listar issues"),
            _w("create_issue", "Criar issue"),
            _r("list_merge_requests", "Listar merge requests"),
            _w("create_merge_request", "Abrir merge request"),
            _r("get_file_content", "Ler arquivo do repo"),
            _w("create_or_update_file", "Criar/editar arquivo"),
            _r("search_blobs", "Buscar código"),
            _r("list_pipelines", "Listar pipelines CI"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="bitbucket",
        display_name="Bitbucket",
        tagline="Repositórios, PRs e pipelines",
        description=(
            "Servidor MCP comunitário para Bitbucket Cloud e Server. Lista "
            "repositórios, gerencia pull requests, lê arquivos, executa builds. "
            "Cloud: Username + App Password. Server: HTTP access token."
        ),
        category="development",
        documentation_url="https://www.npmjs.com/package/@nexus2520/bitbucket-mcp-server",
        logo_key="bitbucket",
        transport_type="stdio",
        command_template=("npx", "-y", "@nexus2520/bitbucket-mcp-server"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="BITBUCKET_USERNAME",
                    label="Username (Cloud)",
                    required=False,
                    input_type="text",
                    help="Para Bitbucket Cloud: seu username Atlassian.",
                ),
                ConnectionField(
                    key="BITBUCKET_APP_PASSWORD",
                    label="App Password (Cloud)",
                    required=False,
                    input_type="password",
                    help=(
                        "Crie em id.atlassian.com/manage-profile/security/app-passwords "
                        "com escopos repository, pullrequest, pipeline."
                    ),
                ),
                ConnectionField(
                    key="BITBUCKET_TOKEN",
                    label="HTTP Access Token (Server)",
                    required=False,
                    input_type="password",
                    help="Para Bitbucket Server self-hosted, gere em User profile → Personal access tokens.",
                ),
                ConnectionField(
                    key="BITBUCKET_URL",
                    label="Base URL (Server)",
                    required=False,
                    input_type="text",
                    help="Apenas para Bitbucket Server (ex.: https://bitbucket.empresa.com).",
                ),
                ConnectionField(
                    key="BITBUCKET_DEFAULT_WORKSPACE",
                    label="Workspace padrão (Cloud)",
                    required=False,
                    input_type="text",
                    help="Opcional: limita o escopo a um único workspace.",
                ),
            ),
        ),
        tools=(
            _r("list_repositories", "Listar repositórios"),
            _r("get_repository", "Detalhes do repositório"),
            _r("list_pull_requests", "Listar pull requests"),
            _w("create_pull_request", "Abrir pull request"),
            _w("merge_pull_request", "Fazer merge de PR"),
            _r("get_pull_request", "Detalhes de PR"),
            _w("comment_pull_request", "Comentar em PR"),
            _r("get_file_content", "Ler arquivo do repo"),
            _r("list_branches", "Listar branches"),
            _r("list_pipelines", "Listar pipelines"),
            _r("get_pipeline", "Detalhes de pipeline"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="gmail",
        display_name="Gmail",
        tagline="Mensagens, threads, drafts e labels",
        description=(
            "Acesse e gerencie sua caixa do Gmail via OAuth do Google. Lista "
            "threads, lê mensagens, cria drafts, aplica/remove labels."
        ),
        category="productivity",
        documentation_url="https://developers.google.com/gmail/api",
        logo_key="gmail",
        transport_type="stdio",
        command_template=("npx", "-y", "@gongrzhe/server-gmail-autoauth-mcp"),
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="google",
            oauth_scopes=(
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.modify",
            ),
            fields=(
                ConnectionField(
                    key="GMAIL_OAUTH_CLIENT_ID",
                    label="OAuth Client ID (fallback)",
                    required=False,
                    input_type="password",
                ),
                ConnectionField(
                    key="GMAIL_OAUTH_CLIENT_SECRET",
                    label="OAuth Client Secret (fallback)",
                    required=False,
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _r("list_threads", "Listar threads"),
            _r("read_message", "Ler mensagem"),
            _r("search_messages", "Buscar mensagens (Gmail query)"),
            _w("send_message", "Enviar mensagem"),
            _w("create_draft", "Criar rascunho"),
            _w("modify_labels", "Aplicar/remover labels"),
            _d("delete_message", "Excluir mensagem"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="google_calendar",
        display_name="Google Calendar",
        tagline="Eventos, calendários e disponibilidade",
        description=(
            "Acesse Google Calendar via OAuth: lista calendários, cria/edita "
            "eventos, consulta disponibilidade (free/busy) e RSVPs."
        ),
        category="productivity",
        documentation_url="https://developers.google.com/calendar/api",
        logo_key="google_calendar",
        transport_type="stdio",
        command_template=("npx", "-y", "@cocal/google-calendar-mcp"),
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="google",
            oauth_scopes=(
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/calendar.events",
            ),
            fields=(
                ConnectionField(
                    key="GOOGLE_OAUTH_CLIENT_ID",
                    label="OAuth Client ID (fallback)",
                    required=False,
                    input_type="password",
                ),
                ConnectionField(
                    key="GOOGLE_OAUTH_CLIENT_SECRET",
                    label="OAuth Client Secret (fallback)",
                    required=False,
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _r("list_calendars", "Listar calendários"),
            _r("list_events", "Listar eventos"),
            _r("get_event", "Detalhes de evento"),
            _w("create_event", "Criar evento"),
            _w("update_event", "Atualizar evento"),
            _d("delete_event", "Excluir evento"),
            _r("freebusy", "Consultar disponibilidade"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="google_drive",
        display_name="Google Drive",
        tagline="Arquivos, pastas e busca no Drive",
        description=(
            "Navegue e gerencie arquivos no Google Drive via OAuth: listar, "
            "buscar, ler conteúdo, criar pastas e fazer upload de novos itens."
        ),
        category="productivity",
        documentation_url="https://developers.google.com/drive/api",
        logo_key="google_drive",
        transport_type="stdio",
        command_template=("npx", "-y", "@isaacphi/mcp-gdrive"),
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="google",
            oauth_scopes=(
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/drive.file",
            ),
            fields=(
                ConnectionField(
                    key="GDRIVE_OAUTH_CLIENT_ID",
                    label="OAuth Client ID (fallback)",
                    required=False,
                    input_type="password",
                ),
                ConnectionField(
                    key="GDRIVE_OAUTH_CLIENT_SECRET",
                    label="OAuth Client Secret (fallback)",
                    required=False,
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _r("list_files", "Listar arquivos"),
            _r("search_files", "Buscar arquivos (Drive query)"),
            _r("read_file", "Ler conteúdo do arquivo"),
            _w("create_folder", "Criar pasta"),
            _w("upload_file", "Upload de arquivo"),
            _w("update_file", "Atualizar arquivo"),
            _d("delete_file", "Excluir arquivo"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="github_mcp",
        display_name="GitHub",
        tagline="Repositórios, PRs, issues e Copilot via MCP oficial",
        description=(
            "Servidor MCP oficial do GitHub: lê e edita repos, abre PRs, gerencia issues e "
            "consulta Copilot/Actions. OAuth 2.1 via api.githubcopilot.com/mcp ou Personal "
            "Access Token classic/fine-grained."
        ),
        category="development",
        documentation_url="https://github.com/github/github-mcp-server",
        logo_key="github",
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://api.githubcopilot.com/mcp"),
        remote_url="https://api.githubcopilot.com/mcp",
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="github",
            oauth_scopes=("repo", "read:org", "read:user"),
            fields=(
                ConnectionField(
                    key="GITHUB_PERSONAL_ACCESS_TOKEN",
                    label="Personal Access Token (fallback)",
                    required=False,
                    input_type="password",
                    help=(
                        "Use preferencialmente OAuth. Para PAT, gere em github.com/settings/tokens "
                        "(classic ou fine-grained) com scopes 'repo', 'read:org' e 'read:user'."
                    ),
                ),
            ),
        ),
        tools=(
            _r("list_repos", "Listar repositórios"),
            _r("get_repo", "Detalhes de um repositório"),
            _r("list_issues", "Listar issues"),
            _w("create_issue", "Criar issue"),
            _w("comment_on_issue", "Comentar em issue"),
            _r("list_pull_requests", "Listar pull requests"),
            _w("create_pull_request", "Abrir pull request"),
            _r("get_file_contents", "Ler arquivo do repo"),
            _w("create_or_update_file", "Criar/editar arquivo"),
            _r("search_code", "Buscar código"),
            _r("list_workflow_runs", "Listar runs de Actions"),
            _r("get_workflow_run", "Detalhes de run"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="aws_knowledge",
        display_name="AWS Knowledge",
        tagline="Documentação AWS, blogs e best practices",
        description=(
            "Servidor MCP oficial da AWS com acesso público (sem credenciais) "
            "à documentação, blogs, What's New e guias de Well-Architected. "
            "Para acesso a recursos AWS reais, use AWS API MCP ou IAM."
        ),
        category="cloud",
        documentation_url="https://docs.aws.amazon.com/mcp/",
        logo_key="aws",
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://knowledge-mcp.global.api.aws"),
        remote_url="https://knowledge-mcp.global.api.aws",
        connection_profile=ConnectionProfile(strategy="none"),
        tools=(
            _r("search_documentation", "Buscar na documentação AWS"),
            _r("read_documentation", "Ler página de documentação"),
            _r("recommend", "Recomendar recursos AWS para um caso de uso"),
            _r("search_whats_new", "Buscar anúncios What's New"),
            _r("search_well_architected", "Buscar guias Well-Architected"),
            _r("search_blogs", "Buscar blogs AWS"),
        ),
        tier="recommended",
    ),
    # ------------------------------------------------------------ Wave 3 (10/2026)
    McpServerSpec(
        server_key="microsoft_365",
        display_name="Microsoft 365",
        tagline="Outlook, Teams, OneDrive via Microsoft Graph",
        description=(
            "Servidor MCP comunitário (Lokka) que conecta ao Microsoft Graph: "
            "Outlook (mail/calendar), Teams (channels/chat), OneDrive (files). "
            "Auth via OAuth 2.1 do Microsoft Identity Platform."
        ),
        category="productivity",
        documentation_url="https://github.com/merill/lokka",
        logo_key="microsoft_365",
        transport_type="stdio",
        command_template=("npx", "-y", "@merill/lokka@0.3.0"),
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="microsoft",
            oauth_scopes=(
                "Mail.ReadWrite",
                "Calendars.ReadWrite",
                "Files.ReadWrite",
                "Team.ReadBasic.All",
                "Chat.ReadWrite",
            ),
            fields=(
                ConnectionField(
                    key="TENANT_ID",
                    label="Tenant ID (fallback)",
                    required=False,
                    input_type="text",
                    help="Apenas para deployments com client credentials.",
                ),
                ConnectionField(
                    key="CLIENT_ID",
                    label="Client ID (fallback)",
                    required=False,
                    input_type="text",
                ),
                ConnectionField(
                    key="CLIENT_SECRET",
                    label="Client Secret (fallback)",
                    required=False,
                    input_type="password",
                ),
            ),
        ),
        tools=(
            _r("list_messages", "Listar emails (Outlook)"),
            _w("send_message", "Enviar email"),
            _r("get_message", "Detalhes de email"),
            _r("list_calendars", "Listar calendários"),
            _r("list_events", "Listar eventos"),
            _w("create_event", "Criar evento"),
            _w("update_event", "Atualizar evento"),
            _d("delete_event", "Excluir evento"),
            _r("list_files", "Listar arquivos (OneDrive)"),
            _r("read_file", "Ler conteúdo do arquivo"),
            _w("upload_file", "Upload de arquivo"),
            _r("list_teams_channels", "Listar canais Teams"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="firecrawl",
        display_name="Firecrawl",
        tagline="Web scraping e crawling para pesquisa",
        description=(
            "Servidor MCP oficial da Firecrawl: scrape de URLs únicas, crawl "
            "de sites inteiros, busca web e extração estruturada via LLM. "
            "Complementa Brave Search para fluxos de research."
        ),
        category="general",
        documentation_url="https://docs.firecrawl.dev/mcp",
        logo_key="firecrawl",
        transport_type="stdio",
        command_template=("npx", "-y", "firecrawl-mcp@3.14.1"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="FIRECRAWL_API_KEY",
                    label="API Key",
                    required=True,
                    input_type="password",
                    help="Crie em firecrawl.dev/app/api-keys.",
                ),
            ),
        ),
        runtime_constraints=("allowed_domains", "allow_private_network"),
        tools=(
            _r("scrape_url", "Scrape de uma URL"),
            _r("crawl_site", "Crawl recursivo de site"),
            _r("search", "Busca web com Firecrawl"),
            _r("extract", "Extração estruturada via LLM"),
            _r("map_site", "Mapear URLs de um site"),
            _r("batch_scrape", "Scrape de múltiplas URLs"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="posthog",
        display_name="PostHog",
        tagline="Product analytics, eventos e feature flags",
        description=(
            "Servidor MCP remoto oficial em mcp.posthog.com. Consulta eventos, "
            "funnels, dashboards, feature flags e personas. Complementa Sentry "
            "(que cobre erros) com analytics de produto."
        ),
        category="data",
        documentation_url="https://posthog.com/docs/model-context-protocol",
        logo_key="posthog",
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://mcp.posthog.com/mcp"),
        remote_url="https://mcp.posthog.com/mcp",
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="POSTHOG_API_KEY",
                    label="Personal API Key",
                    required=True,
                    input_type="password",
                    help="Crie em app.posthog.com/settings/user-api-keys.",
                ),
                ConnectionField(
                    key="POSTHOG_HOST",
                    label="Host (opcional, self-hosted)",
                    required=False,
                    input_type="text",
                    help="Padrão: https://app.posthog.com. Use sua URL self-hosted se aplicável.",
                ),
            ),
        ),
        tools=(
            _r("query_events", "Consultar eventos"),
            _r("query_funnel", "Consultar funnel"),
            _r("get_insight", "Detalhes de insight"),
            _r("list_dashboards", "Listar dashboards"),
            _r("get_feature_flag", "Detalhes de feature flag"),
            _w("update_feature_flag", "Atualizar feature flag"),
            _r("list_persons", "Listar personas/users"),
            _r("query_hogql", "Executar query HogQL"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="discord",
        display_name="Discord",
        tagline="Mensagens, canais, threads e moderação",
        description=(
            "Servidor MCP comunitário para Discord. Lê e envia mensagens, "
            "gerencia threads, lista membros, aplica reações. Auth via Bot Token."
        ),
        category="productivity",
        documentation_url="https://www.npmjs.com/package/discord-mcp",
        logo_key="discord",
        transport_type="stdio",
        command_template=("npx", "-y", "discord-mcp@2.4.0"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="DISCORD_BOT_TOKEN",
                    label="Bot Token",
                    required=True,
                    input_type="password",
                    help=(
                        "Crie em discord.com/developers/applications → New Application → "
                        "Bot → Reset Token. Necessita escopos messages, threads, members."
                    ),
                ),
            ),
        ),
        tools=(
            _r("list_guilds", "Listar servidores"),
            _r("list_channels", "Listar canais"),
            _r("read_messages", "Ler mensagens de canal"),
            _w("send_message", "Enviar mensagem"),
            _w("create_thread", "Criar thread"),
            _w("add_reaction", "Adicionar reação"),
            _r("list_members", "Listar membros"),
            _r("get_user", "Detalhes de usuário"),
            _d("delete_message", "Excluir mensagem"),
            _w("set_status", "Definir status do bot"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="grafana",
        display_name="Grafana",
        tagline="Dashboards, alertas e queries Prometheus/Loki",
        description=(
            "Servidor MCP oficial da Grafana Labs (Python via uvx). Lista e "
            "consulta dashboards, executa queries Prometheus/Loki, gerencia "
            "alertas. Auth via Service Account Token."
        ),
        category="cloud",
        documentation_url="https://github.com/grafana/mcp-grafana",
        logo_key="grafana",
        transport_type="stdio",
        command_template=("uvx", "mcp-grafana==0.13.1"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="GRAFANA_URL",
                    label="Grafana URL",
                    required=True,
                    input_type="text",
                    help="Ex.: https://yourorg.grafana.net ou https://grafana.empresa.com.",
                ),
                ConnectionField(
                    key="GRAFANA_API_KEY",
                    label="Service Account Token",
                    required=True,
                    input_type="password",
                    help="Crie em Administration → Service accounts → Add token.",
                ),
            ),
        ),
        tools=(
            _r("list_dashboards", "Listar dashboards"),
            _r("get_dashboard", "Detalhes de dashboard"),
            _r("query_prometheus", "Query PromQL"),
            _r("query_loki", "Query LogQL"),
            _r("list_datasources", "Listar datasources"),
            _r("list_alerts", "Listar alertas"),
            _w("silence_alert", "Silenciar alerta"),
            _r("get_panel_data", "Dados de painel"),
            _r("search_dashboards", "Buscar dashboards"),
            _r("list_folders", "Listar folders"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="canva",
        display_name="Canva",
        tagline="Designs, brand templates e exports",
        description=(
            "Servidor MCP remoto oficial em mcp.canva.com via OAuth. Lista e "
            "cria designs, aplica brand templates, exporta como PDF/PNG, faz "
            "upload de assets."
        ),
        category="productivity",
        documentation_url="https://www.canva.dev/docs/connect/mcp/",
        logo_key="canva",
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://mcp.canva.com/mcp"),
        remote_url="https://mcp.canva.com/mcp",
        connection_profile=ConnectionProfile(
            strategy="oauth_only",
            oauth_provider="canva",
            oauth_scopes=("design:read", "design:write", "asset:read", "asset:write"),
        ),
        tools=(
            _r("list_designs", "Listar designs"),
            _r("get_design", "Detalhes de design"),
            _w("create_design", "Criar design"),
            _r("export_design", "Exportar design (PDF/PNG)"),
            _r("list_brand_templates", "Listar brand templates"),
            _w("apply_brand_template", "Aplicar brand template"),
            _w("upload_asset", "Upload de asset"),
            _r("list_folders", "Listar folders"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="box",
        display_name="Box",
        tagline="Storage corporativo, files e sharing",
        description=(
            "Servidor MCP comunitário para Box Cloud. Lista, baixa e faz upload "
            "de arquivos, cria folders, compartilha links. Auth via OAuth 2.0 "
            "do Box (preferencial) ou Developer Token."
        ),
        category="productivity",
        documentation_url="https://www.npmjs.com/package/box-mcp-server",
        logo_key="box",
        transport_type="stdio",
        command_template=("npx", "-y", "box-mcp-server@0.3.1"),
        connection_profile=ConnectionProfile(
            strategy="oauth_preferred",
            oauth_provider="box",
            oauth_scopes=("root_readwrite",),
            fields=(
                ConnectionField(
                    key="BOX_DEVELOPER_TOKEN",
                    label="Developer Token (fallback)",
                    required=False,
                    input_type="password",
                    help="Use preferencialmente OAuth. Token disponível em developer.box.com.",
                ),
            ),
        ),
        tools=(
            _r("list_files", "Listar arquivos"),
            _r("get_file", "Detalhes de arquivo"),
            _r("download_file", "Baixar arquivo"),
            _w("upload_file", "Upload de arquivo"),
            _w("create_folder", "Criar folder"),
            _r("list_folders", "Listar folders"),
            _r("search", "Buscar arquivos"),
            _w("share_file", "Compartilhar arquivo"),
            _w("move_file", "Mover arquivo"),
            _d("delete_file", "Excluir arquivo"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="n8n",
        display_name="n8n",
        tagline="Workflow automation, executions e credentials",
        description=(
            "Servidor MCP comunitário para n8n (cloud ou self-hosted). Lista "
            "e executa workflows, consulta histórico de executions, gerencia "
            "metadata de credentials."
        ),
        category="general",
        documentation_url="https://www.npmjs.com/package/n8n-mcp",
        logo_key="n8n",
        transport_type="stdio",
        command_template=("npx", "-y", "n8n-mcp@2.50.0"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="N8N_API_KEY",
                    label="n8n API Key",
                    required=True,
                    input_type="password",
                    help="Crie em Settings → n8n API → Create API Key.",
                ),
                ConnectionField(
                    key="N8N_BASE_URL",
                    label="Base URL",
                    required=True,
                    input_type="text",
                    help="Padrão cloud: https://app.n8n.cloud. Use sua URL self-hosted se aplicável.",
                ),
            ),
        ),
        tools=(
            _r("list_workflows", "Listar workflows"),
            _r("get_workflow", "Detalhes de workflow"),
            _w("execute_workflow", "Executar workflow"),
            _w("activate_workflow", "Ativar workflow"),
            _w("deactivate_workflow", "Desativar workflow"),
            _r("list_executions", "Listar executions"),
            _r("get_execution", "Detalhes de execution"),
            _r("list_credentials", "Listar credentials (metadata)"),
            _w("create_workflow", "Criar workflow"),
            _w("update_workflow", "Atualizar workflow"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="aws_api",
        display_name="AWS API",
        tagline="Execução real de tools AWS (S3, EC2, Lambda, IAM)",
        description=(
            "Servidor MCP oficial AWS Labs (Python via uvx) para execução real "
            "de operações AWS via API. Cobre S3, EC2, Lambda, IAM, CloudWatch, "
            "DynamoDB. Complementa aws_knowledge (read-only docs) com execução "
            "real. Default: always_ask em todas as tools — operador pode habilitar "
            "read_only_mode no grant."
        ),
        category="cloud",
        documentation_url="https://github.com/awslabs/mcp/tree/main/src/aws-api-mcp-server",
        logo_key="aws",
        transport_type="stdio",
        command_template=("uvx", "awslabs.aws-api-mcp-server==1.3.33"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="AWS_ACCESS_KEY_ID",
                    label="Access Key ID",
                    required=True,
                    input_type="password",
                ),
                ConnectionField(
                    key="AWS_SECRET_ACCESS_KEY",
                    label="Secret Access Key",
                    required=True,
                    input_type="password",
                ),
                ConnectionField(
                    key="AWS_REGION",
                    label="Default Region",
                    required=True,
                    input_type="text",
                    help="Ex.: us-east-1, sa-east-1.",
                ),
                ConnectionField(
                    key="AWS_SESSION_TOKEN",
                    label="Session Token (credenciais temporárias)",
                    required=False,
                    input_type="password",
                ),
                ConnectionField(
                    key="AWS_PROFILE",
                    label="AWS Profile (~/.aws/credentials)",
                    required=False,
                    input_type="text",
                ),
            ),
        ),
        runtime_constraints=("read_only_mode", "allow_private_network"),
        tools=(
            _r("s3_list_buckets", "Listar buckets S3"),
            _r("s3_get_object", "Ler objeto S3"),
            _d("s3_put_object", "Upload de objeto S3"),
            _r("ec2_describe_instances", "Listar instâncias EC2"),
            _d("ec2_start_instances", "Iniciar instâncias EC2"),
            _d("ec2_stop_instances", "Parar instâncias EC2"),
            _r("lambda_list_functions", "Listar funções Lambda"),
            _w("lambda_invoke", "Invocar função Lambda"),
            _r("iam_list_users", "Listar usuários IAM"),
            _r("cloudwatch_get_metric_data", "Consultar métricas CloudWatch"),
            _r("dynamodb_query", "Query DynamoDB"),
            _d("dynamodb_put_item", "Inserir item DynamoDB"),
        ),
        tier="recommended",
    ),
    # ------------------------------------------------------------ Wave 4 (10/2026)
    McpServerSpec(
        server_key="postman",
        display_name="Postman",
        tagline="Workspaces, collections e mock servers",
        description=(
            "Servidor MCP para Postman API: gerenciar workspaces, collections, "
            "requests, environments, folders e mock servers. Auth via API Key."
        ),
        category="development",
        documentation_url="https://www.npmjs.com/package/postman-mcp-server",
        logo_key="postman",
        transport_type="stdio",
        command_template=("npx", "-y", "postman-mcp-server@1.2.0"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="POSTMAN_API_KEY",
                    label="API Key",
                    required=True,
                    input_type="password",
                    help="Crie em postman.com → Profile → Settings → API Keys.",
                ),
            ),
        ),
        tools=(
            _r("list_workspaces", "Listar workspaces"),
            _r("get_workspace", "Detalhes de workspace"),
            _r("list_collections", "Listar collections"),
            _r("get_collection", "Detalhes de collection"),
            _w("create_collection", "Criar collection"),
            _w("update_collection", "Atualizar collection"),
            _r("list_environments", "Listar environments"),
            _w("create_environment", "Criar environment"),
            _r("list_mocks", "Listar mock servers"),
            _w("create_mock", "Criar mock server"),
            _r("get_request", "Detalhes de request"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="zapier",
        display_name="Zapier",
        tagline="6.000+ apps via Zaps automatizados",
        description=(
            "Servidor MCP remoto oficial da Zapier. Execute Zaps e acesse as "
            "ações de qualquer app conectado na sua conta Zapier. URL única "
            "por usuário (com token embutido) — gere em mcp.zapier.com."
        ),
        category="general",
        documentation_url="https://zapier.com/mcp",
        logo_key="zapier",
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://mcp.zapier.com/api/mcp/sse"),
        remote_url="https://mcp.zapier.com/api/mcp/sse",
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="ZAPIER_MCP_URL",
                    label="MCP URL (with embedded token)",
                    required=True,
                    input_type="password",
                    help=(
                        "Gere a URL personalizada em mcp.zapier.com — formato: "
                        "https://mcp.zapier.com/api/mcp/<token>/sse"
                    ),
                ),
            ),
        ),
        tools=(
            _r("list_actions", "Listar ações disponíveis"),
            _w("execute_action", "Executar Zap/ação"),
            _r("search_apps", "Buscar apps conectados"),
            _r("get_action_schema", "Schema de uma ação"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="netlify",
        display_name="Netlify",
        tagline="Deploys, sites e edge functions",
        description=(
            "Servidor MCP oficial da Netlify. Gerencie sites, deploys, "
            "environment variables, edge functions, formulários e domínios."
        ),
        category="development",
        documentation_url="https://docs.netlify.com/welcome/build-with-ai/netlify-mcp-server/",
        logo_key="netlify",
        transport_type="stdio",
        command_template=("npx", "-y", "@netlify/mcp@1.15.1"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="NETLIFY_PERSONAL_ACCESS_TOKEN",
                    label="Personal Access Token",
                    required=True,
                    input_type="password",
                    help="Crie em app.netlify.com → User settings → Applications → Personal access tokens.",
                ),
            ),
        ),
        tools=(
            _r("list_sites", "Listar sites"),
            _r("get_site", "Detalhes de site"),
            _w("deploy_site", "Disparar deploy"),
            _r("list_deploys", "Listar deploys"),
            _r("get_deploy", "Detalhes de deploy"),
            _r("list_env_vars", "Listar variáveis de ambiente"),
            _w("set_env_var", "Definir variável de ambiente"),
            _d("delete_env_var", "Remover variável de ambiente"),
            _r("list_forms", "Listar formulários"),
            _r("list_functions", "Listar edge functions"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="huggingface",
        display_name="Hugging Face",
        tagline="Models, datasets, Spaces e inference",
        description=(
            "Servidor MCP remoto oficial em huggingface.co/mcp. Acesso a "
            "models, datasets, Spaces e inference API. Auth via Hugging Face "
            "User Access Token."
        ),
        category="data",
        documentation_url="https://huggingface.co/docs/hub/mcp",
        logo_key="huggingface",
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://huggingface.co/mcp"),
        remote_url="https://huggingface.co/mcp",
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="HF_TOKEN",
                    label="User Access Token",
                    required=True,
                    input_type="password",
                    help="Crie em huggingface.co/settings/tokens com escopo read.",
                ),
            ),
        ),
        tools=(
            _r("search_models", "Buscar models"),
            _r("get_model", "Detalhes de model"),
            _r("search_datasets", "Buscar datasets"),
            _r("get_dataset", "Detalhes de dataset"),
            _r("search_spaces", "Buscar Spaces"),
            _w("run_inference", "Executar inference"),
            _r("list_organizations", "Listar organizações"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="clickup",
        display_name="ClickUp",
        tagline="Tasks, lists, spaces e time tracking",
        description=(
            "Servidor MCP comunitário (oficial-aligned) para ClickUp. Tasks, "
            "lists, folders, spaces, comments, time tracking. Auth via API Key."
        ),
        category="productivity",
        documentation_url="https://www.npmjs.com/package/clickup-mcp-server",
        logo_key="clickup",
        transport_type="stdio",
        command_template=("npx", "-y", "clickup-mcp-server@1.12.0"),
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="CLICKUP_API_KEY",
                    label="API Key",
                    required=True,
                    input_type="password",
                    help="Crie em ClickUp → Settings → Apps → API Token.",
                ),
                ConnectionField(
                    key="CLICKUP_TEAM_ID",
                    label="Team ID",
                    required=True,
                    input_type="text",
                    help="Disponível na URL do workspace (ex.: app.clickup.com/<TEAM_ID>/...).",
                ),
            ),
        ),
        tools=(
            _r("list_spaces", "Listar spaces"),
            _r("list_folders", "Listar folders"),
            _r("list_lists", "Listar lists"),
            _r("list_tasks", "Listar tasks"),
            _r("get_task", "Detalhes de task"),
            _w("create_task", "Criar task"),
            _w("update_task", "Atualizar task"),
            _d("delete_task", "Excluir task"),
            _w("add_comment", "Adicionar comentário"),
            _r("list_members", "Listar membros do team"),
            _w("start_time_tracking", "Iniciar tracking de tempo"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="superhuman",
        display_name="Superhuman",
        tagline="Mail e calendário com agente de produtividade",
        description=(
            "Servidor MCP remoto oficial da Superhuman Mail. Pesquisa, "
            "responde, agenda e resume emails e eventos do calendário usando "
            "seu tom de voz. Auth via OAuth."
        ),
        category="productivity",
        documentation_url="https://help.superhuman.com/hc/en-us/articles/49810745762067-Superhuman-Mail-MCP-Server",
        logo_key="superhuman",
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://mcp.mail.superhuman.com/mcp"),
        remote_url="https://mcp.mail.superhuman.com/mcp",
        connection_profile=ConnectionProfile(
            strategy="oauth_only",
            oauth_provider="superhuman",
        ),
        tools=(
            _r("query_email_and_calendar", "Busca semântica em email/calendário"),
            _r("list_threads", "Listar threads com filtros estruturados"),
            _r("get_thread", "Detalhes de thread"),
            _r("get_message", "Detalhes de mensagem"),
            _r("get_attachment", "Baixar anexo"),
            _r("list_labels", "Listar labels"),
            _r("list_splits", "Listar Split Inboxes"),
            _r("get_read_statuses", "Status de leitura (quem abriu)"),
            _r("get_availability", "Buscar horários disponíveis"),
            _w("create_or_update_draft", "Criar/editar draft"),
            _d("discard_draft", "Descartar draft"),
            _w("send_draft", "Enviar email (Smart/Scheduled Send)"),
            _w("undo_send", "Desfazer envio"),
            _w("create_or_update_event", "Criar/atualizar evento"),
            _w("update_thread", "Label/Star/Trash/Read em threads"),
            _d("trash_thread", "Mover thread para Trash"),
            _w("unsubscribe", "Desinscrever de mailing list"),
            _w("update_personalization", "Atualizar tom/preferências"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="miro",
        display_name="Miro",
        tagline="Boards, diagramas e code↔board",
        description=(
            "Servidor MCP remoto oficial da Miro em mcp.miro.com. Cria e "
            "gerencia boards, gera diagramas a partir de código/texto e gera "
            "código a partir de conteúdo do board. OAuth 2.1 com DCR."
        ),
        category="productivity",
        documentation_url="https://developers.miro.com/docs/miro-mcp",
        logo_key="miro",
        transport_type="http_sse",
        command_template=("npx", "-y", _PINNED_REMOTE_BRIDGE, "https://mcp.miro.com/"),
        remote_url="https://mcp.miro.com/",
        connection_profile=ConnectionProfile(
            strategy="oauth_only",
            oauth_provider="miro",
            oauth_scopes=("boards:read", "boards:write"),
        ),
        tools=(
            _r("list_boards", "Listar boards"),
            _r("get_board", "Detalhes de board"),
            _w("create_board", "Criar board"),
            _r("list_items", "Listar itens de um board"),
            _w("create_item", "Criar item (sticky/shape/text)"),
            _w("update_item", "Atualizar item"),
            _d("delete_item", "Excluir item"),
            _w("generate_diagram", "Gerar diagrama a partir de código/texto"),
            _r("generate_code_from_board", "Gerar código a partir do board"),
        ),
        tier="recommended",
    ),
)


MCP_CATALOG_BY_KEY: dict[str, McpServerSpec] = {spec.server_key: spec for spec in MCP_CATALOG}
