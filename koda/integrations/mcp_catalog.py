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
            "Conecte ao Supabase para executar queries SQL, gerenciar tabelas, listar "
            "funções e inspecionar a configuração do projeto diretamente pela conversa."
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
                    help="Opcional: limita o acesso a um único projeto Supabase.",
                ),
            ),
        ),
        runtime_constraints=("allowed_db_envs", "read_only_mode"),
        tools=(
            _r("list_tables", "Listar todas as tabelas do projeto"),
            _r("get_table_schema", "Inspecionar schema de uma tabela"),
            _d("execute_sql", "Executar queries SQL no banco"),
            _r("list_functions", "Listar funções Postgres"),
            _r("get_project_info", "Recuperar configuração do projeto"),
            _d("apply_migration", "Aplicar migration no banco"),
            _r("list_extensions", "Listar extensões instaladas"),
            _r("list_migrations", "Listar migrations aplicadas"),
        ),
        tier="mandatory",
    ),
    McpServerSpec(
        server_key="stripe",
        display_name="Stripe",
        tagline="Pagamentos, assinaturas e faturamento",
        description=(
            "Gerencie clientes, cobranças, assinaturas e reembolsos no Stripe. Crie "
            "payment links, inspecione invoices e consulte a documentação da API."
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
            _w("create_payment_link", "Gerar link de pagamento"),
            _r("list_payment_intents", "Listar intenções de pagamento"),
            _r("list_subscriptions", "Listar assinaturas"),
            _d("cancel_subscription", "Cancelar assinatura"),
            _d("create_refund", "Processar reembolso"),
            _r("search_stripe_documentation", "Buscar na documentação Stripe"),
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
            _r("snapshot_scene", "Criar snapshot do diagrama"),
            _w("set_viewport", "Ajustar área de visualização"),
        ),
        tier="mandatory",
    ),
    McpServerSpec(
        server_key="vercel",
        display_name="Vercel",
        tagline="Deploy, logs e preview deployments",
        description=(
            "Gerencie deployments, consulte logs de build e runtime, verifique "
            "domínios e monitore status dos projetos na Vercel."
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
            _w("deploy_to_vercel", "Criar novo deployment"),
            _r("check_domain_availability_and_price", "Verificar disponibilidade de domínio"),
        ),
        tier="mandatory",
    ),
    McpServerSpec(
        server_key="granola",
        display_name="Granola",
        tagline="Meeting notes e transcrições",
        description=("Acesse notas de reuniões, transcrições e eventos de calendário capturados pelo Granola."),
        category="productivity",
        documentation_url="https://github.com/btn0s/granola-mcp",
        logo_key="granola",
        transport_type="stdio",
        command_template=("npx", "-y", "granola-mcp-server"),
        connection_profile=ConnectionProfile(
            strategy="local_app",
            local_app_name="Granola",
            local_app_detection_hint=(
                "Instale o app Granola e faça login. O MCP lê as credenciais de "
                "`~/Library/Application Support/Granola/supabase.json`."
            ),
        ),
        tools=(
            _r("list_meetings", "Listar reuniões recentes"),
            _r("get_meeting_transcript", "Obter transcrição de reunião"),
            _r("query_granola_meetings", "Buscar reuniões por critérios"),
            _r("list_meeting_folders", "Listar pastas de reuniões"),
            _r("get_meetings", "Obter detalhes de reuniões"),
        ),
        tier="mandatory",
    ),
    # ----------------------------------------------------------- Recommended
    McpServerSpec(
        server_key="sentry",
        display_name="Sentry",
        tagline="Monitoramento de erros e stack traces",
        description=(
            "Investigue erros em produção, analise stack traces, busque issues e "
            "monitore a saúde dos projetos com integração direta ao Sentry."
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
            _r("search_issues", "Buscar issues com filtros"),
            _r("list_projects", "Listar projetos monitorados"),
            _r("get_project_info", "Configuração do projeto"),
            _w("create_issue", "Criar nova issue"),
            _w("update_issue", "Atualizar status de issue"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="linear",
        display_name="Linear",
        tagline="Gestão de projetos e issues",
        description=(
            "Gerencie issues, projetos e ciclos no Linear. Crie tickets, atualize "
            "status, adicione comentários e acompanhe o progresso das equipes."
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
            _r("get_ticket", "Recuperar detalhes de um ticket"),
            _r("get_my_issues", "Issues atribuídas ao usuário atual"),
            _r("search_issues", "Buscar issues"),
            _w("create_issue", "Criar nova issue"),
            _w("update_issue", "Atualizar propriedades de issue"),
            _w("add_comment", "Adicionar comentário"),
            _r("get_teams", "Listar equipes"),
            _r("list_projects", "Listar projetos"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="brave_search",
        display_name="Brave Search",
        tagline="Busca web com privacidade",
        description=(
            "Realize buscas na web, notícias, imagens e vídeos usando a API do Brave Search com foco em privacidade."
        ),
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
            _r("brave_web_search", "Busca geral na web"),
            _r("brave_local_search", "Busca de negócios locais"),
            _r("brave_news_search", "Notícias recentes"),
            _r("brave_image_search", "Busca de imagens"),
            _r("brave_video_search", "Busca de vídeos"),
            _r("brave_summarizer", "Resumo de resultados gerado por IA"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="slack",
        display_name="Slack",
        tagline="Mensagens, canais e threads",
        description=(
            "Envie mensagens, leia histórico de canais, responda em threads e consulte "
            "perfis de usuários no Slack do seu workspace."
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
            _r("slack_list_channels", "Listar canais disponíveis"),
            _w("slack_post_message", "Enviar mensagem no canal"),
            _w("slack_reply_to_thread", "Responder em thread"),
            _w("slack_add_reaction", "Adicionar reação com emoji"),
            _r("slack_get_channel_history", "Histórico de mensagens"),
            _r("slack_get_thread_replies", "Respostas de uma thread"),
            _r("slack_get_users", "Listar usuários do workspace"),
            _r("slack_get_user_profile", "Perfil de um usuário"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="notion",
        display_name="Notion",
        tagline="Páginas, data sources e knowledge base",
        description=(
            "Busque, crie e edite páginas e data sources no Notion. Consulte conteúdo, "
            "adicione blocos e gerencie sua base de conhecimento."
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
            _r("query_data_source", "Consultar data source (v2)"),
            _r("get_page", "Recuperar conteúdo de página"),
            _w("create_page", "Criar nova página"),
            _w("update_page", "Atualizar propriedades de página"),
            _w("append_block", "Adicionar conteúdo a página"),
            _r("get_data_source", "Schema de um data source"),
            _r("list_pages", "Listar páginas do workspace"),
        ),
        tier="recommended",
    ),
    McpServerSpec(
        server_key="cloudflare",
        display_name="Cloudflare",
        tagline="DNS, Workers e segurança cloud",
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
            _r("list_zones", "Listar domínios/zonas"),
            _r("get_zone_details", "Detalhes de configuração da zona"),
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
            "Consulte a documentação do Google Maps Platform e gere código integrado "
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
            _r("retrieve-google-maps-platform-docs", "Consultar documentação oficial"),
            _r("retrieve-instructions", "Guia de instruções para o agente"),
        ),
        tier="high_impact",
    ),
    McpServerSpec(
        server_key="todoist",
        display_name="Todoist",
        tagline="Tarefas e projetos pessoais",
        description=(
            "Gerencie tarefas, projetos, seções e labels no Todoist. Crie, complete, reabra e organize tarefas."
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
            _w("updateTask", "Atualizar propriedades da tarefa"),
            _w("completeTask", "Marcar tarefa como concluída"),
            _w("reopenTask", "Reabrir tarefa concluída"),
            _d("deleteTask", "Remover tarefa permanentemente"),
            _r("listProjects", "Listar projetos"),
            _w("createProject", "Criar novo projeto"),
            _r("listSections", "Listar seções de um projeto"),
            _w("createSection", "Criar seção em projeto"),
            _w("createLabel", "Criar nova label"),
            _w("addComment", "Adicionar comentário a tarefa"),
        ),
        tier="high_impact",
    ),
    McpServerSpec(
        server_key="obsidian",
        display_name="Obsidian",
        tagline="Second brain e knowledge management local",
        description=(
            "Acesse, busque e edite notas do seu vault Obsidian. Leia frontmatter, "
            "liste tags e pesquise conteúdo em toda a base."
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
            _r("readFile", "Ler conteúdo de uma nota"),
            _w("writeFile", "Criar ou atualizar nota"),
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
            "Execute queries, gerencie coleções e índices no MongoDB. Suporta MongoDB "
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
                    help="Formato: mongodb+srv://usuário:senha@host/banco",
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
            _r("find", "Consultar documentos com filtros"),
            _r("listCollections", "Listar coleções disponíveis"),
            _w("insertOne", "Inserir documento"),
            _w("updateOne", "Atualizar documento"),
            _d("deleteOne", "Remover documento"),
            _w("createIndex", "Criar índice"),
            _d("dropIndex", "Remover índice"),
            _r("indexes", "Listar índices existentes"),
            _r("atlas-list-clusters", "Listar clusters Atlas"),
            _r("atlas-list-projects", "Listar projetos Atlas"),
            _r("atlas-inspect-cluster", "Detalhes do cluster"),
            _d("atlas-create-free-cluster", "Provisionar cluster gratuito"),
            _r("atlas-list-db-users", "Listar usuários do banco"),
            _w("atlas-create-db-user", "Criar usuário do banco"),
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
            _r("getInvoice", "Detalhes de fatura"),
            _r("getProduct", "Informações de produto"),
            _r("getLineItem", "Detalhes de item"),
            _r("getQuote", "Detalhes de cotação"),
            _r("getOrder", "Detalhes de pedido"),
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
            _r("getStyles", "Recuperar estilos do design system"),
            _r("analyzeComponents", "Análise de componentes para code generation"),
            _r("extractAssets", "Exportar todos os assets do arquivo"),
        ),
        tier="verticals",
    ),
    McpServerSpec(
        server_key="twilio",
        display_name="Twilio",
        tagline="SMS, voz e comunicação programática",
        description=(
            "Envie SMS, faça chamadas de voz e gerencie recursos de comunicação do "
            "Twilio incluindo messaging, chat e funções serverless."
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
            _r("listMessages", "Listar mensagens enviadas/recebidas"),
            _r("getAccount", "Informações da conta Twilio"),
            _r("listPhoneNumbers", "Listar números de telefone"),
            _w("createMessagingService", "Criar serviço de messaging"),
        ),
        tier="verticals",
    ),
    McpServerSpec(
        server_key="postgres_mcp",
        display_name="PostgreSQL (MCP)",
        tagline="Queries SQL e inspeção de schema",
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
                    help="Formato: postgresql://usuário:senha@host:5432/banco",
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
            _r("getTableInfo", "Detalhes de colunas e constraints"),
            _r("list_schemas", "Listar schemas disponíveis"),
            _r("list_objects", "Navegar tabelas, views, sequences"),
            _r("get_object_details", "Detalhes de colunas e constraints"),
            _r("execute_sql", "Executar SQL (respeitando modo read-only)"),
            _r("explain_query", "Analisar plano de execução"),
            _r("get_top_queries", "Identificar queries mais lentas"),
            _r("analyze_workload_indexes", "Recomendar índices para a carga"),
            _r("analyze_query_indexes", "Otimizar índices de uma query"),
            _r("analyze_db_health", "Checar health do banco"),
        ),
        tier="verticals",
    ),
)


MCP_CATALOG_BY_KEY: dict[str, McpServerSpec] = {spec.server_key: spec for spec in MCP_CATALOG}
