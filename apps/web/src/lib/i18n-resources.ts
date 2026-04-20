import { generatedLiteralResources } from "@/lib/i18n-generated-literals";

export const resources = {
  "en-US": {
    translation: {
      app: {
        name: "Koda",
        description:
          "Koda is the operational workspace for monitoring agents, executions, costs, memory and routines in real time.",
        skipToContent: "Skip to main content",
      },
      language: {
        label: "Language",
        placeholder: "Language",
        options: {
          "en-US": "English (US)",
          "pt-BR": "Português (Brasil)",
          "es-ES": "Español",
          "fr-FR": "Français",
          "de-DE": "Deutsch",
        },
      },
      theme: {
        label: "Theme",
        placeholder: "Theme",
        options: {
          system: "System",
          light: "Light",
          dark: "Dark",
        },
      },
      common: {
        loading: "Loading",
        ready: "Ready",
        synced: "Synced",
        updating: "Updating",
        retry: "Try again",
        search: "Search",
        ask: "Ask",
        docs: "Docs",
        files: "Files",
        notifications: "Notifications",
        allAgents: "All bots",
        allModels: "All models",
        allTypes: "All types",
        allUsers: "All users",
        allSessions: "All sessions",
        now: "now",
        agent: "Bot",
        status: "Status",
        cost: "Cost",
        duration: "Duration",
        created: "Created",
        source: "Source",
        session: "Session",
        query: "Query",
        summary: "Summary",
        active: "Active",
        paused: "Paused",
        resolved: "Resolved",
        failed: "Failed",
      },
      routeMeta: {
        system: {
          eyebrow: "Koda",
          title: "System",
          summary: "Global governance, providers and shared resources.",
        },
        agents: {
          eyebrow: "Koda",
          title: "Agents",
          summary: "Catalog, editing and publishing for agents.",
        },
        runtime: {
          eyebrow: "Runtime",
          title: "Control plane",
          summary: "Bots, environments and live surfaces.",
        },
        overview: {
          eyebrow: "Workspace",
          title: "Overview",
          summary: "Pulse for bots, costs and activity.",
        },
        executions: {
          eyebrow: "Operations",
          title: "Executions",
          summary: "Tasks, traces and recent state.",
        },
        memory: {
          eyebrow: "Context",
          title: "Memory",
          summary: "Map, curation and context by bot.",
        },
        sessions: {
          eyebrow: "Conversations",
          title: "Sessions",
          summary: "Chats, responses and linked executions.",
        },
        costs: {
          eyebrow: "Consumption",
          title: "Costs",
          summary: "Consumption, distribution and efficiency.",
        },
        schedules: {
          eyebrow: "Routines",
          title: "Schedules",
          summary: "Routines, cadence and coverage.",
        },
        dlq: {
          eyebrow: "Recovery",
          title: "Dead letter queue",
          summary: "Failures, retries and diagnosis.",
        },
        fallback: {
          eyebrow: "Koda",
          title: "Workspace",
          summary: "Koda operational center.",
        },
      },
      sidebar: {
        ariaLabel: "Main navigation",
        newSession: "New session",
        newSessionLabel: "Start a new session",
        recents: "Recents",
        clearRecents: "Clear recents",
        noRecents: "Your recent routes will appear here.",
        sections: {
          atlas: "Koda",
          operations: "Operations",
          analysis: "Analysis",
          system: "System",
        },
        items: {
          home: "Home",
          runtime: "Runtime",
          agents: "Agents",
          executions: "Executions",
          sessions: "Sessions",
          costs: "Costs",
          memory: "Memory",
          schedules: "Schedules",
          dlq: "Dead letter queue",
          generalSettings: "General settings",
        },
        loading: {
          home: "Opening home",
          runtime: "Opening runtime",
          agents: "Opening agents",
          executions: "Opening executions",
          sessions: "Opening sessions",
          costs: "Opening costs",
          memory: "Opening memory",
          schedules: "Opening schedules",
          dlq: "Opening dead letter queue",
          generalSettings: "Opening general settings",
        },
      },
      topbar: {
        openMenu: "Open menu",
        expandSidebar: "Expand sidebar",
        collapseSidebar: "Collapse sidebar",
        docs: {
          eyebrow: "Docs",
          title: "Koda operational base",
          description: "Quick guides for navigating the workspace's critical surfaces.",
          entries: {
            dailyOps: {
              eyebrow: "Playbook",
              title: "Daily operations",
              description: "Executions, sessions and incidents in a single flow.",
            },
            governance: {
              eyebrow: "System",
              title: "Koda governance",
              description: "Global defaults, providers and shared grants.",
            },
            memory: {
              eyebrow: "Context",
              title: "Memory and curation",
              description: "Maps, clusters and operational signals by bot.",
            },
          },
        },
        ask: {
          eyebrow: "Ask",
          title: "Ask Koda",
          description: "Quick answer to take you straight to the right surface.",
          placeholder: "Ex.: where do I see ATLAS critical failures today?",
          responseLabel: "Response",
          button: "Ask",
          loadingButton: "Analyzing...",
          loadingCopy: "Koda is connecting operational context to answer with focus.",
          initialReply:
            "Ask about operations, costs, memory or governance and I will point you to the best Koda surface to start from.",
          suggestions: {
            failures: "How do I prioritize dead letter queue failures?",
            cost: "Which screen shows cost bottlenecks fastest?",
            schedules: "Where can I review paused routines?",
          },
          replies: {
            failures:
              "Start with Dead letter queue to isolate the source, validate retries and inspect the raw payload when you need to confirm root cause.",
            cost:
              "Open Costs to compare distribution by bot and cross-reference with Executions if you want to understand which flow drove consumption up.",
            schedules:
              "Schedules centralizes routine status. Use the bot filter to split what is active, paused or uncovered.",
            sessions:
              "Sessions became the ideal surface for direct interaction with a specific bot, with history and message sending in the same space.",
            fallback:
              "Use Executions for the operational pulse, Sessions for direct conversation, Memory for context and System when the decision involves defaults or governance.",
          },
        },
        files: {
          eyebrow: "Files",
          title: "Recent shortcuts",
          description: "Files and catalogs most used in the recent operational flow.",
          entries: {
            runtime: {
              detail: "Operations, traces and priority routines",
              updatedAt: "12 min ago",
            },
            governance: {
              detail: "Live catalog of defaults, policies and integrations",
              updatedAt: "36 min ago",
            },
            memory: {
              detail: "Recent signals and relevance adjustments",
              updatedAt: "2h ago",
            },
            costs: {
              detail: "Recent consumption distribution by bot",
              updatedAt: "4h ago",
            },
          },
        },
        notifications: {
          eyebrow: "Notifications",
          title: "Recent updates",
          description: "Recent Koda improvements and changes in a quick read.",
          summaryLeft: "{{count}} recent updates",
          summaryRight: "Everything in one place",
          entries: {
            sessions: {
              section: "Sessions",
              title: "New operational view for sessions",
              description:
                "The screen now opens in chat format, with direct bot selection and a fixed composer.",
              timestamp: "Today",
            },
            memory: {
              section: "Memory",
              title: "Memory refined",
              description: "Map redesigned and curation with better vertical usage.",
              timestamp: "Yesterday",
            },
            system: {
              section: "System",
              title: "Unified governance",
              description:
                "System and catalog now follow the same visual and modal foundation.",
              timestamp: "2 days ago",
            },
          },
        },
      },
      tour: {
        actions: {
          start: "Start tour",
          back: "Back",
          continue: "Continue",
          skip: "Skip tour",
          finish: "Finish tour",
        },
        progress: {
          start: "Getting started",
          value: "{{current}} of {{total}}",
        },
        confirmSkip: "Do you want to skip the guided tour?",
        topbar: {
          eyebrow: "Tour",
          title: "Guided tour",
          description: "Open a guided walkthrough for this workspace or for the page you are on.",
          resumeTitle: "Resume guided tour",
          resumeDescription: "Jump back into the current walkthrough from the point where you stopped.",
        },
        welcome: {
          title: "Start with a quick guided tour",
          description:
            "Koda will walk you through the main screens, how to move between them and what each area means. The flow stays objective and you can leave at any time.",
        },
        steps: {
          shellSidebar: {
            title: "This sidebar is your main map",
            description:
              "Use it to move between overview, runtime, catalog and operational views without losing context.",
          },
          shellTopbar: {
            title: "The topbar keeps route context close",
            description:
              "Here you see the active page summary, quick tools, language switcher and the shortcut to reopen this tour later.",
          },
          overviewMetrics: {
            title: "Overview summarizes the operational pulse",
            description:
              "This first block condenses activity, demand and cost so you can understand what changed before drilling down.",
            emptyTitle: "Overview starts as your empty operational pulse",
            emptyDescription:
              "Even before activity appears, this page is where you will return to get the fastest summary of the workspace state.",
          },
          overviewLivePlan: {
            title: "This section highlights the next live moves",
            description:
              "Use it to spot what is running now, what needs attention and where to continue the investigation.",
          },
          controlPlanePrimaryAction: {
            title: "The catalog is where setup starts",
            description:
              "Create bots and workspaces here, then open a bot to configure identity, behavior, resources and publication.",
            emptyTitle: "The catalog is your first stop on a fresh install",
            emptyDescription:
              "If the instance is empty, start here by creating a workspace or a bot. The editor opens right after that.",
          },
          controlPlaneBoard: {
            title: "The board explains how the catalog is organized",
            description:
              "Workspaces, squads and bots stay grouped here so governance and ownership are visible at a glance.",
            emptyTitle: "The board grows with the catalog",
            emptyDescription:
              "Once bots exist, this area becomes the visual map of teams, workspaces and operational ownership.",
          },
          controlPlaneEditorHeader: {
            title: "The editor is the bot control center",
            description:
              "This header shows which bot you are editing and keeps the main actions to save and review publication close.",
          },
          controlPlaneEditorSteps: {
            title: "These sections organize the full bot setup",
            description:
              "Move through identity, behavior, resources, memory, scope and publication without mixing concerns.",
          },
          controlPlaneEditorPublish: {
            title: "Save first, then publish with confidence",
            description:
              "Use these actions to persist draft changes and move toward the publication review when the bot is ready.",
          },
          runtimeHeader: {
            title: "Runtime is the live control room",
            description:
              "This screen concentrates execution health, live activity and filters to focus on the bots you care about now.",
            emptyTitle: "Runtime becomes useful as soon as activity appears",
            emptyDescription:
              "When there are no live environments yet, treat this page as the place that will surface live activity first.",
            unavailableTitle: "Runtime also signals availability problems quickly",
            unavailableDescription:
              "If runtime connectivity is degraded, this surface is where the app exposes that state before deeper inspection.",
          },
          runtimeLiveList: {
            title: "Metrics tell you how much attention runtime needs",
            description:
              "Use these indicators to estimate online coverage, live executions and the current attention load.",
            emptyTitle: "No live executions yet",
            emptyDescription:
              "When the list is empty, this still confirms that runtime is quiet instead of hiding the state.",
          },
          sessionsRail: {
            title: "Sessions is the conversational history rail",
            description:
              "Search and switch conversations here to inspect the dialogue history of each bot.",
            emptyTitle: "Sessions becomes the chat index",
            emptyDescription:
              "As soon as conversations exist, this rail becomes the fastest way to jump between them.",
          },
          sessionsThread: {
            title: "The thread keeps messages and context together",
            description:
              "This area shows the selected conversation, while the composer and context panel keep follow-up actions close.",
            emptyTitle: "You can start a conversation from here",
            emptyDescription:
              "When there is no thread yet, select a bot in the composer and start the first conversation from this surface.",
          },
          executionsFilters: {
            title: "Executions starts with fast filtering",
            description:
              "Use search, bot selection and status chips to narrow the history before opening a specific task.",
            unavailableTitle: "Executions also signals when the feed is unavailable",
            unavailableDescription:
              "If the list cannot be loaded, this area is where you retry and confirm the operational feed state.",
          },
          executionsTable: {
            title: "The table is the execution history backbone",
            description:
              "Open tasks from here to inspect duration, cost, warnings and detail surfaces.",
            emptyTitle: "No executions match yet",
            emptyDescription:
              "When nothing appears, filters may be too strict or the workspace may still be quiet.",
            unavailableTitle: "Execution history can still fail gracefully",
            unavailableDescription:
              "When the backend is unavailable, this area should explain the problem clearly instead of leaving the page blank.",
          },
          memoryPrimary: {
            title: "Memory maps long-lived context",
            description:
              "Use this area to inspect what the workspace is learning, clustering and keeping available to bots.",
          },
          costsPrimary: {
            title: "Costs explains consumption and efficiency",
            description:
              "This page helps compare spend, distribution and operational impact across bots and time windows.",
          },
          schedulesPrimary: {
            title: "Schedules centralizes routines",
            description:
              "Review cadence, paused jobs and automation coverage here when you need to inspect recurring work.",
          },
          dlqPrimary: {
            title: "Dead letter queue isolates failures",
            description:
              "Come here to inspect retries, raw failure state and recovery decisions when tasks fall out of the happy path.",
          },
          systemSettingsPrimary: {
            title: "System settings holds global governance",
            description:
              "This is where providers, defaults and shared controls are configured for the whole workspace.",
          },
        },
        complete: {
          title: "You are ready to explore Koda",
          description:
            "Reopen the tour anytime from Docs if you want a refresher or want to visit a secondary chapter.",
        },
      },
      agentSwitcher: {
        placeholder: "Select bot",
        ariaSingle: "Select bot",
        ariaMultiple: "Select bots",
        searchPlaceholder: "Search bot",
        allAgents: "All bots",
        agentsVisible: "{{count}} bots visible",
        agentsSelected: "{{count}} bots selected",
        agentsSelectedOutOfTotal: "{{selected}} of {{total}} bots selected",
        noAgentFilter: "No bot filter",
        selectOne: "Choose a bot",
        noResults: "No bots found",
      },
      async: {
        loading: "Loading",
        updating: "Updating",
        synced: "Synced",
        ready: "Ready",
        retry: "Try again",
      },
      statuses: {
        all: "All",
        completed: "Completed",
        running: "Running",
        queued: "Queued",
        failed: "Failed",
        retrying: "Retrying",
      },
      costs: {
        filters: {
          agents: "Bots",
          period: "Period",
          model: "Model",
          taskType: "Task type",
          periods: {
            "7d": "7 days",
            "30d": "30 days",
            "90d": "90 days",
          },
        },
        mode: {
          byAgent: "By bot",
          byModel: "By model",
        },
        kpis: {
          totalPeriod: "Total in period",
          today: "Today",
          costPerResolved: "Cost per resolved conversation",
          peakBucket: "Peak of period",
        },
        chart: {
          eyebrow: "Temporal origin",
          title: "Where cost is born in the period",
          description:
            "Stacked buckets to reveal peaks, dispersion and the dominant cost driver.",
        },
        allocation: {
          eyebrow: "Allocation",
          title: "Allocation of consumption",
          description: "A compact reading of where the cost is concentrated in the current cut.",
        },
        ledger: {
          eyebrow: "Cost ledger",
          title: "Operations by cost",
          count: "{{count}} records",
        },
      },
      executions: {
        searchPlaceholder: "Search query, session or model",
        unavailable: "Executions unavailable",
        loadError: "Could not load executions.",
        noSelection: "No execution selected.",
        retryLabel: "Retrying",
      },
      sessions: {
        searchPlaceholder: "Search by session, name or last message",
        noSelection: "No conversation selected.",
        loadError: "Could not load the conversation.",
        chatWithAgent: "Chat with {{bot}}",
        composerHelper:
          "The interface is ready for the bot conversation flow. Real sending depends on the runtime endpoint.",
        composerIdle:
          "Choose a conversation to explore history or prepare a new interaction.",
        sendUnavailable:
          "This bot runtime does not yet expose an HTTP endpoint for the Koda web chat.",
      },
      memory: {
        views: {
          map: "Memory",
          curation: "Curation",
        },
        filters: {
          title: "Filters",
          intro:
            "Adjust the cut by user, session, time and memory types before exploring map connections.",
          search: "Search in map",
          searchPlaceholder: "Content, source or learning...",
          user: "User",
          session: "Session",
          timeWindow: "Time window",
          includeInactive: "Include inactive memories",
          edges: {
            semantic: "Semantic",
            session: "Session",
            source: "Source",
          },
        },
        empty: {
          title: "There are no memories to display yet",
          description:
            "When this bot starts consolidating facts, decisions, tasks or problems, the map will organize those memories into a living mesh of context and learning.",
        },
      },
      schedules: {
        loading: "Loading",
        jobs: "schedules",
        active: "active",
      },
      dlq: {
        filters: {
          all: "All",
          eligible: "Retry eligible",
          ineligible: "No retry",
        },
      },
      controlPlane: {
        botCreate: {
          promptPlaceholder:
            "You are an assistant specialized in...\n\nYour goal is to help users with...\n\nRules:\n- Be clear and objective\n- Always respond in English",
        },
      },
      settings: {
        sections: {
          general: {
            label: "General",
            description: "Timezone and regional preferences.",
          },
          models: {
            label: "Models & Providers",
            description: "AI providers, model selection, and usage controls.",
          },
          integrations: {
            label: "Integrations",
            description: "External services and MCP servers like Jira, Google, databases, and curated tool bridges.",
          },
          providers: {
            label: "Providers",
            description: "AI providers for language models, voice, and media.",
          },
          mcp: {
            label: "MCP Servers",
            description: "Model Context Protocol servers for extending agent tools.",
          },
          intelligence: {
            label: "Intelligence",
            description: "Memory, knowledge, and autonomy governance.",
          },
          variables: {
            label: "Variables & Secrets",
            description: "System variables and secrets for agent operations.",
          },
        },
      },
      auth: {
        login: {
          title: "Welcome back",
          subtitle: "Sign in to access the operational workspace.",
          identifier: "Email or username",
          password: "Password",
          submit: "Sign in",
          submitting: "Signing in...",
          forgot_link: "Lost my password or recovery code?",
          generic_error: "Invalid credentials. Please try again.",
        },
        forgot: {
          title: "Recover access",
          subtitle: "Use a recovery code to define a new password.",
          identifier: "Email or username",
          recovery_code: "Recovery code",
          new_password: "New password",
          confirm_password: "Confirm new password",
          submit: "Reset password",
          submitting: "Resetting...",
          back_to_login: "Back to login",
          success_title: "Password updated",
          success: "You can now sign in with your new password.",
          password_too_short: "Password must be at least {{n}} characters long.",
          password_mismatch: "The passwords do not match.",
          generic_error: "The information provided is invalid or expired. Please try again.",
        },
        setup: {
          create_account: {
            title: "Create the owner account",
            subtitle: "Set up the first operator to unlock the workspace.",
            email: "Work email",
            password: "Password",
            password_hint: "Minimum 12 characters.",
            confirm_password: "Confirm password",
            bootstrap_code: "Bootstrap code",
            bootstrap_hint: "Use the one-time bootstrap code printed by the installer.",
            bootstrap_hint_generic: "Provide the bootstrap code issued for this instance.",
            submit: "Create account",
            submitting: "Creating...",
            errors: {
              bootstrap_required: "The bootstrap code is required.",
              email_invalid: "Enter a valid email address.",
              password_too_short: "Password must be at least {{n}} characters long.",
              password_mismatch: "The passwords do not match.",
              generic: "We could not create the account. Please try again.",
            },
          },
          recovery_codes: {
            title: "Save your recovery codes",
            subtitle: "Store these codes in a safe place. Each code works only once.",
            file_header: "Koda recovery codes",
            copy_all: "Copy all",
            copied: "Copied",
            download: "Download",
            print: "Print",
            saved_checkbox: "I saved the recovery codes in a safe place.",
            continue: "Continue to the workspace",
            already_shown_banner: "These codes will not be shown again.",
          },
        },
        settings: {
          security: {
            title: "Security",
            change_password: "Change password",
            need_current_password: "Enter your current password to continue.",
            regenerate_codes: "Regenerate recovery codes",
            codes_remaining: "{{count}} recovery codes remaining",
          },
        },
      },
    },
  },
  "pt-BR": {
    translation: {
      app: {
        name: "Koda",
        description:
          "Koda é o workspace operacional para monitorar agentes, execuções, custos, memória e rotinas em tempo real.",
        skipToContent: "Ir para o conteúdo principal",
      },
      language: {
        label: "Idioma",
        placeholder: "Idioma",
        options: {
          "en-US": "English (US)",
          "pt-BR": "Português (Brasil)",
          "es-ES": "Español",
          "fr-FR": "Français",
          "de-DE": "Deutsch",
        },
      },
      theme: {
        label: "Tema",
        placeholder: "Tema",
        options: {
          system: "Sistema",
          light: "Claro",
          dark: "Escuro",
        },
      },
      common: {
        loading: "Carregando",
        ready: "Pronto",
        synced: "Sincronizado",
        updating: "Atualizando",
        retry: "Tentar novamente",
        search: "Buscar",
        ask: "Perguntar",
        docs: "Documentação",
        files: "Arquivos",
        notifications: "Notificações",
        allAgents: "Todos os bots",
        allModels: "Todos os modelos",
        allTypes: "Todos os tipos",
        allUsers: "Todos os usuários",
        allSessions: "Todas as sessões",
        now: "agora",
        agent: "Bot",
        status: "Status",
        cost: "Custo",
        duration: "Duração",
        created: "Criada",
        source: "Origem",
        session: "Sessão",
        query: "Consulta",
        summary: "Resumo",
        active: "Ativo",
        paused: "Pausado",
        resolved: "Resolvida",
        failed: "Falhou",
      },
      routeMeta: {
        system: {
          eyebrow: "Koda",
          title: "Sistema",
          summary: "Governança global, providers e recursos compartilhados.",
        },
        agents: {
          eyebrow: "Koda",
          title: "Agentes",
          summary: "Catálogo, edição e publicação dos agentes.",
        },
        runtime: {
          eyebrow: "Runtime",
          title: "Plano de controle",
          summary: "Bots, ambientes e superfícies ao vivo.",
        },
        overview: {
          eyebrow: "Workspace",
          title: "Visão geral",
          summary: "Pulso dos bots, custos e atividade.",
        },
        executions: {
          eyebrow: "Operação",
          title: "Execuções",
          summary: "Tarefas, traces e estado recente.",
        },
        memory: {
          eyebrow: "Contexto",
          title: "Memória",
          summary: "Mapa, curadoria e contexto por bot.",
        },
        sessions: {
          eyebrow: "Conversas",
          title: "Sessões",
          summary: "Conversas, respostas e execuções ligadas.",
        },
        costs: {
          eyebrow: "Consumo",
          title: "Custos",
          summary: "Consumo, distribuição e eficiência.",
        },
        schedules: {
          eyebrow: "Rotinas",
          title: "Agendamentos",
          summary: "Rotinas, cadência e cobertura.",
        },
        dlq: {
          eyebrow: "Recuperação",
          title: "Fila morta",
          summary: "Falhas, retentativas e diagnóstico.",
        },
        fallback: {
          eyebrow: "Koda",
          title: "Workspace",
          summary: "Centro operacional do Koda.",
        },
      },
      sidebar: {
        ariaLabel: "Navegação principal",
        newSession: "Nova sessão",
        newSessionLabel: "Iniciar uma nova sessão",
        recents: "Recentes",
        clearRecents: "Limpar recentes",
        noRecents: "Suas rotas recentes aparecerão aqui.",
        sections: {
          atlas: "Koda",
          operations: "Operação",
          analysis: "Análise",
          system: "Sistema",
        },
        items: {
          home: "Início",
          runtime: "Runtime",
          agents: "Agentes",
          executions: "Execuções",
          sessions: "Sessões",
          costs: "Custos",
          memory: "Memória",
          schedules: "Agendamentos",
          dlq: "Fila morta",
          generalSettings: "Configurações gerais",
        },
        loading: {
          home: "Abrindo início",
          runtime: "Abrindo runtime",
          agents: "Abrindo agentes",
          executions: "Abrindo execuções",
          sessions: "Abrindo sessões",
          costs: "Abrindo custos",
          memory: "Abrindo memória",
          schedules: "Abrindo agendamentos",
          dlq: "Abrindo fila morta",
          generalSettings: "Abrindo configurações gerais",
        },
      },
      topbar: {
        openMenu: "Abrir menu",
        expandSidebar: "Expandir sidebar",
        collapseSidebar: "Colapsar sidebar",
        docs: {
          eyebrow: "Documentação",
          title: "Base operacional Koda",
          description: "Guias rápidos para navegar pelas superfícies críticas do workspace.",
          entries: {
            dailyOps: {
              eyebrow: "Playbook",
              title: "Operação diária",
              description: "Execuções, sessões e incidentes em um único fluxo.",
            },
            governance: {
              eyebrow: "Sistema",
              title: "Governança Koda",
              description: "Defaults globais, providers e grants compartilhados.",
            },
            memory: {
              eyebrow: "Contexto",
              title: "Memória e curadoria",
              description: "Mapas, clusters e sinais operacionais por bot.",
            },
          },
        },
        ask: {
          eyebrow: "Pergunte",
          title: "Pergunte ao Koda",
          description: "Resposta rápida para te levar direto à tela certa.",
          placeholder: "Ex.: onde eu vejo falhas críticas do ATLAS hoje?",
          responseLabel: "Resposta",
          button: "Perguntar",
          loadingButton: "Analisando...",
          loadingCopy: "O Koda está conectando o contexto operacional para responder com foco.",
          initialReply:
            "Pergunte sobre operação, custos, memória ou governança e eu aponto a melhor superfície do Koda para começar.",
          suggestions: {
            failures: "Como priorizar falhas da fila morta?",
            cost: "Qual tela mostra gargalos de custo mais rápido?",
            schedules: "Onde revisar rotinas pausadas?",
          },
          replies: {
            failures:
              "Comece por Fila morta para isolar a origem, validar retentativa e abrir o payload bruto quando precisar confirmar causa raiz.",
            cost:
              "Abra Custos para comparar distribuição por bot e cruze com Execuções se quiser entender qual fluxo puxou o consumo para cima.",
            schedules:
              "Agendamentos concentra o estado das rotinas. Use o filtro por bot para separar o que está ativo, pausado ou sem cobertura.",
            sessions:
              "Sessões virou a superfície ideal para interação direta com um bot específico, com histórico e envio de mensagens no mesmo espaço.",
            fallback:
              "Use Execuções para o pulso operacional, Sessões para conversa direta, Memória para contexto e Sistema quando a decisão envolver defaults ou governança.",
          },
        },
        files: {
          eyebrow: "Arquivos",
          title: "Atalhos recentes",
          description: "Arquivos e catálogos mais usados no fluxo operacional recente.",
          entries: {
            runtime: {
              detail: "Operação, traces e rotinas prioritárias",
              updatedAt: "há 12 min",
            },
            governance: {
              detail: "Catálogo vivo de defaults, políticas e integrações",
              updatedAt: "há 36 min",
            },
            memory: {
              detail: "Sinais recentes e ajustes de relevância",
              updatedAt: "há 2 h",
            },
            costs: {
              detail: "Distribuição recente de consumo por bot",
              updatedAt: "há 4 h",
            },
          },
        },
        notifications: {
          eyebrow: "Notificações",
          title: "Atualizações recentes",
          description: "Melhorias e mudanças recentes do Koda em uma leitura rápida.",
          summaryLeft: "{{count}} novidades recentes",
          summaryRight: "Tudo em um só lugar",
          entries: {
            sessions: {
              section: "Sessões",
              title: "Nova visão operacional para sessões",
              description:
                "A tela agora abre em formato de chat, com seleção direta do bot e composer fixo.",
              timestamp: "Hoje",
            },
            memory: {
              section: "Memória",
              title: "Memória refinada",
              description: "Mapa redesenhado e curadoria com melhor aproveitamento vertical.",
              timestamp: "Ontem",
            },
            system: {
              section: "Sistema",
              title: "Governança unificada",
              description: "Sistema e catálogo agora seguem a mesma base visual e de modais.",
              timestamp: "2 dias atrás",
            },
          },
        },
      },
      tour: {
        actions: {
          start: "Iniciar tour",
          back: "Voltar",
          continue: "Continuar",
          skip: "Pular tour",
          finish: "Finalizar tour",
        },
        progress: {
          start: "Primeiros passos",
          value: "{{current}} de {{total}}",
        },
        confirmSkip: "Deseja pular o tour guiado?",
        topbar: {
          eyebrow: "Tour",
          title: "Tour guiado",
          description: "Abra um passo a passo guiado deste workspace ou da tela em que voce esta.",
          resumeTitle: "Retomar tour guiado",
          resumeDescription: "Volte para o walkthrough atual do ponto em que voce parou.",
        },
        welcome: {
          title: "Comece com um tour rapido",
          description:
            "O Koda vai apresentar as telas principais, como navegar entre elas e o significado de cada area. O fluxo e objetivo e voce pode sair quando quiser.",
        },
        steps: {
          shellSidebar: {
            title: "Esta sidebar e o seu mapa principal",
            description:
              "Use-a para circular entre overview, runtime, catalogo e superficies operacionais sem perder contexto.",
          },
          shellTopbar: {
            title: "O topbar concentra o contexto da rota",
            description:
              "Aqui voce ve o resumo da tela ativa, ferramentas rapidas, seletor de idioma e o atalho para reabrir este tour depois.",
          },
          overviewMetrics: {
            title: "A overview resume o pulso operacional",
            description:
              "Este primeiro bloco condensa atividade, demanda e custo para voce entender o que mudou antes de aprofundar.",
            emptyTitle: "A overview ja nasce como seu pulso operacional",
            emptyDescription:
              "Mesmo antes de existir atividade, e aqui que voce volta para ler o resumo mais rapido do estado do workspace.",
          },
          overviewLivePlan: {
            title: "Esta secao destaca os proximos movimentos ao vivo",
            description:
              "Use-a para enxergar o que esta rodando agora, o que pede atencao e por onde seguir a investigacao.",
          },
          controlPlanePrimaryAction: {
            title: "O catalogo e onde a configuracao comeca",
            description:
              "Crie bots e workspaces aqui e depois abra um bot para configurar identidade, comportamento, recursos e publicacao.",
            emptyTitle: "O catalogo e o ponto de partida numa instalacao nova",
            emptyDescription:
              "Se a instancia estiver vazia, comece aqui criando um workspace ou um bot. O editor entra logo em seguida.",
          },
          controlPlaneBoard: {
            title: "O board explica como o catalogo esta organizado",
            description:
              "Workspaces, squads e bots ficam agrupados aqui para que governanca e ownership aparecam de imediato.",
            emptyTitle: "O board cresce junto com o catalogo",
            emptyDescription:
              "Quando os bots existirem, esta area vira o mapa visual de times, workspaces e ownership operacional.",
          },
          controlPlaneEditorHeader: {
            title: "O editor e o centro de controle do bot",
            description:
              "Este cabecalho mostra qual bot esta sendo editado e deixa salvar e revisar a publicacao sempre por perto.",
          },
          controlPlaneEditorSteps: {
            title: "Estas secoes organizam o setup completo do bot",
            description:
              "Passe por identidade, comportamento, recursos, memoria, escopo e publicacao sem misturar responsabilidades.",
          },
          controlPlaneEditorPublish: {
            title: "Salve primeiro e publique com seguranca",
            description:
              "Use estas acoes para persistir o rascunho e avancar para a revisao de publicacao quando o bot estiver pronto.",
          },
          runtimeHeader: {
            title: "Runtime e a sala de controle ao vivo",
            description:
              "Esta tela concentra saude das execucoes, atividade ao vivo e filtros para focar nos bots que importam agora.",
            emptyTitle: "Runtime fica util assim que a atividade aparece",
            emptyDescription:
              "Quando ainda nao existem ambientes vivos, trate esta pagina como a superficie que primeiro vai mostrar atividade.",
            unavailableTitle: "Runtime tambem sinaliza indisponibilidade rapido",
            unavailableDescription:
              "Se a conectividade do runtime degradar, e aqui que o app expoe esse estado antes da inspecao profunda.",
          },
          runtimeLiveList: {
            title: "As metricas mostram o quanto o runtime pede atencao",
            description:
              "Use estes indicadores para estimar cobertura online, execucoes ativas e a carga atual de atencao.",
            emptyTitle: "Ainda nao ha execucoes ao vivo",
            emptyDescription:
              "Quando a lista estiver vazia, esta area ainda confirma que o runtime esta quieto em vez de esconder o estado.",
          },
          sessionsRail: {
            title: "Sessions e a trilha do historico conversacional",
            description:
              "Pesquise e troque de conversa aqui para inspecionar o historico de dialogo de cada bot.",
            emptyTitle: "Sessions vira o indice das conversas",
            emptyDescription:
              "Assim que existirem conversas, esta trilha passa a ser o jeito mais rapido de pular entre elas.",
          },
          sessionsThread: {
            title: "A thread junta mensagens e contexto",
            description:
              "Esta area mostra a conversa selecionada, enquanto composer e painel de contexto deixam o follow-up por perto.",
            emptyTitle: "Voce pode iniciar uma conversa por aqui",
            emptyDescription:
              "Quando ainda nao houver thread, selecione um bot no composer e comece a primeira conversa por esta superficie.",
          },
          executionsFilters: {
            title: "Executions comeca pela filtragem rapida",
            description:
              "Use busca, selecao de bot e chips de status para estreitar o historico antes de abrir uma tarefa especifica.",
            unavailableTitle: "Executions tambem sinaliza quando o feed falha",
            unavailableDescription:
              "Se a lista nao puder ser carregada, e aqui que voce tenta novamente e confirma o estado do feed operacional.",
          },
          executionsTable: {
            title: "A tabela e a espinha dorsal do historico",
            description:
              "Abra tarefas daqui para inspecionar duracao, custo, alertas e as superficies de detalhe.",
            emptyTitle: "Nenhuma execucao corresponde ainda",
            emptyDescription:
              "Quando nada aparece, os filtros podem estar restritivos demais ou o workspace ainda esta silencioso.",
            unavailableTitle: "O historico tambem precisa falhar com clareza",
            unavailableDescription:
              "Quando o backend estiver indisponivel, esta area deve explicar o problema em vez de deixar a tela vazia.",
          },
          memoryPrimary: {
            title: "Memory mapeia contexto de longa duracao",
            description:
              "Use esta area para inspecionar o que o workspace esta aprendendo, agrupando e deixando disponivel para os bots.",
          },
          costsPrimary: {
            title: "Costs explica consumo e eficiencia",
            description:
              "Esta pagina ajuda a comparar gasto, distribuicao e impacto operacional entre bots e janelas de tempo.",
          },
          schedulesPrimary: {
            title: "Schedules centraliza rotinas",
            description:
              "Revise cadencia, jobs pausados e cobertura de automacoes aqui quando precisar inspecionar trabalho recorrente.",
          },
          dlqPrimary: {
            title: "Dead letter queue isola falhas",
            description:
              "Venha para ca para inspecionar retries, estado bruto de falha e decisoes de recuperacao quando tarefas saem do fluxo feliz.",
          },
          systemSettingsPrimary: {
            title: "System settings concentra a governanca global",
            description:
              "E aqui que providers, defaults e controles compartilhados sao configurados para o workspace inteiro.",
          },
        },
        complete: {
          title: "Voce ja pode explorar o Koda",
          description:
            "Reabra o tour a qualquer momento em Docs se quiser revisar o fluxo ou visitar um capitulo secundario.",
        },
      },
      agentSwitcher: {
        placeholder: "Selecionar bot",
        ariaSingle: "Selecionar bot",
        ariaMultiple: "Selecionar bots",
        searchPlaceholder: "Buscar bot",
        allAgents: "Todos os bots",
        agentsVisible: "{{count}} bots visíveis",
        agentsSelected: "{{count}} bots selecionados",
        agentsSelectedOutOfTotal: "{{selected}} de {{total}} bots selecionados",
        noAgentFilter: "Sem filtro por bot",
        selectOne: "Selecione um bot",
        noResults: "Nenhum bot encontrado",
      },
      async: {
        loading: "Carregando",
        updating: "Atualizando",
        synced: "Sincronizado",
        ready: "Pronto",
        retry: "Tentar novamente",
      },
      statuses: {
        all: "Todas",
        completed: "Concluídas",
        running: "Executando",
        queued: "Na fila",
        failed: "Falhas",
        retrying: "Retentando",
      },
      costs: {
        filters: {
          agents: "Bots",
          period: "Período",
          model: "Modelo",
          taskType: "Tipo de tarefa",
          periods: {
            "7d": "7 dias",
            "30d": "30 dias",
            "90d": "90 dias",
          },
        },
        mode: {
          byAgent: "Por bot",
          byModel: "Por modelo",
        },
        kpis: {
          totalPeriod: "Total no período",
          today: "Hoje",
          costPerResolved: "Custo por conversa resolvida",
          peakBucket: "Pico do período",
        },
        chart: {
          eyebrow: "Origem temporal",
          title: "Onde o custo nasce no período",
          description:
            "Buckets empilhados para revelar picos, dispersão e o motor dominante do custo.",
        },
        allocation: {
          eyebrow: "Alocação",
          title: "Alocação do consumo",
          description: "Leitura compacta de onde o custo está concentrado no recorte atual.",
        },
        ledger: {
          eyebrow: "Ledger de custo",
          title: "Operações por custo",
          count: "{{count}} registros",
        },
      },
      executions: {
        searchPlaceholder: "Buscar consulta, sessão ou modelo",
        unavailable: "Execuções indisponíveis",
        loadError: "Não foi possível carregar execuções.",
        noSelection: "Nenhuma execução selecionada.",
        retryLabel: "Retentando",
      },
      sessions: {
        searchPlaceholder: "Buscar por sessão, nome ou última mensagem",
        noSelection: "Nenhuma conversa selecionada.",
        loadError: "Não foi possível carregar a conversa.",
        chatWithAgent: "Converse com {{bot}}",
        composerHelper:
          "A interface já está pronta para o fluxo conversacional do bot. O envio real depende do endpoint do runtime.",
        composerIdle: "Escolha uma conversa para explorar o histórico ou prepare uma nova interação.",
        sendUnavailable:
          "O runtime deste bot ainda não expõe um endpoint HTTP de envio para o chat web do Koda.",
      },
      memory: {
        views: {
          map: "Memórias",
          curation: "Curadoria",
        },
        filters: {
          title: "Filtros",
          intro:
            "Ajuste o recorte por usuário, sessão, tempo e tipos de memória antes de explorar as conexões do mapa.",
          search: "Buscar no mapa",
          searchPlaceholder: "Conteúdo, origem ou aprendizado...",
          user: "Usuário",
          session: "Sessão",
          timeWindow: "Janela temporal",
          includeInactive: "Incluir memórias inativas",
          edges: {
            semantic: "Semântica",
            session: "Sessão",
            source: "Origem",
          },
        },
        empty: {
          title: "Ainda não existem memórias para exibir",
          description:
            "Quando este bot começar a consolidar fatos, decisões, tarefas ou problemas, o mapa vai organizar essas lembranças em uma malha viva de contexto e aprendizado.",
        },
      },
      schedules: {
        loading: "Carregando",
        jobs: "agendamentos",
        active: "ativos",
      },
      dlq: {
        filters: {
          all: "Todas",
          eligible: "Pode retentar",
          ineligible: "Sem retentativa",
        },
      },
      controlPlane: {
        botCreate: {
          promptPlaceholder:
            "Voce e um assistente especializado em...\n\nSeu objetivo e ajudar usuarios a...\n\nRegras:\n- Seja claro e objetivo\n- Responda sempre em portugues",
        },
      },
      settings: {
        sections: {
          general: {
            label: "Geral",
            description: "Timezone e preferências regionais.",
          },
          models: {
            label: "Modelos e Providers",
            description: "Providers de IA, seleção de modelos e controle de uso.",
          },
          integrations: {
            label: "Integrações",
            description: "Serviços externos e servidores MCP como Jira, Google, bancos de dados e bridges curadas.",
          },
          providers: {
            label: "Provedores",
            description: "Provedores de IA para modelos de linguagem, voz e mídia.",
          },
          mcp: {
            label: "Servidores MCP",
            description: "Servidores do Model Context Protocol para estender ferramentas dos agentes.",
          },
          intelligence: {
            label: "Inteligência",
            description: "Memória, conhecimento e governança de autonomia.",
          },
          variables: {
            label: "Variáveis e Segredos",
            description: "Variáveis de sistema e segredos para operação dos agentes.",
          },
        },
      },
      auth: {
        login: {
          title: "Bem-vindo de volta",
          subtitle: "Entre para acessar o espaço de trabalho operacional.",
          identifier: "E-mail ou nome de usuário",
          password: "Senha",
          submit: "Entrar",
          submitting: "Entrando...",
          forgot_link: "Esqueceu a senha ou o código de recuperação?",
          generic_error: "As credenciais informadas não conferem. Tente novamente.",
        },
        forgot: {
          title: "Recuperar acesso",
          subtitle: "Use um código de recuperação para definir uma nova senha.",
          identifier: "E-mail ou nome de usuário",
          recovery_code: "Código de recuperação",
          new_password: "Nova senha",
          confirm_password: "Confirmar nova senha",
          submit: "Redefinir senha",
          submitting: "Redefinindo...",
          back_to_login: "Voltar ao login",
          success_title: "Senha atualizada",
          success: "Agora você pode entrar com sua nova senha.",
          password_too_short: "A senha deve ter pelo menos {{n}} caracteres.",
          password_mismatch: "As senhas não coincidem.",
          generic_error: "As informações fornecidas são inválidas ou expiraram. Tente novamente.",
        },
        setup: {
          create_account: {
            title: "Criar a conta proprietária",
            subtitle: "Configure o primeiro operador para desbloquear o espaço de trabalho.",
            email: "E-mail corporativo",
            password: "Senha",
            password_hint: "Mínimo de 12 caracteres.",
            confirm_password: "Confirmar senha",
            bootstrap_code: "Código de bootstrap",
            bootstrap_hint: "Use o código de bootstrap único impresso pelo instalador.",
            bootstrap_hint_generic: "Informe o código de bootstrap emitido para esta instância.",
            submit: "Criar conta",
            submitting: "Criando...",
            errors: {
              bootstrap_required: "O código de bootstrap é obrigatório.",
              email_invalid: "Informe um endereço de e-mail válido.",
              password_too_short: "A senha deve ter pelo menos {{n}} caracteres.",
              password_mismatch: "As senhas não coincidem.",
              generic: "Não conseguimos criar a conta. Tente novamente.",
            },
          },
          recovery_codes: {
            title: "Guarde seus códigos de recuperação",
            subtitle: "Armazene estes códigos em local seguro. Cada código funciona apenas uma vez.",
            file_header: "Códigos de recuperação Koda",
            copy_all: "Copiar todos",
            copied: "Copiado",
            download: "Baixar",
            print: "Imprimir",
            saved_checkbox: "Guardei os códigos de recuperação em local seguro.",
            continue: "Continuar para o espaço de trabalho",
            already_shown_banner: "Estes códigos não serão exibidos novamente.",
          },
        },
        settings: {
          security: {
            title: "Segurança",
            change_password: "Alterar senha",
            need_current_password: "Informe sua senha atual para continuar.",
            regenerate_codes: "Regenerar códigos de recuperação",
            codes_remaining: "{{count}} códigos de recuperação restantes",
          },
        },
      },
    },
  },
  "es-ES": {
    translation: {
      app: {
        name: "Koda",
        description:
          "Koda es el espacio operativo para monitorear agentes, ejecuciones, costos, memoria y rutinas en tiempo real.",
        skipToContent: "Ir al contenido principal",
      },
      language: {
        label: "Idioma",
        placeholder: "Idioma",
        options: {
          "en-US": "English (US)",
          "pt-BR": "Português (Brasil)",
          "es-ES": "Español",
          "fr-FR": "Français",
          "de-DE": "Deutsch",
        },
      },
      theme: {
        label: "Tema",
        placeholder: "Tema",
        options: {
          system: "Sistema",
          light: "Claro",
          dark: "Oscuro",
        },
      },
      common: {
        loading: "Cargando",
        ready: "Listo",
        synced: "Sincronizado",
        updating: "Actualizando",
        retry: "Reintentar",
        search: "Buscar",
        ask: "Preguntar",
        docs: "Documentación",
        files: "Archivos",
        notifications: "Notificaciones",
        allAgents: "Todos los bots",
        allModels: "Todos los modelos",
        allTypes: "Todos los tipos",
        allUsers: "Todos los usuarios",
        allSessions: "Todas las sesiones",
        now: "ahora",
        agent: "Bot",
        status: "Estado",
        cost: "Costo",
        duration: "Duración",
        created: "Creada",
        source: "Origen",
        session: "Sesión",
        query: "Consulta",
        summary: "Resumen",
        active: "Activo",
        paused: "Pausado",
        resolved: "Resuelta",
        failed: "Falló",
      },
      routeMeta: {
        system: {
          eyebrow: "Koda",
          title: "Sistema",
          summary: "Gobernanza global, providers y recursos compartidos.",
        },
        agents: {
          eyebrow: "Koda",
          title: "Agentes",
          summary: "Catálogo, edición y publicación de agentes.",
        },
        runtime: {
          eyebrow: "Runtime",
          title: "Panel de control",
          summary: "Bots, entornos y superficies en vivo.",
        },
        overview: {
          eyebrow: "Panel",
          title: "Resumen",
          summary: "Pulso de bots, costos y actividad.",
        },
        executions: {
          eyebrow: "Operación",
          title: "Ejecuciones",
          summary: "Tareas, traces y estado reciente.",
        },
        memory: {
          eyebrow: "Contexto",
          title: "Memoria",
          summary: "Mapa, curaduría y contexto por bot.",
        },
        sessions: {
          eyebrow: "Conversaciones",
          title: "Sesiones",
          summary: "Conversaciones, respuestas y ejecuciones vinculadas.",
        },
        costs: {
          eyebrow: "Consumo",
          title: "Costos",
          summary: "Consumo, distribución y eficiencia.",
        },
        schedules: {
          eyebrow: "Rutinas",
          title: "Programaciones",
          summary: "Rutinas, cadencia y cobertura.",
        },
        dlq: {
          eyebrow: "Recuperación",
          title: "Cola muerta",
          summary: "Fallas, reintentos y diagnóstico.",
        },
        fallback: {
          eyebrow: "Koda",
          title: "Workspace",
          summary: "Centro operativo de Koda.",
        },
      },
      sidebar: {
        ariaLabel: "Navegación principal",
        newSession: "Nueva sesión",
        newSessionLabel: "Iniciar una nueva sesión",
        recents: "Recientes",
        clearRecents: "Limpiar recientes",
        noRecents: "Tus rutas recientes aparecerán aquí.",
        sections: {
          atlas: "Koda",
          operations: "Operación",
          analysis: "Análisis",
          system: "Sistema",
        },
        items: {
          home: "Inicio",
          runtime: "Runtime",
          agents: "Agentes",
          executions: "Ejecuciones",
          sessions: "Sesiones",
          costs: "Costos",
          memory: "Memoria",
          schedules: "Programaciones",
          dlq: "Cola muerta",
          generalSettings: "Configuración general",
        },
        loading: {
          home: "Abriendo inicio",
          runtime: "Abriendo runtime",
          agents: "Abriendo agentes",
          executions: "Abriendo ejecuciones",
          sessions: "Abriendo sesiones",
          costs: "Abriendo costos",
          memory: "Abriendo memoria",
          schedules: "Abriendo programaciones",
          dlq: "Abriendo cola muerta",
          generalSettings: "Abriendo configuración general",
        },
      },
      topbar: {
        openMenu: "Abrir menú",
        expandSidebar: "Expandir sidebar",
        collapseSidebar: "Colapsar sidebar",
        docs: {
          eyebrow: "Documentación",
          title: "Base operativa de Koda",
          description: "Guías rápidas para navegar por las superficies críticas del workspace.",
          entries: {
            dailyOps: {
              eyebrow: "Playbook",
              title: "Operación diaria",
              description: "Ejecuciones, sesiones e incidentes en un solo flujo.",
            },
            governance: {
              eyebrow: "Sistema",
              title: "Gobernanza Koda",
              description: "Defaults globales, providers y grants compartidos.",
            },
            memory: {
              eyebrow: "Contexto",
              title: "Memoria y curaduría",
              description: "Mapas, clusters y señales operativas por bot.",
            },
          },
        },
        ask: {
          eyebrow: "Pregunta",
          title: "Pregunta a Koda",
          description: "Respuesta rápida para llevarte directo a la pantalla correcta.",
          placeholder: "Ej.: ¿dónde veo hoy las fallas críticas de ATLAS?",
          responseLabel: "Respuesta",
          button: "Preguntar",
          loadingButton: "Analizando...",
          loadingCopy: "Koda está conectando el contexto operativo para responder con foco.",
          initialReply:
            "Pregunta sobre operación, costos, memoria o gobernanza y te indicaré la mejor superficie de Koda para empezar.",
          suggestions: {
            failures: "¿Cómo priorizo fallas de la cola muerta?",
            cost: "¿Qué pantalla muestra cuellos de costo más rápido?",
            schedules: "¿Dónde reviso rutinas pausadas?",
          },
          replies: {
            failures:
              "Empieza por Cola muerta para aislar el origen, validar reintentos y abrir el payload bruto cuando necesites confirmar la causa raíz.",
            cost:
              "Abre Costos para comparar la distribución por bot y cruza con Ejecuciones si quieres entender qué flujo elevó el consumo.",
            schedules:
              "Programaciones concentra el estado de las rutinas. Usa el filtro por bot para separar lo que está activo, pausado o sin cobertura.",
            sessions:
              "Sesiones se volvió la superficie ideal para interactuar directamente con un bot específico, con historial y envío de mensajes en el mismo espacio.",
            fallback:
              "Usa Ejecuciones para el pulso operativo, Sesiones para conversación directa, Memoria para contexto y Sistema cuando la decisión involucre defaults o gobernanza.",
          },
        },
        files: {
          eyebrow: "Archivos",
          title: "Atajos recientes",
          description: "Archivos y catálogos más usados en el flujo operativo reciente.",
          entries: {
            runtime: {
              detail: "Operación, traces y rutinas prioritarias",
              updatedAt: "hace 12 min",
            },
            governance: {
              detail: "Catálogo vivo de defaults, políticas e integraciones",
              updatedAt: "hace 36 min",
            },
            memory: {
              detail: "Señales recientes y ajustes de relevancia",
              updatedAt: "hace 2 h",
            },
            costs: {
              detail: "Distribución reciente de consumo por bot",
              updatedAt: "hace 4 h",
            },
          },
        },
        notifications: {
          eyebrow: "Notificaciones",
          title: "Actualizaciones recientes",
          description: "Mejoras y cambios recientes de Koda en una lectura rápida.",
          summaryLeft: "{{count}} novedades recientes",
          summaryRight: "Todo en un solo lugar",
          entries: {
            sessions: {
              section: "Sesiones",
              title: "Nueva vista operativa para sesiones",
              description:
                "La pantalla ahora abre en formato de chat, con selección directa del bot y composer fijo.",
              timestamp: "Hoy",
            },
            memory: {
              section: "Memoria",
              title: "Memoria refinada",
              description: "Mapa rediseñado y curaduría con mejor aprovechamiento vertical.",
              timestamp: "Ayer",
            },
            system: {
              section: "Sistema",
              title: "Gobernanza unificada",
              description: "Sistema y catálogo ahora siguen la misma base visual y de modales.",
              timestamp: "Hace 2 días",
            },
          },
        },
      },
      tour: {
        actions: {
          start: "Iniciar tour",
          back: "Volver",
          continue: "Continuar",
          skip: "Saltar tour",
          finish: "Finalizar tour",
        },
        progress: {
          start: "Primeros pasos",
          value: "{{current}} de {{total}}",
        },
        confirmSkip: "Deseas saltar el tour guiado?",
        topbar: {
          eyebrow: "Tour",
          title: "Tour guiado",
          description: "Abre un recorrido guiado de este workspace o de la pantalla actual.",
          resumeTitle: "Retomar tour guiado",
          resumeDescription: "Vuelve al walkthrough actual desde el punto en el que lo dejaste.",
        },
        welcome: {
          title: "Comienza con un tour rapido",
          description:
            "Koda te mostrara las pantallas principales, como navegar entre ellas y que significa cada superficie. El flujo es objetivo y puedes salir cuando quieras.",
        },
        steps: {
          shellSidebar: {
            title: "Esta barra lateral es tu mapa principal",
            description:
              "Usala para moverte entre overview, runtime, catalogo y superficies operativas sin perder contexto.",
          },
          shellTopbar: {
            title: "La barra superior concentra el contexto de la ruta",
            description:
              "Aqui ves el resumen de la pantalla activa, herramientas rapidas, selector de idioma y el atajo para reabrir este tour despues.",
          },
          overviewMetrics: {
            title: "Overview resume el pulso operativo",
            description:
              "Este primer bloque condensa actividad, demanda y costo para entender que cambio antes de profundizar.",
            emptyTitle: "Overview nace como tu pulso operativo",
            emptyDescription:
              "Incluso antes de que exista actividad, aqui volveras para leer el resumen mas rapido del estado del workspace.",
          },
          overviewLivePlan: {
            title: "Esta seccion destaca los proximos movimientos en vivo",
            description:
              "Usala para ver que esta corriendo ahora, que requiere atencion y por donde continuar la investigacion.",
          },
          controlPlanePrimaryAction: {
            title: "El catalogo es donde empieza la configuracion",
            description:
              "Crea bots y workspaces aqui y despues abre un bot para configurar identidad, comportamiento, recursos y publicacion.",
            emptyTitle: "El catalogo es el primer paso en una instalacion nueva",
            emptyDescription:
              "Si la instancia esta vacia, comienza aqui creando un workspace o un bot. El editor se abre enseguida.",
          },
          controlPlaneBoard: {
            title: "El board explica como se organiza el catalogo",
            description:
              "Workspaces, squads y bots se agrupan aqui para que gobernanza y ownership sean visibles de inmediato.",
            emptyTitle: "El board crece junto con el catalogo",
            emptyDescription:
              "Cuando existan bots, esta area se convierte en el mapa visual de equipos, workspaces y ownership operativo.",
          },
          controlPlaneEditorHeader: {
            title: "El editor es el centro de control del bot",
            description:
              "Este encabezado muestra que bot estas editando y mantiene cerca las acciones principales para guardar y revisar la publicacion.",
          },
          controlPlaneEditorSteps: {
            title: "Estas secciones organizan la configuracion completa del bot",
            description:
              "Recorre identidad, comportamiento, recursos, memoria, alcance y publicacion sin mezclar responsabilidades.",
          },
          controlPlaneEditorPublish: {
            title: "Guarda primero y publica con confianza",
            description:
              "Usa estas acciones para persistir el borrador y avanzar hacia la revision de publicacion cuando el bot este listo.",
          },
          runtimeHeader: {
            title: "Runtime es la sala de control en vivo",
            description:
              "Esta pantalla concentra la salud de las ejecuciones, la actividad en vivo y filtros para enfocarte en los bots que importan ahora.",
            emptyTitle: "Runtime se vuelve util apenas aparece actividad",
            emptyDescription:
              "Cuando todavia no existen entornos vivos, toma esta pagina como la superficie que mostrara primero la actividad real.",
            unavailableTitle: "Runtime tambien señala la indisponibilidad rapidamente",
            unavailableDescription:
              "Si la conectividad del runtime se degrada, aqui es donde la app expone ese estado antes de una inspeccion profunda.",
          },
          runtimeLiveList: {
            title: "Las metricas muestran cuanta atencion necesita runtime",
            description:
              "Usa estos indicadores para estimar cobertura online, ejecuciones activas y la carga actual de atencion.",
            emptyTitle: "Todavia no hay ejecuciones en vivo",
            emptyDescription:
              "Cuando la lista este vacia, esta area igual confirma que runtime esta tranquilo en vez de ocultar el estado.",
          },
          sessionsRail: {
            title: "Sessions es el indice del historial conversacional",
            description:
              "Busca y cambia de conversacion aqui para inspeccionar el historial de dialogo de cada bot.",
            emptyTitle: "Sessions se convierte en el indice de conversaciones",
            emptyDescription:
              "Apenas existan conversaciones, este rail pasa a ser la forma mas rapida de saltar entre ellas.",
          },
          sessionsThread: {
            title: "La thread junta mensajes y contexto",
            description:
              "Esta area muestra la conversacion seleccionada, mientras el composer y el panel de contexto dejan cerca el seguimiento.",
            emptyTitle: "Puedes iniciar una conversacion desde aqui",
            emptyDescription:
              "Cuando todavia no exista una thread, selecciona un bot en el composer y empieza la primera conversacion desde esta superficie.",
          },
          executionsFilters: {
            title: "Executions empieza por el filtrado rapido",
            description:
              "Usa busqueda, seleccion de bot y chips de estado para acotar el historial antes de abrir una tarea concreta.",
            unavailableTitle: "Executions tambien señala cuando el feed falla",
            unavailableDescription:
              "Si la lista no se puede cargar, aqui es donde reintentas y confirmas el estado del feed operativo.",
          },
          executionsTable: {
            title: "La tabla es la columna vertebral del historial",
            description:
              "Abre tareas desde aqui para inspeccionar duracion, costo, alertas y superficies de detalle.",
            emptyTitle: "Todavia no hay ejecuciones coincidentes",
            emptyDescription:
              "Cuando no aparece nada, los filtros pueden estar demasiado estrictos o el workspace todavia esta silencioso.",
            unavailableTitle: "El historial tambien debe fallar con claridad",
            unavailableDescription:
              "Cuando el backend este indisponible, esta area debe explicar el problema en vez de dejar la pantalla vacia.",
          },
          memoryPrimary: {
            title: "Memory mapea el contexto de larga duracion",
            description:
              "Usa esta area para inspeccionar lo que el workspace esta aprendiendo, agrupando y dejando disponible para los bots.",
          },
          costsPrimary: {
            title: "Costs explica consumo y eficiencia",
            description:
              "Esta pagina ayuda a comparar gasto, distribucion e impacto operativo entre bots y ventanas de tiempo.",
          },
          schedulesPrimary: {
            title: "Schedules centraliza las rutinas",
            description:
              "Revisa cadencia, jobs pausados y cobertura de automatizaciones aqui cuando necesites inspeccionar trabajo recurrente.",
          },
          dlqPrimary: {
            title: "Dead letter queue aísla fallos",
            description:
              "Ven aqui para inspeccionar reintentos, estado bruto del fallo y decisiones de recuperacion cuando las tareas salen del camino feliz.",
          },
          systemSettingsPrimary: {
            title: "System settings concentra la gobernanza global",
            description:
              "Aqui se configuran providers, defaults y controles compartidos para todo el workspace.",
          },
        },
        complete: {
          title: "Ya puedes explorar Koda",
          description:
            "Reabre el tour en Docs cuando quieras repasar el flujo o visitar un capitulo secundario.",
        },
      },
      agentSwitcher: {
        placeholder: "Seleccionar bot",
        ariaSingle: "Seleccionar bot",
        ariaMultiple: "Seleccionar bots",
        searchPlaceholder: "Buscar bot",
        allAgents: "Todos los bots",
        agentsVisible: "{{count}} bots visibles",
        agentsSelected: "{{count}} bots seleccionados",
        agentsSelectedOutOfTotal: "{{selected}} de {{total}} bots seleccionados",
        noAgentFilter: "Sin filtro por bot",
        selectOne: "Selecciona un bot",
        noResults: "Ningún bot encontrado",
      },
      async: {
        loading: "Cargando",
        updating: "Actualizando",
        synced: "Sincronizado",
        ready: "Listo",
        retry: "Reintentar",
      },
      statuses: {
        all: "Todas",
        completed: "Completadas",
        running: "Ejecutando",
        queued: "En cola",
        failed: "Fallidas",
        retrying: "Reintentando",
      },
      costs: {
        filters: {
          agents: "Bots",
          period: "Período",
          model: "Modelo",
          taskType: "Tipo de tarea",
          periods: {
            "7d": "7 días",
            "30d": "30 días",
            "90d": "90 días",
          },
        },
        mode: {
          byAgent: "Por bot",
          byModel: "Por modelo",
        },
        kpis: {
          totalPeriod: "Total en el período",
          today: "Hoy",
          costPerResolved: "Costo por conversación resuelta",
          peakBucket: "Pico del período",
        },
        chart: {
          eyebrow: "Origen temporal",
          title: "Dónde nace el costo en el período",
          description:
            "Buckets apilados para revelar picos, dispersión y el motor dominante del costo.",
        },
        allocation: {
          eyebrow: "Asignación",
          title: "Asignación del consumo",
          description: "Lectura compacta de dónde se concentra el costo en el recorte actual.",
        },
        ledger: {
          eyebrow: "Ledger de costo",
          title: "Operaciones por costo",
          count: "{{count}} registros",
        },
      },
      executions: {
        searchPlaceholder: "Buscar consulta, sesión o modelo",
        unavailable: "Ejecuciones no disponibles",
        loadError: "No fue posible cargar las ejecuciones.",
        noSelection: "Ninguna ejecución seleccionada.",
        retryLabel: "Reintentando",
      },
      sessions: {
        searchPlaceholder: "Buscar por sesión, nombre o último mensaje",
        noSelection: "Ninguna conversación seleccionada.",
        loadError: "No fue posible cargar la conversación.",
        chatWithAgent: "Habla con {{bot}}",
        composerHelper:
          "La interfaz ya está lista para el flujo conversacional del bot. El envío real depende del endpoint del runtime.",
        composerIdle: "Elige una conversación para explorar el historial o preparar una nueva interacción.",
        sendUnavailable:
          "El runtime de este bot aún no expone un endpoint HTTP de envío para el chat web de Koda.",
      },
      memory: {
        views: {
          map: "Memorias",
          curation: "Curaduría",
        },
        filters: {
          title: "Filtros",
          intro:
            "Ajusta el recorte por usuario, sesión, tiempo y tipos de memoria antes de explorar las conexiones del mapa.",
          search: "Buscar en el mapa",
          searchPlaceholder: "Contenido, origen o aprendizaje...",
          user: "Usuario",
          session: "Sesión",
          timeWindow: "Ventana temporal",
          includeInactive: "Incluir memorias inactivas",
          edges: {
            semantic: "Semántica",
            session: "Sesión",
            source: "Origen",
          },
        },
        empty: {
          title: "Aún no existen memorias para mostrar",
          description:
            "Cuando este bot empiece a consolidar hechos, decisiones, tareas o problemas, el mapa organizará esos recuerdos en una malla viva de contexto y aprendizaje.",
        },
      },
      schedules: {
        loading: "Cargando",
        jobs: "programaciones",
        active: "activos",
      },
      dlq: {
        filters: {
          all: "Todas",
          eligible: "Puede reintentar",
          ineligible: "Sin reintento",
        },
      },
      controlPlane: {
        botCreate: {
          promptPlaceholder:
            "Eres un asistente especializado en...\n\nTu objetivo es ayudar a los usuarios con...\n\nReglas:\n- Sé claro y objetivo\n- Responde siempre en español",
        },
      },
      settings: {
        sections: {
          general: {
            label: "General",
            description: "Timezone y preferencias regionales.",
          },
          models: {
            label: "Modelos y Providers",
            description: "Proveedores de IA, selección de modelos y controles de uso.",
          },
          integrations: {
            label: "Integraciones",
            description: "Servicios externos y servidores MCP como Jira, Google, bases de datos y bridges curadas.",
          },
          providers: {
            label: "Proveedores",
            description: "Proveedores de IA para modelos de lenguaje, voz y medios.",
          },
          mcp: {
            label: "Servidores MCP",
            description: "Servidores del Model Context Protocol para extender herramientas de agentes.",
          },
          intelligence: {
            label: "Inteligencia",
            description: "Memoria, conocimiento y gobernanza de autonomía.",
          },
          variables: {
            label: "Variables y Secretos",
            description: "Variables de sistema y secretos para operación de agentes.",
          },
        },
      },
      auth: {
        login: {
          title: "Bienvenido de nuevo",
          subtitle: "Inicia sesión para acceder al espacio de trabajo operativo.",
          identifier: "Correo o nombre de usuario",
          password: "Contraseña",
          submit: "Iniciar sesión",
          submitting: "Iniciando sesión...",
          forgot_link: "¿Olvidaste la contraseña o el código de recuperación?",
          generic_error: "Las credenciales no coinciden. Inténtalo de nuevo.",
        },
        forgot: {
          title: "Recuperar acceso",
          subtitle: "Usa un código de recuperación para definir una nueva contraseña.",
          identifier: "Correo o nombre de usuario",
          recovery_code: "Código de recuperación",
          new_password: "Nueva contraseña",
          confirm_password: "Confirmar nueva contraseña",
          submit: "Restablecer contraseña",
          submitting: "Restableciendo...",
          back_to_login: "Volver al inicio de sesión",
          success_title: "Contraseña actualizada",
          success: "Ya puedes iniciar sesión con tu nueva contraseña.",
          password_too_short: "La contraseña debe tener al menos {{n}} caracteres.",
          password_mismatch: "Las contraseñas no coinciden.",
          generic_error: "La información es inválida o ha caducado. Inténtalo de nuevo.",
        },
        setup: {
          create_account: {
            title: "Crear la cuenta propietaria",
            subtitle: "Configura el primer operador para desbloquear el espacio de trabajo.",
            email: "Correo corporativo",
            password: "Contraseña",
            password_hint: "Mínimo 12 caracteres.",
            confirm_password: "Confirmar contraseña",
            bootstrap_code: "Código de bootstrap",
            bootstrap_hint: "Usa el código de bootstrap de un solo uso impreso por el instalador.",
            bootstrap_hint_generic: "Proporciona el código de bootstrap emitido para esta instancia.",
            submit: "Crear cuenta",
            submitting: "Creando...",
            errors: {
              bootstrap_required: "El código de bootstrap es obligatorio.",
              email_invalid: "Introduce un correo válido.",
              password_too_short: "La contraseña debe tener al menos {{n}} caracteres.",
              password_mismatch: "Las contraseñas no coinciden.",
              generic: "No pudimos crear la cuenta. Inténtalo de nuevo.",
            },
          },
          recovery_codes: {
            title: "Guarda tus códigos de recuperación",
            subtitle: "Guarda estos códigos en un lugar seguro. Cada código funciona solo una vez.",
            file_header: "Códigos de recuperación de Koda",
            copy_all: "Copiar todo",
            copied: "Copiado",
            download: "Descargar",
            print: "Imprimir",
            saved_checkbox: "He guardado los códigos de recuperación en un lugar seguro.",
            continue: "Continuar al espacio de trabajo",
            already_shown_banner: "Estos códigos no se volverán a mostrar.",
          },
        },
        settings: {
          security: {
            title: "Seguridad",
            change_password: "Cambiar contraseña",
            need_current_password: "Introduce tu contraseña actual para continuar.",
            regenerate_codes: "Regenerar códigos de recuperación",
            codes_remaining: "{{count}} códigos de recuperación restantes",
          },
        },
      },
    },
  },
  "fr-FR": {
    translation: {
      app: {
        name: "Koda",
        description:
          "Koda est l'espace de travail opérationnel pour superviser les agents, exécutions, coûts, mémoire et routines en temps réel.",
        skipToContent: "Aller au contenu principal",
      },
      language: {
        label: "Langue",
        placeholder: "Langue",
        options: {
          "en-US": "English (US)",
          "pt-BR": "Português (Brasil)",
          "es-ES": "Español",
          "fr-FR": "Français",
          "de-DE": "Deutsch",
        },
      },
      theme: {
        label: "Thème",
        placeholder: "Thème",
        options: {
          system: "Système",
          light: "Clair",
          dark: "Sombre",
        },
      },
      common: {
        loading: "Chargement",
        ready: "Prêt",
        synced: "Synchronisé",
        updating: "Mise à jour",
        retry: "Réessayer",
        search: "Rechercher",
        ask: "Demander",
        docs: "Docs",
        files: "Fichiers",
        notifications: "Notifications",
        allAgents: "Tous les bots",
        allModels: "Tous les modèles",
        allTypes: "Tous les types",
        allUsers: "Tous les utilisateurs",
        allSessions: "Toutes les sessions",
        now: "maintenant",
        agent: "Bot",
        status: "Statut",
        cost: "Coût",
        duration: "Durée",
        created: "Créé",
        source: "Source",
        session: "Session",
        query: "Requête",
        summary: "Résumé",
        active: "Actif",
        paused: "En pause",
        resolved: "Résolu",
        failed: "Échoué",
      },
      routeMeta: {
        system: {
          eyebrow: "Koda",
          title: "Système",
          summary: "Gouvernance globale, fournisseurs et ressources partagées.",
        },
        agents: {
          eyebrow: "Koda",
          title: "Agents",
          summary: "Catalogue, édition et publication pour les agents.",
        },
        runtime: {
          eyebrow: "Runtime",
          title: "Plan de contrôle",
          summary: "Bots, environnements et surfaces en direct.",
        },
        overview: {
          eyebrow: "Espace de travail",
          title: "Aperçu",
          summary: "Pouls des bots, coûts et activité.",
        },
        executions: {
          eyebrow: "Opérations",
          title: "Exécutions",
          summary: "Tâches, traces et état récent.",
        },
        memory: {
          eyebrow: "Contexte",
          title: "Mémoire",
          summary: "Carte, curation et contexte par bot.",
        },
        sessions: {
          eyebrow: "Conversations",
          title: "Sessions",
          summary: "Discussions, réponses et exécutions liées.",
        },
        costs: {
          eyebrow: "Consommation",
          title: "Coûts",
          summary: "Consommation, répartition et efficacité.",
        },
        schedules: {
          eyebrow: "Routines",
          title: "Planifications",
          summary: "Routines, cadence et couverture.",
        },
        dlq: {
          eyebrow: "Récupération",
          title: "File des messages non distribués",
          summary: "Échecs, nouvelles tentatives et diagnostic.",
        },
        fallback: {
          eyebrow: "Koda",
          title: "Espace de travail",
          summary: "Centre opérationnel Koda.",
        },
      },
      sidebar: {
        ariaLabel: "Navigation principale",
        newSession: "Nouvelle session",
        newSessionLabel: "Démarrer une nouvelle session",
        recents: "Récents",
        clearRecents: "Effacer les récents",
        noRecents: "Vos parcours récents apparaîtront ici.",
        sections: {
          atlas: "Koda",
          operations: "Opérations",
          analysis: "Analyse",
          system: "Système",
        },
        items: {
          home: "Accueil",
          runtime: "Runtime",
          agents: "Agents",
          executions: "Exécutions",
          sessions: "Sessions",
          costs: "Coûts",
          memory: "Mémoire",
          schedules: "Planifications",
          dlq: "File des messages non distribués",
          generalSettings: "Paramètres généraux",
        },
        loading: {
          home: "Ouverture de l'accueil",
          runtime: "Ouverture du runtime",
          agents: "Ouverture des agents",
          executions: "Ouverture des exécutions",
          sessions: "Ouverture des sessions",
          costs: "Ouverture des coûts",
          memory: "Ouverture de la mémoire",
          schedules: "Ouverture des planifications",
          dlq: "Ouverture de la file des messages non distribués",
          generalSettings: "Ouverture des paramètres généraux",
        },
      },
      topbar: {
        openMenu: "Ouvrir le menu",
        expandSidebar: "Étendre la barre latérale",
        collapseSidebar: "Réduire la barre latérale",
        docs: {
          eyebrow: "Docs",
          title: "Base opérationnelle Koda",
          description: "Guides rapides pour naviguer dans les surfaces critiques de l'espace de travail.",
          entries: {
            dailyOps: {
              eyebrow: "Playbook",
              title: "Opérations quotidiennes",
              description: "Exécutions, sessions et incidents dans un seul flux.",
            },
            governance: {
              eyebrow: "Système",
              title: "Gouvernance Koda",
              description: "Valeurs par défaut globales, fournisseurs et autorisations partagées.",
            },
            memory: {
              eyebrow: "Contexte",
              title: "Mémoire et curation",
              description: "Cartes, clusters et signaux opérationnels par bot.",
            },
          },
        },
        ask: {
          eyebrow: "Demander",
          title: "Demander à Koda",
          description: "Réponse rapide pour vous amener directement à la bonne surface.",
          placeholder: "Ex. : où voir les échecs critiques ATLAS aujourd'hui ?",
          responseLabel: "Réponse",
          button: "Demander",
          loadingButton: "Analyse en cours...",
          loadingCopy: "Koda met en relation le contexte opérationnel pour répondre avec précision.",
          initialReply:
            "Posez une question sur les opérations, coûts, mémoire ou gouvernance et je vous orienterai vers la meilleure surface Koda.",
          suggestions: {
            failures: "Comment prioriser les échecs de la file des messages non distribués ?",
            cost: "Quel écran montre le plus rapidement les goulots de coût ?",
            schedules: "Où puis-je revoir les routines en pause ?",
          },
          replies: {
            failures:
              "Commencez par la file des messages non distribués pour isoler la source, valider les tentatives et inspecter le payload brut si besoin.",
            cost:
              "Ouvrez Coûts pour comparer la répartition par bot et croiser avec Exécutions pour comprendre quel flux a fait monter la consommation.",
            schedules:
              "Planifications centralise l'état des routines. Utilisez le filtre bot pour séparer ce qui est actif, en pause ou non couvert.",
            sessions:
              "Sessions est devenu la surface idéale pour interagir directement avec un bot, avec l'historique et l'envoi de messages au même endroit.",
            fallback:
              "Utilisez Exécutions pour le pouls opérationnel, Sessions pour la conversation directe, Mémoire pour le contexte et Système quand la décision concerne les valeurs par défaut ou la gouvernance.",
          },
        },
        files: {
          eyebrow: "Fichiers",
          title: "Raccourcis récents",
          description: "Fichiers et catalogues les plus utilisés dans le flux opérationnel récent.",
          entries: {
            runtime: {
              detail: "Opérations, traces et routines prioritaires",
              updatedAt: "il y a 12 min",
            },
            governance: {
              detail: "Catalogue en direct des valeurs par défaut, politiques et intégrations",
              updatedAt: "il y a 36 min",
            },
            memory: {
              detail: "Signaux récents et ajustements de pertinence",
              updatedAt: "il y a 2h",
            },
            costs: {
              detail: "Répartition récente de la consommation par bot",
              updatedAt: "il y a 4h",
            },
          },
        },
        notifications: {
          eyebrow: "Notifications",
          title: "Mises à jour récentes",
          description: "Améliorations et changements récents de Koda en lecture rapide.",
          summaryLeft: "{{count}} mises à jour récentes",
          summaryRight: "Tout au même endroit",
          entries: {
            sessions: {
              section: "Sessions",
              title: "Nouvelle vue opérationnelle pour les sessions",
              description:
                "L'écran s'ouvre maintenant en format chat, avec sélection directe du bot et un composeur fixe.",
              timestamp: "Aujourd'hui",
            },
            memory: {
              section: "Mémoire",
              title: "Mémoire affinée",
              description: "Carte repensée et curation avec une meilleure utilisation verticale.",
              timestamp: "Hier",
            },
            system: {
              section: "Système",
              title: "Gouvernance unifiée",
              description:
                "Système et catalogue suivent désormais la même base visuelle et modale.",
              timestamp: "il y a 2 jours",
            },
          },
        },
      },
      tour: {
        actions: {
          start: "Démarrer la visite",
          back: "Retour",
          continue: "Continuer",
          skip: "Passer la visite",
          finish: "Terminer la visite",
        },
        progress: {
          start: "Démarrage",
          value: "{{current}} sur {{total}}",
        },
        confirmSkip: "Voulez-vous passer la visite guidée ?",
        topbar: {
          eyebrow: "Visite",
          title: "Visite guidée",
          description: "Ouvrir une visite guidée de cet espace de travail ou de la page actuelle.",
          resumeTitle: "Reprendre la visite guidée",
          resumeDescription: "Reprenez la visite en cours à partir de l'endroit où vous vous êtes arrêté.",
        },
        welcome: {
          title: "Commencez par une visite guidée rapide",
          description:
            "Koda vous présente les écrans principaux, comment passer de l'un à l'autre et ce que chaque zone signifie. Le parcours reste concis et vous pouvez quitter à tout moment.",
        },
        steps: {
          shellSidebar: {
            title: "Cette barre latérale est votre carte principale",
            description:
              "Utilisez-la pour passer entre aperçu, runtime, catalogue et vues opérationnelles sans perdre le contexte.",
          },
          shellTopbar: {
            title: "La barre supérieure garde le contexte d'itinéraire à proximité",
            description:
              "Ici s'affichent le résumé de la page active, les outils rapides, le sélecteur de langue et le raccourci pour rouvrir cette visite plus tard.",
          },
          overviewMetrics: {
            title: "Aperçu résume le pouls opérationnel",
            description:
              "Ce premier bloc condense activité, demande et coût pour vous permettre de comprendre ce qui a changé avant d'analyser plus en détail.",
            emptyTitle: "Aperçu démarre comme votre pouls opérationnel vide",
            emptyDescription:
              "Même avant que l'activité n'apparaisse, cette page est l'endroit où vous reviendrez pour un résumé rapide de l'état de l'espace de travail.",
          },
          overviewLivePlan: {
            title: "Cette section met en avant les prochaines actions en direct",
            description:
              "Utilisez-la pour repérer ce qui tourne maintenant, ce qui nécessite de l'attention et où continuer l'investigation.",
          },
          controlPlanePrimaryAction: {
            title: "Le catalogue est le point de départ de la configuration",
            description:
              "Créez ici des bots et espaces de travail, puis ouvrez un bot pour configurer identité, comportement, ressources et publication.",
            emptyTitle: "Le catalogue est votre premier arrêt sur une installation neuve",
            emptyDescription:
              "Si l'instance est vide, commencez ici en créant un espace de travail ou un bot. L'éditeur s'ouvre juste après.",
          },
          controlPlaneBoard: {
            title: "Le tableau explique comment le catalogue est organisé",
            description:
              "Espaces de travail, escouades et bots restent groupés ici pour que gouvernance et responsabilité soient visibles d'un coup d'œil.",
            emptyTitle: "Le tableau s'étoffe avec le catalogue",
            emptyDescription:
              "Dès que des bots existent, cette zone devient la carte visuelle des équipes, espaces de travail et responsabilités opérationnelles.",
          },
          controlPlaneEditorHeader: {
            title: "L'éditeur est le centre de contrôle du bot",
            description:
              "Cet en-tête montre quel bot vous éditez et garde les actions principales (enregistrer, revoir la publication) à portée de main.",
          },
          controlPlaneEditorSteps: {
            title: "Ces sections organisent la configuration complète du bot",
            description:
              "Parcourez identité, comportement, ressources, mémoire, portée et publication sans mélanger les préoccupations.",
          },
          controlPlaneEditorPublish: {
            title: "Enregistrez d'abord, puis publiez avec confiance",
            description:
              "Utilisez ces actions pour enregistrer les modifications en brouillon et avancer vers la revue de publication quand le bot est prêt.",
          },
          runtimeHeader: {
            title: "Runtime est la salle de contrôle en direct",
            description:
              "Cet écran concentre la santé des exécutions, l'activité en direct et les filtres pour vous concentrer sur les bots qui importent maintenant.",
            emptyTitle: "Runtime devient utile dès que l'activité apparaît",
            emptyDescription:
              "Quand aucun environnement n'est encore en direct, considérez cette page comme l'endroit où l'activité en direct apparaîtra en premier.",
            unavailableTitle: "Runtime signale aussi rapidement les problèmes de disponibilité",
            unavailableDescription:
              "Si la connectivité runtime est dégradée, cette surface est l'endroit où l'application expose cet état avant une inspection plus approfondie.",
          },
          runtimeLiveList: {
            title: "Les métriques indiquent à quel point le runtime a besoin d'attention",
            description:
              "Utilisez ces indicateurs pour estimer la couverture en ligne, les exécutions en direct et la charge d'attention actuelle.",
            emptyTitle: "Aucune exécution en direct pour l'instant",
            emptyDescription:
              "Quand la liste est vide, cela confirme tout de même que le runtime est calme au lieu de masquer l'état.",
          },
          sessionsRail: {
            title: "Sessions est le rail d'historique conversationnel",
            description:
              "Recherchez et basculez les conversations ici pour inspecter l'historique du dialogue de chaque bot.",
            emptyTitle: "Sessions devient l'index de chat",
            emptyDescription:
              "Dès que des conversations existent, ce rail devient le moyen le plus rapide d'y naviguer.",
          },
          sessionsThread: {
            title: "Le fil garde messages et contexte ensemble",
            description:
              "Cette zone montre la conversation sélectionnée, tandis que le composeur et le panneau de contexte gardent les actions de suivi à portée.",
            emptyTitle: "Vous pouvez démarrer une conversation d'ici",
            emptyDescription:
              "Quand il n'y a pas encore de fil, sélectionnez un bot dans le composeur et démarrez la première conversation depuis cette surface.",
          },
          executionsFilters: {
            title: "Exécutions commence par un filtrage rapide",
            description:
              "Utilisez la recherche, la sélection de bot et les puces de statut pour restreindre l'historique avant d'ouvrir une tâche spécifique.",
            unavailableTitle: "Exécutions signale aussi quand le flux est indisponible",
            unavailableDescription:
              "Si la liste ne peut pas être chargée, cette zone est l'endroit où vous réessayez et confirmez l'état du flux opérationnel.",
          },
          executionsTable: {
            title: "Le tableau est la colonne vertébrale de l'historique des exécutions",
            description:
              "Ouvrez les tâches d'ici pour inspecter durée, coût, avertissements et surfaces de détail.",
            emptyTitle: "Aucune exécution ne correspond pour l'instant",
            emptyDescription:
              "Quand rien n'apparaît, les filtres peuvent être trop stricts ou l'espace de travail peut encore être calme.",
            unavailableTitle: "L'historique des exécutions peut aussi échouer avec élégance",
            unavailableDescription:
              "Quand le backend est indisponible, cette zone doit expliquer clairement le problème au lieu de laisser la page vide.",
          },
          memoryPrimary: {
            title: "Mémoire cartographie le contexte durable",
            description:
              "Utilisez cette zone pour inspecter ce que l'espace de travail apprend, regroupe et garde disponible pour les bots.",
          },
          costsPrimary: {
            title: "Coûts explique la consommation et l'efficacité",
            description:
              "Cette page aide à comparer dépenses, répartition et impact opérationnel entre bots et fenêtres temporelles.",
          },
          schedulesPrimary: {
            title: "Planifications centralise les routines",
            description:
              "Passez en revue cadence, tâches en pause et couverture d'automatisation ici quand vous devez inspecter le travail récurrent.",
          },
          dlqPrimary: {
            title: "La file des messages non distribués isole les échecs",
            description:
              "Venez ici pour inspecter les tentatives, l'état brut des échecs et les décisions de récupération quand les tâches sortent du chemin heureux.",
          },
          systemSettingsPrimary: {
            title: "Paramètres système contient la gouvernance globale",
            description:
              "C'est ici que fournisseurs, valeurs par défaut et contrôles partagés sont configurés pour tout l'espace de travail.",
          },
        },
        complete: {
          title: "Vous êtes prêt à explorer Koda",
          description:
            "Rouvrez la visite à tout moment depuis Docs si vous voulez un rappel ou visiter un chapitre secondaire.",
        },
      },
      agentSwitcher: {
        placeholder: "Sélectionner un bot",
        ariaSingle: "Sélectionner un bot",
        ariaMultiple: "Sélectionner des bots",
        searchPlaceholder: "Rechercher un bot",
        allAgents: "Tous les bots",
        agentsVisible: "{{count}} bots visibles",
        agentsSelected: "{{count}} bots sélectionnés",
        agentsSelectedOutOfTotal: "{{selected}} sur {{total}} bots sélectionnés",
        noAgentFilter: "Aucun filtre bot",
        selectOne: "Choisissez un bot",
        noResults: "Aucun bot trouvé",
      },
      async: {
        loading: "Chargement",
        updating: "Mise à jour",
        synced: "Synchronisé",
        ready: "Prêt",
        retry: "Réessayer",
      },
      statuses: {
        all: "Tous",
        completed: "Terminé",
        running: "En cours",
        queued: "En file d'attente",
        failed: "Échoué",
        retrying: "Nouvelle tentative",
      },
      costs: {
        filters: {
          agents: "Bots",
          period: "Période",
          model: "Modèle",
          taskType: "Type de tâche",
          periods: {
            "7d": "7 jours",
            "30d": "30 jours",
            "90d": "90 jours",
          },
        },
        mode: {
          byAgent: "Par bot",
          byModel: "Par modèle",
        },
        kpis: {
          totalPeriod: "Total sur la période",
          today: "Aujourd'hui",
          costPerResolved: "Coût par conversation résolue",
          peakBucket: "Pic de la période",
        },
        chart: {
          eyebrow: "Origine temporelle",
          title: "Où le coût naît dans la période",
          description:
            "Compartiments empilés pour révéler les pics, la dispersion et le principal moteur de coût.",
        },
        allocation: {
          eyebrow: "Répartition",
          title: "Répartition de la consommation",
          description: "Une lecture compacte de là où le coût est concentré dans la coupe actuelle.",
        },
        ledger: {
          eyebrow: "Registre des coûts",
          title: "Opérations par coût",
          count: "{{count}} enregistrements",
        },
      },
      executions: {
        searchPlaceholder: "Rechercher requête, session ou modèle",
        unavailable: "Exécutions indisponibles",
        loadError: "Impossible de charger les exécutions.",
        noSelection: "Aucune exécution sélectionnée.",
        retryLabel: "Nouvelle tentative",
      },
      sessions: {
        searchPlaceholder: "Rechercher par session, nom ou dernier message",
        noSelection: "Aucune conversation sélectionnée.",
        loadError: "Impossible de charger la conversation.",
        chatWithAgent: "Discuter avec {{bot}}",
        composerHelper:
          "L'interface est prête pour le flux de conversation avec le bot. L'envoi réel dépend de l'endpoint du runtime.",
        composerIdle:
          "Choisissez une conversation pour explorer l'historique ou préparer une nouvelle interaction.",
        sendUnavailable:
          "Ce runtime de bot n'expose pas encore d'endpoint HTTP pour le chat web Koda.",
      },
      memory: {
        views: {
          map: "Mémoire",
          curation: "Curation",
        },
        filters: {
          title: "Filtres",
          intro:
            "Ajustez la coupe par utilisateur, session, temps et types de mémoire avant d'explorer les connexions de la carte.",
          search: "Rechercher dans la carte",
          searchPlaceholder: "Contenu, source ou apprentissage...",
          user: "Utilisateur",
          session: "Session",
          timeWindow: "Fenêtre temporelle",
          includeInactive: "Inclure les mémoires inactives",
          edges: {
            semantic: "Sémantique",
            session: "Session",
            source: "Source",
          },
        },
        empty: {
          title: "Aucune mémoire à afficher pour le moment",
          description:
            "Lorsque ce bot commencera à consolider des faits, décisions, tâches ou problèmes, la carte organisera ces mémoires en un maillage vivant de contexte et d'apprentissage.",
        },
      },
      schedules: {
        loading: "Chargement",
        jobs: "planifications",
        active: "actif",
      },
      dlq: {
        filters: {
          all: "Tous",
          eligible: "Éligible à la réexécution",
          ineligible: "Pas de réexécution",
        },
      },
      controlPlane: {
        botCreate: {
          promptPlaceholder:
            "Vous êtes un assistant spécialisé dans...\n\nVotre objectif est d'aider les utilisateurs à...\n\nRègles :\n- Soyez clair et concis\n- Répondez toujours en français",
        },
      },
      settings: {
        sections: {
          general: {
            label: "Général",
            description: "Fuseau horaire et préférences régionales.",
          },
          models: {
            label: "Modèles et fournisseurs",
            description: "Fournisseurs d'IA, sélection de modèle et contrôles d'utilisation.",
          },
          integrations: {
            label: "Intégrations",
            description: "Services externes et serveurs MCP tels que Jira, Google, bases de données et passerelles d'outils sélectionnées.",
          },
          providers: {
            label: "Fournisseurs",
            description: "Fournisseurs d'IA pour modèles de langage, voix et médias.",
          },
          mcp: {
            label: "Serveurs MCP",
            description: "Serveurs Model Context Protocol pour étendre les outils des agents.",
          },
          intelligence: {
            label: "Intelligence",
            description: "Mémoire, connaissance et gouvernance de l'autonomie.",
          },
          variables: {
            label: "Variables et secrets",
            description: "Variables système et secrets pour les opérations des agents.",
          },
        },
      },
      auth: {
        login: {
          title: "Bon retour",
          subtitle: "Connectez-vous pour accéder à l'espace de travail opérationnel.",
          identifier: "E-mail ou nom d'utilisateur",
          password: "Mot de passe",
          submit: "Se connecter",
          submitting: "Connexion...",
          forgot_link: "Mot de passe ou code de récupération oublié ?",
          generic_error: "Les identifiants fournis ne correspondent pas. Veuillez réessayer.",
        },
        forgot: {
          title: "Récupérer l'accès",
          subtitle: "Utilisez un code de récupération pour définir un nouveau mot de passe.",
          identifier: "E-mail ou nom d'utilisateur",
          recovery_code: "Code de récupération",
          new_password: "Nouveau mot de passe",
          confirm_password: "Confirmer le nouveau mot de passe",
          submit: "Réinitialiser le mot de passe",
          submitting: "Réinitialisation...",
          back_to_login: "Retour à la connexion",
          success_title: "Mot de passe mis à jour",
          success: "Vous pouvez maintenant vous connecter avec votre nouveau mot de passe.",
          password_too_short: "Le mot de passe doit contenir au moins {{n}} caractères.",
          password_mismatch: "Les mots de passe ne correspondent pas.",
          generic_error: "Les informations fournies sont invalides ou expirées. Veuillez réessayer.",
        },
        setup: {
          create_account: {
            title: "Créer le compte propriétaire",
            subtitle: "Configurez le premier opérateur pour débloquer l'espace de travail.",
            email: "E-mail professionnel",
            password: "Mot de passe",
            password_hint: "Minimum 12 caractères.",
            confirm_password: "Confirmer le mot de passe",
            bootstrap_code: "Code de bootstrap",
            bootstrap_hint: "Utilisez le code de bootstrap unique imprimé par l'installateur.",
            bootstrap_hint_generic: "Fournissez le code de bootstrap émis pour cette instance.",
            submit: "Créer le compte",
            submitting: "Création...",
            errors: {
              bootstrap_required: "Le code de bootstrap est requis.",
              email_invalid: "Saisissez une adresse e-mail valide.",
              password_too_short: "Le mot de passe doit contenir au moins {{n}} caractères.",
              password_mismatch: "Les mots de passe ne correspondent pas.",
              generic: "Nous n'avons pas pu créer le compte. Veuillez réessayer.",
            },
          },
          recovery_codes: {
            title: "Enregistrez vos codes de récupération",
            subtitle: "Conservez ces codes dans un endroit sûr. Chaque code ne fonctionne qu'une seule fois.",
            file_header: "Codes de récupération Koda",
            copy_all: "Tout copier",
            copied: "Copié",
            download: "Télécharger",
            print: "Imprimer",
            saved_checkbox: "J'ai enregistré les codes de récupération dans un endroit sûr.",
            continue: "Continuer vers l'espace de travail",
            already_shown_banner: "Ces codes ne seront plus affichés.",
          },
        },
        settings: {
          security: {
            title: "Sécurité",
            change_password: "Changer le mot de passe",
            need_current_password: "Saisissez votre mot de passe actuel pour continuer.",
            regenerate_codes: "Régénérer les codes de récupération",
            codes_remaining: "{{count}} codes de récupération restants",
          },
        },
      },
    },
  },
  "de-DE": {
    translation: {
      app: {
        name: "Koda",
        description:
          "Koda ist der operative Arbeitsbereich zur Echtzeit-Überwachung von Agenten, Ausführungen, Kosten, Speicher und Routinen.",
        skipToContent: "Zum Hauptinhalt springen",
      },
      language: {
        label: "Sprache",
        placeholder: "Sprache",
        options: {
          "en-US": "English (US)",
          "pt-BR": "Português (Brasil)",
          "es-ES": "Español",
          "fr-FR": "Français",
          "de-DE": "Deutsch",
        },
      },
      theme: {
        label: "Design",
        placeholder: "Design",
        options: {
          system: "System",
          light: "Hell",
          dark: "Dunkel",
        },
      },
      common: {
        loading: "Lädt",
        ready: "Bereit",
        synced: "Synchronisiert",
        updating: "Aktualisierung",
        retry: "Erneut versuchen",
        search: "Suchen",
        ask: "Fragen",
        docs: "Dokumentation",
        files: "Dateien",
        notifications: "Benachrichtigungen",
        allAgents: "Alle Bots",
        allModels: "Alle Modelle",
        allTypes: "Alle Typen",
        allUsers: "Alle Benutzer",
        allSessions: "Alle Sitzungen",
        now: "jetzt",
        agent: "Bot",
        status: "Status",
        cost: "Kosten",
        duration: "Dauer",
        created: "Erstellt",
        source: "Quelle",
        session: "Sitzung",
        query: "Abfrage",
        summary: "Zusammenfassung",
        active: "Aktiv",
        paused: "Pausiert",
        resolved: "Gelöst",
        failed: "Fehlgeschlagen",
      },
      routeMeta: {
        system: {
          eyebrow: "Koda",
          title: "System",
          summary: "Globale Governance, Anbieter und gemeinsam genutzte Ressourcen.",
        },
        agents: {
          eyebrow: "Koda",
          title: "Agenten",
          summary: "Katalog, Bearbeitung und Veröffentlichung für Agenten.",
        },
        runtime: {
          eyebrow: "Laufzeit",
          title: "Steuerungsebene",
          summary: "Bots, Umgebungen und Live-Oberflächen.",
        },
        overview: {
          eyebrow: "Arbeitsbereich",
          title: "Übersicht",
          summary: "Puls für Bots, Kosten und Aktivität.",
        },
        executions: {
          eyebrow: "Operationen",
          title: "Ausführungen",
          summary: "Aufgaben, Traces und aktueller Zustand.",
        },
        memory: {
          eyebrow: "Kontext",
          title: "Speicher",
          summary: "Karte, Kuration und Kontext pro Bot.",
        },
        sessions: {
          eyebrow: "Unterhaltungen",
          title: "Sitzungen",
          summary: "Chats, Antworten und verknüpfte Ausführungen.",
        },
        costs: {
          eyebrow: "Verbrauch",
          title: "Kosten",
          summary: "Verbrauch, Verteilung und Effizienz.",
        },
        schedules: {
          eyebrow: "Routinen",
          title: "Zeitpläne",
          summary: "Routinen, Takt und Abdeckung.",
        },
        dlq: {
          eyebrow: "Wiederherstellung",
          title: "Dead-Letter-Queue",
          summary: "Fehler, Wiederholungen und Diagnose.",
        },
        fallback: {
          eyebrow: "Koda",
          title: "Arbeitsbereich",
          summary: "Koda-Operationszentrum.",
        },
      },
      sidebar: {
        ariaLabel: "Hauptnavigation",
        newSession: "Neue Sitzung",
        newSessionLabel: "Eine neue Sitzung starten",
        recents: "Zuletzt verwendet",
        clearRecents: "Zuletzt verwendet löschen",
        noRecents: "Ihre zuletzt besuchten Routen erscheinen hier.",
        sections: {
          atlas: "Koda",
          operations: "Operationen",
          analysis: "Analyse",
          system: "System",
        },
        items: {
          home: "Start",
          runtime: "Laufzeit",
          agents: "Agenten",
          executions: "Ausführungen",
          sessions: "Sitzungen",
          costs: "Kosten",
          memory: "Speicher",
          schedules: "Zeitpläne",
          dlq: "Dead-Letter-Queue",
          generalSettings: "Allgemeine Einstellungen",
        },
        loading: {
          home: "Start wird geöffnet",
          runtime: "Laufzeit wird geöffnet",
          agents: "Agenten werden geöffnet",
          executions: "Ausführungen werden geöffnet",
          sessions: "Sitzungen werden geöffnet",
          costs: "Kosten werden geöffnet",
          memory: "Speicher wird geöffnet",
          schedules: "Zeitpläne werden geöffnet",
          dlq: "Dead-Letter-Queue wird geöffnet",
          generalSettings: "Allgemeine Einstellungen werden geöffnet",
        },
      },
      topbar: {
        openMenu: "Menü öffnen",
        expandSidebar: "Seitenleiste erweitern",
        collapseSidebar: "Seitenleiste einklappen",
        docs: {
          eyebrow: "Dokumentation",
          title: "Koda-Operationsbasis",
          description: "Schnelle Anleitungen zur Navigation durch die kritischen Oberflächen des Arbeitsbereichs.",
          entries: {
            dailyOps: {
              eyebrow: "Playbook",
              title: "Tägliche Operationen",
              description: "Ausführungen, Sitzungen und Vorfälle in einem einzigen Ablauf.",
            },
            governance: {
              eyebrow: "System",
              title: "Koda-Governance",
              description: "Globale Standards, Anbieter und gemeinsame Freigaben.",
            },
            memory: {
              eyebrow: "Kontext",
              title: "Speicher und Kuration",
              description: "Karten, Cluster und operative Signale pro Bot.",
            },
          },
        },
        ask: {
          eyebrow: "Fragen",
          title: "Koda fragen",
          description: "Schnelle Antwort, die Sie direkt zur richtigen Oberfläche bringt.",
          placeholder: "Beispiel: Wo sehe ich heute kritische ATLAS-Ausfälle?",
          responseLabel: "Antwort",
          button: "Fragen",
          loadingButton: "Analyse läuft...",
          loadingCopy: "Koda verbindet den operativen Kontext, um gezielt zu antworten.",
          initialReply:
            "Fragen Sie zu Operationen, Kosten, Speicher oder Governance – ich leite Sie zur passenden Koda-Oberfläche weiter.",
          suggestions: {
            failures: "Wie priorisiere ich Ausfälle in der Dead-Letter-Queue?",
            cost: "Welcher Bildschirm zeigt Kostenengpässe am schnellsten?",
            schedules: "Wo kann ich pausierte Routinen überprüfen?",
          },
          replies: {
            failures:
              "Beginnen Sie mit der Dead-Letter-Queue, um die Quelle zu isolieren, Wiederholungen zu validieren und den Rohdaten-Payload zu prüfen, wenn Sie die Ursache bestätigen müssen.",
            cost:
              "Öffnen Sie Kosten, um die Verteilung pro Bot zu vergleichen, und gleichen Sie mit Ausführungen ab, um zu verstehen, welcher Ablauf den Verbrauch erhöht hat.",
            schedules:
              "Zeitpläne zentralisiert den Routinestatus. Nutzen Sie den Bot-Filter, um Aktives, Pausiertes und Ungedecktes zu trennen.",
            sessions:
              "Sitzungen ist die ideale Oberfläche für die direkte Interaktion mit einem Bot – Verlauf und Nachrichtenversand am selben Ort.",
            fallback:
              "Nutzen Sie Ausführungen für den operativen Puls, Sitzungen für direkte Unterhaltungen, Speicher für Kontext und System, wenn es um Standards oder Governance geht.",
          },
        },
        files: {
          eyebrow: "Dateien",
          title: "Zuletzt verwendete Verknüpfungen",
          description: "Dateien und Kataloge, die im jüngsten operativen Ablauf am häufigsten verwendet wurden.",
          entries: {
            runtime: {
              detail: "Operationen, Traces und priorisierte Routinen",
              updatedAt: "vor 12 Min",
            },
            governance: {
              detail: "Live-Katalog von Standards, Richtlinien und Integrationen",
              updatedAt: "vor 36 Min",
            },
            memory: {
              detail: "Aktuelle Signale und Relevanzanpassungen",
              updatedAt: "vor 2 Std",
            },
            costs: {
              detail: "Aktuelle Verbrauchsverteilung pro Bot",
              updatedAt: "vor 4 Std",
            },
          },
        },
        notifications: {
          eyebrow: "Benachrichtigungen",
          title: "Aktuelle Updates",
          description: "Aktuelle Verbesserungen und Änderungen in Koda im Kurzüberblick.",
          summaryLeft: "{{count}} aktuelle Updates",
          summaryRight: "Alles an einem Ort",
          entries: {
            sessions: {
              section: "Sitzungen",
              title: "Neue operative Ansicht für Sitzungen",
              description:
                "Der Bildschirm öffnet sich jetzt im Chat-Format mit direkter Bot-Auswahl und festem Composer.",
              timestamp: "Heute",
            },
            memory: {
              section: "Speicher",
              title: "Speicher verfeinert",
              description: "Karte neu gestaltet und Kuration mit besserer vertikaler Nutzung.",
              timestamp: "Gestern",
            },
            system: {
              section: "System",
              title: "Vereinheitlichte Governance",
              description:
                "System und Katalog folgen jetzt derselben visuellen und modalen Grundlage.",
              timestamp: "vor 2 Tagen",
            },
          },
        },
      },
      tour: {
        actions: {
          start: "Tour starten",
          back: "Zurück",
          continue: "Weiter",
          skip: "Tour überspringen",
          finish: "Tour beenden",
        },
        progress: {
          start: "Erste Schritte",
          value: "{{current}} von {{total}}",
        },
        confirmSkip: "Möchten Sie die geführte Tour überspringen?",
        topbar: {
          eyebrow: "Tour",
          title: "Geführte Tour",
          description: "Öffnen Sie eine geführte Tour für diesen Arbeitsbereich oder die aktuelle Seite.",
          resumeTitle: "Geführte Tour fortsetzen",
          resumeDescription: "Setzen Sie die aktuelle Tour an der Stelle fort, an der Sie aufgehört haben.",
        },
        welcome: {
          title: "Beginnen Sie mit einer kurzen geführten Tour",
          description:
            "Koda führt Sie durch die Hauptbildschirme, wie Sie zwischen ihnen wechseln und was jeder Bereich bedeutet. Der Ablauf bleibt zielgerichtet und Sie können jederzeit abbrechen.",
        },
        steps: {
          shellSidebar: {
            title: "Diese Seitenleiste ist Ihre Hauptkarte",
            description:
              "Nutzen Sie sie, um zwischen Übersicht, Laufzeit, Katalog und operativen Ansichten zu wechseln, ohne den Kontext zu verlieren.",
          },
          shellTopbar: {
            title: "Die obere Leiste hält den Routenkontext nah",
            description:
              "Hier sehen Sie die Zusammenfassung der aktiven Seite, Schnellwerkzeuge, den Sprachumschalter und die Verknüpfung, um diese Tour später erneut zu öffnen.",
          },
          overviewMetrics: {
            title: "Übersicht fasst den operativen Puls zusammen",
            description:
              "Dieser erste Block verdichtet Aktivität, Nachfrage und Kosten, damit Sie verstehen, was sich geändert hat, bevor Sie tiefer einsteigen.",
            emptyTitle: "Übersicht startet als Ihr leerer operativer Puls",
            emptyDescription:
              "Schon bevor Aktivität erscheint, ist diese Seite der Ort, an den Sie für die schnellste Zusammenfassung des Arbeitsbereichs zurückkehren.",
          },
          overviewLivePlan: {
            title: "Dieser Abschnitt hebt die nächsten Live-Aktionen hervor",
            description:
              "Nutzen Sie ihn, um zu erkennen, was jetzt läuft, was Aufmerksamkeit braucht und wo die Untersuchung fortgesetzt werden sollte.",
          },
          controlPlanePrimaryAction: {
            title: "Der Katalog ist der Startpunkt der Einrichtung",
            description:
              "Erstellen Sie hier Bots und Arbeitsbereiche und öffnen Sie dann einen Bot, um Identität, Verhalten, Ressourcen und Veröffentlichung zu konfigurieren.",
            emptyTitle: "Der Katalog ist Ihr erster Halt bei einer neuen Installation",
            emptyDescription:
              "Wenn die Instanz leer ist, beginnen Sie hier, indem Sie einen Arbeitsbereich oder einen Bot erstellen. Der Editor öffnet sich direkt danach.",
          },
          controlPlaneBoard: {
            title: "Das Board erklärt, wie der Katalog organisiert ist",
            description:
              "Arbeitsbereiche, Squads und Bots bleiben hier gruppiert, damit Governance und Verantwortung auf einen Blick sichtbar sind.",
            emptyTitle: "Das Board wächst mit dem Katalog",
            emptyDescription:
              "Sobald Bots existieren, wird dieser Bereich zur visuellen Karte von Teams, Arbeitsbereichen und operativer Verantwortung.",
          },
          controlPlaneEditorHeader: {
            title: "Der Editor ist das Kontrollzentrum des Bots",
            description:
              "Diese Kopfzeile zeigt, welchen Bot Sie bearbeiten, und hält die Hauptaktionen Speichern und Veröffentlichung prüfen nah.",
          },
          controlPlaneEditorSteps: {
            title: "Diese Abschnitte organisieren die vollständige Bot-Einrichtung",
            description:
              "Bewegen Sie sich durch Identität, Verhalten, Ressourcen, Speicher, Umfang und Veröffentlichung, ohne Zuständigkeiten zu vermischen.",
          },
          controlPlaneEditorPublish: {
            title: "Erst speichern, dann mit Vertrauen veröffentlichen",
            description:
              "Nutzen Sie diese Aktionen, um Entwurfsänderungen zu persistieren und zur Veröffentlichungsprüfung voranzuschreiten, wenn der Bot bereit ist.",
          },
          runtimeHeader: {
            title: "Laufzeit ist der Live-Kontrollraum",
            description:
              "Dieser Bildschirm bündelt Ausführungsgesundheit, Live-Aktivität und Filter, damit Sie sich auf die aktuell wichtigen Bots konzentrieren können.",
            emptyTitle: "Laufzeit wird nützlich, sobald Aktivität erscheint",
            emptyDescription:
              "Wenn es noch keine Live-Umgebungen gibt, betrachten Sie diese Seite als den Ort, an dem Live-Aktivität zuerst erscheint.",
            unavailableTitle: "Laufzeit signalisiert auch Verfügbarkeitsprobleme schnell",
            unavailableDescription:
              "Wenn die Laufzeitkonnektivität beeinträchtigt ist, ist diese Oberfläche der Ort, an dem die App diesen Zustand vor tieferer Analyse offenlegt.",
          },
          runtimeLiveList: {
            title: "Metriken zeigen, wie viel Aufmerksamkeit die Laufzeit benötigt",
            description:
              "Nutzen Sie diese Indikatoren, um Online-Abdeckung, Live-Ausführungen und die aktuelle Aufmerksamkeitslast einzuschätzen.",
            emptyTitle: "Noch keine Live-Ausführungen",
            emptyDescription:
              "Wenn die Liste leer ist, bestätigt dies dennoch, dass die Laufzeit ruhig ist, statt den Zustand zu verbergen.",
          },
          sessionsRail: {
            title: "Sitzungen ist die Leiste des Unterhaltungsverlaufs",
            description:
              "Suchen und wechseln Sie Unterhaltungen hier, um den Dialogverlauf jedes Bots einzusehen.",
            emptyTitle: "Sitzungen wird zum Chat-Index",
            emptyDescription:
              "Sobald Unterhaltungen existieren, wird diese Leiste zum schnellsten Weg, zwischen ihnen zu wechseln.",
          },
          sessionsThread: {
            title: "Der Thread hält Nachrichten und Kontext zusammen",
            description:
              "Dieser Bereich zeigt die ausgewählte Unterhaltung, während Composer und Kontextpanel Folgeaktionen nah halten.",
            emptyTitle: "Sie können hier eine Unterhaltung starten",
            emptyDescription:
              "Wenn noch kein Thread existiert, wählen Sie einen Bot im Composer und starten Sie die erste Unterhaltung von dieser Oberfläche aus.",
          },
          executionsFilters: {
            title: "Ausführungen beginnt mit schnellem Filtern",
            description:
              "Nutzen Sie Suche, Bot-Auswahl und Status-Chips, um den Verlauf einzugrenzen, bevor Sie eine bestimmte Aufgabe öffnen.",
            unavailableTitle: "Ausführungen signalisiert auch, wenn der Feed nicht verfügbar ist",
            unavailableDescription:
              "Wenn die Liste nicht geladen werden kann, ist dies der Bereich, in dem Sie es erneut versuchen und den Zustand des operativen Feeds bestätigen.",
          },
          executionsTable: {
            title: "Die Tabelle ist das Rückgrat des Ausführungsverlaufs",
            description:
              "Öffnen Sie Aufgaben von hier, um Dauer, Kosten, Warnungen und Detailoberflächen einzusehen.",
            emptyTitle: "Noch keine Ausführungen passend",
            emptyDescription:
              "Wenn nichts erscheint, sind die Filter möglicherweise zu streng oder der Arbeitsbereich ist noch ruhig.",
            unavailableTitle: "Der Ausführungsverlauf kann auch elegant scheitern",
            unavailableDescription:
              "Wenn das Backend nicht verfügbar ist, sollte dieser Bereich das Problem klar erklären, anstatt die Seite leer zu lassen.",
          },
          memoryPrimary: {
            title: "Speicher kartiert langlebigen Kontext",
            description:
              "Nutzen Sie diesen Bereich, um zu prüfen, was der Arbeitsbereich lernt, clustert und für Bots verfügbar hält.",
          },
          costsPrimary: {
            title: "Kosten erklärt Verbrauch und Effizienz",
            description:
              "Diese Seite hilft, Ausgaben, Verteilung und operative Auswirkung über Bots und Zeitfenster hinweg zu vergleichen.",
          },
          schedulesPrimary: {
            title: "Zeitpläne zentralisiert Routinen",
            description:
              "Überprüfen Sie Takt, pausierte Jobs und Automatisierungsabdeckung hier, wenn Sie wiederkehrende Arbeit inspizieren müssen.",
          },
          dlqPrimary: {
            title: "Dead-Letter-Queue isoliert Fehler",
            description:
              "Kommen Sie hierher, um Wiederholungen, Rohfehlerzustände und Wiederherstellungsentscheidungen zu prüfen, wenn Aufgaben vom Happy Path abweichen.",
          },
          systemSettingsPrimary: {
            title: "Systemeinstellungen enthält die globale Governance",
            description:
              "Hier werden Anbieter, Standards und gemeinsame Steuerungen für den gesamten Arbeitsbereich konfiguriert.",
          },
        },
        complete: {
          title: "Sie sind bereit, Koda zu erkunden",
          description:
            "Öffnen Sie die Tour jederzeit aus Docs erneut, wenn Sie eine Auffrischung oder ein Nebenkapitel möchten.",
        },
      },
      agentSwitcher: {
        placeholder: "Bot auswählen",
        ariaSingle: "Bot auswählen",
        ariaMultiple: "Bots auswählen",
        searchPlaceholder: "Bot suchen",
        allAgents: "Alle Bots",
        agentsVisible: "{{count}} Bots sichtbar",
        agentsSelected: "{{count}} Bots ausgewählt",
        agentsSelectedOutOfTotal: "{{selected}} von {{total}} Bots ausgewählt",
        noAgentFilter: "Kein Bot-Filter",
        selectOne: "Bot wählen",
        noResults: "Keine Bots gefunden",
      },
      async: {
        loading: "Lädt",
        updating: "Aktualisierung",
        synced: "Synchronisiert",
        ready: "Bereit",
        retry: "Erneut versuchen",
      },
      statuses: {
        all: "Alle",
        completed: "Abgeschlossen",
        running: "Läuft",
        queued: "In Warteschlange",
        failed: "Fehlgeschlagen",
        retrying: "Wiederholung",
      },
      costs: {
        filters: {
          agents: "Bots",
          period: "Zeitraum",
          model: "Modell",
          taskType: "Aufgabentyp",
          periods: {
            "7d": "7 Tage",
            "30d": "30 Tage",
            "90d": "90 Tage",
          },
        },
        mode: {
          byAgent: "Nach Bot",
          byModel: "Nach Modell",
        },
        kpis: {
          totalPeriod: "Gesamt im Zeitraum",
          today: "Heute",
          costPerResolved: "Kosten pro gelöster Unterhaltung",
          peakBucket: "Spitze im Zeitraum",
        },
        chart: {
          eyebrow: "Zeitlicher Ursprung",
          title: "Wo im Zeitraum Kosten entstehen",
          description:
            "Gestapelte Buckets zur Offenlegung von Spitzen, Streuung und dem dominanten Kostenfaktor.",
        },
        allocation: {
          eyebrow: "Zuteilung",
          title: "Zuteilung des Verbrauchs",
          description: "Eine kompakte Darstellung, wo sich die Kosten im aktuellen Schnitt konzentrieren.",
        },
        ledger: {
          eyebrow: "Kostenbuch",
          title: "Operationen nach Kosten",
          count: "{{count}} Einträge",
        },
      },
      executions: {
        searchPlaceholder: "Abfrage, Sitzung oder Modell suchen",
        unavailable: "Ausführungen nicht verfügbar",
        loadError: "Ausführungen konnten nicht geladen werden.",
        noSelection: "Keine Ausführung ausgewählt.",
        retryLabel: "Wiederholung",
      },
      sessions: {
        searchPlaceholder: "Nach Sitzung, Name oder letzter Nachricht suchen",
        noSelection: "Keine Unterhaltung ausgewählt.",
        loadError: "Die Unterhaltung konnte nicht geladen werden.",
        chatWithAgent: "Mit {{bot}} chatten",
        composerHelper:
          "Die Oberfläche ist bereit für den Bot-Unterhaltungsablauf. Der tatsächliche Versand hängt vom Laufzeit-Endpunkt ab.",
        composerIdle:
          "Wählen Sie eine Unterhaltung, um den Verlauf zu erkunden oder eine neue Interaktion vorzubereiten.",
        sendUnavailable:
          "Diese Bot-Laufzeit bietet noch keinen HTTP-Endpunkt für den Koda-Webchat an.",
      },
      memory: {
        views: {
          map: "Speicher",
          curation: "Kuration",
        },
        filters: {
          title: "Filter",
          intro:
            "Passen Sie den Ausschnitt nach Benutzer, Sitzung, Zeit und Speichertypen an, bevor Sie Kartenverbindungen erkunden.",
          search: "In Karte suchen",
          searchPlaceholder: "Inhalt, Quelle oder Lernen...",
          user: "Benutzer",
          session: "Sitzung",
          timeWindow: "Zeitfenster",
          includeInactive: "Inaktive Speicher einschließen",
          edges: {
            semantic: "Semantisch",
            session: "Sitzung",
            source: "Quelle",
          },
        },
        empty: {
          title: "Es gibt noch keine Speicher anzuzeigen",
          description:
            "Sobald dieser Bot beginnt, Fakten, Entscheidungen, Aufgaben oder Probleme zu konsolidieren, organisiert die Karte diese Speicher zu einem lebendigen Netz aus Kontext und Lernen.",
        },
      },
      schedules: {
        loading: "Lädt",
        jobs: "Zeitpläne",
        active: "aktiv",
      },
      dlq: {
        filters: {
          all: "Alle",
          eligible: "Wiederholung möglich",
          ineligible: "Keine Wiederholung",
        },
      },
      controlPlane: {
        botCreate: {
          promptPlaceholder:
            "Sie sind ein spezialisierter Assistent für...\n\nIhr Ziel ist es, Benutzern zu helfen bei...\n\nRegeln:\n- Klar und sachlich sein\n- Stets auf Deutsch antworten",
        },
      },
      settings: {
        sections: {
          general: {
            label: "Allgemein",
            description: "Zeitzone und regionale Einstellungen.",
          },
          models: {
            label: "Modelle und Anbieter",
            description: "KI-Anbieter, Modellauswahl und Nutzungskontrollen.",
          },
          integrations: {
            label: "Integrationen",
            description: "Externe Dienste und MCP-Server wie Jira, Google, Datenbanken und kuratierte Tool-Brücken.",
          },
          providers: {
            label: "Anbieter",
            description: "KI-Anbieter für Sprachmodelle, Stimme und Medien.",
          },
          mcp: {
            label: "MCP-Server",
            description: "Model-Context-Protocol-Server zur Erweiterung von Agenten-Tools.",
          },
          intelligence: {
            label: "Intelligenz",
            description: "Speicher-, Wissens- und Autonomie-Governance.",
          },
          variables: {
            label: "Variablen und Geheimnisse",
            description: "Systemvariablen und Geheimnisse für Agentenoperationen.",
          },
        },
      },
      auth: {
        login: {
          title: "Willkommen zurück",
          subtitle: "Melden Sie sich an, um auf den operativen Arbeitsbereich zuzugreifen.",
          identifier: "E-Mail oder Benutzername",
          password: "Passwort",
          submit: "Anmelden",
          submitting: "Anmeldung...",
          forgot_link: "Passwort oder Wiederherstellungscode vergessen?",
          generic_error: "Die angegebenen Zugangsdaten stimmen nicht überein. Bitte erneut versuchen.",
        },
        forgot: {
          title: "Zugriff wiederherstellen",
          subtitle: "Verwenden Sie einen Wiederherstellungscode, um ein neues Passwort festzulegen.",
          identifier: "E-Mail oder Benutzername",
          recovery_code: "Wiederherstellungscode",
          new_password: "Neues Passwort",
          confirm_password: "Neues Passwort bestätigen",
          submit: "Passwort zurücksetzen",
          submitting: "Zurücksetzen...",
          back_to_login: "Zurück zur Anmeldung",
          success_title: "Passwort aktualisiert",
          success: "Sie können sich jetzt mit Ihrem neuen Passwort anmelden.",
          password_too_short: "Das Passwort muss mindestens {{n}} Zeichen lang sein.",
          password_mismatch: "Die Passwörter stimmen nicht überein.",
          generic_error: "Die angegebenen Informationen sind ungültig oder abgelaufen. Bitte erneut versuchen.",
        },
        setup: {
          create_account: {
            title: "Besitzerkonto erstellen",
            subtitle: "Richten Sie den ersten Operator ein, um den Arbeitsbereich freizuschalten.",
            email: "Geschäftliche E-Mail",
            password: "Passwort",
            password_hint: "Mindestens 12 Zeichen.",
            confirm_password: "Passwort bestätigen",
            bootstrap_code: "Bootstrap-Code",
            bootstrap_hint: "Verwenden Sie den vom Installer einmalig ausgegebenen Bootstrap-Code.",
            bootstrap_hint_generic: "Geben Sie den für diese Instanz ausgegebenen Bootstrap-Code ein.",
            submit: "Konto erstellen",
            submitting: "Erstellen...",
            errors: {
              bootstrap_required: "Der Bootstrap-Code ist erforderlich.",
              email_invalid: "Geben Sie eine gültige E-Mail-Adresse ein.",
              password_too_short: "Das Passwort muss mindestens {{n}} Zeichen lang sein.",
              password_mismatch: "Die Passwörter stimmen nicht überein.",
              generic: "Das Konto konnte nicht erstellt werden. Bitte erneut versuchen.",
            },
          },
          recovery_codes: {
            title: "Speichern Sie Ihre Wiederherstellungscodes",
            subtitle: "Bewahren Sie diese Codes sicher auf. Jeder Code funktioniert nur einmal.",
            file_header: "Koda-Wiederherstellungscodes",
            copy_all: "Alle kopieren",
            copied: "Kopiert",
            download: "Herunterladen",
            print: "Drucken",
            saved_checkbox: "Ich habe die Wiederherstellungscodes sicher aufbewahrt.",
            continue: "Weiter zum Arbeitsbereich",
            already_shown_banner: "Diese Codes werden nicht erneut angezeigt.",
          },
        },
        settings: {
          security: {
            title: "Sicherheit",
            change_password: "Passwort ändern",
            need_current_password: "Geben Sie Ihr aktuelles Passwort ein, um fortzufahren.",
            regenerate_codes: "Wiederherstellungscodes neu generieren",
            codes_remaining: "{{count}} Wiederherstellungscodes verbleibend",
          },
        },
      },
    },
  },
} as const;

export const literalResources = {
  "en-US": {
    "Ativo": "Active",
    "Pausado": "Paused",
    "Movendo": "Moving",
    "Sem modelo definido": "No model configured",
    "Selecionar": "Select",
    "Desselecionar": "Deselect",
    "Agente": "Agent",
    "Abrir ações do agente": "Open agent actions",
    "Editar": "Edit",
    "Duplicar": "Duplicate",
    "Excluir": "Delete",
    "Voltar": "Back",
    "Próximo": "Next",
    "Aplicando": "Applying",
    "Descartar": "Discard",
    "Salvar alterações": "Save changes",
    "Conta e operação": "Account and operations",
    "Modelos": "Models",
    "Integrações externas": "External integrations",
    "Memória e conhecimento": "Memory and knowledge",
    "Vault de variáveis": "Variables vault",
    "Revisão e aplicação": "Review and apply",
    "Responsável principal": "Primary owner",
    "Email operacional": "Operational email",
    "Usuário GitHub": "GitHub username",
    "Timezone padrão": "Default timezone",
    "Aplicado aos agendamentos e à operação global do sistema.": "Applied to schedules and global system operations.",
    "Diretório padrão de trabalho": "Default working directory",
    "Raiz usada quando o caso não define workspace específico.": "Base path used when a case does not define a specific workspace.",
    "Limite global por minuto": "Global rate limit per minute",
    "Diretórios de projeto": "Project directories",
    "Workspaces que ficam naturalmente disponíveis para operação.": "Workspaces naturally available for operations.",
    "Adicionar diretório": "Add directory",
    "Ex.: Jane Doe": "e.g. Jane Doe",
    "Ex.: operacao@empresa.com": "e.g. ops@company.com",
    "Ex.: jane-doe": "e.g. jane-doe",
    "Ex.: America/Sao_Paulo": "e.g. America/Sao_Paulo",
    "Ex.: /workspace/projetos": "e.g. /workspace/projects",
    "Ex.: 10": "e.g. 10",
    "Ex.: /workspace/base": "e.g. /workspace/base",
    "Identidade do Agente": "Agent identity",
    "Nome, aparencia visual e enderecos do runtime publicados para este agente.": "Name, visual appearance and runtime endpoints published for this agent.",
    "Nome do Agente": "Agent name",
    "Ex: Assistente de Vendas": "e.g. Sales assistant",
    "Cor do Agente": "Agent color",
    "Configuracao de conexao": "Connection settings",
    "Endpoints do runtime do agente. Altere apenas se estiver usando um runtime customizado.": "Agent runtime endpoints. Change only if you are using a custom runtime.",
    "Workspace": "Espaço de trabalho",
    "Organizacao visual deste agente no catalogo.": "Visual organization for this agent in the catalog.",
    "Squad": "Squad",
    "Time interno dentro do workspace selecionado.": "Internal team inside the selected workspace.",
    "URL do Runtime": "Runtime URL",
    "Endereco base onde o agente esta hospedado.": "Base address where the agent is hosted.",
    "URL de Health Check": "Health check URL",
    "Endereco para verificar se o agente esta online.": "Address used to verify whether the agent is online.",
    "Escopo e credenciais": "Scope and credentials",
    "Variaveis compartilhadas, grants globais e segredos locais foram movidos para a aba Escopo para deixar a separacao de responsabilidades clara.": "Shared variables, global grants and local secrets were moved to the Scope tab to keep responsibilities clearly separated.",
    "Use a aba Escopo para conceder recursos globais, cadastrar segredos locais e controlar exatamente quais variaveis este agente pode receber do sistema.": "Use the Scope tab to grant global resources, register local secrets and control exactly which variables this agent can receive from the system.",
    "Sem workspace": "No workspace",
    "Sem squad": "No squad",
    "Editar variável": "Edit variable",
    "Nova variável": "New variable",
    "Use um nome em formato de variável de ambiente.": "Use an environment-variable style name.",
    "Nome": "Name",
    "Tipo": "Type",
    "Segredos ficam criptografados e mascarados em leitura.": "Secrets stay encrypted and masked when viewed.",
    "Texto": "Text",
    "Segredo": "Secret",
    "Escopo": "Scope",
    "Controle se o valor pode ser concedido explicitamente a bots.": "Controls whether this value can be explicitly granted to bots.",
    "Somente sistema": "System only",
    "Disponível para bots mediante grant": "Available to bots through grant",
    "Descrição": "Description",
    "Contexto curto para o operador lembrar o propósito.": "Short context so the operator remembers the purpose.",
    "Fila operacional do time": "Team operational queue",
    "Valor do segredo": "Secret value",
    "Valor": "Value",
    "O valor será salvo globalmente no control plane.": "The value will be saved globally in the control plane.",
    "já configurado": "already configured",
    "Digite apenas se quiser substituir": "Type only if you want to replace it",
    "valor": "value",
    "Segredo será removido ao salvar": "Secret will be removed on save",
    "Marcar para remover": "Mark for removal",
    "Fechar modal": "Close modal",
    "Salvar": "Save",
    "Invalid JSON": "Invalid JSON",
    "Valid JSON": "Valid JSON",
    "Empty": "Empty",
    "Format": "Format",
    "Digite e pressione Enter...": "Type and press Enter...",
    "Pressione Enter para adicionar": "Press Enter to add",
    "chave": "key",
    "Remover": "Remove",
    "Adicionar item": "Add item",
    "Cor": "Color",
    "Valor RGB": "RGB value",
    "Cor em formato RGB": "Color in RGB format",
    "Hex válido": "Valid hex",
    "Hex inválido": "Invalid hex",
    "Abrir seletor de cor": "Open color picker",
    "Painel de cor": "Color panel",
    "Hex color": "Hex color",
    "Ajustar tom": "Adjust hue",
    "Ajustar saturacao": "Adjust saturation",
    "Ajustar luminosidade": "Adjust lightness",
    "Publicando": "Publishing",
    "Publicar": "Publish",
    "Pausando": "Pausing",
    "Ativando": "Activating",
    "Pausar": "Pause",
    "Ativar": "Activate",
    "Bot publicado com sucesso.": "Bot published successfully.",
    "Erro ao publicar.": "Error publishing.",
    "Bot ativado.": "Bot activated.",
    "Bot pausado.": "Bot paused.",
    "Erro ao alterar status.": "Error changing status.",
    "Agentes": "Agents",
    "Perfil salvo com sucesso.": "Profile saved successfully.",
    "Erro ao salvar perfil.": "Error saving profile.",
  },
  "pt-BR": {
    "Workspace": "Espaço de trabalho",
    "Workspaces": "Espaços de trabalho",
    "Squad": "Time",
    "Squads": "Times",
    "Sem workspace": "Sem espaço de trabalho",
    "Sem squad": "Sem time",
    "Nova squad": "Novo time",
    "Adicionar squad": "Adicionar time",
    "Criar squad em {{workspace}}": "Criar time em {{workspace}}",
    "Editar squad": "Editar time",
    "Editar squad {{squad}}": "Editar time {{squad}}",
    "Remover squad": "Remover time",
    "Remover squad {{squad}}": "Remover time {{squad}}",
    "Nome da squad": "Nome do time",
    "Mostrar mais squads de {{section}}": "Mostrar mais times de {{section}}",
    "Mostrar squads anteriores de {{section}}": "Mostrar times anteriores de {{section}}",
    "Buscar bots por nome, ID, workspace ou squad": "Buscar bots por nome, ID, espaço de trabalho ou time",
    "Buscar por nome, ID, workspace ou squad...": "Buscar por nome, ID, espaço de trabalho ou time...",
    "Bots livres, ainda fora de um workspace. Arraste para organizar.": "Bots livres, ainda fora de um espaço de trabalho. Arraste para organizar.",
    "Solte aqui para remover o vínculo com qualquer workspace.": "Solte aqui para remover o vínculo com qualquer espaço de trabalho.",
    "Ponto de entrada do workspace para bots sem time definido.": "Ponto de entrada do espaço de trabalho para bots sem time definido.",
    "Organize squads e distribua os agentes deste workspace.": "Organize times e distribua os agentes deste espaço de trabalho.",
    "Espaço reservado para criar um novo time neste workspace.": "Espaço reservado para criar um novo time neste espaço de trabalho.",
    "Time dedicado dentro deste workspace.": "Time dedicado dentro deste espaço de trabalho.",
    "Tente outra busca para voltar a visualizar a distribuicao dos workspaces e squads.": "Tente outra busca para voltar a visualizar a distribuição dos espaços de trabalho e dos times.",
    "Publicacao": "Publicação",
    "Pipeline de Publicacao": "Pipeline de Publicação",
    "Nome, aparencia visual e enderecos do runtime publicados para este agente.": "Nome, aparência visual e endereços do runtime publicados para este agente.",
    "Defina nome, aparencia e organizacao base do agente.": "Defina nome, aparência e organização base do agente.",
    "Configuracao de conexao": "Configuração de conexão",
    "Organizacao visual deste agente no catalogo.": "Organização visual deste agente no catálogo.",
    "Endereco base onde o agente esta hospedado.": "Endereço base onde o agente está hospedado.",
    "Endereco para verificar se o agente esta online.": "Endereço para verificar se o agente está online.",
    "Variaveis compartilhadas, grants globais e segredos locais foram movidos para a aba Escopo para deixar a separacao de responsabilidades clara.": "Variáveis compartilhadas, grants globais e segredos locais foram movidos para a aba Escopo para deixar a separação de responsabilidades clara.",
    "Use a aba Escopo para conceder recursos globais, cadastrar segredos locais e controlar exatamente quais variaveis este agente pode receber do sistema.": "Use a aba Escopo para conceder recursos globais, cadastrar segredos locais e controlar exatamente quais variáveis este agente pode receber do sistema.",
    "Arraste agentes para ca para reorganizar a composicao deste time.": "Arraste agentes para cá para reorganizar a composição deste time.",
    "Revise os dados principais antes de publicar o novo agente no catalogo.": "Revise os dados principais antes de publicar o novo agente no catálogo.",
    "{{count}} bot": "{{count}} bot",
    "{{count}} bots": "{{count}} bots",
    "{{count}} bot no catálogo": "{{count}} bot no catálogo",
    "{{count}} bots no catálogo": "{{count}} bots no catálogo",
  },
  "es-ES": {
    "Ativo": "Activo",
    "Pausado": "Pausado",
    "Movendo": "Moviendo",
    "Sem modelo definido": "Sin modelo configurado",
    "Selecionar": "Seleccionar",
    "Desselecionar": "Deseleccionar",
    "Agente": "Agente",
    "Abrir ações do agente": "Abrir acciones del agente",
    "Editar": "Editar",
    "Duplicar": "Duplicar",
    "Excluir": "Eliminar",
    "Voltar": "Volver",
    "Próximo": "Siguiente",
    "Aplicando": "Aplicando",
    "Descartar": "Descartar",
    "Salvar alterações": "Guardar cambios",
    "Conta e operação": "Cuenta y operación",
    "Modelos": "Modelos",
    "Integrações externas": "Integraciones externas",
    "Memória e conhecimento": "Memoria y conocimiento",
    "Vault de variáveis": "Bóveda de variables",
    "Revisão e aplicação": "Revisión y aplicación",
    "Responsável principal": "Responsable principal",
    "Email operacional": "Correo operativo",
    "Usuário GitHub": "Usuario de GitHub",
    "Timezone padrão": "Zona horaria predeterminada",
    "Aplicado aos agendamentos e à operação global do sistema.": "Aplicado a las programaciones y a la operación global del sistema.",
    "Diretório padrão de trabalho": "Directorio de trabajo predeterminado",
    "Raiz usada quando o caso não define workspace específico.": "Raíz usada cuando el caso no define un workspace específico.",
    "Limite global por minuto": "Límite global por minuto",
    "Diretórios de projeto": "Directorios de proyecto",
    "Workspaces que ficam naturalmente disponíveis para operação.": "Workspaces disponibles naturalmente para la operación.",
    "Adicionar diretório": "Añadir directorio",
    "Ex.: Jane Doe": "Ej.: Jane Doe",
    "Ex.: operacao@empresa.com": "Ej.: operacion@empresa.com",
    "Ex.: jane-doe": "Ej.: jane-doe",
    "Ex.: America/Sao_Paulo": "Ej.: America/Sao_Paulo",
    "Ex.: /workspace/projetos": "Ej.: /workspace/proyectos",
    "Ex.: 10": "Ej.: 10",
    "Ex.: /workspace/base": "Ej.: /workspace/base",
    "Identidade do Agente": "Identidad del agente",
    "Nome, aparencia visual e enderecos do runtime publicados para este agente.": "Nombre, apariencia visual y direcciones del runtime publicadas para este agente.",
    "Nome do Agente": "Nombre del agente",
    "Ex: Assistente de Vendas": "Ej.: Asistente de ventas",
    "Cor do Agente": "Color del agente",
    "Configuracao de conexao": "Configuración de conexión",
    "Endpoints do runtime do agente. Altere apenas se estiver usando um runtime customizado.": "Endpoints del runtime del agente. Cámbialos solo si usas un runtime personalizado.",
    "Workspace": "Espacio de trabajo",
    "Organizacao visual deste agente no catalogo.": "Organización visual de este agente en el catálogo.",
    "Squad": "Equipo",
    "Time interno dentro do workspace selecionado.": "Equipo interno dentro del workspace seleccionado.",
    "URL do Runtime": "URL del runtime",
    "Endereco base onde o agente esta hospedado.": "Dirección base donde el agente está alojado.",
    "URL de Health Check": "URL de health check",
    "Endereco para verificar se o agente esta online.": "Dirección para verificar si el agente está en línea.",
    "Escopo e credenciais": "Alcance y credenciales",
    "Variaveis compartilhadas, grants globais e segredos locais foram movidos para a aba Escopo para deixar a separacao de responsabilidades clara.": "Las variables compartidas, grants globales y secretos locales se movieron a la pestaña Alcance para dejar clara la separación de responsabilidades.",
    "Use a aba Escopo para conceder recursos globais, cadastrar segredos locais e controlar exatamente quais variaveis este agente pode receber do sistema.": "Usa la pestaña Alcance para conceder recursos globales, registrar secretos locales y controlar exactamente qué variables puede recibir este agente del sistema.",
    "Sem workspace": "Sin workspace",
    "Sem squad": "Sin equipo",
    "Editar variável": "Editar variable",
    "Nova variável": "Nueva variable",
    "Use um nome em formato de variável de ambiente.": "Usa un nombre con formato de variable de entorno.",
    "Nome": "Nombre",
    "Tipo": "Tipo",
    "Segredos ficam criptografados e mascarados em leitura.": "Los secretos permanecen cifrados y enmascarados al mostrarse.",
    "Texto": "Texto",
    "Segredo": "Secreto",
    "Escopo": "Alcance",
    "Controle se o valor pode ser concedido explicitamente a bots.": "Controla si el valor puede concederse explícitamente a bots.",
    "Somente sistema": "Solo sistema",
    "Disponível para bots mediante grant": "Disponible para bots mediante grant",
    "Descrição": "Descripción",
    "Contexto curto para o operador lembrar o propósito.": "Contexto breve para que el operador recuerde el propósito.",
    "Fila operacional do time": "Cola operativa del equipo",
    "Valor do segredo": "Valor del secreto",
    "Valor": "Valor",
    "O valor será salvo globalmente no control plane.": "El valor se guardará globalmente en el control plane.",
    "já configurado": "ya configurado",
    "Digite apenas se quiser substituir": "Escribe solo si quieres reemplazar",
    "Segredo será removido ao salvar": "El secreto se eliminará al guardar",
    "Marcar para remover": "Marcar para eliminar",
    "Fechar modal": "Cerrar modal",
    "Salvar": "Guardar",
    "Invalid JSON": "JSON no válido",
    "Valid JSON": "JSON válido",
    "Empty": "Vacío",
    "Format": "Formatear",
    "Digite e pressione Enter...": "Escribe y presiona Enter...",
    "Pressione Enter para adicionar": "Presiona Enter para añadir",
    "chave": "clave",
    "valor": "valor",
    "Remover": "Eliminar",
    "Adicionar item": "Añadir elemento",
    "Cor": "Color",
    "Valor RGB": "Valor RGB",
    "Cor em formato RGB": "Color en formato RGB",
    "Hex válido": "Hex válido",
    "Hex inválido": "Hex no válido",
    "Abrir seletor de cor": "Abrir selector de color",
    "Painel de cor": "Panel de color",
    "Hex color": "Color hex",
    "Ajustar tom": "Ajustar tono",
    "Ajustar saturacao": "Ajustar saturación",
    "Ajustar luminosidade": "Ajustar luminosidad",
    "Publicando": "Publicando",
    "Publicar": "Publicar",
    "Pausando": "Pausando",
    "Ativando": "Activando",
    "Pausar": "Pausar",
    "Ativar": "Activar",
    "Bot publicado com sucesso.": "Bot publicado con éxito.",
    "Erro ao publicar.": "Error al publicar.",
    "Bot ativado.": "Bot activado.",
    "Bot pausado.": "Bot pausado.",
    "Erro ao alterar status.": "Error al cambiar el estado.",
    "Agentes": "Agentes",
    "Perfil salvo com sucesso.": "Perfil guardado con éxito.",
    "Erro ao salvar perfil.": "Error al guardar el perfil.",
  },
  "fr-FR": {
    "Ativo": "Actif",
    "Pausado": "En pause",
    "Movendo": "Déplacement",
    "Sem modelo definido": "Aucun modèle défini",
    "Selecionar": "Sélectionner",
    "Desselecionar": "Désélectionner",
    "Agente": "Agent",
    "Agents": "Agents",
    "Active": "Actifs",
    "Workspace": "Espace de travail",
    "Workspaces": "Espaces de travail",
    "Squad": "Escouade",
    "Squads": "Escouades",
    "Editar": "Modifier",
    "Duplicar": "Dupliquer",
    "Excluir": "Supprimer",
    "Voltar": "Retour",
    "Próximo": "Suivant",
    "Nome": "Nom",
    "Tipo": "Type",
    "Descrição": "Description",
    "Salvar": "Enregistrer",
    "Cancelar": "Annuler",
    "Confirmar": "Confirmer",
    "Bot publicado com sucesso.": "Bot publié avec succès.",
    "Erro ao publicar.": "Erreur lors de la publication.",
    "Bot ativado.": "Bot activé.",
    "Bot pausado.": "Bot en pause.",
    "Erro ao alterar status.": "Erreur lors du changement de statut.",
    "Agentes": "Agents",
    "Perfil salvo com sucesso.": "Profil enregistré avec succès.",
    "Erro ao salvar perfil.": "Erreur lors de l'enregistrement du profil.",
  },
  "de-DE": {
    "Ativo": "Aktiv",
    "Pausado": "Pausiert",
    "Movendo": "Verschieben",
    "Sem modelo definido": "Kein Modell konfiguriert",
    "Selecionar": "Auswählen",
    "Desselecionar": "Abwählen",
    "Agente": "Agent",
    "Agents": "Agenten",
    "Active": "Aktiv",
    "Workspace": "Arbeitsbereich",
    "Workspaces": "Arbeitsbereiche",
    "Squad": "Squad",
    "Squads": "Squads",
    "Editar": "Bearbeiten",
    "Duplicar": "Duplizieren",
    "Excluir": "Löschen",
    "Voltar": "Zurück",
    "Próximo": "Weiter",
    "Nome": "Name",
    "Tipo": "Typ",
    "Descrição": "Beschreibung",
    "Salvar": "Speichern",
    "Cancelar": "Abbrechen",
    "Confirmar": "Bestätigen",
    "Bot publicado com sucesso.": "Bot erfolgreich veröffentlicht.",
    "Erro ao publicar.": "Fehler bei der Veröffentlichung.",
    "Bot ativado.": "Bot aktiviert.",
    "Bot pausado.": "Bot pausiert.",
    "Erro ao alterar status.": "Fehler beim Ändern des Status.",
    "Agentes": "Agenten",
    "Perfil salvo com sucesso.": "Profil erfolgreich gespeichert.",
    "Erro ao salvar perfil.": "Fehler beim Speichern des Profils.",
  },
} as const;

Object.assign(literalResources["en-US"] as Record<string, string>, {
  "A chave do segredo e obrigatoria.": "The secret key is required.",
  "A configuração está consistente. Nenhum aviso no momento.": "The configuration is consistent. No warnings right now.",
  "Abrir configuracoes do sistema": "Open system settings",
  "Abrir editor": "Open editor",
  "Acoes irreversiveis.": "Irreversible actions.",
  "Acoes proibidas": "Forbidden actions",
  "Add new": "Add new",
  "Adicionar": "Add",
  "Adicionar squad": "Add squad",
  "Advanced JSON": "Advanced JSON",
  "Agente movido para {{target}}.": "Agent moved to {{target}}.",
  "Agente removido com sucesso.": "Agent removed successfully.",
  "Aplicar": "Apply",
  "Applied": "Applied",
  "Approval mode padrao": "Default approval mode",
  "Aprovando...": "Approving...",
  "Aprovar candidate": "Approve candidate",
  "Arraste agentes aqui para deixá-los fora de um workspace.": "Drag agents here to keep them outside any workspace.",
  "Arraste agentes para ca para reorganizar a composicao deste time.": "Drag agents here to reorganize this team composition.",
  "Arraste qualquer agente selecionado para mover o lote inteiro de uma vez.": "Drag any selected agent to move the entire batch at once.",
  "As configurações globais valem para toda a conta, mas este agente só recebe variáveis e segredos quando o grant estiver marcado abaixo. Tools, providers e demais capacidades continuam governados na aba Recursos.": "Global settings apply to the whole account, but this agent only receives variables and secrets when the grant below is enabled. Tools, providers and the remaining capabilities are still governed in the Resources tab.",
  "Assinatura / login": "Subscription / sign-in",
  "Ativa": "Active",
  "Ativos": "Active",
  "Atualizar": "Update",
  "Atualizar fila": "Refresh queue",
  "Atualizar segredo local": "Update local secret",
  "Autonomy Policy JSON": "Autonomy Policy JSON",
  "Autonomy tier padrao": "Default autonomy tier",
  "Ação {{action}} aplicada em {{agentId}}.": "Action {{action}} applied to {{agentId}}.",
  "Bot": "Bot",
  "Bot clonado com sucesso.": "Bot cloned successfully.",
  "Bot criado com sucesso.": "Bot created successfully.",
  "Bot removido.": "Bot removed.",
  "Bot {{id}} criado com sucesso.": "Bot {{id}} created successfully.",
  "Bots": "Bots",
  "Bots livres": "Free bots",
  "Bots livres, ainda fora de um workspace. Arraste para organizar.": "Free bots, still outside a workspace. Drag to organize them.",
  "Budget acumulado": "Accumulated budget",
  "Budget por tarefa": "Per-task budget",
  "Budget por tarefa (USD)": "Budget per task (USD)",
  "Budget total (USD)": "Total budget (USD)",
  "Buscar bots por nome, ID, workspace ou squad": "Search bots by name, ID, workspace or squad",
  "Buscar por nome, ID, workspace ou squad...": "Search by name, ID, workspace or squad...",
  "Cada bot recebe apenas um subset do catálogo governado pelo core.": "Each bot only receives a subset of the catalog governed by the core.",
  "Calmo": "Calm",
  "Camadas ativas": "Active layers",
  "Camadas, recall semântico e governança de proveniência.": "Layers, semantic recall and provenance governance.",
  "Cancel": "Cancel",
  "Cancelar": "Cancel",
  "Candidate ID": "Candidate ID",
  "Candidate aprovado com sucesso.": "Candidate approved successfully.",
  "Candidate rejeitado com sucesso.": "Candidate rejected successfully.",
  "Canônico": "Canonical",
  "Catálogo dinâmico dos bots, defaults globais e atalhos de publicação.": "Dynamic bot catalog, global defaults and publishing shortcuts.",
  "Catálogo governado pelo sistema": "System-governed catalog",
  "Chave": "Key",
  "Clonando": "Cloning",
  "Clonar Agente": "Clone Agent",
  "Clonar agente": "Clone agent",
  "Colaborativo": "Collaborative",
  "Cole o segredo aqui": "Paste the secret here",
  "Collapse": "Collapse",
  "Como o agente responde, decide e se contém.": "How the agent responds, decides and self-governs.",
  "Compatibilidade de provider": "Provider compatibility",
  "Completo": "Complete",
  "Comportamento salvo com sucesso.": "Behavior saved successfully.",
  "Conceder acesso": "Grant access",
  "Concedido": "Granted",
  "Concisao": "Conciseness",
  "Conectado": "Connected",
  "Conecte serviços externos ao sistema.": "Connect external services to the system.",
  "Conexões verificadas": "Verified connections",
  "Conferencia final": "Final review",
  "Configuracao": "Configuration",
  "Configuracoes gerais salvas com sucesso.": "General settings saved successfully.",
  "Configuracoes globais e governanca": "Global settings and governance",
  "Configuradas": "Configured",
  "Configurado": "Configured",
  "Configure providers, runtime, integracoes, variaveis compartilhadas e o vault global em um unico lugar. Cada agente recebe apenas os grants explicitamente aprovados.": "Configure providers, runtime, integrations, shared variables and the global vault in one place. Each agent only receives explicitly approved grants.",
  "Conhecimento": "Knowledge",
  "Conhecimento e RAG": "Knowledge and RAG",
  "Continuar": "Continue",
  "Control Plane": "Control Plane",
  "Copia": "Copy",
  "Copia de...": "Copy of...",
  "Core tools": "Core tools",
  "Credenciais exclusivas deste agente. Permanecem mascaradas e não entram em grants de outros bots.": "Exclusive credentials for this agent. They remain masked and are not granted to other bots.",
  "Criando bot": "Creating bot",
  "Criando...": "Creating...",
  "Criar": "Create",
  "Criar agente": "Create agent",
  "Criar bot": "Create bot",
  "Criar novo workspace": "Create new workspace",
  "Criar squad em {{workspace}}": "Create squad in {{workspace}}",
  "Criar uma copia deste agente.": "Create a copy of this agent.",
  "Criterios de sucesso": "Success criteria",
  "Defaults globais": "Global defaults",
  "Defaults globais atualizados.": "Global defaults updated.",
  "Defaults globais salvos com sucesso.": "Global defaults saved successfully.",
  "Defina exatamente quais recursos globais este agente pode receber do sistema.": "Define exactly which global resources this agent can receive from the system.",
  "Defina nome, aparencia e organizacao base do agente.": "Define the agent's name, appearance and base organization.",
  "Defina nome, descricao curta e a cor de apoio visual desta organizacao.": "Define the name, short description and visual accent color for this organization.",
  "Defina o tipo, escopo e descrição do recurso global.": "Define the type, scope and description of the global resource.",
  "Delete": "Delete",
  "Delete secret {{key}}": "Delete secret {{key}}",
  "Delete {{name}}": "Delete {{name}}",
  "Desabilitada": "Disabled",
  "Desabilitado": "Disabled",
  "Desabilitar": "Disable",
  "Descrever e analisar": "Describe and analyze",
  "Descricao": "Description",
  "Descricao curta opcional": "Optional short description",
  "Desired": "Desired",
  "Destino: {{target}}": "Target: {{target}}",
  "Detalhado": "Detailed",
  "Diagnosticos de publicacao": "Publishing diagnostics",
  "Digite para substituir": "Type to replace",
  "Digite um novo valor para substituir": "Type a new value to replace",
  "Direto": "Direct",
  "Display name": "Display name",
  "Disponíveis por grant": "Available by grant",
  "Disponível globalmente": "Globally available",
  "Disponível por grant": "Available by grant",
  "Documentos do workspace": "Workspace documents",
  "Memória, conhecimento e autonomia": "Memory, knowledge and autonomy",
  "Perfis guiados definem a baseline. Os campos estruturados abaixo refinam o contrato canônico usado também nas configurações por bot.": "Guided profiles define the baseline. The structured fields below refine the canonical contract also used in per-bot settings.",
  "Recall, aprendizado contínuo e auto manutenção do agente.": "Recall, continuous learning and agent self-maintenance.",
  "Preset-base para retenção, recall e manutenção.": "Base preset for retention, recall and maintenance.",
  "Perfil atual": "Current profile",
  "Os presets servem como ponto de partida; os campos abaixo refinam o comportamento.": "Presets serve as a starting point; the fields below refine the behavior.",
  "Grounding com proveniência, semântica e camadas confiáveis.": "Grounding with provenance, semantics and trusted layers.",
  "Perfil de conhecimento": "Knowledge profile",
  "Preset-base para camadas, recall e frescor.": "Base preset for layers, recall and freshness.",
  "Baseline de governança para owner e freshness.": "Governance baseline for owner and freshness.",
  "Autonomia operacional": "Operational autonomy",
  "Envelope padrão para execuções longas, complexas e supervisionadas.": "Default envelope for long, complex and supervised executions.",
  "Duplicata criada: {{id}}": "Duplicate created: {{id}}",
  "Duracao alvo": "Target duration",
  "EXEMPLO_BOT": "SAMPLE_BOT",
  "Editar squad": "Edit squad",
  "Editar squad {{squad}}": "Edit squad {{squad}}",
  "Editar variável local": "Edit local variable",
  "Editar workspace": "Edit workspace",
  "Editar workspace {{workspace}}": "Edit workspace {{workspace}}",
  "Email": "Email",
  "Envelope de modelo": "Model envelope",
  "Envelope global de modelos": "Global model envelope",
  "Enxuto": "Lean",
  "Equilibrado": "Balanced",
  "Erro ao clonar.": "Error cloning.",
  "Erro ao criar agente.": "Error creating agent.",
  "Erro ao duplicar agente.": "Error duplicating agent.",
  "Erro ao executar {{endpoint}}.": "Error running {{endpoint}}.",
  "Erro ao processar candidate.": "Error processing candidate.",
  "Erro ao remover bot.": "Error removing bot.",
  "Erro ao remover item.": "Error removing item.",
  "Erro ao remover organizacao.": "Error removing organization.",
  "Erro ao remover segredo local.": "Error removing local secret.",
  "Erro ao remover segredo.": "Error removing secret.",
  "Erro ao revalidar runbook.": "Error revalidating runbook.",
  "Erro ao salvar comportamento.": "Error saving behavior.",
  "Erro ao salvar defaults.": "Error saving defaults.",
  "Erro ao salvar escopo.": "Error saving scope.",
  "Erro ao salvar organizacao.": "Error saving organization.",
  "Erro ao salvar politicas.": "Error saving policies.",
  "Erro ao salvar recursos.": "Error saving resources.",
  "Erro ao salvar segredo local.": "Error saving local secret.",
  "Erro ao salvar segredo.": "Error saving secret.",
  "Erro ao salvar {{title}}.": "Error saving {{title}}.",
  "Escalation required": "Escalation required",
  "Escolha apenas providers e modelos realmente suportados pelo core.": "Choose only providers and models actually supported by the core.",
  "Escolha o provider principal e as instrucoes iniciais do agente.": "Choose the primary provider and the agent's starting instructions.",
  "Escolha um provider e um modelo habilitados pelo core.": "Choose a core-enabled provider and model.",
  "Escopo de acesso do agente": "Agent access scope",
  "Escopo do agente salvo com sucesso.": "Agent scope saved successfully.",
  "Espaço reservado para criar um novo time neste workspace.": "Reserved slot to create a new team in this workspace.",
  "Estado dos providers": "Provider status",
  "Estilo": "Style",
  "Estilo de colaboracao": "Collaboration style",
  "Estilo de escalacao": "Escalation style",
  "Estilo de escrita": "Writing style",
  "Estruturado": "Structured",
  "Ex.: Plataforma": "e.g. Platform",
  "Ex.: Produto": "e.g. Product",
  "Ex.: squad-platform": "e.g. squad-platform",
  "Ex: 12": "e.g. 12",
  "Ex: 30-45s": "e.g. 30-45s",
  "Ex: 5": "e.g. 5",
  "Ex: Resolver tickets e incidentes com grounding": "e.g. Resolve tickets and incidents with grounding",
  "Ex: SRE autonomo supervisionado": "e.g. supervised autonomous SRE",
  "Ex: acuracia, lead time, cobertura de fontes": "e.g. accuracy, lead time, source coverage",
  "Ex: calmo, executivo, amigavel": "e.g. calm, executive, friendly",
  "Ex: citar label e data quando grounded": "e.g. cite label and date when grounded",
  "Ex: conciso, objetivo e rastreavel": "e.g. concise, objective and traceable",
  "Ex: deploy sem aprovacao explicita": "e.g. deploy without explicit approval",
  "Ex: entender, buscar grounding, agir, verificar": "e.g. understand, gather grounding, act, verify",
  "Ex: escalar com contexto e proposta": "e.g. escalate with context and proposal",
  "Ex: escalar com contexto e proxima acao sugerida": "e.g. escalate with context and suggested next action",
  "Ex: evitar inferir identidade, checar texto sensivel": "e.g. avoid inferring identity, inspect sensitive text",
  "Ex: funcionario tecnico confiavel": "e.g. trustworthy technical operator",
  "Ex: honestidade, grounding, ownership": "e.g. honesty, grounding, ownership",
  "Ex: nao aprovar deploy em producao": "e.g. do not approve production deploys",
  "Ex: nao expor segredos ou PII": "e.g. do not expose secrets or PII",
  "Ex: nao inventar fatos": "e.g. do not invent facts",
  "Ex: objetos, texto, contexto, risco": "e.g. objects, text, context, risk",
  "Ex: preferir knowledge canonico e runbooks": "e.g. prefer canonical knowledge and runbooks",
  "Ex: producao exige confirmacao humana": "e.g. production requires human confirmation",
  "Ex: profissional, rastreavel, sem invencao": "e.g. professional, traceable, no fabrication",
  "Ex: propor, executar, verificar": "e.g. propose, execute, verify",
  "Ex: reduzir tempo de triagem": "e.g. reduce triage time",
  "Ex: resposta correta, segura e verificavel": "e.g. correct, safe and verifiable response",
  "Ex: usar modelo menor para triagem": "e.g. use a smaller model for triage",
  "Exemplo Bot": "Sample Bot",
  "Expand": "Expand",
  "Expectativas de handoff": "Handoff expectations",
  "Falha ao criar bot.": "Failed to create bot.",
  "Falha ao executar {{action}}.": "Failed to run {{action}}.",
  "Falha ao executar {{endpoint}}.": "Failed to run {{endpoint}}.",
  "Falha ao salvar defaults globais.": "Failed to save global defaults.",
  "Fallback": "Fallback",
  "Fechar": "Close",
  "Fechar formulario": "Close form",
  "Ferramentas configuráveis": "Configurable tools",
  "Formato": "Format",
  "Funcao profissional desempenhada pelo agente.": "Professional function performed by the agent.",
  "Gerado automaticamente a partir do nome. Editavel.": "Generated automatically from the name. Editable.",
  "Gerenciamento de secrets — chaves de API, tokens e credenciais.": "Secrets management — API keys, tokens and credentials.",
  "Global": "Global",
  "Global defaults": "Global defaults",
  "Governanca e aprendizado": "Governance and learning",
  "Governança": "Governance",
  "Grantável": "Grantable",
  "Guarded": "Guarded",
  "Habilitada": "Enabled",
  "Habilitado": "Enabled",
  "Habilitar": "Enable",
  "Health port": "Health port",
  "Herança base para novos bots e overrides": "Base inheritance for new bots and overrides",
  "Herdar do sistema": "Inherit from system",
  "Heuristicas de execucao": "Execution heuristics",
  "Historico de Versoes": "Version history",
  "ID": "ID",
  "ID do Clone": "Clone ID",
  "ID do agente e obrigatorio.": "The agent ID is required.",
  "ID do clone e obrigatorio.": "The clone ID is required.",
  "Identidade": "Identity",
  "Identificador unico para o novo agente.": "Unique identifier for the new agent.",
  "Identity": "Identity",
  "Idioma": "Language",
  "Image Analysis Policy JSON": "Image Analysis Policy JSON",
  "Image Prompt (image_prompt_md)": "Image Prompt (image_prompt_md)",
  "Imagem": "Image",
  "Inativa": "Inactive",
  "Indicadores de qualidade ou desempenho.": "Quality or performance indicators.",
  "Indicadores do board": "Board indicators",
  "Indisponível": "Unavailable",
  "Informe o nome da variável local.": "Enter the local variable name.",
  "Informe o nome da variável.": "Enter the variable name.",
  "Informe o nome do segredo local.": "Enter the local secret name.",
  "Informe o valor da variável local.": "Enter the local variable value.",
  "Informe o valor do segredo local.": "Enter the local secret value.",
  "Informe um candidate ID valido.": "Enter a valid candidate ID.",
  "Informe um runbook ID valido.": "Enter a valid runbook ID.",
  "Informe um valor inicial para o segredo.": "Provide an initial value for the secret.",
  "Informe um valor para a variável.": "Provide a value for the variable.",
  "Instrucoes": "Instructions",
  "Instrucoes do agente": "Agent instructions",
  "Instructions": "Instructions",
  "Instruções especializadas para análise visual e comportamento de fallback.": "Specialized instructions for visual analysis and fallback behavior.",
  "Integracoes globais": "Global integrations",
  "Integrações ativas": "Active integrations",
  "Item {{id}} removido.": "Item {{id}} removed.",
  "JIRA_API_TOKEN": "JIRA_API_TOKEN",
  "JSON syntax error detected": "JSON syntax error detected",
  "KPIs": "KPIs",
  "Knowledge Assets": "Knowledge Assets",
  "Knowledge Policy JSON": "Knowledge Policy JSON",
  "Knowledge candidates pendentes": "Pending knowledge candidates",
  "Limite de {{count}} itens atingido": "{{count}} item limit reached",
  "Limites de responsabilidade": "Responsibility limits",
  "Limpar seleção": "Clear selection",
  "Local ao agente": "Local to agent",
  "Luminosidade": "Lightness",
  "MEU_AGENTE": "MY_AGENT",
  "Mascarado": "Masked",
  "Memory Extraction Prompt (memory_extraction_prompt_md)": "Memory Extraction Prompt (memory_extraction_prompt_md)",
  "Memory Extraction Schema": "Memory Extraction Schema",
  "Memory Policy JSON": "Memory Policy JSON",
  "Memória global": "Global memory",
  "Memória persistente": "Persistent memory",
  "Mesmo contrato canônico usado nas configurações globais.": "The same canonical contract used in global settings.",
  "Missao": "Mission",
  "Missao e estilo": "Mission and style",
  "Model Policy JSON": "Model Policy JSON",
  "Modelo": "Model",
  "Modelo e instrucoes": "Model and instructions",
  "Modelo padrao": "Default model",
  "Modelo principal usado no provider padrao.": "Primary model used by the default provider.",
  "Modelos e providers": "Models and providers",
  "Modo": "Mode",
  "Mostrar mais squads de {{section}}": "Show more squads from {{section}}",
  "Mostrar squads anteriores de {{section}}": "Show previous squads from {{section}}",
  "Movendo {{count}} agente(s) para {{target}}": "Moving {{count}} agent(s) to {{target}}",
  "Namespace": "Namespace",
  "Nao foi possivel mover os agentes selecionados.": "Could not move the selected agents.",
  "Nao negociaveis": "Non-negotiables",
  "Nenhum": "None",
  "Nenhum agente corresponde a esta busca nesta area.": "No agent matches this search in this area.",
  "Nenhum agente encontrado": "No agent found",
  "Nenhum segredo cadastrado.": "No secrets registered.",
  "Nenhum segredo global disponível ainda. Cadastre-os primeiro em Configurações gerais.": "No global secrets available yet. Register them first in General settings.",
  "Nenhum segredo local cadastrado para este agente.": "No local secrets registered for this agent.",
  "Nenhuma": "None",
  "Nenhuma ativa": "None active",
  "Nenhuma variável global customizada foi adicionada ainda.": "No custom global variable has been added yet.",
  "Nenhuma variável global disponível ainda. Crie-as primeiro em Configurações gerais.": "No global variables available yet. Create them first in General settings.",
  "Nenhuma variável local cadastrada para este agente.": "No local variable registered for this agent.",
  "Nenhuma versao disponivel.": "No version available.",
  "Nome da chave": "Key name",
  "Nome da squad": "Squad name",
  "Nome de exibicao do novo agente.": "Display name for the new agent.",
  "Nome do Clone": "Clone name",
  "Nome do workspace": "Workspace name",
  "Notas de seguranca": "Security notes",
  "Nova squad": "New squad",
  "Nova variável local": "New local variable",
  "Novo bot self-hosted": "New self-hosted bot",
  "Novo segredo": "New secret",
  "Novo segredo local": "New local secret",
  "Novo valor": "New value",
  "Novo workspace": "New workspace",
  "Não encontrado nas variáveis globais atuais": "Not found in the current global variables",
  "Não encontrado no vault atual": "Not found in the current vault",
  "O bot pode escolher apenas dentro deste envelope do core.": "The bot can only choose within this core envelope.",
  "O bot só poderá usar tools do core explicitamente aprovadas.": "The bot may only use explicitly approved core tools.",
  "O nome e obrigatorio.": "The name is required.",
  "O objetivo central do agente.": "The agent's central objective.",
  "O que o bot sabe — assets, templates, skills e politicas.": "What the bot knows — assets, templates, skills and policies.",
  "O valor atual continua mascarado e não é exibido pela interface.": "The current value remains masked and is not shown by the interface.",
  "O valor do segredo e obrigatorio.": "The secret value is required.",
  "Obrigatório": "Required",
  "Onde o agente deve parar e escalar.": "Where the agent must stop and escalate.",
  "Opcional": "Optional",
  "Opcional. Limite suave para uma tarefa.": "Optional. Soft limit for one task.",
  "Opcional. Teto global acumulado.": "Optional. Global accumulated cap.",
  "Organize squads e distribua os agentes deste workspace.": "Organize squads and distribute this workspace's agents.",
  "Origem das camadas": "Layer origin",
  "Os bots só habilitam subsets desse catálogo.": "Bots only enable subsets from this catalog.",
  "Outcomes principais": "Primary outcomes",
  "Override avancado usado pelo runtime quando a politica de voz estiver ativa.": "Advanced override used by the runtime when voice policy is active.",
  "Override bruto do schema canônico completo.": "Raw override of the complete canonical schema.",
  "Overrides JSON avancados": "Advanced JSON overrides",
  "Padrões observados": "Observed patterns",
  "Papel": "Role",
  "Pendente": "Pending",
  "Perfil de memória": "Memory profile",
  "Perfil de uso": "Usage profile",
  "Perfil operacional e forma de colaboracao do agente.": "Operational profile and collaboration style for the agent.",
  "Persona": "Persona",
  "Pipeline de Publicacao": "Publishing pipeline",
  "Policies e capabilities": "Policies and capabilities",
  "Politica de citacao": "Citation policy",
  "Politica de fontes": "Source policy",
  "Politicas de conhecimento": "Knowledge policies",
  "Politicas de conhecimento salvas.": "Knowledge policies saved.",
  "Política avançada de análise visual.": "Advanced visual analysis policy.",
  "Política avançada de voz/TTS.": "Advanced voice/TTS policy.",
  "Política de proveniência": "Provenance policy",
  "Política especializada de TTS/fala e prompt avançado correspondente.": "Specialized speech/TTS policy and its matching advanced prompt.",
  "Ponto de entrada do workspace para bots sem time definido.": "Workspace entry point for bots with no team defined.",
  "Portugues (Brasil)": "Portuguese (Brazil)",
  "Preencha apenas para substituir.": "Fill only to replace.",
  "Preencha o valor": "Fill in the value",
  "Prioridades de analise": "Analysis priorities",
  "Proativa": "Proactive",
  "Procedural": "Procedural",
  "Profissional": "Professional",
  "Prompt Compilado": "Compiled prompt",
  "Prompt de analise de imagem.": "Image analysis prompt.",
  "Prompt de extracao de memoria.": "Memory extraction prompt.",
  "Prompts derivados e overrides avancados": "Derived prompts and advanced overrides",
  "Protegido no sistema": "Protected in the system",
  "Proveniencia e freshness": "Provenance and freshness",
  "Provider padrao": "Default provider",
  "Provider padrão": "Default provider",
  "Provider preferido para a maioria dos turnos.": "Preferred provider for most turns.",
  "Providers": "Providers",
  "Providers habilitados": "Enabled providers",
  "Providers permitidos": "Allowed providers",
  "Publicado": "Published",
  "Publico e contexto": "Audience and context",
  "Quality bar": "Quality bar",
  "Quem recebe as respostas e em que contexto ele atua.": "Who receives the responses and in which context they operate.",
  "RAG global": "Global RAG",
  "Rascunho": "Draft",
  "Rate limit": "Rate limit",
  "Read only": "Read only",
  "Recursos livres do operador com tipo, descrição e escopo explícitos.": "Operator-owned resources with explicit type, description and scope.",
  "Recursos salvos com sucesso.": "Resources saved successfully.",
  "Regras de seguranca": "Security rules",
  "Rejeitando...": "Rejecting...",
  "Rejeitar candidate": "Reject candidate",
  "Removendo": "Removing",
  "Remover acesso": "Remove access",
  "Remover agente": "Remove agent",
  "Remover agente permanentemente": "Remove agent permanently",
  "Remover permanentemente este agente, incluindo todas as configuracoes, documentos, versoes e credenciais associadas.": "Permanently remove this agent, including all related settings, documents, versions and credentials.",
  "Remover segredo": "Remove secret",
  "Remover squad": "Remove squad",
  "Remover squad {{squad}}": "Remove squad {{squad}}",
  "Remover workspace": "Remove workspace",
  "Remover workspace {{workspace}}": "Remove workspace {{workspace}}",
  "Remover {{key}}": "Remove {{key}}",
  "Requisitos de aprovacao": "Approval requirements",
  "Responsável": "Owner",
  "Resposta, operacao e guardrails": "Responses, operations and guardrails",
  "Resultados que o agente deve perseguir continuamente.": "Outcomes the agent should keep pursuing.",
  "Resumir visualmente": "Summarize visually",
  "Revalidando...": "Revalidating...",
  "Revalidar runbook": "Revalidate runbook",
  "Rules": "Rules",
  "Runbook ID": "Runbook ID",
  "Runbook revalidado com sucesso.": "Runbook revalidated successfully.",
  "Runbooks aprovados": "Approved runbooks",
  "Salvando": "Saving",
  "Salvando defaults": "Saving defaults",
  "Salvando...": "Saving...",
  "Salvar defaults": "Save defaults",
  "Salvar politicas": "Save policies",
  "Salvar segredo": "Save secret",
  "Schema canonico completo de autonomia, incluindo task_overrides.": "Complete canonical autonomy schema, including task overrides.",
  "Schema canônico que o runtime materializa de verdade.": "Canonical schema that the runtime actually materializes.",
  "Schema de extracao de memoria.": "Memory extraction schema.",
  "Segredo local": "Local secret",
  "Segredos": "Secrets",
  "Segredos criptografados do vault global. O bot só recebe o que for explicitamente concedido.": "Encrypted secrets from the global vault. The bot only receives what is explicitly granted.",
  "Segredos existentes ({{count}})": "Existing secrets ({{count}})",
  "Segredos globais": "Global secrets",
  "Segredos locais do agente": "Agent local secrets",
  "Selecione outros cards para formar um lote, ou arraste este agente para mover agora.": "Select other cards to form a batch, or drag this agent to move it now.",
  "Sem descrição": "No description",
  "Sem limite": "No limit",
  "Sem plano detectado": "No plan detected",
  "Sem valor configurado": "No value configured",
  "Sem valor preenchido": "No value filled in",
  "Ser conservador": "Be conservative",
  "Será removido ao salvar": "Will be removed on save",
  "Skills": "Skills",
  "Solte aqui para remover o vínculo com qualquer workspace.": "Drop here to remove the link with any workspace.",
  "Soul / Interaction Style": "Soul / Interaction Style",
  "Spec efetivo": "Effective spec",
  "Squad atualizada com sucesso.": "Squad updated successfully.",
  "Squad criada com sucesso.": "Squad created successfully.",
  "Squad removida com sucesso.": "Squad removed successfully.",
  "Squads": "Squads",
  "Status das integrações": "Integration status",
  "Subset de tools": "Tools subset",
  "Subset de tools resolvido": "Resolved tools subset",
  "Subset efetivo do catálogo de tools do core.": "Effective subset of the core tools catalog.",
  "Supervised": "Supervised",
  "System Prompt": "System Prompt",
  "TTS ativo": "TTS active",
  "Templates": "Templates",
  "Tente outra busca para voltar a visualizar a distribuicao dos workspaces e squads.": "Try another search to view workspace and squad distribution again.",
  "Texto simples": "Plain text",
  "Time dedicado dentro deste workspace.": "Dedicated team inside this workspace.",
  "Timezone": "Timezone",
  "Tom": "Tone",
  "Tool Policy JSON": "Tool Policy JSON",
  "Tools habilitadas": "Enabled tools",
  "Use esta área para dados exclusivos do agente que não sejam sensíveis.": "Use this area for agent-exclusive data that is not sensitive.",
  "Use segredos locais quando a credencial não deve ficar disponível para outros agentes.": "Use local secrets when the credential should not be available to other agents.",
  "Validacao concluida.": "Validation completed.",
  "Validar": "Validate",
  "Validar, verificar e publicar o agente.": "Validate, verify and publish the agent.",
  "Valores": "Values",
  "Valores globais não sensíveis que este agente pode receber do sistema.": "Non-sensitive global values this agent may receive from the system.",
  "Valores não sensíveis usados somente por este agente. Segredos devem ficar no vault local abaixo.": "Non-sensitive values used only by this agent. Secrets must stay in the local vault below.",
  "Variáveis compartilhadas": "Shared variables",
  "Variáveis de texto": "Text variables",
  "Variáveis globais": "Global variables",
  "Variáveis locais do agente": "Agent local variables",
  "Verificacoes de publicacao ok.": "Publishing checks passed.",
  "Verificado": "Verified",
  "Verificar": "Verify",
  "Você está substituindo o valor de": "You are replacing the value of",
  "Voice Policy JSON": "Voice Policy JSON",
  "Voice Prompt": "Voice Prompt",
  "Voice active": "Voice active",
  "Voz": "Voice",
  "Workflow padrao": "Default workflow",
  "{{count}} bot": "{{count}} bot",
  "{{count}} bots": "{{count}} bots",
  "{{count}} bot no catálogo": "{{count}} bot in the catalog",
  "{{count}} bots no catálogo": "{{count}} bots in the catalog",
  "Workspace atualizado com sucesso.": "Espaço de trabalho atualizado com sucesso.",
  "Workspace criado com sucesso.": "Espaço de trabalho criado com sucesso.",
  "Workspace removido com sucesso.": "Espacio de trabajo eliminado con éxito.",
  "Workspaces": "Espacios de trabajo",
  "Zona de Perigo": "Danger zone",
  "baseline": "baseline",
  "mascarado": "masked",
  "new": "new",
  "novo-agente-id": "new-agent-id",
  "{{count}} agente(s) selecionado(s)": "{{count}} agent(s) selected",
  "{{count}} agente(s) sincronizado(s)": "{{count}} agent(s) synced",
  "{{count}} agentes movidos para {{target}}.": "{{count}} agents moved to {{target}}.",
  "{{count}} bot(s)": "{{count}} bot(s)",
  "{{count}} bot(s) no catálogo": "{{count}} bot(s) in the catalog",
  "{{count}} core tools": "{{count}} core tools",
  "{{count}} item(ns)": "{{count}} item(s)",
  "{{count}} item(s) existente(s)": "{{count}} existing item(s)",
  "{{count}} pendente(s)": "{{count}} pending",
  "{{done}} concluido(s) · {{failed}} falha(s)": "{{done}} completed · {{failed}} failed",
  "{{done}} de {{total}} atualizados em background. Você pode continuar navegando normalmente.": "{{done}} of {{total}} updated in the background. You can keep navigating normally.",
  "{{moved}} agentes movidos e {{failed}} falharam.": "{{moved}} agents moved and {{failed}} failed.",
  "{{selected}}/{{total}} concedido(s)": "{{selected}}/{{total}} granted",
  "{{title}} salvos com sucesso.": "{{title}} saved successfully.",
});

Object.assign(literalResources["es-ES"] as Record<string, string>, {
  "A chave do segredo e obrigatoria.": "La clave del secreto es obligatoria.",
  "A configuração está consistente. Nenhum aviso no momento.": "La configuración es consistente. No hay avisos por ahora.",
  "Abrir configuracoes do sistema": "Abrir configuraciones del sistema",
  "Abrir editor": "Abrir editor",
  "Acoes irreversiveis.": "Acciones irreversibles.",
  "Acoes proibidas": "Acciones prohibidas",
  "Add new": "Añadir nuevo",
  "Adicionar": "Añadir",
  "Adicionar squad": "Añadir equipo",
  "Advanced JSON": "JSON avanzado",
  "Agente movido para {{target}}.": "Agente movido a {{target}}.",
  "Agente removido com sucesso.": "Agente eliminado con éxito.",
  "Aplicar": "Aplicar",
  "Applied": "Aplicado",
  "Approval mode padrao": "Modo de aprobación predeterminado",
  "Aprovando...": "Aprobando...",
  "Aprovar candidate": "Aprobar candidate",
  "Arraste agentes aqui para deixá-los fora de um workspace.": "Arrastra agentes aquí para dejarlos fuera de cualquier workspace.",
  "Arraste agentes para ca para reorganizar a composicao deste time.": "Arrastra agentes aquí para reorganizar la composición de este equipo.",
  "Arraste qualquer agente selecionado para mover o lote inteiro de uma vez.": "Arrastra cualquier agente seleccionado para mover todo el lote de una vez.",
  "As configurações globais valem para toda a conta, mas este agente só recebe variáveis e segredos quando o grant estiver marcado abaixo. Tools, providers e demais capacidades continuam governados na aba Recursos.": "La configuración global vale para toda la cuenta, pero este agente solo recibe variables y secretos cuando la concesión está activada abajo. Tools, providers y el resto de capacidades siguen gobernados en la pestaña Recursos.",
  "Assinatura / login": "Suscripción / acceso",
  "Ativa": "Activa",
  "Ativos": "Activos",
  "Atualizar": "Actualizar",
  "Atualizar fila": "Actualizar cola",
  "Atualizar segredo local": "Actualizar secreto local",
  "Autonomy Policy JSON": "Autonomy Policy JSON",
  "Autonomy tier padrao": "Nivel de autonomía predeterminado",
  "Ação {{action}} aplicada em {{agentId}}.": "Acción {{action}} aplicada en {{agentId}}.",
  "Bot": "Bot",
  "Bot clonado com sucesso.": "Bot clonado con éxito.",
  "Bot criado com sucesso.": "Bot creado con éxito.",
  "Bot removido.": "Bot eliminado.",
  "Bot {{id}} criado com sucesso.": "Bot {{id}} creado con éxito.",
  "Bots": "Bots",
  "Bots livres": "Bots libres",
  "Bots livres, ainda fora de um workspace. Arraste para organizar.": "Bots libres, todavía fuera de un workspace. Arrastra para organizarlos.",
  "Budget acumulado": "Presupuesto acumulado",
  "Budget por tarefa": "Presupuesto por tarea",
  "Budget por tarefa (USD)": "Presupuesto por tarea (USD)",
  "Budget total (USD)": "Presupuesto total (USD)",
  "Buscar bots por nome, ID, workspace ou squad": "Buscar bots por nombre, ID, workspace o equipo",
  "Buscar por nome, ID, workspace ou squad...": "Buscar por nombre, ID, workspace o equipo...",
  "Cada bot recebe apenas um subset do catálogo governado pelo core.": "Cada bot recibe solo un subconjunto del catálogo gobernado por el core.",
  "Calmo": "Calmo",
  "Camadas ativas": "Capas activas",
  "Camadas, recall semântico e governança de proveniência.": "Capas, recuerdo semántico y gobernanza de procedencia.",
  "Cancel": "Cancelar",
  "Cancelar": "Cancelar",
  "Candidate ID": "ID del candidate",
  "Candidate aprovado com sucesso.": "Candidate aprobado con éxito.",
  "Candidate rejeitado com sucesso.": "Candidate rechazado con éxito.",
  "Canônico": "Canónico",
  "Catálogo dinâmico dos bots, defaults globais e atalhos de publicação.": "Catálogo dinámico de bots, defaults globales y atajos de publicación.",
  "Catálogo governado pelo sistema": "Catálogo gobernado por el sistema",
  "Chave": "Clave",
  "Clonando": "Clonando",
  "Clonar Agente": "Clonar agente",
  "Clonar agente": "Clonar agente",
  "Colaborativo": "Colaborativo",
  "Cole o segredo aqui": "Pega aquí el secreto",
  "Collapse": "Colapsar",
  "Como o agente responde, decide e se contém.": "Cómo responde, decide y se contiene el agente.",
  "Compatibilidade de provider": "Compatibilidad del provider",
  "Completo": "Completo",
  "Comportamento salvo com sucesso.": "Comportamiento guardado con éxito.",
  "Conceder acesso": "Conceder acceso",
  "Concedido": "Concedido",
  "Concisao": "Concisión",
  "Conectado": "Conectado",
  "Conecte serviços externos ao sistema.": "Conecta servicios externos al sistema.",
  "Conexões verificadas": "Conexiones verificadas",
  "Conferencia final": "Revisión final",
  "Configuracao": "Configuración",
  "Configuracoes gerais salvas com sucesso.": "Configuraciones generales guardadas con éxito.",
  "Configuracoes globais e governanca": "Configuraciones globales y gobernanza",
  "Configuradas": "Configuradas",
  "Configurado": "Configurado",
  "Configure providers, runtime, integracoes, variaveis compartilhadas e o vault global em um unico lugar. Cada agente recebe apenas os grants explicitamente aprovados.": "Configura providers, runtime, integraciones, variables compartidas y el vault global en un solo lugar. Cada agente recibe únicamente los grants aprobados explícitamente.",
  "Conhecimento": "Conocimiento",
  "Conhecimento e RAG": "Conocimiento y RAG",
  "Continuar": "Continuar",
  "Control Plane": "Control Plane",
  "Copia": "Copia",
  "Copia de...": "Copia de...",
  "Core tools": "Core tools",
  "Credenciais exclusivas deste agente. Permanecem mascaradas e não entram em grants de outros bots.": "Credenciales exclusivas de este agente. Permanecen enmascaradas y no entran en grants de otros bots.",
  "Criando bot": "Creando bot",
  "Criando...": "Creando...",
  "Criar": "Crear",
  "Criar agente": "Crear agente",
  "Criar bot": "Crear bot",
  "Criar novo workspace": "Crear nuevo workspace",
  "Criar squad em {{workspace}}": "Crear equipo en {{workspace}}",
  "Criar uma copia deste agente.": "Crear una copia de este agente.",
  "Criterios de sucesso": "Criterios de éxito",
  "Defaults globais": "Defaults globales",
  "Defaults globais atualizados.": "Defaults globales actualizados.",
  "Defaults globais salvos com sucesso.": "Defaults globales guardados con éxito.",
  "Defina exatamente quais recursos globais este agente pode receber do sistema.": "Define exactamente qué recursos globales puede recibir este agente del sistema.",
  "Defina nome, aparencia e organizacao base do agente.": "Define el nombre, la apariencia y la organización base del agente.",
  "Defina nome, descricao curta e a cor de apoio visual desta organizacao.": "Define el nombre, la descripción breve y el color de apoyo visual de esta organización.",
  "Defina o tipo, escopo e descrição do recurso global.": "Define el tipo, el alcance y la descripción del recurso global.",
  "Delete": "Eliminar",
  "Delete secret {{key}}": "Eliminar secreto {{key}}",
  "Delete {{name}}": "Eliminar {{name}}",
  "Desabilitada": "Deshabilitada",
  "Desabilitado": "Deshabilitado",
  "Desabilitar": "Deshabilitar",
  "Descrever e analisar": "Describir y analizar",
  "Descricao": "Descripción",
  "Descricao curta opcional": "Descripción breve opcional",
  "Desired": "Deseado",
  "Destino: {{target}}": "Destino: {{target}}",
  "Detalhado": "Detallado",
  "Diagnosticos de publicacao": "Diagnósticos de publicación",
  "Digite para substituir": "Escribe para reemplazar",
  "Digite um novo valor para substituir": "Escribe un valor nuevo para reemplazar",
  "Direto": "Directo",
  "Display name": "Nombre visible",
  "Disponíveis por grant": "Disponibles por grant",
  "Disponível globalmente": "Disponible globalmente",
  "Disponível por grant": "Disponible por grant",
  "Documentos do workspace": "Documentos del workspace",
  "Memória, conhecimento e autonomia": "Memoria, conocimiento y autonomía",
  "Perfis guiados definem a baseline. Os campos estruturados abaixo refinam o contrato canônico usado também nas configurações por bot.": "Los perfiles guiados definen la baseline. Los campos estructurados de abajo refinan el contrato canónico usado también en la configuración por bot.",
  "Recall, aprendizado contínuo e auto manutenção do agente.": "Recall, aprendizaje continuo y auto-mantenimiento del agente.",
  "Preset-base para retenção, recall e manutenção.": "Preset base para retención, recall y mantenimiento.",
  "Perfil atual": "Perfil actual",
  "Os presets servem como ponto de partida; os campos abaixo refinam o comportamento.": "Los presets sirven como punto de partida; los campos de abajo refinan el comportamiento.",
  "Grounding com proveniência, semântica e camadas confiáveis.": "Grounding con procedencia, semántica y capas confiables.",
  "Perfil de conhecimento": "Perfil de conocimiento",
  "Preset-base para camadas, recall e frescor.": "Preset base para capas, recall y frescura.",
  "Baseline de governança para owner e freshness.": "Baseline de gobernanza para owner y freshness.",
  "Autonomia operacional": "Autonomía operacional",
  "Envelope padrão para execuções longas, complexas e supervisionadas.": "Envelope predeterminado para ejecuciones largas, complejas y supervisadas.",
  "Duplicata criada: {{id}}": "Duplicado creado: {{id}}",
  "Duracao alvo": "Duración objetivo",
  "EXEMPLO_BOT": "EJEMPLO_BOT",
  "Editar squad": "Editar equipo",
  "Editar squad {{squad}}": "Editar equipo {{squad}}",
  "Editar variável local": "Editar variable local",
  "Editar workspace": "Editar workspace",
  "Editar workspace {{workspace}}": "Editar workspace {{workspace}}",
  "Email": "Correo",
  "Envelope de modelo": "Envelope de modelo",
  "Envelope global de modelos": "Envelope global de modelos",
  "Enxuto": "Ligero",
  "Equilibrado": "Equilibrado",
  "Erro ao clonar.": "Error al clonar.",
  "Erro ao criar agente.": "Error al crear el agente.",
  "Erro ao duplicar agente.": "Error al duplicar el agente.",
  "Erro ao executar {{endpoint}}.": "Error al ejecutar {{endpoint}}.",
  "Erro ao processar candidate.": "Error al procesar el candidate.",
  "Erro ao remover bot.": "Error al eliminar el bot.",
  "Erro ao remover item.": "Error al eliminar el elemento.",
  "Erro ao remover organizacao.": "Error al eliminar la organización.",
  "Erro ao remover segredo local.": "Error al eliminar el secreto local.",
  "Erro ao remover segredo.": "Error al eliminar el secreto.",
  "Erro ao revalidar runbook.": "Error al revalidar el runbook.",
  "Erro ao salvar comportamento.": "Error al guardar el comportamiento.",
  "Erro ao salvar defaults.": "Error al guardar los defaults.",
  "Erro ao salvar escopo.": "Error al guardar el alcance.",
  "Erro ao salvar organizacao.": "Error al guardar la organización.",
  "Erro ao salvar politicas.": "Error al guardar las políticas.",
  "Erro ao salvar recursos.": "Error al guardar los recursos.",
  "Erro ao salvar segredo local.": "Error al guardar el secreto local.",
  "Erro ao salvar segredo.": "Error al guardar el secreto.",
  "Erro ao salvar {{title}}.": "Error al guardar {{title}}.",
  "Escalation required": "Escalada obligatoria",
  "Escolha apenas providers e modelos realmente suportados pelo core.": "Elige solo providers y modelos realmente soportados por el core.",
  "Escolha o provider principal e as instrucoes iniciais do agente.": "Elige el provider principal y las instrucciones iniciales del agente.",
  "Escolha um provider e um modelo habilitados pelo core.": "Elige un provider y un modelo habilitados por el core.",
  "Escopo de acesso do agente": "Alcance de acceso del agente",
  "Escopo do agente salvo com sucesso.": "Alcance del agente guardado con éxito.",
  "Espaço reservado para criar um novo time neste workspace.": "Espacio reservado para crear un nuevo equipo en este workspace.",
  "Estado dos providers": "Estado de los providers",
  "Estilo": "Estilo",
  "Estilo de colaboracao": "Estilo de colaboración",
  "Estilo de escalacao": "Estilo de escalado",
  "Estilo de escrita": "Estilo de escritura",
  "Estruturado": "Estructurado",
  "Ex.: Plataforma": "Ej.: Plataforma",
  "Ex.: Produto": "Ej.: Producto",
  "Ex.: squad-platform": "Ej.: squad-platform",
  "Ex: 12": "Ej.: 12",
  "Ex: 30-45s": "Ej.: 30-45s",
  "Ex: 5": "Ej.: 5",
  "Ex: Resolver tickets e incidentes com grounding": "Ej.: resolver tickets e incidentes con grounding",
  "Ex: SRE autonomo supervisionado": "Ej.: SRE autónomo supervisado",
  "Ex: acuracia, lead time, cobertura de fontes": "Ej.: exactitud, lead time, cobertura de fuentes",
  "Ex: calmo, executivo, amigavel": "Ej.: calmo, ejecutivo, amable",
  "Ex: citar label e data quando grounded": "Ej.: citar label y fecha cuando haya grounding",
  "Ex: conciso, objetivo e rastreavel": "Ej.: conciso, objetivo y trazable",
  "Ex: deploy sem aprovacao explicita": "Ej.: despliegue sin aprobación explícita",
  "Ex: entender, buscar grounding, agir, verificar": "Ej.: entender, buscar grounding, actuar, verificar",
  "Ex: escalar com contexto e proposta": "Ej.: escalar con contexto y propuesta",
  "Ex: escalar com contexto e proxima acao sugerida": "Ej.: escalar con contexto y próxima acción sugerida",
  "Ex: evitar inferir identidade, checar texto sensivel": "Ej.: evitar inferir identidad, revisar texto sensible",
  "Ex: funcionario tecnico confiavel": "Ej.: operador técnico confiable",
  "Ex: honestidade, grounding, ownership": "Ej.: honestidad, grounding, ownership",
  "Ex: nao aprovar deploy em producao": "Ej.: no aprobar despliegues en producción",
  "Ex: nao expor segredos ou PII": "Ej.: no exponer secretos ni PII",
  "Ex: nao inventar fatos": "Ej.: no inventar hechos",
  "Ex: objetos, texto, contexto, risco": "Ej.: objetos, texto, contexto, riesgo",
  "Ex: preferir knowledge canonico e runbooks": "Ej.: preferir knowledge canónico y runbooks",
  "Ex: producao exige confirmacao humana": "Ej.: producción exige confirmación humana",
  "Ex: profissional, rastreavel, sem invencao": "Ej.: profesional, trazable, sin invención",
  "Ex: propor, executar, verificar": "Ej.: proponer, ejecutar, verificar",
  "Ex: reduzir tempo de triagem": "Ej.: reducir tiempo de triaje",
  "Ex: resposta correta, segura e verificavel": "Ej.: respuesta correcta, segura y verificable",
  "Ex: usar modelo menor para triagem": "Ej.: usar un modelo menor para el triaje",
  "Exemplo Bot": "Bot de ejemplo",
  "Expand": "Expandir",
  "Expectativas de handoff": "Expectativas de handoff",
  "Falha ao criar bot.": "Falló al crear el bot.",
  "Falha ao executar {{action}}.": "Falló al ejecutar {{action}}.",
  "Falha ao executar {{endpoint}}.": "Falló al ejecutar {{endpoint}}.",
  "Falha ao salvar defaults globais.": "Falló al guardar los defaults globales.",
  "Fallback": "Fallback",
  "Fechar": "Cerrar",
  "Fechar formulario": "Cerrar formulario",
  "Ferramentas configuráveis": "Herramientas configurables",
  "Formato": "Formato",
  "Funcao profissional desempenhada pelo agente.": "Función profesional desempeñada por el agente.",
  "Gerado automaticamente a partir do nome. Editavel.": "Generado automáticamente a partir del nombre. Editable.",
  "Gerenciamento de secrets — chaves de API, tokens e credenciais.": "Gestión de secrets: claves API, tokens y credenciales.",
  "Global": "Global",
  "Global defaults": "Defaults globales",
  "Governanca e aprendizado": "Gobernanza y aprendizaje",
  "Governança": "Gobernanza",
  "Grantável": "Concedible",
  "Guarded": "Protegido",
  "Habilitada": "Habilitada",
  "Habilitado": "Habilitado",
  "Habilitar": "Habilitar",
  "Health port": "Puerto health",
  "Herança base para novos bots e overrides": "Herencia base para nuevos bots y overrides",
  "Herdar do sistema": "Heredar del sistema",
  "Heuristicas de execucao": "Heurísticas de ejecución",
  "Historico de Versoes": "Historial de versiones",
  "ID": "ID",
  "ID do Clone": "ID del clon",
  "ID do agente e obrigatorio.": "El ID del agente es obligatorio.",
  "ID do clone e obrigatorio.": "El ID del clon es obligatorio.",
  "Identidade": "Identidad",
  "Identificador unico para o novo agente.": "Identificador único para el nuevo agente.",
  "Identity": "Identidad",
  "Idioma": "Idioma",
  "Image Analysis Policy JSON": "Image Analysis Policy JSON",
  "Image Prompt (image_prompt_md)": "Image Prompt (image_prompt_md)",
  "Imagem": "Imagen",
  "Inativa": "Inactiva",
  "Indicadores de qualidade ou desempenho.": "Indicadores de calidad o rendimiento.",
  "Indicadores do board": "Indicadores del board",
  "Indisponível": "No disponible",
  "Informe o nome da variável local.": "Indica el nombre de la variable local.",
  "Informe o nome da variável.": "Indica el nombre de la variable.",
  "Informe o nome do segredo local.": "Indica el nombre del secreto local.",
  "Informe o valor da variável local.": "Indica el valor de la variable local.",
  "Informe o valor do segredo local.": "Indica el valor del secreto local.",
  "Informe um candidate ID valido.": "Indica un ID de candidate válido.",
  "Informe um runbook ID valido.": "Indica un ID de runbook válido.",
  "Informe um valor inicial para o segredo.": "Indica un valor inicial para el secreto.",
  "Informe um valor para a variável.": "Indica un valor para la variable.",
  "Instrucoes": "Instrucciones",
  "Instrucoes do agente": "Instrucciones del agente",
  "Instructions": "Instrucciones",
  "Instruções especializadas para análise visual e comportamento de fallback.": "Instrucciones especializadas para análisis visual y comportamiento de fallback.",
  "Integracoes globais": "Integraciones globales",
  "Integrações ativas": "Integraciones activas",
  "Item {{id}} removido.": "Elemento {{id}} eliminado.",
  "JIRA_API_TOKEN": "JIRA_API_TOKEN",
  "JSON syntax error detected": "Se detectó un error de sintaxis JSON",
  "KPIs": "KPIs",
  "Knowledge Assets": "Knowledge Assets",
  "Knowledge Policy JSON": "Knowledge Policy JSON",
  "Knowledge candidates pendentes": "Knowledge candidates pendientes",
  "Limite de {{count}} itens atingido": "Se alcanzó el límite de {{count}} elementos",
  "Limites de responsabilidade": "Límites de responsabilidad",
  "Limpar seleção": "Limpiar selección",
  "Local ao agente": "Local al agente",
  "Luminosidade": "Luminosidad",
  "MEU_AGENTE": "MI_AGENTE",
  "Mascarado": "Enmascarado",
  "Memory Extraction Prompt (memory_extraction_prompt_md)": "Memory Extraction Prompt (memory_extraction_prompt_md)",
  "Memory Extraction Schema": "Memory Extraction Schema",
  "Memory Policy JSON": "Memory Policy JSON",
  "Memória global": "Memoria global",
  "Memória persistente": "Memoria persistente",
  "Mesmo contrato canônico usado nas configurações globais.": "El mismo contrato canónico usado en las configuraciones globales.",
  "Missao": "Misión",
  "Missao e estilo": "Misión y estilo",
  "Model Policy JSON": "Model Policy JSON",
  "Modelo": "Modelo",
  "Modelo e instrucoes": "Modelo e instrucciones",
  "Modelo padrao": "Modelo predeterminado",
  "Modelo principal usado no provider padrao.": "Modelo principal usado en el provider predeterminado.",
  "Modelos e providers": "Modelos y providers",
  "Modo": "Modo",
  "Mostrar mais squads de {{section}}": "Mostrar más equipos de {{section}}",
  "Mostrar squads anteriores de {{section}}": "Mostrar equipos anteriores de {{section}}",
  "Movendo {{count}} agente(s) para {{target}}": "Moviendo {{count}} agente(s) a {{target}}",
  "Namespace": "Namespace",
  "Nao foi possivel mover os agentes selecionados.": "No fue posible mover los agentes seleccionados.",
  "Nao negociaveis": "No negociables",
  "Nenhum": "Ninguno",
  "Nenhum agente corresponde a esta busca nesta area.": "Ningún agente coincide con esta búsqueda en esta área.",
  "Nenhum agente encontrado": "No se encontró ningún agente",
  "Nenhum segredo cadastrado.": "No hay secretos registrados.",
  "Nenhum segredo global disponível ainda. Cadastre-os primeiro em Configurações gerais.": "Todavía no hay secretos globales disponibles. Regístralos primero en Configuraciones generales.",
  "Nenhum segredo local cadastrado para este agente.": "No hay secretos locales registrados para este agente.",
  "Nenhuma": "Ninguna",
  "Nenhuma ativa": "Ninguna activa",
  "Nenhuma variável global customizada foi adicionada ainda.": "Todavía no se ha agregado ninguna variable global personalizada.",
  "Nenhuma variável global disponível ainda. Crie-as primeiro em Configurações gerais.": "Todavía no hay variables globales disponibles. Créelas primero en Configuraciones generales.",
  "Nenhuma variável local cadastrada para este agente.": "No hay variables locales registradas para este agente.",
  "Nenhuma versao disponivel.": "No hay versiones disponibles.",
  "Nome da chave": "Nombre de la clave",
  "Nome da squad": "Nombre del equipo",
  "Nome de exibicao do novo agente.": "Nombre visible del nuevo agente.",
  "Nome do Clone": "Nombre del clon",
  "Nome do workspace": "Nombre del workspace",
  "Notas de seguranca": "Notas de seguridad",
  "Nova squad": "Nuevo equipo",
  "Nova variável local": "Nueva variable local",
  "Novo bot self-hosted": "Nuevo bot self-hosted",
  "Novo segredo": "Nuevo secreto",
  "Novo segredo local": "Nuevo secreto local",
  "Novo valor": "Nuevo valor",
  "Novo workspace": "Nuevo workspace",
  "Não encontrado nas variáveis globais atuais": "No se encontró en las variables globales actuales",
  "Não encontrado no vault atual": "No se encontró en el vault actual",
  "O bot pode escolher apenas dentro deste envelope do core.": "El bot solo puede elegir dentro de este envelope del core.",
  "O bot só poderá usar tools do core explicitamente aprovadas.": "El bot solo podrá usar tools del core aprobadas explícitamente.",
  "O nome e obrigatorio.": "El nombre es obligatorio.",
  "O objetivo central do agente.": "El objetivo central del agente.",
  "O que o bot sabe — assets, templates, skills e politicas.": "Lo que sabe el bot: assets, templates, skills y políticas.",
  "O valor atual continua mascarado e não é exibido pela interface.": "El valor actual sigue enmascarado y no se muestra en la interfaz.",
  "O valor do segredo e obrigatorio.": "El valor del secreto es obligatorio.",
  "Obrigatório": "Obligatorio",
  "Onde o agente deve parar e escalar.": "Dónde debe detenerse y escalar el agente.",
  "Opcional": "Opcional",
  "Opcional. Limite suave para uma tarefa.": "Opcional. Límite suave para una tarea.",
  "Opcional. Teto global acumulado.": "Opcional. Tope global acumulado.",
  "Organize squads e distribua os agentes deste workspace.": "Organiza los equipos y distribuye los agentes de este workspace.",
  "Origem das camadas": "Origen de las capas",
  "Os bots só habilitam subsets desse catálogo.": "Los bots solo habilitan subconjuntos de este catálogo.",
  "Outcomes principais": "Resultados principales",
  "Override avancado usado pelo runtime quando a politica de voz estiver ativa.": "Override avanzado usado por el runtime cuando la política de voz está activa.",
  "Override bruto do schema canônico completo.": "Override bruto del esquema canónico completo.",
  "Overrides JSON avancados": "Overrides JSON avanzados",
  "Padrões observados": "Patrones observados",
  "Papel": "Rol",
  "Pendente": "Pendiente",
  "Perfil de memória": "Perfil de memoria",
  "Perfil de uso": "Perfil de uso",
  "Perfil operacional e forma de colaboracao do agente.": "Perfil operativo y forma de colaboración del agente.",
  "Persona": "Persona",
  "Pipeline de Publicacao": "Pipeline de publicación",
  "Policies e capabilities": "Policies y capabilities",
  "Politica de citacao": "Política de citación",
  "Politica de fontes": "Política de fuentes",
  "Politicas de conhecimento": "Políticas de conocimiento",
  "Politicas de conhecimento salvas.": "Políticas de conocimiento guardadas.",
  "Política avançada de análise visual.": "Política avanzada de análisis visual.",
  "Política avançada de voz/TTS.": "Política avanzada de voz/TTS.",
  "Política de proveniência": "Política de procedencia",
  "Política especializada de TTS/fala e prompt avançado correspondente.": "Política especializada de TTS/voz y prompt avanzado correspondiente.",
  "Ponto de entrada do workspace para bots sem time definido.": "Punto de entrada del workspace para bots sin equipo definido.",
  "Portugues (Brasil)": "Portugués (Brasil)",
  "Preencha apenas para substituir.": "Rellena solo para reemplazar.",
  "Preencha o valor": "Rellena el valor",
  "Prioridades de analise": "Prioridades de análisis",
  "Proativa": "Proactiva",
  "Procedural": "Procedural",
  "Profissional": "Profesional",
  "Prompt Compilado": "Prompt compilado",
  "Prompt de analise de imagem.": "Prompt de análisis de imagen.",
  "Prompt de extracao de memoria.": "Prompt de extracción de memoria.",
  "Prompts derivados e overrides avancados": "Prompts derivados y overrides avanzados",
  "Protegido no sistema": "Protegido en el sistema",
  "Proveniencia e freshness": "Procedencia y freshness",
  "Provider padrao": "Provider predeterminado",
  "Provider padrão": "Provider predeterminado",
  "Provider preferido para a maioria dos turnos.": "Provider preferido para la mayoría de los turnos.",
  "Providers": "Providers",
  "Providers habilitados": "Providers habilitados",
  "Providers permitidos": "Providers permitidos",
  "Publicado": "Publicado",
  "Publico e contexto": "Público y contexto",
  "Quality bar": "Quality bar",
  "Quem recebe as respostas e em que contexto ele atua.": "Quién recibe las respuestas y en qué contexto actúa.",
  "RAG global": "RAG global",
  "Rascunho": "Borrador",
  "Rate limit": "Rate limit",
  "Read only": "Solo lectura",
  "Recursos livres do operador com tipo, descrição e escopo explícitos.": "Recursos del operador con tipo, descripción y alcance explícitos.",
  "Recursos salvos com sucesso.": "Recursos guardados con éxito.",
  "Regras de seguranca": "Reglas de seguridad",
  "Rejeitando...": "Rechazando...",
  "Rejeitar candidate": "Rechazar candidate",
  "Removendo": "Eliminando",
  "Remover acesso": "Quitar acceso",
  "Remover agente": "Eliminar agente",
  "Remover agente permanentemente": "Eliminar agente permanentemente",
  "Remover permanentemente este agente, incluindo todas as configuracoes, documentos, versoes e credenciais associadas.": "Eliminar permanentemente este agente, incluyendo configuraciones, documentos, versiones y credenciales asociadas.",
  "Remover segredo": "Eliminar secreto",
  "Remover squad": "Eliminar equipo",
  "Remover squad {{squad}}": "Eliminar equipo {{squad}}",
  "Remover workspace": "Eliminar workspace",
  "Remover workspace {{workspace}}": "Eliminar workspace {{workspace}}",
  "Remover {{key}}": "Eliminar {{key}}",
  "Requisitos de aprovacao": "Requisitos de aprobación",
  "Responsável": "Responsable",
  "Resposta, operacao e guardrails": "Respuesta, operación y guardrails",
  "Resultados que o agente deve perseguir continuamente.": "Resultados que el agente debe perseguir continuamente.",
  "Resumir visualmente": "Resumir visualmente",
  "Revalidando...": "Revalidando...",
  "Revalidar runbook": "Revalidar runbook",
  "Rules": "Rules",
  "Runbook ID": "ID del runbook",
  "Runbook revalidado com sucesso.": "Runbook revalidado con éxito.",
  "Runbooks aprovados": "Runbooks aprobados",
  "Salvando": "Guardando",
  "Salvando defaults": "Guardando defaults",
  "Salvando...": "Guardando...",
  "Salvar defaults": "Guardar defaults",
  "Salvar politicas": "Guardar políticas",
  "Salvar segredo": "Guardar secreto",
  "Schema canonico completo de autonomia, incluindo task_overrides.": "Esquema canónico completo de autonomía, incluyendo task_overrides.",
  "Schema canônico que o runtime materializa de verdade.": "Esquema canónico que el runtime materializa de verdad.",
  "Schema de extracao de memoria.": "Esquema de extracción de memoria.",
  "Segredo local": "Secreto local",
  "Segredos": "Secretos",
  "Segredos criptografados do vault global. O bot só recebe o que for explicitamente concedido.": "Secretos cifrados del vault global. El bot solo recibe lo que se concede explícitamente.",
  "Segredos existentes ({{count}})": "Secretos existentes ({{count}})",
  "Segredos globais": "Secretos globales",
  "Segredos locais do agente": "Secretos locales del agente",
  "Selecione outros cards para formar um lote, ou arraste este agente para mover agora.": "Selecciona otras tarjetas para formar un lote, o arrastra este agente para moverlo ahora.",
  "Sem descrição": "Sin descripción",
  "Sem limite": "Sin límite",
  "Sem plano detectado": "Sin plan detectado",
  "Sem valor configurado": "Sin valor configurado",
  "Sem valor preenchido": "Sin valor informado",
  "Ser conservador": "Ser conservador",
  "Será removido ao salvar": "Se eliminará al guardar",
  "Skills": "Skills",
  "Solte aqui para remover o vínculo com qualquer workspace.": "Suelta aquí para quitar el vínculo con cualquier workspace.",
  "Soul / Interaction Style": "Soul / Interaction Style",
  "Spec efetivo": "Spec efectivo",
  "Squad atualizada com sucesso.": "Equipo actualizado con éxito.",
  "Squad criada com sucesso.": "Equipo creado con éxito.",
  "Squad removida com sucesso.": "Equipo eliminado con éxito.",
  "Squads": "Equipos",
  "Status das integrações": "Estado de las integraciones",
  "Subset de tools": "Subset de tools",
  "Subset de tools resolvido": "Subset de tools resuelto",
  "Subset efetivo do catálogo de tools do core.": "Subset efectivo del catálogo de tools del core.",
  "Supervised": "Supervisado",
  "System Prompt": "System Prompt",
  "TTS ativo": "TTS activo",
  "Templates": "Templates",
  "Tente outra busca para voltar a visualizar a distribuicao dos workspaces e squads.": "Prueba otra búsqueda para volver a ver la distribución de workspaces y equipos.",
  "Texto simples": "Texto simple",
  "Time dedicado dentro deste workspace.": "Equipo dedicado dentro de este workspace.",
  "Timezone": "Zona horaria",
  "Tom": "Tono",
  "Tool Policy JSON": "Tool Policy JSON",
  "Tools habilitadas": "Tools habilitadas",
  "Use esta área para dados exclusivos do agente que não sejam sensíveis.": "Usa esta área para datos exclusivos del agente que no sean sensibles.",
  "Use segredos locais quando a credencial não deve ficar disponível para outros agentes.": "Usa secretos locales cuando la credencial no deba estar disponible para otros agentes.",
  "Validacao concluida.": "Validación concluida.",
  "Validar": "Validar",
  "Validar, verificar e publicar o agente.": "Validar, verificar y publicar el agente.",
  "Valores": "Valores",
  "Valores globais não sensíveis que este agente pode receber do sistema.": "Valores globales no sensibles que este agente puede recibir del sistema.",
  "Valores não sensíveis usados somente por este agente. Segredos devem ficar no vault local abaixo.": "Valores no sensibles usados solo por este agente. Los secretos deben quedar en el vault local inferior.",
  "Variáveis compartilhadas": "Variables compartidas",
  "Variáveis de texto": "Variables de texto",
  "Variáveis globais": "Variables globales",
  "Variáveis locais do agente": "Variables locales del agente",
  "Verificacoes de publicacao ok.": "Verificaciones de publicación correctas.",
  "Verificado": "Verificado",
  "Verificar": "Verificar",
  "Você está substituindo o valor de": "Estás sustituyendo el valor de",
  "Voice Policy JSON": "Voice Policy JSON",
  "Voice Prompt": "Voice Prompt",
  "Voice active": "Voice active",
  "Voz": "Voz",
  "Workflow padrao": "Workflow predeterminado",
  "{{count}} bot": "{{count}} bot",
  "{{count}} bots": "{{count}} bots",
  "{{count}} bot no catálogo": "{{count}} bot en el catálogo",
  "{{count}} bots no catálogo": "{{count}} bots en el catálogo",
  "Workspace atualizado com sucesso.": "Espacio de trabajo actualizado con éxito.",
  "Workspace criado com sucesso.": "Espacio de trabajo creado con éxito.",
  "Workspace removido com sucesso.": "Espacio de trabajo eliminado con éxito.",
  "Workspaces": "Espacios de trabajo",
  "Zona de Perigo": "Zona de peligro",
  "baseline": "baseline",
  "mascarado": "enmascarado",
  "new": "nuevo",
  "novo-agente-id": "nuevo-agente-id",
  "{{count}} agente(s) selecionado(s)": "{{count}} agente(s) seleccionado(s)",
  "{{count}} agente(s) sincronizado(s)": "{{count}} agente(s) sincronizado(s)",
  "{{count}} agentes movidos para {{target}}.": "{{count}} agentes movidos a {{target}}.",
  "{{count}} bot(s)": "{{count}} bot(s)",
  "{{count}} bot(s) no catálogo": "{{count}} bot(s) en el catálogo",
  "{{count}} core tools": "{{count}} core tools",
  "{{count}} item(ns)": "{{count}} elemento(s)",
  "{{count}} item(s) existente(s)": "{{count}} elemento(s) existente(s)",
  "{{count}} pendente(s)": "{{count}} pendiente(s)",
  "{{done}} concluido(s) · {{failed}} falha(s)": "{{done}} completado(s) · {{failed}} fallo(s)",
  "{{done}} de {{total}} atualizados em background. Você pode continuar navegando normalmente.": "{{done}} de {{total}} actualizados en segundo plano. Puedes seguir navegando con normalidad.",
  "{{moved}} agentes movidos e {{failed}} falharam.": "{{moved}} agentes movidos y {{failed}} fallaron.",
  "{{selected}}/{{total}} concedido(s)": "{{selected}}/{{total}} concedido(s)",
  "{{title}} salvos com sucesso.": "{{title}} guardados con éxito.",
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mutableResources = resources as unknown as Record<string, { translation: Record<string, any> }>;

mutableResources["en-US"].translation.overview = {
  toolbar: {
    visibleBots: "{{count}} visible agents",
  },
  greeting: {
    morning: "Good morning, {{name}}",
    afternoon: "Good afternoon, {{name}}",
    evening: "Good evening, {{name}}",
    night: "Still up, {{name}}?",
    fallback: "Good to see you, {{name}}",
  },
  composer: {
    placeholder: "Ask Koda or start a task…",
    submit: "Send",
    actions: {
      runTask: "Run task",
      newSchedule: "New schedule",
      newAgent: "New agent",
      reviewMemory: "Review memory",
    },
  },
  heatmap: {
    title: "Agent activity",
    subtitle: "Last six months of execution signals across your agents.",
    tooltip: "{{count}} signals on {{date}}",
    emptyTooltip: "{{date}} — idle",
    less: "less",
    more: "more",
    tabs: {
      all: "All",
      "30d": "30d",
      "7d": "7d",
    },
    stats: {
      activeDays: "Active days",
      totalSignals: "Total signals",
      peakDay: "Peak day",
      peakHint: "{{count}} signals",
      longestStreak: "Longest streak",
      days: "{{count}} days",
      days_one: "{{count}} day",
      days_other: "{{count}} days",
    },
    footerActive: "{{total}} execution signals over the last {{days}} days.",
    footerEmpty: "No execution signals yet — run a task to start populating this map.",
  },
  liveAgents: {
    title: "Live agents",
    empty: "No agents in the current selection.",
    viewAll: "Runtime",
    active: "{{count}} active",
    idle: "Idle",
    waiting: "Waiting for base",
  },
  roster: {
    empty: "No agents in the current selection.",
    noActiveMessage: "No message published",
    lastDelivery: "Last delivery {{value}}",
    waitingFirst: "Waiting for first execution",
    status: {
      running: "Running",
      retrying: "Retrying",
      queued: "Queued",
      idle: "Idle",
      waiting: "Waiting",
    },
  },
  history: {
    title: "Recent activity",
    subtitle: "Last executions",
    empty: "No executions yet.",
    noMessage: "No message",
    status: {
      completed: "Completed",
      failed: "Failed",
      running: "Running",
      retrying: "Retrying",
      queued: "Queued",
    },
  },
  news: {
    eyebrow: "Latest",
    title: "Koda 1.4",
    body: "New activity heatmap on Home.",
  },
  stats: {
    totalTasks: "Total tasks",
    activeTasks: "Active tasks",
    totalQueries: "Total queries",
    costToday: "Cost today",
    operating: "{{count}} operating",
    noActiveOperation: "No active operation",
    waiting: "{{count}} waiting",
    coveragePublished: "Published coverage",
    inPeriod: "{{value}} in period",
  },
  sections: {
    recentActivityTitle: "Recent activity",
    recentActivityDescription: "Recent signals from filtered agents.",
    currentScope: "Current scope",
    livePlanTitle: "Live plan",
    livePlanDescription: "Expand to see what each agent is doing right now.",
    livePlanHint: "Expanding shows recent activities for the filtered scope.",
    focusSingle: "Focused agent",
    focusMultiple: "Latest agent signals",
    focusDescription: "Name, current activity and latest published message.",
    costsTitle: "Costs",
    costsDescription: "Consolidated window for the filtered scope.",
    totalInPeriod: "Total in period",
  },
  activity: {
    activeNow: "{{count}} active now",
    lastActivity: "Last activity {{value}}",
    waiting: "Waiting",
    noBase: "No database",
    noPublishedActivity: "No published activity",
    waitingForNewExecutions: "Waiting for new executions",
    waitingFirstExecution: "Waiting for the first execution",
    connectedNoRecent:
      "This agent is connected, but has not published new activity in the current window.",
    botNotReady:
      "This agent has not yet published enough tasks or messages to feed monitoring.",
    base: "base",
    connected: "Connected",
    pending: "Pending",
    queries: "queries",
    noPublishedMessage: "No published message",
    executing: "Running",
    lastDelivery: "Last delivery",
    completed: "Completed {{value}}",
    failed: "Failed {{value}}",
    activeAt: "Active {{value}}",
    session: "session {{value}}",
    attempt: "attempt {{current}}/{{max}}",
  },
  taskStatus: {
    running: "Running",
    retrying: "Retrying",
    queued: "Queued",
    completed: "Completed",
    failed: "Failed",
  },
};

mutableResources["pt-BR"].translation.overview = {
  toolbar: {
    visibleBots: "{{count}} BOTs visíveis",
  },
  greeting: {
    morning: "Bom dia, {{name}}",
    afternoon: "Boa tarde, {{name}}",
    evening: "Boa noite, {{name}}",
    night: "Ainda acordado, {{name}}?",
    fallback: "Que bom te ver, {{name}}",
  },
  composer: {
    placeholder: "Pergunte ao Koda ou inicie uma tarefa…",
    submit: "Enviar",
    actions: {
      runTask: "Executar tarefa",
      newSchedule: "Novo agendamento",
      newAgent: "Novo agente",
      reviewMemory: "Revisar memória",
    },
  },
  heatmap: {
    title: "Atividade dos agentes",
    subtitle: "Últimos seis meses de sinais de execução dos seus agentes.",
    tooltip: "{{count}} sinais em {{date}}",
    emptyTooltip: "{{date}} — inativo",
    less: "menos",
    more: "mais",
    tabs: {
      all: "Tudo",
      "30d": "30d",
      "7d": "7d",
    },
    stats: {
      activeDays: "Dias ativos",
      totalSignals: "Sinais totais",
      peakDay: "Pico",
      peakHint: "{{count}} sinais",
      longestStreak: "Maior sequência",
      days: "{{count}} dias",
      days_one: "{{count}} dia",
      days_other: "{{count}} dias",
    },
    footerActive: "{{total}} sinais de execução nos últimos {{days}} dias.",
    footerEmpty: "Sem sinais de execução ainda — rode uma tarefa para alimentar o mapa.",
  },
  liveAgents: {
    title: "Agentes ativos",
    empty: "Nenhum agente na seleção atual.",
    viewAll: "Runtime",
    active: "{{count}} ativos",
    idle: "Ocioso",
    waiting: "Aguardando base",
  },
  roster: {
    empty: "Nenhum agente na seleção atual.",
    noActiveMessage: "Nenhuma mensagem publicada",
    lastDelivery: "Última entrega {{value}}",
    waitingFirst: "Aguardando primeira execução",
    status: {
      running: "Em execução",
      retrying: "Reprocessando",
      queued: "Na fila",
      idle: "Ocioso",
      waiting: "Aguardando",
    },
  },
  history: {
    title: "Atividade recente",
    subtitle: "Últimas execuções",
    empty: "Sem execuções ainda.",
    noMessage: "Sem mensagem",
    status: {
      completed: "Concluído",
      failed: "Falhou",
      running: "Em execução",
      retrying: "Reprocessando",
      queued: "Na fila",
    },
  },
  news: {
    eyebrow: "Novidade",
    title: "Koda 1.4",
    body: "Novo heatmap de atividade na Home.",
  },
  stats: {
    totalTasks: "Total de tarefas",
    activeTasks: "Tarefas ativas",
    totalQueries: "Total de consultas",
    costToday: "Custo hoje",
    operating: "{{count}} operando",
    noActiveOperation: "Sem operação ativa",
    waiting: "{{count}} em espera",
    coveragePublished: "Cobertura publicada",
    inPeriod: "{{value}} no período",
  },
  sections: {
    recentActivityTitle: "Atividade recente",
    recentActivityDescription: "Sinais recentes dos agentes filtrados.",
    currentScope: "Escopo atual",
    livePlanTitle: "Plano vivo",
    livePlanDescription: "Expanda para ver o que cada agente está fazendo agora.",
    livePlanHint: "Expandir mostra as atividades recentes do escopo filtrado.",
    focusSingle: "Agente em foco",
    focusMultiple: "Últimos sinais dos agentes",
    focusDescription: "Nome, atividade atual e última mensagem publicada.",
    costsTitle: "Custos",
    costsDescription: "Janela consolidada do escopo filtrado.",
    totalInPeriod: "Total no período",
  },
  activity: {
    activeNow: "{{count}} ativa{{count !== 1 ? 's' : ''}} agora",
    lastActivity: "Última atividade {{value}}",
    waiting: "Em espera",
    noBase: "Sem base",
    noPublishedActivity: "Sem atividade publicada",
    waitingForNewExecutions: "Aguardando novas execuções",
    waitingFirstExecution: "Aguardando primeira execução",
    connectedNoRecent:
      "Este agente está conectado, mas ainda não publicou uma nova atividade na janela atual.",
    botNotReady:
      "Este agente ainda não publicou tarefas ou mensagens suficientes para alimentar o monitoramento.",
    base: "base",
    connected: "Conectada",
    pending: "Pendente",
    queries: "consultas",
    noPublishedMessage: "Sem mensagem publicada",
    executing: "Executando",
    lastDelivery: "Última entrega",
    completed: "Concluída {{value}}",
    failed: "Falhou {{value}}",
    activeAt: "Ativa {{value}}",
    session: "sessão {{value}}",
    attempt: "tentativa {{current}}/{{max}}",
  },
  taskStatus: {
    running: "Executando",
    retrying: "Retentando",
    queued: "Na fila",
    completed: "Concluída",
    failed: "Falhou",
  },
};

mutableResources["es-ES"].translation.overview = {
  toolbar: {
    visibleBots: "{{count}} agentes visibles",
  },
  greeting: {
    morning: "Buen día, {{name}}",
    afternoon: "Buenas tardes, {{name}}",
    evening: "Buenas noches, {{name}}",
    night: "¿Despierto aún, {{name}}?",
    fallback: "Qué bueno verte, {{name}}",
  },
  composer: {
    placeholder: "Pregúntale a Koda o inicia una tarea…",
    submit: "Enviar",
    actions: {
      runTask: "Ejecutar tarea",
      newSchedule: "Nueva programación",
      newAgent: "Nuevo agente",
      reviewMemory: "Revisar memoria",
    },
  },
  heatmap: {
    title: "Actividad de agentes",
    subtitle: "Últimos seis meses de señales de ejecución de tus agentes.",
    tooltip: "{{count}} señales en {{date}}",
    emptyTooltip: "{{date}} — inactivo",
    less: "menos",
    more: "más",
    tabs: {
      all: "Todo",
      "30d": "30d",
      "7d": "7d",
    },
    stats: {
      activeDays: "Días activos",
      totalSignals: "Señales totales",
      peakDay: "Pico",
      peakHint: "{{count}} señales",
      longestStreak: "Racha más larga",
      days: "{{count}} días",
      days_one: "{{count}} día",
      days_other: "{{count}} días",
    },
    footerActive: "{{total}} señales de ejecución en los últimos {{days}} días.",
    footerEmpty: "Aún no hay señales de ejecución — ejecuta una tarea para empezar a llenar el mapa.",
  },
  liveAgents: {
    title: "Agentes activos",
    empty: "Ningún agente en la selección actual.",
    viewAll: "Runtime",
    active: "{{count}} activos",
    idle: "Inactivo",
    waiting: "Esperando base",
  },
  roster: {
    empty: "Ningún agente en la selección actual.",
    noActiveMessage: "Sin mensaje publicado",
    lastDelivery: "Última entrega {{value}}",
    waitingFirst: "Esperando primera ejecución",
    status: {
      running: "En ejecución",
      retrying: "Reintentando",
      queued: "En cola",
      idle: "Inactivo",
      waiting: "Esperando",
    },
  },
  history: {
    title: "Actividad reciente",
    subtitle: "Últimas ejecuciones",
    empty: "Aún no hay ejecuciones.",
    noMessage: "Sin mensaje",
    status: {
      completed: "Completado",
      failed: "Fallido",
      running: "En ejecución",
      retrying: "Reintentando",
      queued: "En cola",
    },
  },
  news: {
    eyebrow: "Novedad",
    title: "Koda 1.4",
    body: "Nuevo heatmap de actividad en la Home.",
  },
  stats: {
    totalTasks: "Tareas totales",
    activeTasks: "Tareas activas",
    totalQueries: "Consultas totales",
    costToday: "Costo hoy",
    operating: "{{count}} operando",
    noActiveOperation: "Sin operación activa",
    waiting: "{{count}} en espera",
    coveragePublished: "Cobertura publicada",
    inPeriod: "{{value}} en el período",
  },
  sections: {
    recentActivityTitle: "Actividad reciente",
    recentActivityDescription: "Señales recientes de los agentes filtrados.",
    currentScope: "Alcance actual",
    livePlanTitle: "Plan vivo",
    livePlanDescription: "Expande para ver qué está haciendo cada agente ahora mismo.",
    livePlanHint: "Expandir muestra las actividades recientes del alcance filtrado.",
    focusSingle: "Agente en foco",
    focusMultiple: "Últimas señales de los agentes",
    focusDescription: "Nombre, actividad actual y último mensaje publicado.",
    costsTitle: "Costos",
    costsDescription: "Ventana consolidada del alcance filtrado.",
    totalInPeriod: "Total en el período",
  },
  activity: {
    activeNow: "{{count}} activa ahora",
    lastActivity: "Última actividad {{value}}",
    waiting: "En espera",
    noBase: "Sin base",
    noPublishedActivity: "Sin actividad publicada",
    waitingForNewExecutions: "Esperando nuevas ejecuciones",
    waitingFirstExecution: "Esperando la primera ejecución",
    connectedNoRecent:
      "Este agente está conectado, pero aún no publicó actividad nueva en la ventana actual.",
    botNotReady:
      "Este agente todavía no publicó suficientes tareas o mensajes para alimentar el monitoreo.",
    base: "base",
    connected: "Conectada",
    pending: "Pendiente",
    queries: "consultas",
    noPublishedMessage: "Sin mensaje publicado",
    executing: "Ejecutando",
    lastDelivery: "Última entrega",
    completed: "Completada {{value}}",
    failed: "Falló {{value}}",
    activeAt: "Activa {{value}}",
    session: "sesión {{value}}",
    attempt: "intento {{current}}/{{max}}",
  },
  taskStatus: {
    running: "Ejecutando",
    retrying: "Reintentando",
    queued: "En cola",
    completed: "Completada",
    failed: "Falló",
  },
};

mutableResources["fr-FR"].translation.overview = {
  ...mutableResources["en-US"].translation.overview,
  toolbar: {
    visibleBots: "{{count}} agents visibles",
  },
  greeting: {
    morning: "Bonjour, {{name}}",
    afternoon: "Bon après-midi, {{name}}",
    evening: "Bonsoir, {{name}}",
    night: "Encore debout, {{name}} ?",
    fallback: "Content de vous voir, {{name}}",
  },
  composer: {
    placeholder: "Demandez à Koda ou lancez une tâche…",
    submit: "Envoyer",
    actions: {
      runTask: "Lancer la tâche",
      newSchedule: "Nouvelle planification",
      newAgent: "Nouvel agent",
      reviewMemory: "Revoir la mémoire",
    },
  },
  heatmap: {
    ...mutableResources["en-US"].translation.overview.heatmap,
    title: "Activité des agents",
    subtitle: "Six derniers mois de signaux d'exécution de vos agents.",
    tooltip: "{{count}} signaux le {{date}}",
    emptyTooltip: "{{date}} — inactif",
    less: "moins",
    more: "plus",
    stats: {
      activeDays: "Jours actifs",
      totalSignals: "Signaux totaux",
      peakDay: "Jour de pointe",
      peakHint: "{{count}} signaux",
      longestStreak: "Plus longue série",
      days: "{{count}} jours",
      days_one: "{{count}} jour",
      days_other: "{{count}} jours",
    },
    footerActive: "{{total}} signaux d'exécution sur les {{days}} derniers jours.",
    footerEmpty: "Aucun signal d'exécution pour l'instant — lancez une tâche pour remplir cette carte.",
  },
  liveAgents: {
    title: "Agents en direct",
    empty: "Aucun agent dans la sélection actuelle.",
    viewAll: "Runtime",
    active: "{{count}} actifs",
    idle: "Inactif",
    waiting: "En attente de base",
  },
  roster: {
    empty: "Aucun agent dans la sélection actuelle.",
    noActiveMessage: "Aucun message publié",
    lastDelivery: "Dernière livraison {{value}}",
    waitingFirst: "En attente de la première exécution",
    status: {
      running: "En cours",
      retrying: "Nouvelle tentative",
      queued: "En file d'attente",
      idle: "Inactif",
      waiting: "En attente",
    },
  },
  history: {
    title: "Activité récente",
    subtitle: "Dernières exécutions",
    empty: "Aucune exécution pour l'instant.",
    noMessage: "Aucun message",
    status: {
      completed: "Terminé",
      failed: "Échoué",
      running: "En cours",
      retrying: "Nouvelle tentative",
      queued: "En file d'attente",
    },
  },
  news: {
    eyebrow: "Nouveautés",
    title: "Koda 1.4",
    body: "Nouvelle carte d'activité sur l'accueil.",
  },
  stats: {
    totalTasks: "Tâches totales",
    activeTasks: "Tâches actives",
    totalQueries: "Requêtes totales",
    costToday: "Coût aujourd'hui",
    operating: "{{count}} en fonctionnement",
    noActiveOperation: "Aucune opération active",
    waiting: "{{count}} en attente",
    coveragePublished: "Couverture publiée",
    inPeriod: "{{value}} sur la période",
  },
  sections: {
    recentActivityTitle: "Activité récente",
    recentActivityDescription: "Signaux récents des agents filtrés.",
    currentScope: "Portée actuelle",
    livePlanTitle: "Plan en direct",
    livePlanDescription: "Développez pour voir ce que fait chaque agent en ce moment.",
    livePlanHint: "Le développement affiche les activités récentes de la portée filtrée.",
    focusSingle: "Agent ciblé",
    focusMultiple: "Derniers signaux d'agent",
    focusDescription: "Nom, activité actuelle et dernier message publié.",
    costsTitle: "Coûts",
    costsDescription: "Fenêtre consolidée pour la portée filtrée.",
    totalInPeriod: "Total sur la période",
  },
  activity: {
    activeNow: "{{count}} actifs maintenant",
    lastActivity: "Dernière activité {{value}}",
    waiting: "En attente",
    noBase: "Aucune base de données",
    noPublishedActivity: "Aucune activité publiée",
    waitingForNewExecutions: "En attente de nouvelles exécutions",
    waitingFirstExecution: "En attente de la première exécution",
    connectedNoRecent:
      "Cet agent est connecté, mais n'a publié aucune nouvelle activité dans la fenêtre actuelle.",
    botNotReady:
      "Cet agent n'a pas encore publié suffisamment de tâches ou de messages pour alimenter le suivi.",
    base: "base",
    connected: "Connecté",
    pending: "En attente",
    queries: "requêtes",
    noPublishedMessage: "Aucun message publié",
    executing: "En cours",
    lastDelivery: "Dernière livraison",
    completed: "Terminé {{value}}",
    failed: "Échoué {{value}}",
    activeAt: "Actif {{value}}",
    session: "session {{value}}",
    attempt: "tentative {{current}}/{{max}}",
  },
  taskStatus: {
    running: "En cours",
    retrying: "Nouvelle tentative",
    queued: "En file d'attente",
    completed: "Terminé",
    failed: "Échoué",
  },
};

mutableResources["de-DE"].translation.overview = {
  ...mutableResources["en-US"].translation.overview,
  toolbar: {
    visibleBots: "{{count}} sichtbare Agenten",
  },
  greeting: {
    morning: "Guten Morgen, {{name}}",
    afternoon: "Guten Tag, {{name}}",
    evening: "Guten Abend, {{name}}",
    night: "Noch wach, {{name}}?",
    fallback: "Schön, Sie zu sehen, {{name}}",
  },
  composer: {
    placeholder: "Koda fragen oder eine Aufgabe starten…",
    submit: "Senden",
    actions: {
      runTask: "Aufgabe ausführen",
      newSchedule: "Neuer Zeitplan",
      newAgent: "Neuer Agent",
      reviewMemory: "Speicher überprüfen",
    },
  },
  heatmap: {
    ...mutableResources["en-US"].translation.overview.heatmap,
    title: "Agenten-Aktivität",
    subtitle: "Letzte sechs Monate Ausführungssignale Ihrer Agenten.",
    tooltip: "{{count}} Signale am {{date}}",
    emptyTooltip: "{{date}} — inaktiv",
    less: "weniger",
    more: "mehr",
    stats: {
      activeDays: "Aktive Tage",
      totalSignals: "Gesamte Signale",
      peakDay: "Spitzentag",
      peakHint: "{{count}} Signale",
      longestStreak: "Längste Serie",
      days: "{{count}} Tage",
      days_one: "{{count}} Tag",
      days_other: "{{count}} Tage",
    },
    footerActive: "{{total}} Ausführungssignale in den letzten {{days}} Tagen.",
    footerEmpty: "Noch keine Ausführungssignale — starten Sie eine Aufgabe, um diese Karte zu füllen.",
  },
  liveAgents: {
    title: "Live-Agenten",
    empty: "Keine Agenten in der aktuellen Auswahl.",
    viewAll: "Laufzeit",
    active: "{{count}} aktiv",
    idle: "Untätig",
    waiting: "Warten auf Basis",
  },
  roster: {
    empty: "Keine Agenten in der aktuellen Auswahl.",
    noActiveMessage: "Keine Nachricht veröffentlicht",
    lastDelivery: "Letzte Lieferung {{value}}",
    waitingFirst: "Warten auf erste Ausführung",
    status: {
      running: "Läuft",
      retrying: "Wiederholung",
      queued: "In Warteschlange",
      idle: "Untätig",
      waiting: "Warten",
    },
  },
  history: {
    title: "Aktuelle Aktivität",
    subtitle: "Letzte Ausführungen",
    empty: "Noch keine Ausführungen.",
    noMessage: "Keine Nachricht",
    status: {
      completed: "Abgeschlossen",
      failed: "Fehlgeschlagen",
      running: "Läuft",
      retrying: "Wiederholung",
      queued: "In Warteschlange",
    },
  },
  news: {
    eyebrow: "Neuestes",
    title: "Koda 1.4",
    body: "Neue Aktivitäts-Heatmap auf der Startseite.",
  },
  stats: {
    totalTasks: "Gesamtaufgaben",
    activeTasks: "Aktive Aufgaben",
    totalQueries: "Gesamtanfragen",
    costToday: "Kosten heute",
    operating: "{{count}} in Betrieb",
    noActiveOperation: "Keine aktive Operation",
    waiting: "{{count}} wartend",
    coveragePublished: "Veröffentlichte Abdeckung",
    inPeriod: "{{value}} im Zeitraum",
  },
  sections: {
    recentActivityTitle: "Aktuelle Aktivität",
    recentActivityDescription: "Aktuelle Signale gefilterter Agenten.",
    currentScope: "Aktueller Geltungsbereich",
    livePlanTitle: "Live-Plan",
    livePlanDescription: "Erweitern, um zu sehen, was jeder Agent gerade tut.",
    livePlanHint: "Die Erweiterung zeigt aktuelle Aktivitäten für den gefilterten Bereich.",
    focusSingle: "Fokussierter Agent",
    focusMultiple: "Letzte Agent-Signale",
    focusDescription: "Name, aktuelle Aktivität und zuletzt veröffentlichte Nachricht.",
    costsTitle: "Kosten",
    costsDescription: "Konsolidiertes Fenster für den gefilterten Bereich.",
    totalInPeriod: "Gesamt im Zeitraum",
  },
  activity: {
    activeNow: "{{count}} jetzt aktiv",
    lastActivity: "Letzte Aktivität {{value}}",
    waiting: "Warten",
    noBase: "Keine Datenbank",
    noPublishedActivity: "Keine veröffentlichte Aktivität",
    waitingForNewExecutions: "Warten auf neue Ausführungen",
    waitingFirstExecution: "Warten auf die erste Ausführung",
    connectedNoRecent:
      "Dieser Agent ist verbunden, hat aber im aktuellen Fenster keine neue Aktivität veröffentlicht.",
    botNotReady:
      "Dieser Agent hat noch nicht genügend Aufgaben oder Nachrichten veröffentlicht, um das Monitoring zu speisen.",
    base: "Basis",
    connected: "Verbunden",
    pending: "Ausstehend",
    queries: "Abfragen",
    noPublishedMessage: "Keine veröffentlichte Nachricht",
    executing: "Läuft",
    lastDelivery: "Letzte Lieferung",
    completed: "Abgeschlossen {{value}}",
    failed: "Fehlgeschlagen {{value}}",
    activeAt: "Aktiv {{value}}",
    session: "Sitzung {{value}}",
    attempt: "Versuch {{current}}/{{max}}",
  },
  taskStatus: {
    running: "Läuft",
    retrying: "Wiederholung",
    queued: "In Warteschlange",
    completed: "Abgeschlossen",
    failed: "Fehlgeschlagen",
  },
};

mutableResources["en-US"].translation.overview.activity = {
  ...mutableResources["en-US"].translation.overview.activity,
  latestExecutions: "Latest executions",
  events: "{{count}} events",
  noRecent: "No recent activity",
  showingRecent: "Showing the most recent events",
  taskCompleted: "Task completed",
  taskFailed: "Task failed",
  taskStarted: "Task started",
  taskQueued: "Task queued",
  deploy: "Deploy",
  retry: "Retry",
  noRecentExecution: "No recent execution",
  baseConnected: "connected base",
  noBaseTag: "no base",
  queriesCount: "{{count}} queries",
  waitingFirstPublishedExecution: "Waiting for the first published execution to start the live plan.",
  noRecentPublished: "No recent activity published in the current selection.",
  attemptLabel: "attempt",
};

mutableResources["pt-BR"].translation.overview.activity = {
  ...mutableResources["pt-BR"].translation.overview.activity,
  latestExecutions: "Últimas execuções",
  events: "{{count}} eventos",
  noRecent: "Nenhuma atividade recente",
  showingRecent: "Exibindo os eventos mais recentes",
  taskCompleted: "Tarefa concluída",
  taskFailed: "Tarefa falhou",
  taskStarted: "Tarefa iniciada",
  taskQueued: "Tarefa na fila",
  deploy: "Deploy",
  retry: "Retentativa",
  noRecentExecution: "Sem execução recente",
  baseConnected: "base conectada",
  noBaseTag: "sem base",
  queriesCount: "{{count}} consultas",
  waitingFirstPublishedExecution: "Aguardando primeira execução publicada para iniciar o plano vivo.",
  noRecentPublished: "Sem atividade recente publicada no recorte atual.",
  attemptLabel: "tentativa",
};

mutableResources["fr-FR"].translation.overview.activity = {
  ...mutableResources["fr-FR"].translation.overview.activity,
  latestExecutions: "Dernières exécutions",
  events: "{{count}} événements",
  noRecent: "Aucune activité récente",
  showingRecent: "Affichage des événements les plus récents",
  taskCompleted: "Tâche terminée",
  taskFailed: "Tâche échouée",
  taskStarted: "Tâche démarrée",
  taskQueued: "Tâche en file",
  deploy: "Déployer",
  retry: "Réessayer",
  noRecentExecution: "Aucune exécution récente",
  baseConnected: "base connectée",
  noBaseTag: "aucune base",
  queriesCount: "{{count}} requêtes",
  waitingFirstPublishedExecution: "En attente de la première exécution publiée pour démarrer le plan en direct.",
  noRecentPublished: "Aucune activité récente publiée dans la sélection actuelle.",
  attemptLabel: "tentative",
};

mutableResources["de-DE"].translation.overview.activity = {
  ...mutableResources["de-DE"].translation.overview.activity,
  latestExecutions: "Letzte Ausführungen",
  events: "{{count}} Ereignisse",
  noRecent: "Keine aktuelle Aktivität",
  showingRecent: "Anzeige der aktuellsten Ereignisse",
  taskCompleted: "Aufgabe abgeschlossen",
  taskFailed: "Aufgabe fehlgeschlagen",
  taskStarted: "Aufgabe gestartet",
  taskQueued: "Aufgabe in Warteschlange",
  deploy: "Bereitstellen",
  retry: "Erneut versuchen",
  noRecentExecution: "Keine aktuelle Ausführung",
  baseConnected: "verbundene Basis",
  noBaseTag: "keine Basis",
  queriesCount: "{{count}} Abfragen",
  waitingFirstPublishedExecution: "Warten auf die erste veröffentlichte Ausführung, um den Live-Plan zu starten.",
  noRecentPublished: "Keine aktuelle Aktivität in der aktuellen Auswahl veröffentlicht.",
  attemptLabel: "Versuch",
};

mutableResources["es-ES"].translation.overview.activity = {
  ...mutableResources["es-ES"].translation.overview.activity,
  latestExecutions: "Últimas ejecuciones",
  events: "{{count}} eventos",
  noRecent: "No hay actividad reciente",
  showingRecent: "Mostrando los eventos más recientes",
  taskCompleted: "Tarea completada",
  taskFailed: "Tarea falló",
  taskStarted: "Tarea iniciada",
  taskQueued: "Tarea en cola",
  deploy: "Deploy",
  retry: "Reintento",
  noRecentExecution: "Sin ejecución reciente",
  baseConnected: "base conectada",
  noBaseTag: "sin base",
  queriesCount: "{{count}} consultas",
  waitingFirstPublishedExecution: "Esperando la primera ejecución publicada para iniciar el plan vivo.",
  noRecentPublished: "No hay actividad reciente publicada en el recorte actual.",
  attemptLabel: "intento",
};

mutableResources["en-US"].translation.screenTime = {
  aggregate: "Aggregate activity",
  last24h: "in the last 24h",
  hourlyWindow: "consolidated hourly window",
  focusBots: "Bots in focus",
  items: "{{count}} items",
};

mutableResources["pt-BR"].translation.screenTime = {
  aggregate: "Atividade agregada",
  last24h: "nas últimas 24h",
  hourlyWindow: "janela horária consolidada",
  focusBots: "Bots em foco",
  items: "{{count}} itens",
};

mutableResources["es-ES"].translation.screenTime = {
  aggregate: "Actividad agregada",
  last24h: "en las últimas 24h",
  hourlyWindow: "ventana horaria consolidada",
  focusBots: "Bots en foco",
  items: "{{count}} elementos",
};

mutableResources["fr-FR"].translation.screenTime = {
  aggregate: "Activité agrégée",
  last24h: "au cours des dernières 24h",
  hourlyWindow: "fenêtre horaire consolidée",
  focusBots: "Bots en focus",
  items: "{{count}} éléments",
};

mutableResources["de-DE"].translation.screenTime = {
  aggregate: "Aggregierte Aktivität",
  last24h: "in den letzten 24 Std.",
  hourlyWindow: "konsolidiertes Stundenfenster",
  focusBots: "Bots im Fokus",
  items: "{{count}} Einträge",
};

mutableResources["en-US"].translation.executions.page = {
  statusAll: "All",
  statusCompleted: "Completed",
  statusRunning: "Running",
  statusQueued: "Queued",
  statusFailed: "Failed",
  statusRetrying: "Retrying",
  noSelection: "No execution selected.",
  detailLoadError: "Could not load execution details.",
  metrics: {
    cost: "Cost",
    avgDuration: "Avg. duration",
    tools: "Tools",
    warnings: "Warnings",
  },
};

mutableResources["pt-BR"].translation.executions.page = {
  statusAll: "Todas",
  statusCompleted: "Concluídas",
  statusRunning: "Executando",
  statusQueued: "Na fila",
  statusFailed: "Falhas",
  statusRetrying: "Retentando",
  noSelection: "Nenhuma execução selecionada.",
  detailLoadError: "Não foi possível carregar os detalhes da execução.",
  metrics: {
    cost: "Custo",
    avgDuration: "Duração média",
    tools: "Ferramentas",
    warnings: "Avisos",
  },
};

mutableResources["es-ES"].translation.executions.page = {
  statusAll: "Todas",
  statusCompleted: "Completadas",
  statusRunning: "Ejecutando",
  statusQueued: "En cola",
  statusFailed: "Fallidas",
  statusRetrying: "Reintentando",
  noSelection: "Ninguna ejecución seleccionada.",
  detailLoadError: "No se pudieron cargar los detalles de la ejecución.",
  metrics: {
    cost: "Costo",
    avgDuration: "Duración media",
    tools: "Herramientas",
    warnings: "Avisos",
  },
};

mutableResources["fr-FR"].translation.executions.page = {
  statusAll: "Toutes",
  statusCompleted: "Terminées",
  statusRunning: "En cours",
  statusQueued: "En file",
  statusFailed: "Échouées",
  statusRetrying: "Nouvelle tentative",
  noSelection: "Aucune exécution sélectionnée.",
  detailLoadError: "Impossible de charger les détails de l'exécution.",
  metrics: {
    cost: "Coût",
    avgDuration: "Durée moyenne",
    tools: "Outils",
    warnings: "Avertissements",
  },
};

mutableResources["de-DE"].translation.executions.page = {
  statusAll: "Alle",
  statusCompleted: "Abgeschlossen",
  statusRunning: "Läuft",
  statusQueued: "In Warteschlange",
  statusFailed: "Fehlgeschlagen",
  statusRetrying: "Wiederholung",
  noSelection: "Keine Ausführung ausgewählt.",
  detailLoadError: "Ausführungsdetails konnten nicht geladen werden.",
  metrics: {
    cost: "Kosten",
    avgDuration: "Durchschn. Dauer",
    tools: "Tools",
    warnings: "Warnungen",
  },
};

mutableResources["en-US"].translation.executions.table = {
  richTrace: "Rich trace",
  rebuilt: "Rebuilt",
  noTrace: "No trace",
  execution: "Execution",
  queryColumn: "Query",
  trace: "Trace",
  noQuery: "No query",
  noQueryRegistered: "No recorded query",
  noResults: "No executions found.",
  tools: "Tools",
  warnings: "Warnings",
};

mutableResources["pt-BR"].translation.executions.table = {
  richTrace: "Trace rico",
  rebuilt: "Reconstruído",
  noTrace: "Sem trace",
  execution: "Execução",
  queryColumn: "Consulta",
  trace: "Trace",
  noQuery: "Sem consulta",
  noQueryRegistered: "Sem consulta registrada",
  noResults: "Nenhuma execução encontrada.",
  tools: "Ferramentas",
  warnings: "Avisos",
};

mutableResources["es-ES"].translation.executions.table = {
  richTrace: "Trace rico",
  rebuilt: "Reconstruido",
  noTrace: "Sin trace",
  execution: "Ejecución",
  queryColumn: "Consulta",
  trace: "Trace",
  noQuery: "Sin consulta",
  noQueryRegistered: "Sin consulta registrada",
  noResults: "No se encontró ninguna ejecución.",
  tools: "Herramientas",
  warnings: "Avisos",
};

mutableResources["fr-FR"].translation.executions.table = {
  richTrace: "Trace riche",
  rebuilt: "Reconstruit",
  noTrace: "Aucun trace",
  execution: "Exécution",
  queryColumn: "Requête",
  trace: "Trace",
  noQuery: "Aucune requête",
  noQueryRegistered: "Aucune requête enregistrée",
  noResults: "Aucune exécution trouvée.",
  tools: "Outils",
  warnings: "Avertissements",
};

mutableResources["de-DE"].translation.executions.table = {
  richTrace: "Umfangreicher Trace",
  rebuilt: "Neu aufgebaut",
  noTrace: "Kein Trace",
  execution: "Ausführung",
  queryColumn: "Abfrage",
  trace: "Trace",
  noQuery: "Keine Abfrage",
  noQueryRegistered: "Keine Abfrage erfasst",
  noResults: "Keine Ausführungen gefunden.",
  tools: "Tools",
  warnings: "Warnungen",
};

mutableResources["en-US"].translation.sessions.page = {
  openConversations: "Open conversations",
  botChat: "Bot chat",
  chooseBot: "Choose a bot",
  conversationInfo: "Conversation info",
  activity: "activity {{value}}",
  loadingHistory: "Loading history...",
  availableConversations_one: "{{count}} conversation",
  availableConversations_other: "{{count}} conversations",
  noAvailable: "No conversations available",
  chooseConversation: "Choose a conversation to open history",
  switchBot: "Switch the bot in the side rail to see a different history or wait for new sessions.",
  useRail: "Use the side rail to navigate through sessions and follow the conversation full screen.",
  selectHistory: "Select a history or start a new conversation",
  botConversations: "Bot conversations",
  totals: {
    messages_one: "{{count}} message",
    messages_other: "{{count}} messages",
    executions_one: "{{count}} execution",
    executions_other: "{{count}} executions",
  },
};

mutableResources["pt-BR"].translation.sessions.page = {
  openConversations: "Abrir conversas",
  botChat: "Chat do bot",
  chooseBot: "Escolha um bot",
  conversationInfo: "Informações da conversa",
  activity: "atividade {{value}}",
  loadingHistory: "Carregando histórico...",
  availableConversations_one: "{{count}} conversa",
  availableConversations_other: "{{count}} conversas",
  noAvailable: "Nenhuma conversa disponível",
  chooseConversation: "Escolha uma conversa para abrir o histórico",
  switchBot: "Troque o bot na coluna lateral para ver outro histórico ou aguarde novas sessões.",
  useRail: "Use a coluna lateral para navegar entre as sessões e acompanhar a conversa em tela cheia.",
  selectHistory: "Selecione um histórico ou inicie uma nova conversa",
  botConversations: "Conversas do bot",
  totals: {
    messages_one: "{{count}} mensagem",
    messages_other: "{{count}} mensagens",
    executions_one: "{{count}} execução",
    executions_other: "{{count}} execuções",
  },
};

mutableResources["es-ES"].translation.sessions.page = {
  openConversations: "Abrir conversaciones",
  botChat: "Chat del bot",
  chooseBot: "Elige un bot",
  conversationInfo: "Información de la conversación",
  activity: "actividad {{value}}",
  loadingHistory: "Cargando historial...",
  availableConversations_one: "{{count}} conversación",
  availableConversations_other: "{{count}} conversaciones",
  noAvailable: "No hay conversaciones disponibles",
  chooseConversation: "Elige una conversación para abrir el historial",
  switchBot: "Cambia el bot en la columna lateral para ver otro historial o espera nuevas sesiones.",
  useRail: "Usa la columna lateral para navegar entre sesiones y seguir la conversación en pantalla completa.",
  selectHistory: "Selecciona un historial o inicia una nueva conversación",
  botConversations: "Conversaciones del bot",
  totals: {
    messages_one: "{{count}} mensaje",
    messages_other: "{{count}} mensajes",
    executions_one: "{{count}} ejecución",
    executions_other: "{{count}} ejecuciones",
  },
};

mutableResources["fr-FR"].translation.sessions.page = {
  openConversations: "Ouvrir les conversations",
  botChat: "Discussion avec le bot",
  chooseBot: "Choisissez un bot",
  conversationInfo: "Informations sur la conversation",
  activity: "activité {{value}}",
  loadingHistory: "Chargement de l'historique...",
  availableConversations_one: "{{count}} conversation",
  availableConversations_other: "{{count}} conversations",
  noAvailable: "Aucune conversation disponible",
  chooseConversation: "Choisissez une conversation pour ouvrir l'historique",
  switchBot: "Changez de bot dans la colonne latérale pour voir un autre historique ou attendez de nouvelles sessions.",
  useRail: "Utilisez la colonne latérale pour naviguer entre les sessions et suivre la conversation en plein écran.",
  selectHistory: "Sélectionnez un historique ou démarrez une nouvelle conversation",
  botConversations: "Conversations du bot",
  totals: {
    messages_one: "{{count}} message",
    messages_other: "{{count}} messages",
    executions_one: "{{count}} exécution",
    executions_other: "{{count}} exécutions",
  },
};

mutableResources["de-DE"].translation.sessions.page = {
  openConversations: "Unterhaltungen öffnen",
  botChat: "Bot-Chat",
  chooseBot: "Bot wählen",
  conversationInfo: "Informationen zur Unterhaltung",
  activity: "Aktivität {{value}}",
  loadingHistory: "Verlauf wird geladen...",
  availableConversations_one: "{{count}} Unterhaltung",
  availableConversations_other: "{{count}} Unterhaltungen",
  noAvailable: "Keine Unterhaltungen verfügbar",
  chooseConversation: "Wählen Sie eine Unterhaltung, um den Verlauf zu öffnen",
  switchBot: "Wechseln Sie den Bot in der Seitenleiste, um einen anderen Verlauf zu sehen, oder warten Sie auf neue Sitzungen.",
  useRail: "Verwenden Sie die Seitenleiste, um durch Sitzungen zu navigieren und der Unterhaltung im Vollbildmodus zu folgen.",
  selectHistory: "Wählen Sie einen Verlauf oder starten Sie eine neue Unterhaltung",
  botConversations: "Bot-Unterhaltungen",
  totals: {
    messages_one: "{{count}} Nachricht",
    messages_other: "{{count}} Nachrichten",
    executions_one: "{{count}} Ausführung",
    executions_other: "{{count}} Ausführungen",
  },
};

mutableResources["en-US"].translation.sessions.rail = {
  title: "Bot conversations",
  loadingHistory: "Loading history...",
  available: "{{count}} conversations available",
  refresh: "Refresh conversations",
  close: "Close conversation list",
  searchPlaceholder: "Search by name or message",
  loadError: "Could not load conversations",
  unavailable: "History unavailable",
  unavailableDescription: "This bot runtime has not yet exposed sessions to the web.",
  noResults: "No conversations found",
  noResultsDescription: "Switch the bot or adjust the search to find another session.",
  noMessages: "No messages recorded in this conversation.",
  newChat: "New chat",
  recent: "most recent",
  messagesCount: "{{count}} msgs",
};

mutableResources["pt-BR"].translation.sessions.rail = {
  title: "Conversas do bot",
  loadingHistory: "Carregando histórico...",
  available: "{{count}} conversas disponíveis",
  refresh: "Atualizar conversas",
  close: "Fechar lista de conversas",
  searchPlaceholder: "Buscar por nome ou mensagem",
  loadError: "Não foi possível carregar as conversas",
  unavailable: "Histórico indisponível",
  unavailableDescription: "O runtime deste bot ainda não expôs as sessões para o web.",
  noResults: "Nenhuma conversa encontrada",
  noResultsDescription: "Troque o bot ou ajuste a busca para encontrar outra sessão.",
  noMessages: "Sem mensagens registradas nesta conversa.",
  newChat: "Nova conversa",
  recent: "mais recentes",
  messagesCount: "{{count}} msgs",
};

mutableResources["es-ES"].translation.sessions.rail = {
  title: "Conversaciones del bot",
  loadingHistory: "Cargando historial...",
  available: "{{count}} conversaciones disponibles",
  refresh: "Actualizar conversaciones",
  close: "Cerrar lista de conversaciones",
  searchPlaceholder: "Buscar por nombre o mensaje",
  loadError: "No se pudieron cargar las conversaciones",
  unavailable: "Historial no disponible",
  unavailableDescription: "El runtime de este bot todavía no expuso las sesiones en la web.",
  noResults: "No se encontró ninguna conversación",
  noResultsDescription: "Cambia el bot o ajusta la búsqueda para encontrar otra sesión.",
  noMessages: "No hay mensajes registrados en esta conversación.",
  newChat: "Nuevo chat",
  recent: "más recientes",
  messagesCount: "{{count}} msgs",
};

mutableResources["fr-FR"].translation.sessions.rail = {
  title: "Conversations du bot",
  loadingHistory: "Chargement de l'historique...",
  available: "{{count}} conversations disponibles",
  refresh: "Actualiser les conversations",
  close: "Fermer la liste des conversations",
  searchPlaceholder: "Rechercher par nom ou message",
  loadError: "Impossible de charger les conversations",
  unavailable: "Historique indisponible",
  unavailableDescription: "Le runtime de ce bot n'a pas encore exposé les sessions au web.",
  noResults: "Aucune conversation trouvée",
  noResultsDescription: "Changez de bot ou ajustez la recherche pour trouver une autre session.",
  noMessages: "Aucun message enregistré dans cette conversation.",
  newChat: "Nouvelle discussion",
  recent: "les plus récents",
  messagesCount: "{{count}} msgs",
};

mutableResources["de-DE"].translation.sessions.rail = {
  title: "Bot-Unterhaltungen",
  loadingHistory: "Verlauf wird geladen...",
  available: "{{count}} Unterhaltungen verfügbar",
  refresh: "Unterhaltungen aktualisieren",
  close: "Unterhaltungsliste schließen",
  searchPlaceholder: "Nach Name oder Nachricht suchen",
  loadError: "Unterhaltungen konnten nicht geladen werden",
  unavailable: "Verlauf nicht verfügbar",
  unavailableDescription: "Die Laufzeit dieses Bots hat die Sitzungen noch nicht für das Web bereitgestellt.",
  noResults: "Keine Unterhaltung gefunden",
  noResultsDescription: "Wechseln Sie den Bot oder passen Sie die Suche an, um eine andere Sitzung zu finden.",
  noMessages: "In dieser Unterhaltung wurden keine Nachrichten erfasst.",
  newChat: "Neuer Chat",
  recent: "aktuellste",
  messagesCount: "{{count}} Nachr.",
};

mutableResources["en-US"].translation.sessions.detail = {
  runningExecution: "Execution in progress",
  failedExecution: "Execution failed",
  error: "error",
  you: "You",
  close: "Close conversation",
  loadError: "Could not load the conversation",
  emptyTitle: "Select a conversation",
  emptyDescription: "Open a session from the list to follow messages and linked executions.",
  conversation: "Conversation",
  sessionInProgress: "Session in progress",
  orphanEvents: "Events without linked turn",
};

mutableResources["pt-BR"].translation.sessions.detail = {
  runningExecution: "Execução em andamento",
  failedExecution: "Execução com falha",
  error: "erro",
  you: "Você",
  close: "Fechar conversa",
  loadError: "Não foi possível carregar a conversa",
  emptyTitle: "Selecione uma conversa",
  emptyDescription: "Abra uma sessão da lista para acompanhar as mensagens e execuções vinculadas.",
  conversation: "Conversa",
  sessionInProgress: "Sessão em andamento",
  orphanEvents: "Eventos sem turno associado",
};

mutableResources["es-ES"].translation.sessions.detail = {
  runningExecution: "Ejecución en curso",
  failedExecution: "Ejecución con fallo",
  error: "error",
  you: "Tú",
  close: "Cerrar conversación",
  loadError: "No se pudo cargar la conversación",
  emptyTitle: "Selecciona una conversación",
  emptyDescription: "Abre una sesión de la lista para seguir los mensajes y las ejecuciones vinculadas.",
  conversation: "Conversación",
  sessionInProgress: "Sesión en curso",
  orphanEvents: "Eventos sin turno asociado",
  executionLabel: "Execution #{{id}}",
  toolsCount: "{{count}} tools",
  noMessagesYet: "This session has not yet published messages to the queries table.",
};

mutableResources["fr-FR"].translation.sessions.detail = {
  runningExecution: "Exécution en cours",
  failedExecution: "Exécution échouée",
  error: "erreur",
  you: "Vous",
  close: "Fermer la conversation",
  loadError: "Impossible de charger la conversation",
  emptyTitle: "Sélectionnez une conversation",
  emptyDescription: "Ouvrez une session dans la liste pour suivre les messages et les exécutions liées.",
  conversation: "Conversation",
  sessionInProgress: "Session en cours",
  orphanEvents: "Événements sans tour associé",
  executionLabel: "Exécution #{{id}}",
  toolsCount: "{{count}} outils",
  noMessagesYet: "Cette session n'a pas encore publié de messages dans la table des requêtes.",
};

mutableResources["de-DE"].translation.sessions.detail = {
  runningExecution: "Ausführung läuft",
  failedExecution: "Ausführung fehlgeschlagen",
  error: "Fehler",
  you: "Sie",
  close: "Unterhaltung schließen",
  loadError: "Unterhaltung konnte nicht geladen werden",
  emptyTitle: "Wählen Sie eine Unterhaltung",
  emptyDescription: "Öffnen Sie eine Sitzung aus der Liste, um Nachrichten und verknüpfte Ausführungen zu verfolgen.",
  conversation: "Unterhaltung",
  sessionInProgress: "Sitzung läuft",
  orphanEvents: "Ereignisse ohne zugeordneten Turn",
  executionLabel: "Ausführung #{{id}}",
  toolsCount: "{{count}} Tools",
  noMessagesYet: "Diese Sitzung hat noch keine Nachrichten in der Abfragetabelle veröffentlicht.",
};

mutableResources["en-US"].translation.sessions.composer = {
  selectBot: "Select a bot to chat",
  sendingMessage: "Sending message...",
  enterToSend: "Enter to send • Shift + Enter for a line break",
  disabledPlaceholder: "Web sending is not yet available for this bot.",
  selectBotToStart: "Select a specific bot here to start a chat.",
  enabledPlaceholder: "Write your message to start or continue the conversation...",
  syncHint: "History keeps syncing while the conversation stays open.",
  send: "Send",
  sending: "Sending",
};

mutableResources["pt-BR"].translation.sessions.composer = {
  selectBot: "Selecione um bot para conversar",
  sendingMessage: "Enviando mensagem...",
  enterToSend: "Enter para enviar • Shift + Enter para quebrar linha",
  disabledPlaceholder: "O envio web ainda não está disponível para este bot.",
  selectBotToStart: "Selecione um bot específico aqui para iniciar um chat.",
  enabledPlaceholder: "Escreva sua mensagem para iniciar ou continuar a conversa...",
  syncHint: "O histórico continua sendo sincronizado enquanto a conversa está aberta.",
  send: "Enviar",
  sending: "Enviando",
};

mutableResources["es-ES"].translation.sessions.composer = {
  selectBot: "Selecciona un bot para conversar",
  sendingMessage: "Enviando mensaje...",
  enterToSend: "Enter para enviar • Shift + Enter para salto de línea",
  disabledPlaceholder: "El envío web todavía no está disponible para este bot.",
  selectBotToStart: "Selecciona un bot específico aquí para iniciar un chat.",
  enabledPlaceholder: "Escribe tu mensaje para iniciar o continuar la conversación...",
  syncHint: "El historial sigue sincronizándose mientras la conversación está abierta.",
  send: "Enviar",
  sending: "Enviando",
};

mutableResources["fr-FR"].translation.sessions.composer = {
  selectBot: "Sélectionnez un bot pour discuter",
  sendingMessage: "Envoi du message...",
  enterToSend: "Entrée pour envoyer • Maj + Entrée pour un saut de ligne",
  disabledPlaceholder: "L'envoi web n'est pas encore disponible pour ce bot.",
  selectBotToStart: "Sélectionnez ici un bot spécifique pour démarrer une discussion.",
  enabledPlaceholder: "Écrivez votre message pour démarrer ou continuer la conversation...",
  syncHint: "L'historique continue de se synchroniser pendant que la conversation est ouverte.",
  send: "Envoyer",
  sending: "Envoi",
};

mutableResources["de-DE"].translation.sessions.composer = {
  selectBot: "Wählen Sie einen Bot zum Chatten",
  sendingMessage: "Nachricht wird gesendet...",
  enterToSend: "Enter zum Senden • Umschalt + Enter für einen Zeilenumbruch",
  disabledPlaceholder: "Der Web-Versand ist für diesen Bot noch nicht verfügbar.",
  selectBotToStart: "Wählen Sie hier einen bestimmten Bot aus, um einen Chat zu starten.",
  enabledPlaceholder: "Schreiben Sie Ihre Nachricht, um die Unterhaltung zu starten oder fortzusetzen...",
  syncHint: "Der Verlauf wird weiter synchronisiert, solange die Unterhaltung geöffnet ist.",
  send: "Senden",
  sending: "Senden",
};

mutableResources["en-US"].translation.sessions.thread = {
  newConversation: "New conversation",
  lastActive: "Last activity {{value}}",
  chooseBot: "Choose a bot",
  activeBot: "Conversation bot",
  modelUnknown: "Model not informed",
  waitingForReply: "Waiting for the bot reply...",
  loadingOlder: "Loading older messages...",
  pending: "Pending",
  failed: "Failed to send",
  retry: "Retry",
  continueConversation: "Continue the current conversation.",
  startConversationTitle: "Start a new conversation",
  startConversationDescription:
    "Use the composer below to begin a fresh conversation or choose a previous session from the inbox.",
  noBotTitle: "Select a specific bot",
  noBotDescription: "Choose a specific bot in the composer to start a new chat.",
};

mutableResources["pt-BR"].translation.sessions.thread = {
  newConversation: "Nova conversa",
  lastActive: "Última atividade {{value}}",
  chooseBot: "Escolha um bot",
  activeBot: "Bot da conversa",
  modelUnknown: "Modelo não informado",
  waitingForReply: "Aguardando a resposta do bot...",
  loadingOlder: "Carregando mensagens anteriores...",
  pending: "Pendente",
  failed: "Falha no envio",
  retry: "Tentar novamente",
  continueConversation: "Continue a conversa atual.",
  startConversationTitle: "Inicie uma nova conversa",
  startConversationDescription:
    "Use o composer abaixo para começar uma nova conversa ou escolha uma sessão anterior na inbox.",
  noBotTitle: "Selecione um bot específico",
  noBotDescription: "Escolha um bot específico no composer para iniciar um novo chat.",
};

mutableResources["es-ES"].translation.sessions.thread = {
  newConversation: "Nueva conversación",
  lastActive: "Última actividad {{value}}",
  chooseBot: "Elige un bot",
  activeBot: "Bot de la conversación",
  modelUnknown: "Modelo no informado",
  waitingForReply: "Esperando la respuesta del bot...",
  loadingOlder: "Cargando mensajes anteriores...",
  pending: "Pendiente",
  failed: "No se pudo enviar",
  retry: "Reintentar",
  continueConversation: "Continúa la conversación actual.",
  startConversationTitle: "Inicia una nueva conversación",
  startConversationDescription:
    "Usa el composer de abajo para empezar una conversación nueva o elige una sesión anterior en la bandeja.",
  noBotTitle: "Selecciona un bot específico",
  noBotDescription: "Elige un bot específico en el composer para iniciar un chat nuevo.",
};

mutableResources["fr-FR"].translation.sessions.thread = {
  newConversation: "Nouvelle conversation",
  lastActive: "Dernière activité {{value}}",
  chooseBot: "Choisissez un bot",
  activeBot: "Bot de la conversation",
  modelUnknown: "Modèle non renseigné",
  waitingForReply: "En attente de la réponse du bot...",
  loadingOlder: "Chargement des messages précédents...",
  pending: "En attente",
  failed: "Échec de l'envoi",
  retry: "Réessayer",
  continueConversation: "Poursuivez la conversation actuelle.",
  startConversationTitle: "Démarrez une nouvelle conversation",
  startConversationDescription:
    "Utilisez le composeur ci-dessous pour démarrer une nouvelle conversation ou choisissez une session précédente dans la boîte de réception.",
  noBotTitle: "Sélectionnez un bot spécifique",
  noBotDescription: "Choisissez un bot spécifique dans le composeur pour démarrer une nouvelle discussion.",
};

mutableResources["de-DE"].translation.sessions.thread = {
  newConversation: "Neue Unterhaltung",
  lastActive: "Letzte Aktivität {{value}}",
  chooseBot: "Bot wählen",
  activeBot: "Bot der Unterhaltung",
  modelUnknown: "Modell nicht angegeben",
  waitingForReply: "Warten auf die Antwort des Bots...",
  loadingOlder: "Ältere Nachrichten werden geladen...",
  pending: "Ausstehend",
  failed: "Senden fehlgeschlagen",
  retry: "Erneut versuchen",
  continueConversation: "Setzen Sie die aktuelle Unterhaltung fort.",
  startConversationTitle: "Starten Sie eine neue Unterhaltung",
  startConversationDescription:
    "Verwenden Sie den Composer unten, um eine neue Unterhaltung zu starten, oder wählen Sie eine frühere Sitzung aus dem Posteingang.",
  noBotTitle: "Wählen Sie einen bestimmten Bot",
  noBotDescription: "Wählen Sie einen bestimmten Bot im Composer, um einen neuen Chat zu starten.",
};

mutableResources["en-US"].translation.sessions.context = {
  emptyTitle: "Conversation details",
  emptyDescription:
    "Choose a conversation to inspect status, activity, linked executions and identifiers.",
  messages: "Messages",
  executions: "Executions",
  tools: "Tools",
  cost: "Cost",
  createdAt: "Created",
  lastActivity: "Last activity",
  sessionId: "Session ID",
  userId: "User ID",
  recentExecutions: "Recent executions",
  noExecutions: "No linked executions yet.",
};

mutableResources["pt-BR"].translation.sessions.context = {
  emptyTitle: "Detalhes da conversa",
  emptyDescription:
    "Escolha uma conversa para inspecionar status, atividade, execuções vinculadas e identificadores.",
  messages: "Mensagens",
  executions: "Execuções",
  tools: "Ferramentas",
  cost: "Custo",
  createdAt: "Criada em",
  lastActivity: "Última atividade",
  sessionId: "ID da sessão",
  userId: "ID do usuário",
  recentExecutions: "Execuções recentes",
  noExecutions: "Ainda não há execuções vinculadas.",
};

mutableResources["es-ES"].translation.sessions.context = {
  emptyTitle: "Detalles de la conversación",
  emptyDescription:
    "Elige una conversación para revisar estado, actividad, ejecuciones vinculadas e identificadores.",
  messages: "Mensajes",
  executions: "Ejecuciones",
  tools: "Herramientas",
  cost: "Costo",
  createdAt: "Creada",
  lastActivity: "Última actividad",
  sessionId: "ID de sesión",
  userId: "ID de usuario",
  recentExecutions: "Ejecuciones recientes",
  noExecutions: "Todavía no hay ejecuciones vinculadas.",
};

mutableResources["fr-FR"].translation.sessions.context = {
  emptyTitle: "Détails de la conversation",
  emptyDescription:
    "Choisissez une conversation pour examiner le statut, l'activité, les exécutions liées et les identifiants.",
  messages: "Messages",
  executions: "Exécutions",
  tools: "Outils",
  cost: "Coût",
  createdAt: "Créée",
  lastActivity: "Dernière activité",
  sessionId: "ID de session",
  userId: "ID utilisateur",
  recentExecutions: "Exécutions récentes",
  noExecutions: "Aucune exécution liée pour l'instant.",
};

mutableResources["de-DE"].translation.sessions.context = {
  emptyTitle: "Unterhaltungsdetails",
  emptyDescription:
    "Wählen Sie eine Unterhaltung, um Status, Aktivität, verknüpfte Ausführungen und Kennungen zu prüfen.",
  messages: "Nachrichten",
  executions: "Ausführungen",
  tools: "Tools",
  cost: "Kosten",
  createdAt: "Erstellt",
  lastActivity: "Letzte Aktivität",
  sessionId: "Sitzungs-ID",
  userId: "Benutzer-ID",
  recentExecutions: "Letzte Ausführungen",
  noExecutions: "Noch keine verknüpften Ausführungen.",
};

mutableResources["en-US"].translation.sessions.detail = {
  ...mutableResources["en-US"].translation.sessions.detail,
  executionLabel: "Execution #{{id}}",
  toolsCount: "{{count}} tools",
  noMessagesYet: "This session has not yet published messages to the queries table.",
};

mutableResources["pt-BR"].translation.sessions.detail = {
  ...mutableResources["pt-BR"].translation.sessions.detail,
  executionLabel: "Execução #{{id}}",
  toolsCount: "{{count}} ferramentas",
  noMessagesYet: "Esta sessão ainda não publicou mensagens na tabela de queries.",
};

mutableResources["es-ES"].translation.sessions.detail = {
  ...mutableResources["es-ES"].translation.sessions.detail,
  executionLabel: "Ejecución #{{id}}",
  toolsCount: "{{count}} herramientas",
  noMessagesYet: "Esta sesión todavía no publicó mensajes en la tabla de queries.",
};

mutableResources["en-US"].translation.schedules.page = {
  visibleBots: "Visible bots",
  withSchedule: "With schedule",
  enabled: "Enabled",
  paused: "Paused",
  withAtLeastOne: "Bots with at least one configured routine",
  runningNormally: "Routines running normally",
  registeredDisabled: "Registered routines currently switched off",
  eyebrow: "Schedules",
  title: "Scheduled routines by bot",
  description: "Each card summarizes visible routines with cron, primary command, scope and operational status.",
  noVisible: "No visible routines right now",
  noVisibleDescription: "When the selected bots have schedules, they will appear here with the same operational reading as the rest of the app.",
  routines: "{{count}} routines",
  active: "{{count}} active",
  configured: "{{count}} configured",
  configuredDescription: "Consolidated view of routines configured for this bot.",
  pausedCount: "{{count}} paused",
};

mutableResources["pt-BR"].translation.schedules.page = {
  visibleBots: "Bots visíveis",
  withSchedule: "Com agenda",
  enabled: "Ativos",
  paused: "Pausados",
  withAtLeastOne: "Bots com pelo menos uma rotina configurada",
  runningNormally: "Rotinas executando normalmente",
  registeredDisabled: "Rotinas cadastradas mas desligadas",
  eyebrow: "Agendamentos",
  title: "Rotinas programadas por bot",
  description: "Cada card resume as rotinas visíveis, com expressão cron, comando principal, escopo e status operacional.",
  noVisible: "Nenhuma rotina visível no momento",
  noVisibleDescription: "Quando os bots selecionados tiverem agendamentos, eles aparecem aqui com a mesma leitura operacional do restante do app.",
  routines: "{{count}} rotinas",
  active: "{{count}} ativas",
  configured: "{{count}} configurada{{count !== 1 ? 's' : ''}}",
  configuredDescription: "Visão consolidada das automações configuradas para este bot.",
  pausedCount: "{{count}} pausadas",
};

mutableResources["es-ES"].translation.schedules.page = {
  visibleBots: "Bots visibles",
  withSchedule: "Con agenda",
  enabled: "Activos",
  paused: "Pausados",
  withAtLeastOne: "Bots con al menos una rutina configurada",
  runningNormally: "Rutinas ejecutándose normalmente",
  registeredDisabled: "Rutinas registradas pero apagadas",
  eyebrow: "Programaciones",
  title: "Rutinas programadas por bot",
  description: "Cada tarjeta resume las rutinas visibles con expresión cron, comando principal, alcance y estado operativo.",
  noVisible: "No hay rutinas visibles por ahora",
  noVisibleDescription: "Cuando los bots seleccionados tengan programaciones, aparecerán aquí con la misma lectura operativa del resto de la app.",
  routines: "{{count}} rutinas",
  active: "{{count}} activas",
  configured: "{{count}} configuradas",
  configuredDescription: "Vista consolidada de las automatizaciones configuradas para este bot.",
  pausedCount: "{{count}} pausadas",
};

mutableResources["en-US"].translation.schedules.table = {
  noRoutine: "No routines configured for {{bot}}",
  noRoutineDescription: "When there are active or paused schedules, they will appear here in operational format.",
  noSummary: "No summary configured",
  noDirectory: "No directory",
  schedule: "Schedule",
  routine: "Routine",
  summary: "Summary",
  scope: "Scope",
};

mutableResources["pt-BR"].translation.schedules.table = {
  noRoutine: "Nenhuma rotina configurada para {{bot}}",
  noRoutineDescription: "Quando houver agendamentos ativos ou pausados, eles aparecem aqui em formato operacional.",
  noSummary: "Sem resumo configurado",
  noDirectory: "Sem diretório",
  schedule: "Agenda",
  routine: "Rotina",
  summary: "Resumo",
  scope: "Escopo",
};

mutableResources["es-ES"].translation.schedules.table = {
  noRoutine: "No hay rutinas configuradas para {{bot}}",
  noRoutineDescription: "Cuando existan programaciones activas o pausadas, aparecerán aquí en formato operativo.",
  noSummary: "Sin resumen configurado",
  noDirectory: "Sin directorio",
  schedule: "Agenda",
  routine: "Rutina",
  summary: "Resumen",
  scope: "Alcance",
};

mutableResources["fr-FR"].translation.schedules.page = {
  visibleBots: "Bots visibles",
  withSchedule: "Avec planning",
  enabled: "Activés",
  paused: "En pause",
  withAtLeastOne: "Bots avec au moins une routine configurée",
  runningNormally: "Routines s'exécutant normalement",
  registeredDisabled: "Routines enregistrées actuellement désactivées",
  eyebrow: "Planifications",
  title: "Routines planifiées par bot",
  description: "Chaque carte résume les routines visibles avec cron, commande principale, portée et état opérationnel.",
  noVisible: "Aucune routine visible pour l'instant",
  noVisibleDescription: "Lorsque les bots sélectionnés ont des plannings, ils apparaîtront ici avec la même lecture opérationnelle que le reste de l'application.",
  routines: "{{count}} routines",
  active: "{{count}} actifs",
  configured: "{{count}} configurés",
  configuredDescription: "Vue consolidée des routines configurées pour ce bot.",
  pausedCount: "{{count}} en pause",
};

mutableResources["de-DE"].translation.schedules.page = {
  visibleBots: "Sichtbare Bots",
  withSchedule: "Mit Zeitplan",
  enabled: "Aktiviert",
  paused: "Pausiert",
  withAtLeastOne: "Bots mit mindestens einer konfigurierten Routine",
  runningNormally: "Routinen laufen normal",
  registeredDisabled: "Registrierte, aber deaktivierte Routinen",
  eyebrow: "Zeitpläne",
  title: "Geplante Routinen pro Bot",
  description: "Jede Karte fasst die sichtbaren Routinen mit Cron, Hauptbefehl, Geltungsbereich und operativem Status zusammen.",
  noVisible: "Derzeit keine sichtbaren Routinen",
  noVisibleDescription: "Wenn die ausgewählten Bots Zeitpläne haben, erscheinen sie hier mit derselben operativen Lesart wie im Rest der Anwendung.",
  routines: "{{count}} Routinen",
  active: "{{count}} aktiv",
  configured: "{{count}} konfiguriert",
  configuredDescription: "Konsolidierte Ansicht der für diesen Bot konfigurierten Routinen.",
  pausedCount: "{{count}} pausiert",
};

mutableResources["fr-FR"].translation.schedules.table = {
  noRoutine: "Aucune routine configurée pour {{bot}}",
  noRoutineDescription: "Lorsque des plannings actifs ou en pause existent, ils apparaîtront ici en format opérationnel.",
  noSummary: "Aucun résumé configuré",
  noDirectory: "Aucun répertoire",
  schedule: "Planning",
  routine: "Routine",
  summary: "Résumé",
  scope: "Portée",
};

mutableResources["de-DE"].translation.schedules.table = {
  noRoutine: "Keine Routinen für {{bot}} konfiguriert",
  noRoutineDescription: "Wenn aktive oder pausierte Zeitpläne vorhanden sind, erscheinen sie hier im operativen Format.",
  noSummary: "Keine Zusammenfassung konfiguriert",
  noDirectory: "Kein Verzeichnis",
  schedule: "Zeitplan",
  routine: "Routine",
  summary: "Zusammenfassung",
  scope: "Geltungsbereich",
};

mutableResources["en-US"].translation.schedules.inspector = {
  eyebrow: "Inspector",
  jobTitle: "Job #{{id}}",
  detailFallback: "Schedule detail",
  loadingDetail: "Loading schedule detail…",
  currentStatus: "Current status",
  status: "Status",
  unknown: "unknown",
  nextRun: "Next run",
  pendingValidation: "pending validation",
  version: "Version",
  runtimeTask: "Runtime task",
  phase: "Phase",
  recentRuns: "Recent runs",
  noRunsYet: "No runs yet.",
  auditTrail: "Audit trail",
  noEventsYet: "No events yet.",
  selectToInspect: "Select a job to inspect or edit it.",
  trigger: "Trigger",
  timezone: "Timezone",
  scheduleExpression: "Schedule expression",
  reminderText: "Reminder text",
  command: "Command",
  query: "Query",
  description: "Description",
  workDir: "Work dir",
  notificationMode: "Notification mode",
  verificationMode: "Verification mode",
  triggerTypes: {
    one_shot: "One-shot",
    interval: "Interval",
    cron: "Cron",
  },
  actions: {
    saveChanges: "Save changes",
    queueValidation: "Queue validation",
    archiveJob: "Archive job",
    refreshDetail: "Refresh detail",
  },
  lifecycle: {
    update: "Update job",
    pause: "Pause job",
    resume: "Resume job",
    activate: "Activate job",
    resumeFailedOpen: "Resume failed-open job",
    queueValidation: "Queue validation",
    activateOrResume: "Activate or resume",
  },
  messages: {
    updated: "Schedule updated.",
    updateFailed: "Unable to update schedule",
    updateReason: "Updated from schedules page",
  },
};

mutableResources["pt-BR"].translation.schedules.inspector = {
  eyebrow: "Inspetor",
  jobTitle: "Job #{{id}}",
  detailFallback: "Detalhe do agendamento",
  loadingDetail: "Carregando detalhes do agendamento…",
  currentStatus: "Status atual",
  status: "Status",
  unknown: "desconhecido",
  nextRun: "Próxima execução",
  pendingValidation: "aguardando validação",
  version: "Versão",
  runtimeTask: "Tarefa de runtime",
  phase: "Fase",
  recentRuns: "Execuções recentes",
  noRunsYet: "Nenhuma execução ainda.",
  auditTrail: "Trilha de auditoria",
  noEventsYet: "Nenhum evento ainda.",
  selectToInspect: "Selecione um job para inspecionar ou editar.",
  trigger: "Gatilho",
  timezone: "Fuso horário",
  scheduleExpression: "Expressão do agendamento",
  reminderText: "Texto do lembrete",
  command: "Comando",
  query: "Consulta",
  description: "Descrição",
  workDir: "Diretório de trabalho",
  notificationMode: "Modo de notificação",
  verificationMode: "Modo de verificação",
  triggerTypes: {
    one_shot: "Uma vez",
    interval: "Intervalo",
    cron: "Cron",
  },
  actions: {
    saveChanges: "Salvar alterações",
    queueValidation: "Enfileirar validação",
    archiveJob: "Arquivar job",
    refreshDetail: "Atualizar detalhes",
  },
  lifecycle: {
    update: "Atualizar job",
    pause: "Pausar job",
    resume: "Retomar job",
    activate: "Ativar job",
    resumeFailedOpen: "Retomar job em failed-open",
    queueValidation: "Enfileirar validação",
    activateOrResume: "Ativar ou retomar",
  },
  messages: {
    updated: "Agendamento atualizado.",
    updateFailed: "Não foi possível atualizar o agendamento",
    updateReason: "Atualizado a partir da página de agendamentos",
  },
};

mutableResources["es-ES"].translation.schedules.inspector = {
  eyebrow: "Inspector",
  jobTitle: "Tarea #{{id}}",
  detailFallback: "Detalle de la programación",
  loadingDetail: "Cargando detalles de la programación…",
  currentStatus: "Estado actual",
  status: "Estado",
  unknown: "desconocido",
  nextRun: "Próxima ejecución",
  pendingValidation: "pendiente de validación",
  version: "Versión",
  runtimeTask: "Tarea en runtime",
  phase: "Fase",
  recentRuns: "Ejecuciones recientes",
  noRunsYet: "Aún no hay ejecuciones.",
  auditTrail: "Registro de auditoría",
  noEventsYet: "Aún no hay eventos.",
  selectToInspect: "Selecciona una tarea para inspeccionar o editar.",
  trigger: "Disparador",
  timezone: "Zona horaria",
  scheduleExpression: "Expresión de programación",
  reminderText: "Texto del recordatorio",
  command: "Comando",
  query: "Consulta",
  description: "Descripción",
  workDir: "Directorio de trabajo",
  notificationMode: "Modo de notificación",
  verificationMode: "Modo de verificación",
  triggerTypes: {
    one_shot: "Una vez",
    interval: "Intervalo",
    cron: "Cron",
  },
  actions: {
    saveChanges: "Guardar cambios",
    queueValidation: "Encolar validación",
    archiveJob: "Archivar tarea",
    refreshDetail: "Actualizar detalle",
  },
  lifecycle: {
    update: "Actualizar tarea",
    pause: "Pausar tarea",
    resume: "Reanudar tarea",
    activate: "Activar tarea",
    resumeFailedOpen: "Reanudar tarea en failed-open",
    queueValidation: "Encolar validación",
    activateOrResume: "Activar o reanudar",
  },
  messages: {
    updated: "Programación actualizada.",
    updateFailed: "No se pudo actualizar la programación",
    updateReason: "Actualizado desde la página de programaciones",
  },
};

mutableResources["fr-FR"].translation.schedules.inspector = {
  eyebrow: "Inspecteur",
  jobTitle: "Tâche #{{id}}",
  detailFallback: "Détail du planning",
  loadingDetail: "Chargement des détails du planning…",
  currentStatus: "Statut actuel",
  status: "Statut",
  unknown: "inconnu",
  nextRun: "Prochaine exécution",
  pendingValidation: "validation en attente",
  version: "Version",
  runtimeTask: "Tâche runtime",
  phase: "Phase",
  recentRuns: "Exécutions récentes",
  noRunsYet: "Aucune exécution pour l'instant.",
  auditTrail: "Piste d'audit",
  noEventsYet: "Aucun événement pour l'instant.",
  selectToInspect: "Sélectionnez une tâche pour l'inspecter ou la modifier.",
  trigger: "Déclencheur",
  timezone: "Fuseau horaire",
  scheduleExpression: "Expression de planification",
  reminderText: "Texte du rappel",
  command: "Commande",
  query: "Requête",
  description: "Description",
  workDir: "Répertoire de travail",
  notificationMode: "Mode de notification",
  verificationMode: "Mode de vérification",
  triggerTypes: {
    one_shot: "Unique",
    interval: "Intervalle",
    cron: "Cron",
  },
  actions: {
    saveChanges: "Enregistrer les modifications",
    queueValidation: "Mettre en file la validation",
    archiveJob: "Archiver la tâche",
    refreshDetail: "Actualiser le détail",
  },
  lifecycle: {
    update: "Mettre à jour la tâche",
    pause: "Mettre la tâche en pause",
    resume: "Reprendre la tâche",
    activate: "Activer la tâche",
    resumeFailedOpen: "Reprendre la tâche en failed-open",
    queueValidation: "Mettre en file la validation",
    activateOrResume: "Activer ou reprendre",
  },
  messages: {
    updated: "Planning mis à jour.",
    updateFailed: "Impossible de mettre à jour le planning",
    updateReason: "Mis à jour depuis la page des plannings",
  },
};

mutableResources["de-DE"].translation.schedules.inspector = {
  eyebrow: "Inspektor",
  jobTitle: "Aufgabe #{{id}}",
  detailFallback: "Zeitplan-Detail",
  loadingDetail: "Zeitplan-Details werden geladen…",
  currentStatus: "Aktueller Status",
  status: "Status",
  unknown: "unbekannt",
  nextRun: "Nächste Ausführung",
  pendingValidation: "Validierung ausstehend",
  version: "Version",
  runtimeTask: "Laufzeit-Aufgabe",
  phase: "Phase",
  recentRuns: "Letzte Ausführungen",
  noRunsYet: "Noch keine Ausführungen.",
  auditTrail: "Prüfpfad",
  noEventsYet: "Noch keine Ereignisse.",
  selectToInspect: "Wählen Sie eine Aufgabe aus, um sie zu prüfen oder zu bearbeiten.",
  trigger: "Auslöser",
  timezone: "Zeitzone",
  scheduleExpression: "Zeitplan-Ausdruck",
  reminderText: "Erinnerungstext",
  command: "Befehl",
  query: "Abfrage",
  description: "Beschreibung",
  workDir: "Arbeitsverzeichnis",
  notificationMode: "Benachrichtigungsmodus",
  verificationMode: "Verifizierungsmodus",
  triggerTypes: {
    one_shot: "Einmalig",
    interval: "Intervall",
    cron: "Cron",
  },
  actions: {
    saveChanges: "Änderungen speichern",
    queueValidation: "Validierung einreihen",
    archiveJob: "Aufgabe archivieren",
    refreshDetail: "Detail aktualisieren",
  },
  lifecycle: {
    update: "Aufgabe aktualisieren",
    pause: "Aufgabe pausieren",
    resume: "Aufgabe fortsetzen",
    activate: "Aufgabe aktivieren",
    resumeFailedOpen: "Failed-open-Aufgabe fortsetzen",
    queueValidation: "Validierung einreihen",
    activateOrResume: "Aktivieren oder fortsetzen",
  },
  messages: {
    updated: "Zeitplan aktualisiert.",
    updateFailed: "Zeitplan konnte nicht aktualisiert werden",
    updateReason: "Von der Zeitpläne-Seite aktualisiert",
  },
};

mutableResources["en-US"].translation.dlq.page = {
  all: "All",
  retryEligible: "Retry eligible",
  noRetry: "No retry",
  failures: "{{count}} failures",
  visibleFailures: "Visible failures",
  orderedByRecent: "Ordered by most recent failure",
  alreadyRetried: "Already retried",
  affectedBots: "Affected bots",
  retryEligibleHint: "Entries still eligible for reprocessing",
  alreadyRetriedHint: "Failures that already went through another attempt",
  actionTitle: "Failures that require operational action",
  actionDescription: "Select an entry to open the full diagnosis, review the context and decide the next step.",
  unavailable: "Dead letter queue unavailable",
  unavailableDescription: "Could not sync the failures for the visible bots right now.",
  emptyEligible: "No failures ready for retry",
  emptyEligibleDescription: "Eligible entries will reappear here when new failures can still be reprocessed.",
  emptyIneligible: "No blocked failures for retry",
  emptyIneligibleDescription: "Failures that require manual action are listed here when there are entries without retry available.",
  emptyDefault: "No pending failures in the dead letter queue",
  emptyDefaultDescription: "Visible bots have no pending failures right now.",
};

mutableResources["pt-BR"].translation.dlq.page = {
  all: "Todas",
  retryEligible: "Pode retentar",
  noRetry: "Sem retentativa",
  failures: "{{count}} falhas",
  visibleFailures: "Falhas visíveis",
  orderedByRecent: "Ordenadas pela falha mais recente",
  alreadyRetried: "Já retentadas",
  affectedBots: "Bots afetados",
  retryEligibleHint: "Entradas ainda elegíveis para reprocessamento",
  alreadyRetriedHint: "Falhas que já passaram por nova tentativa",
  actionTitle: "Falhas que exigem ação operacional",
  actionDescription: "Selecione uma entrada para abrir o diagnóstico completo, revisar o contexto e decidir o próximo passo.",
  unavailable: "Fila morta indisponível",
  unavailableDescription: "Não foi possível sincronizar as falhas dos bots visíveis agora.",
  emptyEligible: "Nenhuma falha pronta para retentativa",
  emptyEligibleDescription: "As entradas elegíveis reaparecem aqui quando houver novas falhas que ainda podem ser reprocessadas.",
  emptyIneligible: "Nenhuma falha bloqueada para retentativa",
  emptyIneligibleDescription: "As falhas que exigem ação manual ficam listadas aqui quando existirem entradas sem retentativa disponível.",
  emptyDefault: "Nenhuma falha pendente na fila morta",
  emptyDefaultDescription: "Os bots visíveis não têm falhas pendentes no momento.",
};

mutableResources["es-ES"].translation.dlq.page = {
  all: "Todas",
  retryEligible: "Puede reintentar",
  noRetry: "Sin reintento",
  failures: "{{count}} fallos",
  visibleFailures: "Fallos visibles",
  orderedByRecent: "Ordenados por el fallo más reciente",
  alreadyRetried: "Ya reintentados",
  affectedBots: "Bots afectados",
  retryEligibleHint: "Entradas todavía elegibles para reprocesamiento",
  alreadyRetriedHint: "Fallos que ya pasaron por un nuevo intento",
  actionTitle: "Fallos que exigen acción operativa",
  actionDescription: "Selecciona una entrada para abrir el diagnóstico completo, revisar el contexto y decidir el siguiente paso.",
  unavailable: "Cola muerta no disponible",
  unavailableDescription: "No se pudieron sincronizar los fallos de los bots visibles en este momento.",
  emptyEligible: "No hay fallos listos para reintento",
  emptyEligibleDescription: "Las entradas elegibles reaparecerán aquí cuando existan nuevos fallos que todavía puedan reprocesarse.",
  emptyIneligible: "No hay fallos bloqueados para reintento",
  emptyIneligibleDescription: "Los fallos que requieren acción manual se listan aquí cuando existan entradas sin reintento disponible.",
  emptyDefault: "No hay fallos pendientes en la cola muerta",
  emptyDefaultDescription: "Los bots visibles no tienen fallos pendientes en este momento.",
};

mutableResources["en-US"].translation.dlq.table = {
  canRetry: "Can retry",
  retried: "Retried",
  noRetry: "No retry",
  entry: "Entry",
  origin: "Origin",
  error: "Error",
  lastFailure: "Last failure",
  noBot: "No bot linked",
  modelUnknown: "Model not informed",
  alreadyReprocessed: "Already reprocessed",
  waitingDecision: "Awaiting decision",
  noErrorMessage: "No error message",
  noFailures: "No failures recorded.",
};

mutableResources["pt-BR"].translation.dlq.table = {
  canRetry: "Pode retentar",
  retried: "Retentado",
  noRetry: "Sem retentativa",
  entry: "Entrada",
  origin: "Origem",
  error: "Erro",
  lastFailure: "Última falha",
  noBot: "Sem bot associado",
  modelUnknown: "Modelo não informado",
  alreadyReprocessed: "Já reprocessada",
  waitingDecision: "Aguardando decisão",
  noErrorMessage: "Sem mensagem de erro",
  noFailures: "Nenhuma falha registrada.",
};

mutableResources["es-ES"].translation.dlq.table = {
  canRetry: "Puede reintentar",
  retried: "Reintentado",
  noRetry: "Sin reintento",
  entry: "Entrada",
  origin: "Origen",
  error: "Error",
  lastFailure: "Último fallo",
  noBot: "Sin bot asociado",
  modelUnknown: "Modelo no informado",
  alreadyReprocessed: "Ya reprocesada",
  waitingDecision: "Esperando decisión",
  noErrorMessage: "Sin mensaje de error",
  noFailures: "No hay fallos registrados.",
};

mutableResources["fr-FR"].translation.dlq.page = {
  all: "Tous",
  retryEligible: "Éligible à la réexécution",
  noRetry: "Pas de réexécution",
  failures: "{{count}} échecs",
  visibleFailures: "Échecs visibles",
  orderedByRecent: "Triés par échec le plus récent",
  alreadyRetried: "Déjà réessayés",
  affectedBots: "Bots affectés",
  retryEligibleHint: "Entrées toujours éligibles au retraitement",
  alreadyRetriedHint: "Échecs qui ont déjà eu une nouvelle tentative",
  actionTitle: "Échecs nécessitant une action opérationnelle",
  actionDescription: "Sélectionnez une entrée pour ouvrir le diagnostic complet, examiner le contexte et décider de l'étape suivante.",
  unavailable: "File des messages non distribués indisponible",
  unavailableDescription: "Impossible de synchroniser les échecs des bots visibles pour le moment.",
  emptyEligible: "Aucun échec prêt à être réessayé",
  emptyEligibleDescription: "Les entrées éligibles réapparaîtront ici lorsque de nouveaux échecs pourront encore être retraités.",
  emptyIneligible: "Aucun échec bloqué pour réessai",
  emptyIneligibleDescription: "Les échecs nécessitant une action manuelle sont listés ici lorsqu'il existe des entrées sans réessai possible.",
  emptyDefault: "Aucun échec en attente dans la file des messages non distribués",
  emptyDefaultDescription: "Les bots visibles n'ont aucun échec en attente pour le moment.",
};

mutableResources["de-DE"].translation.dlq.page = {
  all: "Alle",
  retryEligible: "Wiederholung möglich",
  noRetry: "Keine Wiederholung",
  failures: "{{count}} Fehler",
  visibleFailures: "Sichtbare Fehler",
  orderedByRecent: "Geordnet nach aktuellstem Fehler",
  alreadyRetried: "Bereits wiederholt",
  affectedBots: "Betroffene Bots",
  retryEligibleHint: "Einträge, die noch für eine erneute Verarbeitung in Frage kommen",
  alreadyRetriedHint: "Fehler, die bereits einen weiteren Versuch hatten",
  actionTitle: "Fehler, die operatives Eingreifen erfordern",
  actionDescription: "Wählen Sie einen Eintrag, um die vollständige Diagnose zu öffnen, den Kontext zu prüfen und den nächsten Schritt zu entscheiden.",
  unavailable: "Dead-Letter-Queue nicht verfügbar",
  unavailableDescription: "Die Fehler der sichtbaren Bots konnten derzeit nicht synchronisiert werden.",
  emptyEligible: "Keine Fehler bereit für erneuten Versuch",
  emptyEligibleDescription: "Berechtigte Einträge erscheinen hier wieder, wenn neue Fehler noch erneut verarbeitet werden können.",
  emptyIneligible: "Keine blockierten Fehler für erneuten Versuch",
  emptyIneligibleDescription: "Fehler, die manuelles Handeln erfordern, werden hier aufgelistet, wenn Einträge ohne verfügbare Wiederholung vorhanden sind.",
  emptyDefault: "Keine ausstehenden Fehler in der Dead-Letter-Queue",
  emptyDefaultDescription: "Die sichtbaren Bots haben derzeit keine ausstehenden Fehler.",
};

mutableResources["fr-FR"].translation.dlq.table = {
  canRetry: "Peut être réessayé",
  retried: "Réessayé",
  noRetry: "Pas de réessai",
  entry: "Entrée",
  origin: "Origine",
  error: "Erreur",
  lastFailure: "Dernier échec",
  noBot: "Aucun bot lié",
  modelUnknown: "Modèle non renseigné",
  alreadyReprocessed: "Déjà retraité",
  waitingDecision: "En attente de décision",
  noErrorMessage: "Aucun message d'erreur",
  noFailures: "Aucun échec enregistré.",
};

mutableResources["de-DE"].translation.dlq.table = {
  canRetry: "Kann wiederholt werden",
  retried: "Wiederholt",
  noRetry: "Keine Wiederholung",
  entry: "Eintrag",
  origin: "Quelle",
  error: "Fehler",
  lastFailure: "Letzter Fehler",
  noBot: "Kein verknüpfter Bot",
  modelUnknown: "Modell nicht angegeben",
  alreadyReprocessed: "Bereits erneut verarbeitet",
  waitingDecision: "Wartet auf Entscheidung",
  noErrorMessage: "Keine Fehlermeldung",
  noFailures: "Keine Fehler erfasst.",
};

mutableResources["en-US"].translation.memory.curation = {
  mode: "Mode",
  states: "State",
  type: "Type",
  search: "Search",
  allStates: "All states",
  allTypes: "All types",
  searchPlaceholder: "Search by content, source or session...",
  selectedCount_one: "{{count}} item selected",
  selectedCount_other: "{{count}} items selected",
  memories: "Memories",
  clusters: "Clusters",
  clustersAndLearning: "Clusters / learning",
  pendingCount: "{{count}} pending",
  noMemoryFound: "No memory found",
  noClusterFound: "No grouping found",
  adjustFilters: "Adjust search and filters to find relevant items again.",
  sortHint: "most recent",
  detailLoadError: "Could not load detail.",
  actionError: "Could not apply action.",
  kpis: {
    pendingMemories: "Pending memories",
    pendingMemoriesMeta: "awaiting editorial decision",
    pendingClusters: "Pending clusters",
    pendingClustersMeta: "learning items without a decision",
    expiringSoon: "Expiring soon",
    expiringSoonMeta: "expire in the next 7 days",
    reviewed7d: "Reviewed in 7 days",
    reviewed7dMeta: "{{approved}} approved · {{merged}} merged · {{discarded}} discarded",
  },
  actions: {
    approve: "Approve",
    expire: "Expire",
    archive: "Archive",
    discard: "Discard",
    restore: "Restore",
    merge: "Merge",
    mergeTarget: "Merge target",
    mergeSelectedHint: "Merges the selected memories into the first selected one.",
    mergeChooseHint: "Choose a target memory to merge into.",
  },
  row: {
    select: "Select {{title}}",
    sessionCount_one: "{{count}} session",
    sessionCount_other: "{{count}} sessions",
  },
};

mutableResources["pt-BR"].translation.memory.curation = {
  mode: "Modo",
  states: "Estado",
  type: "Tipo",
  search: "Busca",
  allStates: "Todos os estados",
  allTypes: "Todos os tipos",
  searchPlaceholder: "Buscar por conteúdo, origem ou sessão...",
  selectedCount_one: "{{count}} item selecionado",
  selectedCount_other: "{{count}} itens selecionados",
  memories: "Memórias",
  clusters: "Clusters",
  clustersAndLearning: "Clusters / aprendizados",
  pendingCount: "{{count}} pendentes",
  noMemoryFound: "Nenhuma memória encontrada",
  noClusterFound: "Nenhum agrupamento encontrado",
  adjustFilters: "Ajuste busca e filtros para reencontrar itens relevantes.",
  sortHint: "mais recentes",
  detailLoadError: "Não foi possível carregar o detalhe.",
  actionError: "Falha ao aplicar ação.",
  kpis: {
    pendingMemories: "Memórias pendentes",
    pendingMemoriesMeta: "aguardando decisão editorial",
    pendingClusters: "Clusters pendentes",
    pendingClustersMeta: "aprendizados sem decisão",
    expiringSoon: "Expiram em breve",
    expiringSoonMeta: "vencem nos próximos 7 dias",
    reviewed7d: "Revisadas em 7 dias",
    reviewed7dMeta: "{{approved}} aprovadas · {{merged}} mescladas · {{discarded}} descartadas",
  },
  actions: {
    approve: "Aprovar",
    expire: "Expirar",
    archive: "Arquivar",
    discard: "Descartar",
    restore: "Restaurar",
    merge: "Unir",
    mergeTarget: "Destino da união",
    mergeSelectedHint: "Mescla as memórias selecionadas na primeira selecionada.",
    mergeChooseHint: "Escolha uma memória destino para unir.",
  },
  row: {
    select: "Selecionar {{title}}",
    sessionCount_one: "{{count}} sessão",
    sessionCount_other: "{{count}} sessões",
  },
};

mutableResources["es-ES"].translation.memory.curation = {
  mode: "Modo",
  states: "Estado",
  type: "Tipo",
  search: "Búsqueda",
  allStates: "Todos los estados",
  allTypes: "Todos los tipos",
  searchPlaceholder: "Buscar por contenido, origen o sesión...",
  selectedCount_one: "{{count}} elemento seleccionado",
  selectedCount_other: "{{count}} elementos seleccionados",
  memories: "Memorias",
  clusters: "Clusters",
  clustersAndLearning: "Clusters / aprendizajes",
  pendingCount: "{{count}} pendientes",
  noMemoryFound: "No se encontró ninguna memoria",
  noClusterFound: "No se encontró ninguna agrupación",
  adjustFilters: "Ajusta la búsqueda y los filtros para reencontrar elementos relevantes.",
  sortHint: "más recientes",
  detailLoadError: "No se pudo cargar el detalle.",
  actionError: "No se pudo aplicar la acción.",
  kpis: {
    pendingMemories: "Memorias pendientes",
    pendingMemoriesMeta: "esperando decisión editorial",
    pendingClusters: "Clusters pendientes",
    pendingClustersMeta: "aprendizajes sin decisión",
    expiringSoon: "Expiran pronto",
    expiringSoonMeta: "vencen en los próximos 7 días",
    reviewed7d: "Revisadas en 7 días",
    reviewed7dMeta: "{{approved}} aprobadas · {{merged}} fusionadas · {{discarded}} descartadas",
  },
  actions: {
    approve: "Aprobar",
    expire: "Expirar",
    archive: "Archivar",
    discard: "Descartar",
    restore: "Restaurar",
    merge: "Unir",
    mergeTarget: "Destino de la unión",
    mergeSelectedHint: "Fusiona las memorias seleccionadas en la primera seleccionada.",
    mergeChooseHint: "Elige una memoria destino para unir.",
  },
  row: {
    select: "Seleccionar {{title}}",
    sessionCount_one: "{{count}} sesión",
    sessionCount_other: "{{count}} sesiones",
  },
};

mutableResources["fr-FR"].translation.memory.curation = {
  mode: "Mode",
  states: "État",
  type: "Type",
  search: "Recherche",
  allStates: "Tous les états",
  allTypes: "Tous les types",
  searchPlaceholder: "Rechercher par contenu, origine ou session...",
  selectedCount_one: "{{count}} élément sélectionné",
  selectedCount_other: "{{count}} éléments sélectionnés",
  memories: "Mémoires",
  clusters: "Clusters",
  clustersAndLearning: "Clusters / apprentissages",
  pendingCount: "{{count}} en attente",
  noMemoryFound: "Aucune mémoire trouvée",
  noClusterFound: "Aucun regroupement trouvé",
  adjustFilters: "Ajustez la recherche et les filtres pour retrouver des éléments pertinents.",
  sortHint: "plus récents",
  detailLoadError: "Impossible de charger le détail.",
  actionError: "Impossible d'appliquer l'action.",
  kpis: {
    pendingMemories: "Mémoires en attente",
    pendingMemoriesMeta: "en attente de décision éditoriale",
    pendingClusters: "Clusters en attente",
    pendingClustersMeta: "apprentissages sans décision",
    expiringSoon: "Expirent bientôt",
    expiringSoonMeta: "expirent dans les 7 prochains jours",
    reviewed7d: "Révisées en 7 jours",
    reviewed7dMeta: "{{approved}} approuvées · {{merged}} fusionnées · {{discarded}} rejetées",
  },
  actions: {
    approve: "Approuver",
    expire: "Expirer",
    archive: "Archiver",
    discard: "Rejeter",
    restore: "Restaurer",
    merge: "Fusionner",
    mergeTarget: "Cible de la fusion",
    mergeSelectedHint: "Fusionne les mémoires sélectionnées dans la première sélectionnée.",
    mergeChooseHint: "Choisissez une mémoire cible pour la fusion.",
  },
  row: {
    select: "Sélectionner {{title}}",
    sessionCount_one: "{{count}} session",
    sessionCount_other: "{{count}} sessions",
  },
};

mutableResources["de-DE"].translation.memory.curation = {
  mode: "Modus",
  states: "Zustand",
  type: "Typ",
  search: "Suche",
  allStates: "Alle Zustände",
  allTypes: "Alle Typen",
  searchPlaceholder: "Nach Inhalt, Quelle oder Sitzung suchen...",
  selectedCount_one: "{{count}} Element ausgewählt",
  selectedCount_other: "{{count}} Elemente ausgewählt",
  memories: "Speicher",
  clusters: "Cluster",
  clustersAndLearning: "Cluster / Lernen",
  pendingCount: "{{count}} ausstehend",
  noMemoryFound: "Kein Speicher gefunden",
  noClusterFound: "Keine Gruppierung gefunden",
  adjustFilters: "Passen Sie Suche und Filter an, um relevante Elemente wiederzufinden.",
  sortHint: "aktuellste",
  detailLoadError: "Detail konnte nicht geladen werden.",
  actionError: "Aktion konnte nicht angewendet werden.",
  kpis: {
    pendingMemories: "Ausstehende Speicher",
    pendingMemoriesMeta: "warten auf redaktionelle Entscheidung",
    pendingClusters: "Ausstehende Cluster",
    pendingClustersMeta: "Lerninhalte ohne Entscheidung",
    expiringSoon: "Laufen bald ab",
    expiringSoonMeta: "laufen in den nächsten 7 Tagen ab",
    reviewed7d: "In 7 Tagen geprüft",
    reviewed7dMeta: "{{approved}} genehmigt · {{merged}} zusammengeführt · {{discarded}} verworfen",
  },
  actions: {
    approve: "Genehmigen",
    expire: "Ablaufen lassen",
    archive: "Archivieren",
    discard: "Verwerfen",
    restore: "Wiederherstellen",
    merge: "Zusammenführen",
    mergeTarget: "Zusammenführungsziel",
    mergeSelectedHint: "Fügt die ausgewählten Speicher in den zuerst ausgewählten zusammen.",
    mergeChooseHint: "Wählen Sie einen Zielspeicher für die Zusammenführung.",
  },
  row: {
    select: "{{title}} auswählen",
    sessionCount_one: "{{count}} Sitzung",
    sessionCount_other: "{{count}} Sitzungen",
  },
};

mutableResources["en-US"].translation.runtime = {
  labels: {
    active: "Active",
    cleaning: "Cleaning",
    cleaned: "Cleaned",
    retained: "Retained",
    queued: "Queued",
    running: "Running",
    retrying: "Retrying",
    completed: "Completed",
    failed: "Failed",
    cancelled: "Cancelled",
    cancel_requested: "Cancellation requested",
    paused_for_operator: "Paused",
    operator_attached: "Operator attached",
    recoverable_failed_retained: "Recoverable failure",
    cancel_requested_retained: "Cancellation retained",
    cancelled_retained: "Cancelled and retained",
    save_verified: "Verified snapshot",
    unavailable: "Unavailable",
    warning: "Warning",
  },
};

mutableResources["pt-BR"].translation.runtime = {
  labels: {
    active: "Ativo",
    cleaning: "Limpando",
    cleaned: "Limpo",
    retained: "Retido",
    queued: "Na fila",
    running: "Executando",
    retrying: "Retentando",
    completed: "Concluído",
    failed: "Falhou",
    cancelled: "Cancelado",
    cancel_requested: "Cancelamento solicitado",
    paused_for_operator: "Pausado",
    operator_attached: "Operador no ambiente",
    recoverable_failed_retained: "Falha recuperável",
    cancel_requested_retained: "Cancelamento retido",
    cancelled_retained: "Cancelado e retido",
    save_verified: "Snapshot verificado",
    unavailable: "Indisponível",
    warning: "Atenção",
  },
};

mutableResources["es-ES"].translation.runtime = {
  labels: {
    active: "Activo",
    cleaning: "Limpiando",
    cleaned: "Limpio",
    retained: "Retenido",
    queued: "En cola",
    running: "Ejecutando",
    retrying: "Reintentando",
    completed: "Completado",
    failed: "Falló",
    cancelled: "Cancelado",
    cancel_requested: "Cancelación solicitada",
    paused_for_operator: "Pausado",
    operator_attached: "Operador conectado",
    recoverable_failed_retained: "Fallo recuperable",
    cancel_requested_retained: "Cancelación retenida",
    cancelled_retained: "Cancelado y retenido",
    save_verified: "Snapshot verificado",
    unavailable: "No disponible",
    warning: "Atención",
  },
};

mutableResources["fr-FR"].translation.runtime = {
  labels: {
    active: "Actif",
    cleaning: "Nettoyage",
    cleaned: "Nettoyé",
    retained: "Conservé",
    queued: "En file",
    running: "En cours",
    retrying: "Nouvelle tentative",
    completed: "Terminé",
    failed: "Échoué",
    cancelled: "Annulé",
    cancel_requested: "Annulation demandée",
    paused_for_operator: "En pause",
    operator_attached: "Opérateur attaché",
    recoverable_failed_retained: "Échec récupérable",
    cancel_requested_retained: "Annulation conservée",
    cancelled_retained: "Annulé et conservé",
    save_verified: "Snapshot vérifié",
    unavailable: "Indisponible",
    warning: "Avertissement",
  },
};

mutableResources["de-DE"].translation.runtime = {
  labels: {
    active: "Aktiv",
    cleaning: "Wird bereinigt",
    cleaned: "Bereinigt",
    retained: "Aufbewahrt",
    queued: "In Warteschlange",
    running: "Läuft",
    retrying: "Wiederholung",
    completed: "Abgeschlossen",
    failed: "Fehlgeschlagen",
    cancelled: "Abgebrochen",
    cancel_requested: "Abbruch angefordert",
    paused_for_operator: "Pausiert",
    operator_attached: "Operator angebunden",
    recoverable_failed_retained: "Wiederherstellbarer Fehler",
    cancel_requested_retained: "Abbruch aufbewahrt",
    cancelled_retained: "Abgebrochen und aufbewahrt",
    save_verified: "Verifiziertes Snapshot",
    unavailable: "Nicht verfügbar",
    warning: "Warnung",
  },
};

mutableResources["en-US"].translation.runtime.labels = {
  ...mutableResources["en-US"].translation.runtime.labels,
  available: "Available",
  disabled: "Disabled",
  offline: "Offline",
  partial: "Degraded",
};

mutableResources["pt-BR"].translation.runtime.labels = {
  ...mutableResources["pt-BR"].translation.runtime.labels,
  available: "Disponível",
  disabled: "Desabilitado",
  offline: "Fora do ar",
  partial: "Degradado",
};

mutableResources["es-ES"].translation.runtime.labels = {
  ...mutableResources["es-ES"].translation.runtime.labels,
  available: "Disponible",
  disabled: "Deshabilitado",
  offline: "Fuera de línea",
  partial: "Degradado",
};

mutableResources["fr-FR"].translation.runtime.labels = {
  ...mutableResources["fr-FR"].translation.runtime.labels,
  available: "Disponible",
  disabled: "Désactivé",
  offline: "Hors ligne",
  partial: "Dégradé",
};

mutableResources["de-DE"].translation.runtime.labels = {
  ...mutableResources["de-DE"].translation.runtime.labels,
  available: "Verfügbar",
  disabled: "Deaktiviert",
  offline: "Offline",
  partial: "Eingeschränkt",
};

mutableResources["en-US"].translation.costs = {
  ...mutableResources["en-US"].translation.costs,
  page: {
    unavailable: "Costs unavailable",
    loadError: "Could not load costs.",
    loadGenericError: "Error loading costs.",
    shareInPeriod: "Share in period",
    noConversations: "No conversations in the current filter.",
    noRecentPreview: "No recent preview",
    noModel: "No model",
    noDominantOrigin: "No dominant origin",
    noDominantModel: "No dominant model",
    noPeak: "No highlighted peak in the period",
    queriesCount: "{{count}} queries",
    executionsCount: "{{count}} executions",
    operationalRail: "Operational rail",
    operationalRailHint: "4 signals from the current cut",
    itemsCount: "{{count}} items",
    emptyBreakdown: "Not enough data in the selected period.",
    breakdownDefaultMeta: "Consolidated share in the selected period",
    allocationDominant: "Dominant:",
    noDominantAllocation: "No dominant concentration",
    allocationFooter:
      "{{label}} accounts for {{value}} of the current cut and leads the observed distribution.",
    noAllocationData: "Not enough cost to build the distribution in the period.",
    allocationModes: {
      task: "By task",
    },
    kpiContexts: {
      totalPeriod: "{{queries}} queries · {{executions}} executions",
      noComparableBase: "No comparable baseline",
      previousBase: "Previous base {{value}}",
      resolvedConversations: "{{count}} resolved conversations",
    },
    timeChart: {
      empty: "Not enough data to build the temporal origin.",
      peak: "Peak:",
      base: "Base:",
      buckets: "Buckets:",
      variation: "Variation:",
      noBucket: "No bucket",
      driver: "Driver · {{value}}",
      noDriver: "No dominant driver",
    },
    breakdowns: {
      byBotTitle: "Distribution by bot",
      byBotSubtitle: "Who concentrates the cost and what the efficiency per resolved conversation is.",
      byModelTitle: "Distribution by model",
      byModelSubtitle: "Where model allocation is weighing on the current cut.",
      byTaskTitle: "Distribution by task type",
      byTaskSubtitle: "Dominant task type and average pressure per occurrence.",
    },
  },
};

mutableResources["pt-BR"].translation.costs = {
  ...mutableResources["pt-BR"].translation.costs,
  page: {
    unavailable: "Custos indisponíveis",
    loadError: "Não foi possível carregar custos.",
    loadGenericError: "Erro ao carregar custos.",
    shareInPeriod: "Participação no período",
    noConversations: "Nenhuma conversa no filtro atual.",
    noRecentPreview: "Sem preview recente",
    noModel: "Sem modelo",
    noDominantOrigin: "Sem origem dominante",
    noDominantModel: "Sem modelo dominante",
    noPeak: "Nenhum pico destacado no período",
    queriesCount: "{{count}} consultas",
    executionsCount: "{{count}} execuções",
    operationalRail: "Rail operacional",
    operationalRailHint: "4 sinais do recorte atual",
    itemsCount: "{{count}} itens",
    emptyBreakdown: "Dados insuficientes no período selecionado.",
    breakdownDefaultMeta: "Participação consolidada no período selecionado",
    allocationDominant: "Dominante:",
    noDominantAllocation: "Sem concentração dominante",
    allocationFooter:
      "{{label}} responde por {{value}} do recorte atual e lidera a distribuição observada.",
    noAllocationData: "Não há custo suficiente para montar a distribuição no período.",
    allocationModes: {
      task: "Por tarefa",
    },
    kpiContexts: {
      totalPeriod: "{{queries}} consultas · {{executions}} execuções",
      noComparableBase: "Sem baseline comparável",
      previousBase: "Base anterior {{value}}",
      resolvedConversations: "{{count}} conversas resolvidas",
    },
    timeChart: {
      empty: "Dados insuficientes para montar a origem temporal.",
      peak: "Pico:",
      base: "Base:",
      buckets: "Blocos:",
      variation: "Variação:",
      noBucket: "Sem bucket",
      driver: "Motor · {{value}}",
      noDriver: "Sem motor dominante",
    },
    breakdowns: {
      byBotTitle: "Distribuição por bot",
      byBotSubtitle: "Quem concentra o custo e como está a eficiência por conversa resolvida.",
      byModelTitle: "Distribuição por modelo",
      byModelSubtitle: "Onde a alocação por modelo está pesando no recorte atual.",
      byTaskTitle: "Distribuição por tipo de tarefa",
      byTaskSubtitle: "Tipo de tarefa dominante e pressão média por ocorrência.",
    },
  },
};

mutableResources["es-ES"].translation.costs = {
  ...mutableResources["es-ES"].translation.costs,
  page: {
    unavailable: "Costos no disponibles",
    loadError: "No fue posible cargar los costos.",
    loadGenericError: "Error al cargar los costos.",
    shareInPeriod: "Participación en el período",
    noConversations: "No hay conversaciones en el filtro actual.",
    noRecentPreview: "Sin vista previa reciente",
    noModel: "Sin modelo",
    noDominantOrigin: "Sin origen dominante",
    noDominantModel: "Sin modelo dominante",
    noPeak: "No hay un pico destacado en el período",
    queriesCount: "{{count}} consultas",
    executionsCount: "{{count}} ejecuciones",
    operationalRail: "Rail operativo",
    operationalRailHint: "4 señales del recorte actual",
    itemsCount: "{{count}} elementos",
    emptyBreakdown: "Datos insuficientes en el período seleccionado.",
    breakdownDefaultMeta: "Participación consolidada en el período seleccionado",
    allocationDominant: "Dominante:",
    noDominantAllocation: "Sin concentración dominante",
    allocationFooter:
      "{{label}} representa {{value}} del recorte actual y lidera la distribución observada.",
    noAllocationData: "No hay suficiente costo para construir la distribución en el período.",
    allocationModes: {
      task: "Por tarea",
    },
    kpiContexts: {
      totalPeriod: "{{queries}} consultas · {{executions}} ejecuciones",
      noComparableBase: "Sin base comparable",
      previousBase: "Base anterior {{value}}",
      resolvedConversations: "{{count}} conversaciones resueltas",
    },
    timeChart: {
      empty: "No hay suficientes datos para construir el origen temporal.",
      peak: "Pico:",
      base: "Base:",
      buckets: "Bloques:",
      variation: "Variación:",
      noBucket: "Sin bucket",
      driver: "Motor · {{value}}",
      noDriver: "Sin motor dominante",
    },
    breakdowns: {
      byBotTitle: "Distribución por bot",
      byBotSubtitle: "Quién concentra el costo y cómo está la eficiencia por conversación resuelta.",
      byModelTitle: "Distribución por modelo",
      byModelSubtitle: "Dónde la asignación por modelo pesa en el recorte actual.",
      byTaskTitle: "Distribución por tipo de tarea",
      byTaskSubtitle: "Tipo de tarea dominante y presión media por ocurrencia.",
    },
  },
};

mutableResources["fr-FR"].translation.costs = {
  ...mutableResources["fr-FR"].translation.costs,
  page: {
    unavailable: "Coûts indisponibles",
    loadError: "Impossible de charger les coûts.",
    loadGenericError: "Erreur lors du chargement des coûts.",
    shareInPeriod: "Part sur la période",
    noConversations: "Aucune conversation dans le filtre actuel.",
    noRecentPreview: "Aucun aperçu récent",
    noModel: "Aucun modèle",
    noDominantOrigin: "Aucune origine dominante",
    noDominantModel: "Aucun modèle dominant",
    noPeak: "Aucun pic notable dans la période",
    queriesCount: "{{count}} requêtes",
    executionsCount: "{{count}} exécutions",
    operationalRail: "Rail opérationnel",
    operationalRailHint: "4 signaux de la coupe actuelle",
    itemsCount: "{{count}} éléments",
    emptyBreakdown: "Données insuffisantes sur la période sélectionnée.",
    breakdownDefaultMeta: "Part consolidée sur la période sélectionnée",
    allocationDominant: "Dominant :",
    noDominantAllocation: "Aucune concentration dominante",
    allocationFooter:
      "{{label}} représente {{value}} de la coupe actuelle et mène la distribution observée.",
    noAllocationData: "Pas assez de coût pour construire la distribution sur la période.",
    allocationModes: {
      task: "Par tâche",
    },
    kpiContexts: {
      totalPeriod: "{{queries}} requêtes · {{executions}} exécutions",
      noComparableBase: "Pas de base comparable",
      previousBase: "Base précédente {{value}}",
      resolvedConversations: "{{count}} conversations résolues",
    },
    timeChart: {
      empty: "Données insuffisantes pour construire l'origine temporelle.",
      peak: "Pic :",
      base: "Base :",
      buckets: "Compartiments :",
      variation: "Variation :",
      noBucket: "Aucun compartiment",
      driver: "Moteur · {{value}}",
      noDriver: "Aucun moteur dominant",
    },
    breakdowns: {
      byBotTitle: "Répartition par bot",
      byBotSubtitle: "Qui concentre le coût et quelle est l'efficacité par conversation résolue.",
      byModelTitle: "Répartition par modèle",
      byModelSubtitle: "Où l'allocation par modèle pèse sur la coupe actuelle.",
      byTaskTitle: "Répartition par type de tâche",
      byTaskSubtitle: "Type de tâche dominant et pression moyenne par occurrence.",
    },
  },
};

mutableResources["de-DE"].translation.costs = {
  ...mutableResources["de-DE"].translation.costs,
  page: {
    unavailable: "Kosten nicht verfügbar",
    loadError: "Kosten konnten nicht geladen werden.",
    loadGenericError: "Fehler beim Laden der Kosten.",
    shareInPeriod: "Anteil im Zeitraum",
    noConversations: "Keine Unterhaltungen im aktuellen Filter.",
    noRecentPreview: "Keine aktuelle Vorschau",
    noModel: "Kein Modell",
    noDominantOrigin: "Keine dominante Quelle",
    noDominantModel: "Kein dominantes Modell",
    noPeak: "Kein hervorgehobener Peak im Zeitraum",
    queriesCount: "{{count}} Abfragen",
    executionsCount: "{{count}} Ausführungen",
    operationalRail: "Operativer Rail",
    operationalRailHint: "4 Signale aus dem aktuellen Ausschnitt",
    itemsCount: "{{count}} Einträge",
    emptyBreakdown: "Nicht genügend Daten im ausgewählten Zeitraum.",
    breakdownDefaultMeta: "Konsolidierter Anteil im ausgewählten Zeitraum",
    allocationDominant: "Dominant:",
    noDominantAllocation: "Keine dominante Konzentration",
    allocationFooter:
      "{{label}} macht {{value}} des aktuellen Ausschnitts aus und führt die beobachtete Verteilung an.",
    noAllocationData: "Nicht genug Kosten, um die Verteilung im Zeitraum aufzubauen.",
    allocationModes: {
      task: "Nach Aufgabe",
    },
    kpiContexts: {
      totalPeriod: "{{queries}} Abfragen · {{executions}} Ausführungen",
      noComparableBase: "Keine vergleichbare Basis",
      previousBase: "Vorherige Basis {{value}}",
      resolvedConversations: "{{count}} gelöste Unterhaltungen",
    },
    timeChart: {
      empty: "Nicht genügend Daten, um den zeitlichen Ursprung aufzubauen.",
      peak: "Peak:",
      base: "Basis:",
      buckets: "Buckets:",
      variation: "Variation:",
      noBucket: "Kein Bucket",
      driver: "Treiber · {{value}}",
      noDriver: "Kein dominanter Treiber",
    },
    breakdowns: {
      byBotTitle: "Verteilung nach Bot",
      byBotSubtitle: "Wer die Kosten konzentriert und wie die Effizienz pro gelöster Unterhaltung ist.",
      byModelTitle: "Verteilung nach Modell",
      byModelSubtitle: "Wo die Modellzuweisung den aktuellen Ausschnitt belastet.",
      byTaskTitle: "Verteilung nach Aufgabentyp",
      byTaskSubtitle: "Dominanter Aufgabentyp und durchschnittlicher Druck pro Vorkommen.",
    },
  },
};

mutableResources["en-US"].translation.common = {
  ...mutableResources["en-US"].translation.common,
  clear: "Clear",
  refresh: "Refresh",
  refine: "Refine",
  hideRefinements: "Hide refinements",
  on: "On",
  off: "Off",
  user: "User",
};

mutableResources["pt-BR"].translation.common = {
  ...mutableResources["pt-BR"].translation.common,
  clear: "Limpar",
  refresh: "Atualizar",
  refine: "Refinar",
  hideRefinements: "Ocultar refinamentos",
  on: "Ligado",
  off: "Desligado",
  user: "Usuário",
};

mutableResources["es-ES"].translation.common = {
  ...mutableResources["es-ES"].translation.common,
  clear: "Limpiar",
  refresh: "Actualizar",
  refine: "Refinar",
  hideRefinements: "Ocultar refinamientos",
  on: "Activado",
  off: "Desactivado",
  user: "Usuario",
};

mutableResources["fr-FR"].translation.common = {
  ...mutableResources["fr-FR"].translation.common,
  clear: "Effacer",
  refresh: "Actualiser",
  refine: "Affiner",
  hideRefinements: "Masquer les affinements",
  on: "Activé",
  off: "Désactivé",
  user: "Utilisateur",
};

mutableResources["de-DE"].translation.common = {
  ...mutableResources["de-DE"].translation.common,
  clear: "Löschen",
  refresh: "Aktualisieren",
  refine: "Verfeinern",
  hideRefinements: "Verfeinerungen ausblenden",
  on: "An",
  off: "Aus",
  user: "Benutzer",
};

mutableResources["en-US"].translation.memory.types = {
  fact: "Fact",
  procedure: "Procedure",
  event: "Event",
  preference: "Preference",
  decision: "Decision",
  problem: "Problem",
  task: "Task",
  commit: "Commitment",
  relationship: "Relationship",
};

mutableResources["pt-BR"].translation.memory.types = {
  fact: "Fato",
  procedure: "Procedimento",
  event: "Evento",
  preference: "Preferência",
  decision: "Decisão",
  problem: "Problema",
  task: "Tarefa",
  commit: "Compromisso",
  relationship: "Relação",
};

mutableResources["es-ES"].translation.memory.types = {
  fact: "Hecho",
  procedure: "Procedimiento",
  event: "Evento",
  preference: "Preferencia",
  decision: "Decisión",
  problem: "Problema",
  task: "Tarea",
  commit: "Compromiso",
  relationship: "Relación",
};

mutableResources["fr-FR"].translation.memory.types = {
  fact: "Fait",
  procedure: "Procédure",
  event: "Événement",
  preference: "Préférence",
  decision: "Décision",
  problem: "Problème",
  task: "Tâche",
  commit: "Engagement",
  relationship: "Relation",
};

mutableResources["de-DE"].translation.memory.types = {
  fact: "Fakt",
  procedure: "Verfahren",
  event: "Ereignis",
  preference: "Präferenz",
  decision: "Entscheidung",
  problem: "Problem",
  task: "Aufgabe",
  commit: "Verpflichtung",
  relationship: "Beziehung",
};

mutableResources["en-US"].translation.memory.map = {
  toggleViewAria: "Switch between map and curation",
  refreshAria: "Refresh memories",
  unavailableTitle: "Memory unavailable",
  fallbackLoadError: "Could not load memory map.",
  mapAndFilters: "Map and filters",
  memoryCount_one: "{{count}} memory",
  memoryCount_other: "{{count}} memories",
  documentsCount_one: "{{count}} document",
  documentsCount_other: "{{count}} documents",
  connectionsCount_one: "{{count}} connection",
  connectionsCount_other: "{{count}} connections",
  activeFilters_one: "{{count}} active filter",
  activeFilters_other: "{{count}} active filters",
  searchMap: "Search in map",
  searchPlaceholder: "Content, source, memory or learning...",
  timeWindow: "Time window",
  days: "{{count}} days",
  inactiveMemories: "Inactive memories",
  filterTitle: "Memory types",
  visibleConnections: "Visible connections",
  visible: "Visible",
  hidden: "Hidden",
  legend: "Legend",
  isolatedCluster: "isolated cluster",
  statistics: "Statistics",
  nodes: "Nodes",
  document: "Document",
  memoryLatest: "Memory (latest)",
  memoryOlder: "Memory (older)",
  statusTitle: "Status",
  forgotten: "Forgotten",
  expiringSoon: "Expiring soon",
  currentFocus: "Current focus",
  learning: "Learning",
  memory: "Memory",
  noContentAvailable: "No content available.",
};

mutableResources["en-US"].translation.memory.health = {
  eyebrow: "Memory health",
  title: "Current state of the mesh",
  semanticAvailable: "Active embeddings",
  semanticFallback: "Contextual fallback",
  semanticUnavailable: "No semantic data",
  active: "Active",
  inactive: "Inactive",
  learning: "Learning",
  expiring: "Expiring",
  semanticEdges: "Semantic edges",
  contextualEdges: "Contextual edges",
  maintenance: "Maintenance",
  lastMaintenance: "Last maintenance",
  noMaintenance: "No record",
};

mutableResources["pt-BR"].translation.memory.map = {
  toggleViewAria: "Alternar entre mapa e curadoria",
  refreshAria: "Atualizar memórias",
  unavailableTitle: "Memória indisponível",
  fallbackLoadError: "Não foi possível carregar o mapa de memória.",
  mapAndFilters: "Mapa e filtros",
  memoryCount_one: "{{count}} memória",
  memoryCount_other: "{{count}} memórias",
  documentsCount_one: "{{count}} documento",
  documentsCount_other: "{{count}} documentos",
  connectionsCount_one: "{{count}} conexão",
  connectionsCount_other: "{{count}} conexões",
  activeFilters_one: "{{count}} filtro ativo",
  activeFilters_other: "{{count}} filtros ativos",
  searchMap: "Buscar no mapa",
  searchPlaceholder: "Conteúdo, origem, memória ou aprendizado...",
  timeWindow: "Janela temporal",
  days: "{{count}} dias",
  inactiveMemories: "Memórias inativas",
  filterTitle: "Tipos de memória",
  visibleConnections: "Conexões visíveis",
  visible: "Visível",
  hidden: "Oculta",
  legend: "Legenda",
  isolatedCluster: "cluster isolado",
  statistics: "Estatísticas",
  nodes: "Nós",
  document: "Documento",
  memoryLatest: "Memória (recente)",
  memoryOlder: "Memória (antiga)",
  statusTitle: "Status",
  forgotten: "Esquecida",
  expiringSoon: "Expira em breve",
  currentFocus: "Foco atual",
  learning: "Aprendizado",
  memory: "Memória",
  noContentAvailable: "Sem conteúdo disponível.",
};

mutableResources["pt-BR"].translation.memory.health = {
  eyebrow: "Saúde da memória",
  title: "Estado atual da malha",
  semanticAvailable: "Embeddings ativos",
  semanticFallback: "Fallback contextual",
  semanticUnavailable: "Sem dados semânticos",
  active: "Ativas",
  inactive: "Inativas",
  learning: "Aprendizados",
  expiring: "Expirando",
  semanticEdges: "Arestas semânticas",
  contextualEdges: "Arestas contextuais",
  maintenance: "Manutenções",
  lastMaintenance: "Última manutenção",
  noMaintenance: "Sem registro",
};

mutableResources["es-ES"].translation.memory.map = {
  toggleViewAria: "Alternar entre mapa y curaduría",
  refreshAria: "Actualizar memorias",
  unavailableTitle: "Memoria no disponible",
  fallbackLoadError: "No se pudo cargar el mapa de memoria.",
  mapAndFilters: "Mapa y filtros",
  memoryCount_one: "{{count}} memoria",
  memoryCount_other: "{{count}} memorias",
  documentsCount_one: "{{count}} documento",
  documentsCount_other: "{{count}} documentos",
  connectionsCount_one: "{{count}} conexión",
  connectionsCount_other: "{{count}} conexiones",
  activeFilters_one: "{{count}} filtro activo",
  activeFilters_other: "{{count}} filtros activos",
  searchMap: "Buscar en el mapa",
  searchPlaceholder: "Contenido, origen, memoria o aprendizaje...",
  timeWindow: "Ventana temporal",
  days: "{{count}} días",
  inactiveMemories: "Memorias inactivas",
  filterTitle: "Tipos de memoria",
  visibleConnections: "Conexiones visibles",
  visible: "Visible",
  hidden: "Oculta",
  legend: "Leyenda",
  isolatedCluster: "cluster aislado",
  statistics: "Estadísticas",
  nodes: "Nodos",
  document: "Documento",
  memoryLatest: "Memoria (reciente)",
  memoryOlder: "Memoria (anterior)",
  statusTitle: "Estado",
  forgotten: "Olvidada",
  expiringSoon: "Expira pronto",
  currentFocus: "Foco actual",
  learning: "Aprendizaje",
  memory: "Memoria",
  noContentAvailable: "No hay contenido disponible.",
};

mutableResources["es-ES"].translation.memory.health = {
  eyebrow: "Salud de la memoria",
  title: "Estado actual de la malla",
  semanticAvailable: "Embeddings activos",
  semanticFallback: "Fallback contextual",
  semanticUnavailable: "Sin datos semánticos",
  active: "Activas",
  inactive: "Inactivas",
  learning: "Aprendizajes",
  expiring: "Expirando",
  semanticEdges: "Aristas semánticas",
  contextualEdges: "Aristas contextuales",
  maintenance: "Mantenimientos",
  lastMaintenance: "Último mantenimiento",
  noMaintenance: "Sin registro",
};

mutableResources["fr-FR"].translation.memory.map = {
  toggleViewAria: "Basculer entre carte et curation",
  refreshAria: "Actualiser les mémoires",
  unavailableTitle: "Mémoire indisponible",
  fallbackLoadError: "Impossible de charger la carte mémoire.",
  mapAndFilters: "Carte et filtres",
  memoryCount_one: "{{count}} mémoire",
  memoryCount_other: "{{count}} mémoires",
  documentsCount_one: "{{count}} document",
  documentsCount_other: "{{count}} documents",
  connectionsCount_one: "{{count}} connexion",
  connectionsCount_other: "{{count}} connexions",
  activeFilters_one: "{{count}} filtre actif",
  activeFilters_other: "{{count}} filtres actifs",
  searchMap: "Rechercher dans la carte",
  searchPlaceholder: "Contenu, source, mémoire ou apprentissage...",
  timeWindow: "Fenêtre temporelle",
  days: "{{count}} jours",
  inactiveMemories: "Mémoires inactives",
  filterTitle: "Types de mémoire",
  visibleConnections: "Connexions visibles",
  visible: "Visible",
  hidden: "Masqué",
  legend: "Légende",
  isolatedCluster: "cluster isolé",
  statistics: "Statistiques",
  nodes: "Nœuds",
  document: "Document",
  memoryLatest: "Mémoire (récente)",
  memoryOlder: "Mémoire (plus ancienne)",
  statusTitle: "Statut",
  forgotten: "Oubliée",
  expiringSoon: "Expire bientôt",
  currentFocus: "Focus actuel",
  learning: "Apprentissage",
  memory: "Mémoire",
  noContentAvailable: "Aucun contenu disponible.",
  clusters: "Clusters",
};

mutableResources["fr-FR"].translation.memory.health = {
  eyebrow: "Santé de la mémoire",
  title: "État actuel du maillage",
  semanticAvailable: "Embeddings actifs",
  semanticFallback: "Repli contextuel",
  semanticUnavailable: "Aucune donnée sémantique",
  active: "Actives",
  inactive: "Inactives",
  learning: "Apprentissages",
  expiring: "Expirant",
  semanticEdges: "Arêtes sémantiques",
  contextualEdges: "Arêtes contextuelles",
  maintenance: "Maintenances",
  lastMaintenance: "Dernière maintenance",
  noMaintenance: "Aucun enregistrement",
};

mutableResources["de-DE"].translation.memory.map = {
  toggleViewAria: "Zwischen Karte und Kuration wechseln",
  refreshAria: "Speicher aktualisieren",
  unavailableTitle: "Speicher nicht verfügbar",
  fallbackLoadError: "Speicherkarte konnte nicht geladen werden.",
  mapAndFilters: "Karte und Filter",
  memoryCount_one: "{{count}} Speicher",
  memoryCount_other: "{{count}} Speicher",
  documentsCount_one: "{{count}} Dokument",
  documentsCount_other: "{{count}} Dokumente",
  connectionsCount_one: "{{count}} Verbindung",
  connectionsCount_other: "{{count}} Verbindungen",
  activeFilters_one: "{{count}} aktiver Filter",
  activeFilters_other: "{{count}} aktive Filter",
  searchMap: "In Karte suchen",
  searchPlaceholder: "Inhalt, Quelle, Speicher oder Lernen...",
  timeWindow: "Zeitfenster",
  days: "{{count}} Tage",
  inactiveMemories: "Inaktive Speicher",
  filterTitle: "Speichertypen",
  visibleConnections: "Sichtbare Verbindungen",
  visible: "Sichtbar",
  hidden: "Verborgen",
  legend: "Legende",
  isolatedCluster: "isolierter Cluster",
  statistics: "Statistiken",
  nodes: "Knoten",
  document: "Dokument",
  memoryLatest: "Speicher (aktuell)",
  memoryOlder: "Speicher (älter)",
  statusTitle: "Status",
  forgotten: "Vergessen",
  expiringSoon: "Läuft bald ab",
  currentFocus: "Aktueller Fokus",
  learning: "Lernen",
  memory: "Speicher",
  noContentAvailable: "Kein Inhalt verfügbar.",
  clusters: "Cluster",
};

mutableResources["de-DE"].translation.memory.health = {
  eyebrow: "Speicherzustand",
  title: "Aktueller Netzzustand",
  semanticAvailable: "Aktive Embeddings",
  semanticFallback: "Kontextueller Fallback",
  semanticUnavailable: "Keine semantischen Daten",
  active: "Aktiv",
  inactive: "Inaktiv",
  learning: "Lernen",
  expiring: "Läuft ab",
  semanticEdges: "Semantische Kanten",
  contextualEdges: "Kontextuelle Kanten",
  maintenance: "Wartungen",
  lastMaintenance: "Letzte Wartung",
  noMaintenance: "Kein Eintrag",
};

mutableResources["en-US"].translation.memory.inspector = {
  selectPoint: "Select a point on the map",
  close: "Close inspector",
  active: "Active",
  inactive: "Inactive",
  importance: "Importance",
  accesses: "Accesses",
  lastUsed: "Last used",
  notAccessedYet: "Not accessed yet",
  createdAt: "Created at",
  noDate: "No date",
  origin: "Origin",
  noLinkedSession: "No linked session",
  unavailable: "Unavailable",
  relatedConnections: "Related connections",
  syntheticLearning: "Synthetic learning",
  semantic: "Semantic",
  source: "Source",
  learning: "Learning",
  noVisibleConnections: "No visible connections.",
  metadata: "Metadata",
  learningBadge: "Learning",
  memoriesCount: "{{count}} memories",
  dominantType: "Dominant type",
  intensity: "Intensity",
  semanticStrength: "Semantic strength",
  noStrongAffinity: "No strong affinity",
  contextualFallback: "Contextual fallback",
  sessions: "Sessions",
  relatedMemories: "Related memories",
  noRelatedMemories: "No related memories.",
};

mutableResources["pt-BR"].translation.memory.inspector = {
  selectPoint: "Selecione um ponto do mapa",
  close: "Fechar inspector",
  active: "Ativa",
  inactive: "Inativa",
  importance: "Importância",
  accesses: "Acessos",
  lastUsed: "Último uso",
  notAccessedYet: "Ainda não acessada",
  createdAt: "Criada em",
  noDate: "Sem data",
  origin: "Origem",
  noLinkedSession: "Sem sessão associada",
  unavailable: "Não disponível",
  relatedConnections: "Conexões relacionadas",
  syntheticLearning: "Aprendizado sintético",
  semantic: "Semântica",
  source: "Origem",
  learning: "Aprendizado",
  noVisibleConnections: "Sem conexões visíveis.",
  metadata: "Metadados",
  learningBadge: "Aprendizado",
  memoriesCount: "{{count}} memórias",
  dominantType: "Tipo dominante",
  intensity: "Intensidade",
  semanticStrength: "Força semântica",
  noStrongAffinity: "Sem afinidade forte",
  contextualFallback: "Fallback contextual",
  sessions: "Sessões",
  relatedMemories: "Memórias relacionadas",
  noRelatedMemories: "Sem memórias relacionadas.",
};

mutableResources["es-ES"].translation.memory.inspector = {
  selectPoint: "Selecciona un punto del mapa",
  close: "Cerrar inspector",
  active: "Activa",
  inactive: "Inactiva",
  importance: "Importancia",
  accesses: "Accesos",
  lastUsed: "Último uso",
  notAccessedYet: "Aún no accedida",
  createdAt: "Creada en",
  noDate: "Sin fecha",
  origin: "Origen",
  noLinkedSession: "Sin sesión asociada",
  unavailable: "No disponible",
  relatedConnections: "Conexiones relacionadas",
  syntheticLearning: "Aprendizaje sintético",
  semantic: "Semántica",
  source: "Origen",
  learning: "Aprendizaje",
  noVisibleConnections: "Sin conexiones visibles.",
  metadata: "Metadatos",
  learningBadge: "Aprendizaje",
  memoriesCount: "{{count}} memorias",
  dominantType: "Tipo dominante",
  intensity: "Intensidad",
  semanticStrength: "Fuerza semántica",
  noStrongAffinity: "Sin afinidad fuerte",
  contextualFallback: "Fallback contextual",
  sessions: "Sesiones",
  relatedMemories: "Memorias relacionadas",
  noRelatedMemories: "Sin memorias relacionadas.",
};

mutableResources["fr-FR"].translation.memory.inspector = {
  selectPoint: "Sélectionnez un point sur la carte",
  close: "Fermer l'inspecteur",
  active: "Active",
  inactive: "Inactive",
  importance: "Importance",
  accesses: "Accès",
  lastUsed: "Dernière utilisation",
  notAccessedYet: "Pas encore accédée",
  createdAt: "Créée le",
  noDate: "Aucune date",
  origin: "Origine",
  noLinkedSession: "Aucune session liée",
  unavailable: "Indisponible",
  relatedConnections: "Connexions associées",
  syntheticLearning: "Apprentissage synthétique",
  semantic: "Sémantique",
  source: "Source",
  learning: "Apprentissage",
  noVisibleConnections: "Aucune connexion visible.",
  metadata: "Métadonnées",
  learningBadge: "Apprentissage",
  memoriesCount: "{{count}} mémoires",
  dominantType: "Type dominant",
  intensity: "Intensité",
  semanticStrength: "Force sémantique",
  noStrongAffinity: "Aucune affinité forte",
  contextualFallback: "Repli contextuel",
  sessions: "Sessions",
  relatedMemories: "Mémoires associées",
  noRelatedMemories: "Aucune mémoire associée.",
};

mutableResources["de-DE"].translation.memory.inspector = {
  selectPoint: "Wählen Sie einen Punkt auf der Karte",
  close: "Inspektor schließen",
  active: "Aktiv",
  inactive: "Inaktiv",
  importance: "Wichtigkeit",
  accesses: "Zugriffe",
  lastUsed: "Zuletzt verwendet",
  notAccessedYet: "Noch nicht abgerufen",
  createdAt: "Erstellt am",
  noDate: "Kein Datum",
  origin: "Quelle",
  noLinkedSession: "Keine verknüpfte Sitzung",
  unavailable: "Nicht verfügbar",
  relatedConnections: "Verwandte Verbindungen",
  syntheticLearning: "Synthetisches Lernen",
  semantic: "Semantisch",
  source: "Quelle",
  learning: "Lernen",
  noVisibleConnections: "Keine sichtbaren Verbindungen.",
  metadata: "Metadaten",
  learningBadge: "Lernen",
  memoriesCount: "{{count}} Speicher",
  dominantType: "Dominanter Typ",
  intensity: "Intensität",
  semanticStrength: "Semantische Stärke",
  noStrongAffinity: "Keine starke Affinität",
  contextualFallback: "Kontextueller Fallback",
  sessions: "Sitzungen",
  relatedMemories: "Verwandte Speicher",
  noRelatedMemories: "Keine verwandten Speicher.",
};

mutableResources["en-US"].translation.memory.curation.status = {
  approved: "Approved",
  merged: "Merged",
  discarded: "Discarded",
  expired: "Expired",
  archived: "Archived",
  pending: "Pending",
};

mutableResources["pt-BR"].translation.memory.curation.status = {
  approved: "Aprovada",
  merged: "Mesclada",
  discarded: "Descartada",
  expired: "Expirada",
  archived: "Arquivada",
  pending: "Pendente",
};

mutableResources["es-ES"].translation.memory.curation.status = {
  approved: "Aprobada",
  merged: "Fusionada",
  discarded: "Descartada",
  expired: "Expirada",
  archived: "Archivada",
  pending: "Pendiente",
};

mutableResources["fr-FR"].translation.memory.curation.status = {
  approved: "Approuvée",
  merged: "Fusionnée",
  discarded: "Rejetée",
  expired: "Expirée",
  archived: "Archivée",
  pending: "En attente",
};

mutableResources["de-DE"].translation.memory.curation.status = {
  approved: "Genehmigt",
  merged: "Zusammengeführt",
  discarded: "Verworfen",
  expired: "Abgelaufen",
  archived: "Archiviert",
  pending: "Ausstehend",
};

mutableResources["en-US"].translation.memory.curation.detail = {
  noReviewRecorded: "No review recorded.",
  content: "Content",
  sourceAndContext: "Source and context",
  sourceQuery: "Source query",
  noSourceQuery: "No source query recorded.",
  cluster: "Cluster",
  noGrouping: "No grouping",
  editorialStatus: "Editorial status",
  navigation: "Navigation",
  viewOnMap: "View on map",
  editorialReason: "Editorial reason",
  relatedAndDuplicates: "Related items and duplicates",
  relatedMemories: "Related memories",
  noStrongRelation: "No strong relation found in this reading.",
  possibleDuplicates: "Possible duplicates",
  noDuplicateDetected: "No obvious duplicates detected.",
  history: "History",
  loadDetailErrorTitle: "Could not load detail",
  selectEditorialItemTitle: "Select an editorial item",
  selectEditorialItemDescription:
    "Open a memory or a cluster to review context, duplication and editorial decisions.",
  loadingMemoryDetail: "Loading memory detail",
  loadingClusterDetail: "Loading grouping detail",
  learningTitle: "Learning",
  learningDescription: "Review this grouping before promoting it as recurring context.",
  createdMeta: "Created {{value}}",
  lastAccessedMeta: "Last accessed {{value}}",
  importanceMeta: "{{value}}% importance",
  accessesMeta: "{{value}} accesses",
  sessionFallback: "No session",
  memoriesConnected_one: "{{count}} connected memory",
  memoriesConnected_other: "{{count}} connected memories",
  groupingContext: "Grouping context",
  created: "Created",
  sessionsCovered: "Covered sessions",
  primaryMembers: "Primary members",
  noLinkedSessions: "No linked sessions.",
};

mutableResources["pt-BR"].translation.memory.curation.detail = {
  noReviewRecorded: "Sem revisão registrada.",
  content: "Conteúdo",
  sourceAndContext: "Origem e contexto",
  sourceQuery: "Query de origem",
  noSourceQuery: "Sem query de origem registrada.",
  cluster: "Cluster",
  noGrouping: "Sem agrupamento",
  editorialStatus: "Status editorial",
  navigation: "Navegação",
  viewOnMap: "Ver no mapa",
  editorialReason: "Motivo editorial",
  relatedAndDuplicates: "Relacionadas e duplicatas",
  relatedMemories: "Memórias relacionadas",
  noStrongRelation: "Nenhuma relação forte encontrada nesta leitura.",
  possibleDuplicates: "Possíveis duplicatas",
  noDuplicateDetected: "Nenhuma duplicata evidente detectada.",
  history: "Histórico",
  loadDetailErrorTitle: "Não foi possível carregar o detalhe",
  selectEditorialItemTitle: "Selecione um item editorial",
  selectEditorialItemDescription:
    "Abra uma memória ou um cluster para revisar contexto, duplicidade e decisões editoriais.",
  loadingMemoryDetail: "Carregando detalhe da memória",
  loadingClusterDetail: "Carregando detalhe do agrupamento",
  learningTitle: "Aprendizado",
  learningDescription: "Revise este agrupamento antes de promovê-lo como contexto recorrente.",
  createdMeta: "Criada {{value}}",
  lastAccessedMeta: "Último acesso {{value}}",
  importanceMeta: "{{value}}% importância",
  accessesMeta: "{{value}} acessos",
  sessionFallback: "Sem sessão",
  memoriesConnected_one: "{{count}} memória conectada",
  memoriesConnected_other: "{{count}} memórias conectadas",
  groupingContext: "Contexto do agrupamento",
  created: "Criado",
  sessionsCovered: "Sessões cobertas",
  primaryMembers: "Membros principais",
  noLinkedSessions: "Sem sessões vinculadas.",
};

mutableResources["es-ES"].translation.memory.curation.detail = {
  noReviewRecorded: "No hay revisión registrada.",
  content: "Contenido",
  sourceAndContext: "Origen y contexto",
  sourceQuery: "Query de origen",
  noSourceQuery: "No hay query de origen registrada.",
  cluster: "Cluster",
  noGrouping: "Sin agrupación",
  editorialStatus: "Estado editorial",
  navigation: "Navegación",
  viewOnMap: "Ver en el mapa",
  editorialReason: "Motivo editorial",
  relatedAndDuplicates: "Relacionadas y duplicados",
  relatedMemories: "Memorias relacionadas",
  noStrongRelation: "No se encontró una relación fuerte en esta lectura.",
  possibleDuplicates: "Posibles duplicados",
  noDuplicateDetected: "No se detectaron duplicados evidentes.",
  history: "Historial",
  loadDetailErrorTitle: "No se pudo cargar el detalle",
  selectEditorialItemTitle: "Selecciona un elemento editorial",
  selectEditorialItemDescription:
    "Abre una memoria o un cluster para revisar contexto, duplicidad y decisiones editoriales.",
  loadingMemoryDetail: "Cargando detalle de la memoria",
  loadingClusterDetail: "Cargando detalle de la agrupación",
  learningTitle: "Aprendizaje",
  learningDescription: "Revisa esta agrupación antes de promoverla como contexto recurrente.",
  createdMeta: "Creada {{value}}",
  lastAccessedMeta: "Último acceso {{value}}",
  importanceMeta: "{{value}}% importancia",
  accessesMeta: "{{value}} accesos",
  sessionFallback: "Sin sesión",
  memoriesConnected_one: "{{count}} memoria conectada",
  memoriesConnected_other: "{{count}} memorias conectadas",
  groupingContext: "Contexto de la agrupación",
  created: "Creado",
  sessionsCovered: "Sesiones cubiertas",
  primaryMembers: "Miembros principales",
  noLinkedSessions: "Sin sesiones vinculadas.",
};

mutableResources["fr-FR"].translation.memory.curation.detail = {
  noReviewRecorded: "Aucune révision enregistrée.",
  content: "Contenu",
  sourceAndContext: "Origine et contexte",
  sourceQuery: "Requête d'origine",
  noSourceQuery: "Aucune requête d'origine enregistrée.",
  cluster: "Cluster",
  noGrouping: "Aucun regroupement",
  editorialStatus: "Statut éditorial",
  navigation: "Navigation",
  viewOnMap: "Voir sur la carte",
  editorialReason: "Motif éditorial",
  relatedAndDuplicates: "Éléments associés et doublons",
  relatedMemories: "Mémoires associées",
  noStrongRelation: "Aucune relation forte trouvée dans cette lecture.",
  possibleDuplicates: "Doublons possibles",
  noDuplicateDetected: "Aucun doublon évident détecté.",
  history: "Historique",
  loadDetailErrorTitle: "Impossible de charger le détail",
  selectEditorialItemTitle: "Sélectionnez un élément éditorial",
  selectEditorialItemDescription:
    "Ouvrez une mémoire ou un cluster pour examiner contexte, duplication et décisions éditoriales.",
  loadingMemoryDetail: "Chargement du détail de la mémoire",
  loadingClusterDetail: "Chargement du détail du regroupement",
  learningTitle: "Apprentissage",
  learningDescription: "Révisez ce regroupement avant de le promouvoir comme contexte récurrent.",
  createdMeta: "Créée {{value}}",
  lastAccessedMeta: "Dernier accès {{value}}",
  importanceMeta: "{{value}}% d'importance",
  accessesMeta: "{{value}} accès",
  sessionFallback: "Aucune session",
  memoriesConnected_one: "{{count}} mémoire connectée",
  memoriesConnected_other: "{{count}} mémoires connectées",
  groupingContext: "Contexte du regroupement",
  created: "Créé",
  sessionsCovered: "Sessions couvertes",
  primaryMembers: "Membres principaux",
  noLinkedSessions: "Aucune session liée.",
};

mutableResources["de-DE"].translation.memory.curation.detail = {
  noReviewRecorded: "Keine Überprüfung erfasst.",
  content: "Inhalt",
  sourceAndContext: "Quelle und Kontext",
  sourceQuery: "Quellabfrage",
  noSourceQuery: "Keine Quellabfrage erfasst.",
  cluster: "Cluster",
  noGrouping: "Keine Gruppierung",
  editorialStatus: "Redaktioneller Status",
  navigation: "Navigation",
  viewOnMap: "Auf der Karte anzeigen",
  editorialReason: "Redaktioneller Grund",
  relatedAndDuplicates: "Verwandte Elemente und Duplikate",
  relatedMemories: "Verwandte Speicher",
  noStrongRelation: "In dieser Lesung wurde keine starke Beziehung gefunden.",
  possibleDuplicates: "Mögliche Duplikate",
  noDuplicateDetected: "Keine offensichtlichen Duplikate erkannt.",
  history: "Verlauf",
  loadDetailErrorTitle: "Detail konnte nicht geladen werden",
  selectEditorialItemTitle: "Wählen Sie ein redaktionelles Element",
  selectEditorialItemDescription:
    "Öffnen Sie einen Speicher oder einen Cluster, um Kontext, Duplikate und redaktionelle Entscheidungen zu prüfen.",
  loadingMemoryDetail: "Speicherdetail wird geladen",
  loadingClusterDetail: "Gruppierungsdetail wird geladen",
  learningTitle: "Lernen",
  learningDescription: "Überprüfen Sie diese Gruppierung, bevor Sie sie als wiederkehrenden Kontext fördern.",
  createdMeta: "Erstellt {{value}}",
  lastAccessedMeta: "Letzter Zugriff {{value}}",
  importanceMeta: "{{value}}% Wichtigkeit",
  accessesMeta: "{{value}} Zugriffe",
  sessionFallback: "Keine Sitzung",
  memoriesConnected_one: "{{count}} verbundener Speicher",
  memoriesConnected_other: "{{count}} verbundene Speicher",
  groupingContext: "Gruppierungskontext",
  created: "Erstellt",
  sessionsCovered: "Abgedeckte Sitzungen",
  primaryMembers: "Hauptmitglieder",
  noLinkedSessions: "Keine verknüpften Sitzungen.",
};

mutableResources["en-US"].translation.overview.activity = {
  ...mutableResources["en-US"].translation.overview.activity,
  activeTasksCount_one: "{{count}} active",
  activeTasksCount_other: "{{count}} active",
};

mutableResources["pt-BR"].translation.overview.activity = {
  ...mutableResources["pt-BR"].translation.overview.activity,
  activeTasksCount_one: "{{count}} ativa",
  activeTasksCount_other: "{{count}} ativas",
};

mutableResources["es-ES"].translation.overview.activity = {
  ...mutableResources["es-ES"].translation.overview.activity,
  activeTasksCount_one: "{{count}} activa",
  activeTasksCount_other: "{{count}} activas",
};

mutableResources["en-US"].translation.common = {
  ...mutableResources["en-US"].translation.common,
  task: "Task",
  tasks: "Tasks",
  attempts: "Attempts",
  model: "Model",
  message: "Message",
  details: "Details",
  timing: "Timing",
  startedAt: "Started at",
  completedAt: "Completed at",
  totalTime: "Total time",
  close: "Close",
  copy: "Copy",
  event: "Event",
  context: "Context",
  noBot: "No bot",
  payload: "Payload",
  pod: "Pod",
  tools: "Tools",
  warnings: "Warnings",
  lastActivity: "Last activity",
  schedules: "Schedules",
  sessions: "Sessions",
  executions: "Executions",
  noHistory: "No history",
  workspaceDirectory: "Working directory",
  save: "Save",
  cancel: "Cancel",
  edit: "Edit",
  create: "Create",
  delete: "Delete",
  refresh: "Refresh",
  reconnect: "Reconnect",
  preview: "Preview",
  code: "Code",
  back: "Back",
  open: "Open",
  mode: "Mode",
  display: "Display",
  visual: "Visual",
  state: "State",
  phase: "Phase",
  lines: "lines",
};

mutableResources["pt-BR"].translation.common = {
  ...mutableResources["pt-BR"].translation.common,
  task: "Tarefa",
  tasks: "Tarefas",
  attempts: "Tentativas",
  model: "Modelo",
  message: "Mensagem",
  details: "Detalhes",
  timing: "Tempo",
  startedAt: "Iniciada em",
  completedAt: "Concluída em",
  totalTime: "Tempo total",
  close: "Fechar",
  copy: "Copiar",
  event: "Evento",
  context: "Contexto",
  noBot: "Sem bot",
  payload: "Payload",
  pod: "Pod",
  tools: "Ferramentas",
  warnings: "Avisos",
  lastActivity: "Última atividade",
  schedules: "Agendamentos",
  sessions: "Sessões",
  executions: "Execuções",
  noHistory: "Sem histórico",
  workspaceDirectory: "Diretório de trabalho",
  save: "Salvar",
  cancel: "Cancelar",
  edit: "Editar",
  create: "Criar",
  delete: "Excluir",
  refresh: "Atualizar",
  reconnect: "Reconectar",
  preview: "Preview",
  code: "Código",
  back: "Voltar",
  open: "Abrir",
  mode: "Modo",
  display: "Display",
  visual: "Visual",
  state: "Estado",
  phase: "Etapa",
  lines: "linhas",
};

mutableResources["es-ES"].translation.common = {
  ...mutableResources["es-ES"].translation.common,
  task: "Tarea",
  tasks: "Tareas",
  attempts: "Intentos",
  model: "Modelo",
  message: "Mensaje",
  details: "Detalles",
  timing: "Tiempo",
  startedAt: "Iniciada en",
  completedAt: "Completada en",
  totalTime: "Tiempo total",
  close: "Cerrar",
  copy: "Copiar",
  event: "Evento",
  context: "Contexto",
  noBot: "Sin bot",
  payload: "Payload",
  pod: "Pod",
  tools: "Herramientas",
  warnings: "Avisos",
  lastActivity: "Última actividad",
  schedules: "Programaciones",
  sessions: "Sesiones",
  executions: "Ejecuciones",
  noHistory: "Sin historial",
  workspaceDirectory: "Directorio de trabajo",
  save: "Guardar",
  cancel: "Cancelar",
  edit: "Editar",
  create: "Crear",
  delete: "Eliminar",
  refresh: "Actualizar",
  reconnect: "Reconectar",
  preview: "Vista previa",
  code: "Código",
  back: "Volver",
  open: "Abrir",
  mode: "Modo",
  display: "Display",
  visual: "Visual",
  state: "Estado",
  phase: "Fase",
  lines: "líneas",
};

mutableResources["en-US"].translation.runtime.overview = {
  title: "Runtime",
  searchPlaceholder: "Search task, branch or bot",
  filterLabel: "Filter executions",
  filters: {
    all: "All",
    active: "Now",
    retained: "Retained",
    recovery: "Attention",
  },
  metrics: {
    onlineBots: "Bots online",
    executions: "Executions",
    attention: "Attention",
  },
  liveExecutions: "Live executions",
  noExecutionsMatch: "No execution matches the current filters.",
  agents: "Bots",
  noVisibleAgents: "No visible bot.",
  live: "Live",
};

mutableResources["pt-BR"].translation.runtime.overview = {
  title: "Runtime",
  searchPlaceholder: "Buscar task, branch ou bot",
  filterLabel: "Filtrar execuções",
  filters: {
    all: "Tudo",
    active: "Agora",
    retained: "Retidos",
    recovery: "Atenção",
  },
  metrics: {
    onlineBots: "Bots online",
    executions: "Execuções",
    attention: "Atenção",
  },
  liveExecutions: "Execuções ao vivo",
  noExecutionsMatch: "Nenhuma execução combina com os filtros atuais.",
  agents: "Bots",
  noVisibleAgents: "Nenhum bot visível.",
  live: "Ao vivo",
};

mutableResources["es-ES"].translation.runtime.overview = {
  title: "Runtime",
  searchPlaceholder: "Buscar tarea, rama o bot",
  filterLabel: "Filtrar ejecuciones",
  filters: {
    all: "Todo",
    active: "Ahora",
    retained: "Retenidas",
    recovery: "Atención",
  },
  metrics: {
    onlineBots: "Bots online",
    executions: "Ejecuciones",
    attention: "Atención",
  },
  liveExecutions: "Ejecuciones en vivo",
  noExecutionsMatch: "Ninguna ejecución coincide con los filtros actuales.",
  agents: "Bots",
  noVisibleAgents: "Ningún bot visible.",
  live: "En vivo",
};

mutableResources["fr-FR"].translation.runtime.overview = {
  title: "Runtime",
  searchPlaceholder: "Rechercher tâche, branche ou bot",
  filterLabel: "Filtrer les exécutions",
  filters: {
    all: "Tout",
    active: "Maintenant",
    retained: "Conservées",
    recovery: "Attention",
  },
  metrics: {
    onlineBots: "Bots en ligne",
    executions: "Exécutions",
    attention: "Attention",
  },
  liveExecutions: "Exécutions en direct",
  noExecutionsMatch: "Aucune exécution ne correspond aux filtres actuels.",
  agents: "Bots",
  noVisibleAgents: "Aucun bot visible.",
  live: "En direct",
};

mutableResources["de-DE"].translation.runtime.overview = {
  title: "Laufzeit",
  searchPlaceholder: "Aufgabe, Branch oder Bot suchen",
  filterLabel: "Ausführungen filtern",
  filters: {
    all: "Alle",
    active: "Jetzt",
    retained: "Aufbewahrt",
    recovery: "Aufmerksamkeit",
  },
  metrics: {
    onlineBots: "Bots online",
    executions: "Ausführungen",
    attention: "Aufmerksamkeit",
  },
  liveExecutions: "Live-Ausführungen",
  noExecutionsMatch: "Keine Ausführung entspricht den aktuellen Filtern.",
  agents: "Bots",
  noVisibleAgents: "Kein sichtbarer Bot.",
  live: "Live",
};

mutableResources["en-US"].translation.runtime.controlCard = {
  eyebrow: "Runtime",
  title: "Live control plane",
  description: "Environments, recovery backlog and direct shortcuts to operational rooms.",
  openRuntime: "Open runtime",
  active: "Active",
  retained: "Retained",
  incidents: "Incidents",
  loading: "Loading runtime for visible bots...",
  empty: "No operational task was published in the current runtime.",
  live: "Live",
  backlogNotice:
    "There is cleanup/recovery backlog in at least one visible bot. The Runtime page shows the full state and lets you act without leaving the flow.",
};

mutableResources["en-US"].translation.runtime.terminal = {
  connecting: "Connecting terminal",
  waitingAttach: "Waiting for terminal attach...",
  assumeControl: "Taking control...",
  enterReadMode: "Entering read mode",
  attachUnavailable: "Could not attach to the terminal.",
  writeChannelActive: "Supervised channel active. The keyboard now writes into the environment.",
  readChannelActive: "Read-only channel connected. Use 'Take control' to type.",
  live: "Live terminal",
  terminated: "Terminal closed",
  invalidFrame: "[invalid frame ignored]",
  channelClosed: "Channel closed",
  relayFailure: "Terminal relay failed.",
  connectFailure: "Failed to connect terminal",
  terminalError: "Terminal error",
  previewHeader: "Preview of the environment terminal. Authenticated attach is not active.",
  previewMode: "Terminal preview",
  noOutputYet: "[no output available yet]",
  control: "Control",
  read: "Read",
  searchPlaceholder: "Search terminal...",
};

mutableResources["pt-BR"].translation.runtime.terminal = {
  connecting: "Conectando terminal",
  waitingAttach: "Aguardando attach do terminal...",
  assumeControl: "Assumindo controle...",
  enterReadMode: "Entrando em leitura",
  attachUnavailable: "Não foi possível anexar ao terminal.",
  writeChannelActive: "Canal supervisionado ativo. O teclado agora escreve no ambiente.",
  readChannelActive: "Canal em leitura conectado. Use 'Assumir controle' para escrever.",
  live: "Terminal ao vivo",
  terminated: "Terminal encerrado",
  invalidFrame: "[frame inválido ignorado]",
  channelClosed: "Canal encerrado",
  relayFailure: "Falha no relay do terminal.",
  connectFailure: "Falha ao conectar terminal",
  terminalError: "Erro no terminal",
  previewHeader: "Preview do terminal do ambiente. O attach autenticado não está ativo.",
  previewMode: "Preview do terminal",
  noOutputYet: "[sem saída disponível ainda]",
  control: "Controle",
  read: "Leitura",
  searchPlaceholder: "Buscar no terminal...",
};

mutableResources["es-ES"].translation.runtime.terminal = {
  connecting: "Conectando terminal",
  waitingAttach: "Esperando attach del terminal...",
  assumeControl: "Tomando control...",
  enterReadMode: "Entrando en lectura",
  attachUnavailable: "No fue posible anexar al terminal.",
  writeChannelActive: "Canal supervisado activo. El teclado ahora escribe en el entorno.",
  readChannelActive: "Canal de solo lectura conectado. Usa 'Tomar control' para escribir.",
  live: "Terminal en vivo",
  terminated: "Terminal cerrado",
  invalidFrame: "[frame inválido ignorado]",
  channelClosed: "Canal cerrado",
  relayFailure: "Falló el relay del terminal.",
  connectFailure: "No fue posible conectar el terminal",
  terminalError: "Error del terminal",
  previewHeader: "Vista previa del terminal del entorno. El attach autenticado no está activo.",
  previewMode: "Vista previa del terminal",
  noOutputYet: "[sin salida disponible todavía]",
  control: "Control",
  read: "Lectura",
  searchPlaceholder: "Buscar en el terminal...",
};

mutableResources["fr-FR"].translation.runtime.terminal = {
  connecting: "Connexion au terminal",
  waitingAttach: "En attente de l'attachement du terminal...",
  assumeControl: "Prise de contrôle...",
  enterReadMode: "Passage en mode lecture",
  attachUnavailable: "Impossible de s'attacher au terminal.",
  writeChannelActive: "Canal supervisé actif. Le clavier écrit désormais dans l'environnement.",
  readChannelActive: "Canal en lecture seule connecté. Utilisez « Prendre le contrôle » pour écrire.",
  live: "Terminal en direct",
  terminated: "Terminal terminé",
  invalidFrame: "[trame non valide ignorée]",
  channelClosed: "Canal fermé",
  relayFailure: "Le relais du terminal a échoué.",
  connectFailure: "Impossible de connecter le terminal",
  terminalError: "Erreur du terminal",
  previewHeader: "Aperçu du terminal de l'environnement. L'attachement authentifié n'est pas actif.",
  previewMode: "Aperçu du terminal",
  noOutputYet: "[aucune sortie disponible pour l'instant]",
  control: "Contrôle",
  read: "Lecture",
  searchPlaceholder: "Rechercher dans le terminal...",
};

mutableResources["de-DE"].translation.runtime.terminal = {
  connecting: "Terminal wird verbunden",
  waitingAttach: "Warten auf Terminal-Attach...",
  assumeControl: "Kontrolle wird übernommen...",
  enterReadMode: "Wechsel in den Lesemodus",
  attachUnavailable: "Anhängen an das Terminal nicht möglich.",
  writeChannelActive: "Überwachter Kanal aktiv. Die Tastatur schreibt jetzt in die Umgebung.",
  readChannelActive: "Nur-Lese-Kanal verbunden. Verwenden Sie „Kontrolle übernehmen“, um zu schreiben.",
  live: "Terminal live",
  terminated: "Terminal beendet",
  invalidFrame: "[ungültiger Frame ignoriert]",
  channelClosed: "Kanal geschlossen",
  relayFailure: "Terminal-Relay fehlgeschlagen.",
  connectFailure: "Terminal konnte nicht verbunden werden",
  terminalError: "Terminalfehler",
  previewHeader: "Vorschau des Umgebungs-Terminals. Der authentifizierte Attach ist nicht aktiv.",
  previewMode: "Terminal-Vorschau",
  noOutputYet: "[noch keine Ausgabe verfügbar]",
  control: "Kontrolle",
  read: "Lesen",
  searchPlaceholder: "Im Terminal suchen...",
};

mutableResources["en-US"].translation.runtime.browser = {
  preparing: "Preparing live browser",
  endpointError: "Browser endpoint returned an error",
  screenshotUnavailable: "Could not obtain a visual snapshot for this browser session.",
  invalidImage: "The runtime returned no valid image for this browser session.",
  snapshotMetadata: "Browser snapshot and metadata",
  preparingAttach: "Preparing browser attach...",
  snapshotActive: "Browser snapshot active",
  snapshotClosed: "Browser snapshot closed",
  snapshotFailure: "Browser snapshot channel failed.",
  liveConnected: "Live browser connected",
  liveDisconnected: "Live browser disconnected",
  noVncFallback: "Browser without noVNC; showing snapshot and metadata only",
  openFailure: "Failed to open live browser",
  title: "Browser",
  visualSessionUnavailable: "Visual session unavailable",
  noGraphicsTransport: "Live browser without graphical transport",
  noVncDescription:
    "The runtime returned without noVNC. When there is an active page in the browser, the dashboard will show periodic snapshots here.",
  missingBinaries: "Missing binaries",
  activeSnapshot: "Active snapshot",
  noVisualSurface: "No visual surface available",
  sessionGone:
    "The browser visual session is no longer active in this runtime instance. The environment was retained, but the in-memory browser did not survive the bot restart.",
  noScreenshot: "The runtime is connected, but there is no screenshot available for this session right now.",
  noVisualForSession: "There is no visual surface available for this session.",
};

mutableResources["en-US"].translation.runtime.attach = {
  terminalTimeout:
    "Terminal attach took longer than expected; showing the log preview while the environment responds.",
  browserTimeout:
    "Browser attach took longer than expected; showing snapshot and metadata while the runtime responds.",
  terminalPreviewFallback: "Could not attach to the terminal; showing log preview.",
  browserSnapshotFallback: "Could not attach to the browser; showing snapshot.",
};

mutableResources["pt-BR"].translation.runtime.browser = {
  preparing: "Preparando browser live",
  endpointError: "Browser endpoint retornou erro",
  screenshotUnavailable: "Não foi possível obter um snapshot visual desta sessão de browser.",
  invalidImage: "O runtime respondeu sem imagem válida para esta sessão de browser.",
  snapshotMetadata: "Snapshot e metadados do browser",
  preparingAttach: "Preparando attach do browser...",
  snapshotActive: "Snapshot do browser ativo",
  snapshotClosed: "Snapshot do browser encerrado",
  snapshotFailure: "Falha no canal de snapshot do browser.",
  liveConnected: "Browser live conectado",
  liveDisconnected: "Browser live desconectado",
  noVncFallback: "Browser sem noVNC; exibindo somente snapshot e metadados",
  openFailure: "Falha ao abrir browser live",
  title: "Browser",
  visualSessionUnavailable: "Sessão visual indisponível",
  noGraphicsTransport: "Browser live sem transporte gráfico",
  noVncDescription:
    "O runtime respondeu sem noVNC. Quando houver uma página ativa no browser, o dashboard passa a exibir snapshots periódicos aqui.",
  missingBinaries: "Binários ausentes",
  activeSnapshot: "Snapshot ativo",
  noVisualSurface: "Sem superfície visual",
  sessionGone:
    "A sessão visual do browser não está mais ativa nesta instância do runtime. O ambiente foi retido, mas o browser em memória não sobreviveu ao restart do bot.",
  noScreenshot: "O runtime está conectado, mas não há screenshot disponível para esta sessão agora.",
  noVisualForSession: "Não há superfície visual disponível para esta sessão.",
};

mutableResources["pt-BR"].translation.runtime.attach = {
  terminalTimeout:
    "O attach do terminal demorou além do esperado; exibindo preview do log enquanto o ambiente responde.",
  browserTimeout:
    "O attach do browser demorou além do esperado; exibindo snapshot e metadados enquanto o runtime responde.",
  terminalPreviewFallback: "Não foi possível anexar ao terminal; exibindo preview do log.",
  browserSnapshotFallback: "Não foi possível anexar ao browser; exibindo snapshot.",
};

mutableResources["es-ES"].translation.runtime.browser = {
  preparing: "Preparando browser en vivo",
  endpointError: "El endpoint del browser devolvió un error",
  screenshotUnavailable: "No fue posible obtener un snapshot visual de esta sesión de browser.",
  invalidImage: "El runtime devolvió una imagen no válida para esta sesión de browser.",
  snapshotMetadata: "Snapshot y metadatos del browser",
  preparingAttach: "Preparando attach del browser...",
  snapshotActive: "Snapshot del browser activo",
  snapshotClosed: "Snapshot del browser cerrado",
  snapshotFailure: "Falló el canal de snapshot del browser.",
  liveConnected: "Browser en vivo conectado",
  liveDisconnected: "Browser en vivo desconectado",
  noVncFallback: "Browser sin noVNC; mostrando solo snapshot y metadatos",
  openFailure: "No fue posible abrir el browser en vivo",
  title: "Browser",
  visualSessionUnavailable: "Sesión visual no disponible",
  noGraphicsTransport: "Browser en vivo sin transporte gráfico",
  noVncDescription:
    "El runtime respondió sin noVNC. Cuando exista una página activa en el browser, el dashboard mostrará snapshots periódicos aquí.",
  missingBinaries: "Binarios faltantes",
  activeSnapshot: "Snapshot activo",
  noVisualSurface: "Sin superficie visual",
  sessionGone:
    "La sesión visual del browser ya no está activa en esta instancia del runtime. El entorno fue retenido, pero el browser en memoria no sobrevivió al reinicio del bot.",
  noScreenshot: "El runtime está conectado, pero ahora no hay screenshot disponible para esta sesión.",
  noVisualForSession: "No hay superficie visual disponible para esta sesión.",
};

mutableResources["es-ES"].translation.runtime.attach = {
  terminalTimeout:
    "El attach del terminal tardó más de lo esperado; mostrando la vista previa del log mientras responde el entorno.",
  browserTimeout:
    "El attach del browser tardó más de lo esperado; mostrando snapshot y metadatos mientras responde el runtime.",
  terminalPreviewFallback: "No fue posible anexar al terminal; mostrando vista previa del log.",
  browserSnapshotFallback: "No fue posible anexar al browser; mostrando snapshot.",
};

mutableResources["fr-FR"].translation.runtime.browser = {
  preparing: "Préparation du navigateur en direct",
  endpointError: "Le point d'accès du navigateur a renvoyé une erreur",
  screenshotUnavailable: "Impossible d'obtenir un instantané visuel de cette session du navigateur.",
  invalidImage: "Le runtime a renvoyé une image non valide pour cette session de navigateur.",
  snapshotMetadata: "Instantané et métadonnées du navigateur",
  preparingAttach: "Préparation de l'attachement du navigateur...",
  snapshotActive: "Instantané du navigateur actif",
  snapshotClosed: "Instantané du navigateur fermé",
  snapshotFailure: "Le canal d'instantané du navigateur a échoué.",
  liveConnected: "Navigateur en direct connecté",
  liveDisconnected: "Navigateur en direct déconnecté",
  noVncFallback: "Navigateur sans noVNC ; affichage de l'instantané et des métadonnées uniquement",
  openFailure: "Échec de l'ouverture du navigateur en direct",
  title: "Navigateur",
  visualSessionUnavailable: "Session visuelle indisponible",
  noGraphicsTransport: "Navigateur en direct sans transport graphique",
  noVncDescription:
    "Le runtime a répondu sans noVNC. Lorsqu'une page est active dans le navigateur, le tableau de bord affiche ici des instantanés périodiques.",
  missingBinaries: "Binaires manquants",
  activeSnapshot: "Instantané actif",
  noVisualSurface: "Aucune surface visuelle disponible",
  sessionGone:
    "La session visuelle du navigateur n'est plus active dans cette instance de runtime. L'environnement a été conservé, mais le navigateur en mémoire n'a pas survécu au redémarrage du bot.",
  noScreenshot: "Le runtime est connecté, mais aucune capture d'écran n'est disponible pour cette session pour l'instant.",
  noVisualForSession: "Aucune surface visuelle disponible pour cette session.",
};

mutableResources["fr-FR"].translation.runtime.attach = {
  terminalTimeout:
    "L'attachement du terminal a pris plus de temps que prévu ; affichage de l'aperçu des journaux pendant la réponse de l'environnement.",
  browserTimeout:
    "L'attachement du navigateur a pris plus de temps que prévu ; affichage de l'instantané et des métadonnées pendant la réponse du runtime.",
  terminalPreviewFallback: "Impossible de s'attacher au terminal ; affichage de l'aperçu des journaux.",
  browserSnapshotFallback: "Impossible de s'attacher au navigateur ; affichage de l'instantané.",
};

mutableResources["de-DE"].translation.runtime.browser = {
  preparing: "Live-Browser wird vorbereitet",
  endpointError: "Der Browser-Endpunkt hat einen Fehler zurückgegeben",
  screenshotUnavailable: "Es konnte kein visueller Snapshot dieser Browser-Sitzung erstellt werden.",
  invalidImage: "Das Runtime gab für diese Browser-Sitzung kein gültiges Bild zurück.",
  snapshotMetadata: "Browser-Snapshot und Metadaten",
  preparingAttach: "Browser-Attach wird vorbereitet...",
  snapshotActive: "Browser-Snapshot aktiv",
  snapshotClosed: "Browser-Snapshot geschlossen",
  snapshotFailure: "Der Browser-Snapshot-Kanal ist fehlgeschlagen.",
  liveConnected: "Live-Browser verbunden",
  liveDisconnected: "Live-Browser getrennt",
  noVncFallback: "Browser ohne noVNC; nur Snapshot und Metadaten werden angezeigt",
  openFailure: "Live-Browser konnte nicht geöffnet werden",
  title: "Browser",
  visualSessionUnavailable: "Visuelle Sitzung nicht verfügbar",
  noGraphicsTransport: "Live-Browser ohne grafischen Transport",
  noVncDescription:
    "Das Runtime hat ohne noVNC geantwortet. Wenn eine Seite im Browser aktiv ist, zeigt das Dashboard hier regelmäßige Snapshots an.",
  missingBinaries: "Fehlende Binärdateien",
  activeSnapshot: "Aktiver Snapshot",
  noVisualSurface: "Keine visuelle Oberfläche verfügbar",
  sessionGone:
    "Die visuelle Browser-Sitzung ist in dieser Runtime-Instanz nicht mehr aktiv. Die Umgebung wurde erhalten, aber der Browser im Speicher hat den Bot-Neustart nicht überlebt.",
  noScreenshot: "Das Runtime ist verbunden, aber derzeit ist kein Screenshot für diese Sitzung verfügbar.",
  noVisualForSession: "Für diese Sitzung ist keine visuelle Oberfläche verfügbar.",
};

mutableResources["de-DE"].translation.runtime.attach = {
  terminalTimeout:
    "Der Terminal-Attach hat länger als erwartet gedauert; die Log-Vorschau wird angezeigt, während die Umgebung antwortet.",
  browserTimeout:
    "Der Browser-Attach hat länger als erwartet gedauert; Snapshot und Metadaten werden angezeigt, während das Runtime antwortet.",
  terminalPreviewFallback: "Anhängen an das Terminal fehlgeschlagen; Log-Vorschau wird angezeigt.",
  browserSnapshotFallback: "Anhängen an den Browser fehlgeschlagen; Snapshot wird angezeigt.",
};

mutableResources["en-US"].translation.runtime.room = {
  executionLive: "Live execution",
  stats: {
    state: "State",
    phase: "Phase",
    cpu: "CPU",
    memory: "Memory",
    now: "Now",
    noHeartbeat: "no heartbeat",
  },
  tabs: {
    terminal: "Terminal",
    browser: "Browser",
    files: "Files",
    activity: "Activity",
  },
  detailTabs: {
    details: "Details",
    logs: "Logs",
    diagnostics: "Diagnostics",
  },
  openErrorTitle: "Could not open the execution",
  openErrorDescription: "The task did not respond to the bot runtime.",
  trackingLabel: "Execution tracking",
  switchSurface: "Switch surface",
  pause: "Pause",
  resume: "Resume",
  saveSnapshot: "Save snapshot",
  cancelExecution: "Cancel execution",
  cancelExecutionConfirm: "Cancel this execution now?",
  more: "More",
  refresh: "Refresh",
  retry: "Retry",
  recover: "Recover",
  pin: "Pin",
  unpin: "Unpin",
  requestCleanup: "Request cleanup",
  requestCleanupConfirm: "Schedule cleanup for this environment?",
  forceCleanup: "Force cleanup",
  forceCleanupConfirm: "Force cleanup may remove the environment immediately. Continue?",
  details: "Details",
  history: "History",
  closeDetails: "Close details",
  closeDetailsPanel: "Close details panel",
  detailTabsAria: "Detail tabs",
  warnings: "Warnings",
  events: "Events",
  services: "Services",
  checkpointsAndArtifacts: "Checkpoints & artifacts",
  sessions: "Sessions",
  recentGuardrails: "Recent guardrails",
  workspace: "Workspace",
  runtimeDir: "Runtime dir",
  gitStatus: "Git status",
  diff: "Diff",
  noStatus: "No status",
  noDiff: "No diff",
  noMovementYet: "No movement appeared yet.",
  noEvents: "No events recorded.",
  noActiveServices: "No active service.",
  latestCheckpoint: "Latest checkpoint",
  noRecentGuardrails: "No recent guardrail.",
  attach: "Attach",
  terminals: "Terminals",
  branch: "Branch",
  retention: "Retention",
  processes: "Processes",
  disk: "Disk",
  loops: "Loops",
  guardrails: "Guardrails",
  taskRoomBack: "Back to runtime",
  eventFallback: "event",
  eventRecordedNow: "now",
  phasePreview: "Phase {{value}}.",
  environmentUpdateRecorded: "Runtime environment update recorded.",
  completed: "{{label}} completed.",
};

mutableResources["pt-BR"].translation.runtime.room = {
  executionLive: "Execução ao vivo",
  stats: {
    state: "Estado",
    phase: "Etapa",
    cpu: "CPU",
    memory: "Memória",
    now: "Agora",
    noHeartbeat: "sem pulso",
  },
  tabs: {
    terminal: "Terminal",
    browser: "Navegador",
    files: "Arquivos",
    activity: "Atividade",
  },
  detailTabs: {
    details: "Detalhes",
    logs: "Logs",
    diagnostics: "Diagnóstico",
  },
  openErrorTitle: "Não foi possível abrir a execução",
  openErrorDescription: "A tarefa não respondeu ao runtime do bot.",
  trackingLabel: "Acompanhamento da execução",
  switchSurface: "Alternar superfície",
  pause: "Pausar",
  resume: "Retomar",
  saveSnapshot: "Salvar snapshot",
  cancelExecution: "Cancelar execução",
  cancelExecutionConfirm: "Cancelar esta execução agora?",
  more: "Mais",
  refresh: "Atualizar",
  retry: "Retentar",
  recover: "Recuperar",
  pin: "Fixar",
  unpin: "Desafixar",
  requestCleanup: "Solicitar cleanup",
  requestCleanupConfirm: "Agendar cleanup deste ambiente?",
  forceCleanup: "Forçar cleanup",
  forceCleanupConfirm: "Forçar cleanup pode remover o ambiente imediatamente. Continuar?",
  details: "Detalhes",
  history: "Histórico",
  closeDetails: "Fechar detalhes",
  closeDetailsPanel: "Fechar painel de detalhes",
  detailTabsAria: "Abas de detalhes",
  warnings: "Avisos",
  events: "Eventos",
  services: "Serviços",
  checkpointsAndArtifacts: "Checkpoints e artefatos",
  sessions: "Sessões",
  recentGuardrails: "Guardrails recentes",
  workspace: "Espaço de trabalho",
  runtimeDir: "Diretório do runtime",
  gitStatus: "Status do Git",
  diff: "Diff",
  noStatus: "Sem status",
  noDiff: "Sem diff",
  noMovementYet: "Nenhum movimento apareceu ainda.",
  noEvents: "Sem eventos registrados.",
  noActiveServices: "Nenhum serviço ativo.",
  latestCheckpoint: "Último checkpoint",
  noRecentGuardrails: "Nenhum guardrail recente.",
  attach: "Anexar",
  terminals: "Terminais",
  branch: "Branch",
  retention: "Retenção",
  processes: "Processos",
  disk: "Disco",
  loops: "Loops",
  guardrails: "Guardrails",
  taskRoomBack: "Voltar ao runtime",
  eventFallback: "evento",
  eventRecordedNow: "agora",
  phasePreview: "Etapa {{value}}.",
  environmentUpdateRecorded: "Atualização do ambiente registrada pelo runtime.",
  completed: "{{label}} concluído.",
};

mutableResources["fr-FR"].translation.runtime.room = {
  executionLive: "Exécution en direct",
  stats: {
    state: "État",
    phase: "Phase",
    cpu: "CPU",
    memory: "Mémoire",
    now: "Maintenant",
    noHeartbeat: "aucun heartbeat",
  },
  tabs: {
    terminal: "Terminal",
    browser: "Navigateur",
    files: "Fichiers",
    activity: "Activité",
  },
  detailTabs: {
    details: "Détails",
    logs: "Journaux",
    diagnostics: "Diagnostics",
  },
  openErrorTitle: "Impossible d'ouvrir l'exécution",
  openErrorDescription: "La tâche n'a pas répondu au runtime du bot.",
  trackingLabel: "Suivi de l'exécution",
  switchSurface: "Changer de surface",
  pause: "Mettre en pause",
  resume: "Reprendre",
  saveSnapshot: "Enregistrer le snapshot",
  cancelExecution: "Annuler l'exécution",
  cancelExecutionConfirm: "Annuler cette exécution maintenant ?",
  more: "Plus",
  refresh: "Actualiser",
  retry: "Réessayer",
  recover: "Récupérer",
  pin: "Épingler",
  unpin: "Désépingler",
  requestCleanup: "Demander le nettoyage",
  requestCleanupConfirm: "Planifier le nettoyage de cet environnement ?",
  forceCleanup: "Forcer le nettoyage",
  forceCleanupConfirm: "Forcer le nettoyage peut supprimer immédiatement l'environnement. Continuer ?",
  details: "Détails",
  history: "Historique",
  closeDetails: "Fermer les détails",
  closeDetailsPanel: "Fermer le panneau de détails",
  detailTabsAria: "Onglets de détails",
  warnings: "Avertissements",
  events: "Événements",
  services: "Services",
  checkpointsAndArtifacts: "Checkpoints et artefacts",
  sessions: "Sessions",
  recentGuardrails: "Garde-fous récents",
  workspace: "Espace de travail",
  runtimeDir: "Répertoire runtime",
  gitStatus: "Statut Git",
  diff: "Diff",
  noStatus: "Aucun statut",
  noDiff: "Aucun diff",
  noMovementYet: "Aucun mouvement n'est encore apparu.",
  noEvents: "Aucun événement enregistré.",
  noActiveServices: "Aucun service actif.",
  latestCheckpoint: "Dernier checkpoint",
  noRecentGuardrails: "Aucun garde-fou récent.",
  attach: "Attacher",
  terminals: "Terminaux",
  branch: "Branche",
  retention: "Rétention",
  processes: "Processus",
  disk: "Disque",
  loops: "Boucles",
  guardrails: "Garde-fous",
  taskRoomBack: "Retour au runtime",
  eventFallback: "événement",
  eventRecordedNow: "maintenant",
  phasePreview: "Phase {{value}}.",
  environmentUpdateRecorded: "Mise à jour de l'environnement runtime enregistrée.",
  completed: "{{label}} terminé.",
};

mutableResources["de-DE"].translation.runtime.room = {
  executionLive: "Live-Ausführung",
  stats: {
    state: "Zustand",
    phase: "Phase",
    cpu: "CPU",
    memory: "Speicher",
    now: "Jetzt",
    noHeartbeat: "kein Heartbeat",
  },
  tabs: {
    terminal: "Terminal",
    browser: "Browser",
    files: "Dateien",
    activity: "Aktivität",
  },
  detailTabs: {
    details: "Details",
    logs: "Protokolle",
    diagnostics: "Diagnose",
  },
  openErrorTitle: "Ausführung konnte nicht geöffnet werden",
  openErrorDescription: "Die Aufgabe hat nicht auf das Bot-Runtime reagiert.",
  trackingLabel: "Ausführungsverfolgung",
  switchSurface: "Oberfläche wechseln",
  pause: "Pausieren",
  resume: "Fortsetzen",
  saveSnapshot: "Snapshot speichern",
  cancelExecution: "Ausführung abbrechen",
  cancelExecutionConfirm: "Diese Ausführung jetzt abbrechen?",
  more: "Mehr",
  refresh: "Aktualisieren",
  retry: "Erneut versuchen",
  recover: "Wiederherstellen",
  pin: "Anheften",
  unpin: "Lösen",
  requestCleanup: "Bereinigung anfordern",
  requestCleanupConfirm: "Bereinigung für diese Umgebung planen?",
  forceCleanup: "Bereinigung erzwingen",
  forceCleanupConfirm: "Die erzwungene Bereinigung kann die Umgebung sofort entfernen. Fortfahren?",
  details: "Details",
  history: "Verlauf",
  closeDetails: "Details schließen",
  closeDetailsPanel: "Detailpanel schließen",
  detailTabsAria: "Detail-Tabs",
  warnings: "Warnungen",
  events: "Ereignisse",
  services: "Dienste",
  checkpointsAndArtifacts: "Checkpoints & Artefakte",
  sessions: "Sitzungen",
  recentGuardrails: "Aktuelle Guardrails",
  workspace: "Arbeitsbereich",
  runtimeDir: "Runtime-Verzeichnis",
  gitStatus: "Git-Status",
  diff: "Diff",
  noStatus: "Kein Status",
  noDiff: "Kein Diff",
  noMovementYet: "Noch keine Bewegung erkennbar.",
  noEvents: "Keine Ereignisse erfasst.",
  noActiveServices: "Kein aktiver Dienst.",
  latestCheckpoint: "Aktuellster Checkpoint",
  noRecentGuardrails: "Keine aktuellen Guardrails.",
  attach: "Anhängen",
  terminals: "Terminals",
  branch: "Branch",
  retention: "Aufbewahrung",
  processes: "Prozesse",
  disk: "Festplatte",
  loops: "Schleifen",
  guardrails: "Guardrails",
  taskRoomBack: "Zurück zum Runtime",
  eventFallback: "Ereignis",
  eventRecordedNow: "jetzt",
  phasePreview: "Phase {{value}}.",
  environmentUpdateRecorded: "Runtime-Umgebungsupdate erfasst.",
  completed: "{{label}} abgeschlossen.",
};

mutableResources["es-ES"].translation.runtime.room = {
  executionLive: "Ejecución en vivo",
  stats: {
    state: "Estado",
    phase: "Fase",
    cpu: "CPU",
    memory: "Memoria",
    now: "Ahora",
    noHeartbeat: "sin latido",
  },
  tabs: {
    terminal: "Terminal",
    browser: "Navegador",
    files: "Archivos",
    activity: "Actividad",
  },
  detailTabs: {
    details: "Detalles",
    logs: "Logs",
    diagnostics: "Diagnóstico",
  },
  openErrorTitle: "No fue posible abrir la ejecución",
  openErrorDescription: "La tarea no respondió al runtime del bot.",
  trackingLabel: "Seguimiento de la ejecución",
  switchSurface: "Cambiar superficie",
  pause: "Pausar",
  resume: "Reanudar",
  saveSnapshot: "Guardar snapshot",
  cancelExecution: "Cancelar ejecución",
  cancelExecutionConfirm: "¿Cancelar esta ejecución ahora?",
  more: "Más",
  refresh: "Actualizar",
  retry: "Reintentar",
  recover: "Recuperar",
  pin: "Fijar",
  unpin: "Desfijar",
  requestCleanup: "Solicitar cleanup",
  requestCleanupConfirm: "¿Programar cleanup de este entorno?",
  forceCleanup: "Forzar cleanup",
  forceCleanupConfirm: "Forzar cleanup puede eliminar el entorno inmediatamente. ¿Continuar?",
  details: "Detalles",
  history: "Historial",
  closeDetails: "Cerrar detalles",
  closeDetailsPanel: "Cerrar panel de detalles",
  detailTabsAria: "Pestañas de detalles",
  warnings: "Avisos",
  events: "Eventos",
  services: "Servicios",
  checkpointsAndArtifacts: "Checkpoints y artefactos",
  sessions: "Sesiones",
  recentGuardrails: "Guardrails recientes",
  workspace: "Espacio de trabajo",
  runtimeDir: "Directorio del runtime",
  gitStatus: "Estado de Git",
  diff: "Diff",
  noStatus: "Sin estado",
  noDiff: "Sin diff",
  noMovementYet: "Aún no apareció ningún movimiento.",
  noEvents: "Sin eventos registrados.",
  noActiveServices: "Ningún servicio activo.",
  latestCheckpoint: "Último checkpoint",
  noRecentGuardrails: "Ningún guardrail reciente.",
  attach: "Adjuntar",
  terminals: "Terminales",
  branch: "Branch",
  retention: "Retención",
  processes: "Procesos",
  disk: "Disco",
  loops: "Loops",
  guardrails: "Guardrails",
  taskRoomBack: "Volver al runtime",
  eventFallback: "evento",
  eventRecordedNow: "ahora",
  phasePreview: "Fase {{value}}.",
  environmentUpdateRecorded: "Actualización del entorno registrada por el runtime.",
  completed: "{{label}} completado.",
};

mutableResources["en-US"].translation.runtime.files = {
  discardUnsaved: "Discard unsaved changes?",
  saveFailure: "Save failed",
  deleteFileConfirm: 'Delete "{{path}}"?',
  folder: "folder",
  file: "file",
  collapseSidebar: "Collapse sidebar",
  expandSidebar: "Expand sidebar",
  new: "New",
  createPathPlaceholder: "path/file-name.ext",
  createFile: "Create",
  noVisibleFiles: "No visible files here.",
  loadingFile: "Loading file...",
  sourceCode: "Source code",
  deleteFile: "Delete file",
  searchPlaceholder: "Search...",
  truncatedFile: "Truncated file — editing disabled.",
  binaryFile: "Binary file — preview not available.",
  openFileToView: "Open a file to see its contents.",
};

mutableResources["pt-BR"].translation.runtime.files = {
  discardUnsaved: "Descartar alterações não salvas?",
  saveFailure: "Falha ao salvar",
  deleteFileConfirm: 'Deletar "{{path}}"?',
  folder: "pasta",
  file: "arquivo",
  collapseSidebar: "Colapsar sidebar",
  expandSidebar: "Expandir sidebar",
  new: "Novo",
  createPathPlaceholder: "caminho/nome-do-arquivo.ext",
  createFile: "Criar",
  noVisibleFiles: "Sem arquivos visíveis aqui.",
  loadingFile: "Carregando arquivo...",
  sourceCode: "Código fonte",
  deleteFile: "Deletar arquivo",
  searchPlaceholder: "Buscar...",
  truncatedFile: "Arquivo truncado — edição desabilitada.",
  binaryFile: "Arquivo binário — visualização não disponível.",
  openFileToView: "Abra um arquivo para ver o conteúdo.",
};

mutableResources["es-ES"].translation.runtime.files = {
  discardUnsaved: "¿Descartar cambios no guardados?",
  saveFailure: "Falló al guardar",
  deleteFileConfirm: '¿Eliminar "{{path}}"?',
  folder: "carpeta",
  file: "archivo",
  collapseSidebar: "Colapsar sidebar",
  expandSidebar: "Expandir sidebar",
  new: "Nuevo",
  createPathPlaceholder: "ruta/nombre-del-archivo.ext",
  createFile: "Crear",
  noVisibleFiles: "No hay archivos visibles aquí.",
  loadingFile: "Cargando archivo...",
  sourceCode: "Código fuente",
  deleteFile: "Eliminar archivo",
  searchPlaceholder: "Buscar...",
  truncatedFile: "Archivo truncado: edición deshabilitada.",
  binaryFile: "Archivo binario: vista previa no disponible.",
  openFileToView: "Abre un archivo para ver su contenido.",
};

mutableResources["fr-FR"].translation.runtime.files = {
  discardUnsaved: "Rejeter les modifications non enregistrées ?",
  saveFailure: "Échec de l'enregistrement",
  deleteFileConfirm: 'Supprimer "{{path}}" ?',
  folder: "dossier",
  file: "fichier",
  collapseSidebar: "Réduire la barre latérale",
  expandSidebar: "Étendre la barre latérale",
  new: "Nouveau",
  createPathPlaceholder: "chemin/nom-du-fichier.ext",
  createFile: "Créer",
  noVisibleFiles: "Aucun fichier visible ici.",
  loadingFile: "Chargement du fichier...",
  sourceCode: "Code source",
  deleteFile: "Supprimer le fichier",
  searchPlaceholder: "Rechercher...",
  truncatedFile: "Fichier tronqué — édition désactivée.",
  binaryFile: "Fichier binaire — aperçu indisponible.",
  openFileToView: "Ouvrez un fichier pour voir son contenu.",
};

mutableResources["de-DE"].translation.runtime.files = {
  discardUnsaved: "Nicht gespeicherte Änderungen verwerfen?",
  saveFailure: "Speichern fehlgeschlagen",
  deleteFileConfirm: '"{{path}}" löschen?',
  folder: "Ordner",
  file: "Datei",
  collapseSidebar: "Seitenleiste einklappen",
  expandSidebar: "Seitenleiste erweitern",
  new: "Neu",
  createPathPlaceholder: "pfad/dateiname.ext",
  createFile: "Erstellen",
  noVisibleFiles: "Keine sichtbaren Dateien hier.",
  loadingFile: "Datei wird geladen...",
  sourceCode: "Quellcode",
  deleteFile: "Datei löschen",
  searchPlaceholder: "Suchen...",
  truncatedFile: "Gekürzte Datei — Bearbeitung deaktiviert.",
  binaryFile: "Binärdatei — Vorschau nicht verfügbar.",
  openFileToView: "Öffnen Sie eine Datei, um den Inhalt zu sehen.",
};

mutableResources["en-US"].translation.toast = {
  success: "Success",
  error: "Failed",
  warning: "Warning",
  info: "Information",
  loading: "Processing",
};

mutableResources["pt-BR"].translation.toast = {
  success: "Sucesso",
  error: "Falha",
  warning: "Atenção",
  info: "Informação",
  loading: "Processando",
};

mutableResources["es-ES"].translation.toast = {
  success: "Éxito",
  error: "Fallo",
  warning: "Atención",
  info: "Información",
  loading: "Procesando",
};

mutableResources["fr-FR"].translation.toast = {
  success: "Succès",
  error: "Échec",
  warning: "Avertissement",
  info: "Information",
  loading: "Traitement",
};

mutableResources["de-DE"].translation.toast = {
  success: "Erfolg",
  error: "Fehlgeschlagen",
  warning: "Warnung",
  info: "Information",
  loading: "Verarbeitung",
};

mutableResources["en-US"].translation.controlPlane = {
  unavailable: {
    title: "Control Plane unavailable",
    pageTitle: "Could not load Control Plane",
    description:
      "Check whether the control plane API is active and whether the dashboard can reach the configured endpoint before trying again.",
    retry: "Try again",
  },
  shared: {
    saveBar: {
      saved: "Saved successfully",
      unsaved: "Unsaved changes",
      discard: "Discard",
      saving: "Saving",
    },
    confirmation: {
      confirm: "Confirm",
    },
  },
  system: {
    loadTitle: "Failed to load system settings",
    loadDescription: "Could not load global system settings.",
  },
  agent: {
    loadTitle: "Failed to load {{agentId}}",
    loadDescription: "Could not load the configuration for bot {{agentId}}.",
  },
};

mutableResources["pt-BR"].translation.controlPlane = {
  unavailable: {
    title: "Control Plane indisponível",
    pageTitle: "Não foi possível carregar o Control Plane",
    description:
      "Verifique se a API do control plane está ativa e se o dashboard consegue acessar o endpoint configurado antes de tentar novamente.",
    retry: "Tentar novamente",
  },
  shared: {
    saveBar: {
      saved: "Salvo com sucesso",
      unsaved: "Alterações não salvas",
      discard: "Descartar",
      saving: "Salvando",
    },
    confirmation: {
      confirm: "Confirmar",
    },
  },
  system: {
    loadTitle: "Falha ao carregar configurações do sistema",
    loadDescription: "Não foi possível carregar as configurações globais do sistema.",
  },
  agent: {
    loadTitle: "Falha ao carregar {{agentId}}",
    loadDescription: "Não foi possível carregar a configuração do bot {{agentId}}.",
  },
};

mutableResources["es-ES"].translation.controlPlane = {
  unavailable: {
    title: "Control Plane no disponible",
    pageTitle: "No fue posible cargar el Control Plane",
    description:
      "Verifica si la API del control plane está activa y si el dashboard puede acceder al endpoint configurado antes de volver a intentarlo.",
    retry: "Reintentar",
  },
  shared: {
    saveBar: {
      saved: "Guardado correctamente",
      unsaved: "Cambios no guardados",
      discard: "Descartar",
      saving: "Guardando",
    },
    confirmation: {
      confirm: "Confirmar",
    },
  },
  system: {
    loadTitle: "Error al cargar la configuración del sistema",
    loadDescription: "No fue posible cargar la configuración global del sistema.",
  },
  agent: {
    loadTitle: "Error al cargar {{agentId}}",
    loadDescription: "No fue posible cargar la configuración del bot {{agentId}}.",
  },
};

mutableResources["fr-FR"].translation.controlPlane = {
  unavailable: {
    title: "Plan de contrôle indisponible",
    pageTitle: "Impossible de charger le plan de contrôle",
    description:
      "Vérifiez si l'API du plan de contrôle est active et si le tableau de bord peut joindre le point d'accès configuré avant de réessayer.",
    retry: "Réessayer",
  },
  shared: {
    saveBar: {
      saved: "Enregistré avec succès",
      unsaved: "Modifications non enregistrées",
      discard: "Rejeter",
      saving: "Enregistrement",
    },
    confirmation: {
      confirm: "Confirmer",
    },
  },
  system: {
    loadTitle: "Échec du chargement des paramètres système",
    loadDescription: "Impossible de charger les paramètres système globaux.",
  },
  agent: {
    loadTitle: "Échec du chargement de {{agentId}}",
    loadDescription: "Impossible de charger la configuration du bot {{agentId}}.",
  },
};

mutableResources["de-DE"].translation.controlPlane = {
  unavailable: {
    title: "Steuerungsebene nicht verfügbar",
    pageTitle: "Steuerungsebene konnte nicht geladen werden",
    description:
      "Prüfen Sie, ob die API der Steuerungsebene aktiv ist und ob das Dashboard den konfigurierten Endpunkt erreichen kann, bevor Sie es erneut versuchen.",
    retry: "Erneut versuchen",
  },
  shared: {
    saveBar: {
      saved: "Erfolgreich gespeichert",
      unsaved: "Nicht gespeicherte Änderungen",
      discard: "Verwerfen",
      saving: "Speichern",
    },
    confirmation: {
      confirm: "Bestätigen",
    },
  },
  system: {
    loadTitle: "Systemeinstellungen konnten nicht geladen werden",
    loadDescription: "Globale Systemeinstellungen konnten nicht geladen werden.",
  },
  agent: {
    loadTitle: "{{agentId}} konnte nicht geladen werden",
    loadDescription: "Konfiguration für Bot {{agentId}} konnte nicht geladen werden.",
  },
};

mutableResources["pt-BR"].translation.runtime.controlCard = {
  eyebrow: "Runtime",
  title: "Control plane ao vivo",
  description: "Ambientes, backlog de recovery e atalhos diretos para as salas operacionais.",
  openRuntime: "Abrir runtime",
  active: "Ativos",
  retained: "Retidos",
  incidents: "Incidentes",
  loading: "Carregando runtime dos bots visíveis...",
  empty: "Nenhuma task operacional foi publicada no runtime atual.",
  live: "Ao vivo",
  backlogNotice:
    "Há backlog de cleanup/recovery em pelo menos um bot visível. A página Runtime mostra o estado completo e permite agir sem sair do fluxo.",
};

mutableResources["es-ES"].translation.runtime.controlCard = {
  eyebrow: "Runtime",
  title: "Control plane en vivo",
  description: "Entornos, backlog de recovery y atajos directos a las salas operativas.",
  openRuntime: "Abrir runtime",
  active: "Activos",
  retained: "Retenidos",
  incidents: "Incidentes",
  loading: "Cargando runtime de los bots visibles...",
  empty: "No se publicó ninguna tarea operativa en el runtime actual.",
  live: "En vivo",
  backlogNotice:
    "Hay backlog de cleanup/recovery en al menos un bot visible. La página Runtime muestra el estado completo y permite actuar sin salir del flujo.",
};

mutableResources["fr-FR"].translation.runtime.controlCard = {
  eyebrow: "Runtime",
  title: "Plan de contrôle en direct",
  description: "Environnements, backlog de récupération et raccourcis directs vers les salles opérationnelles.",
  openRuntime: "Ouvrir le runtime",
  active: "Actifs",
  retained: "Conservés",
  incidents: "Incidents",
  loading: "Chargement du runtime pour les bots visibles...",
  empty: "Aucune tâche opérationnelle publiée dans le runtime actuel.",
  live: "En direct",
  backlogNotice:
    "Il existe un backlog de cleanup/recovery sur au moins un bot visible. La page Runtime affiche l'état complet et vous permet d'agir sans quitter le flux.",
};

mutableResources["de-DE"].translation.runtime.controlCard = {
  eyebrow: "Laufzeit",
  title: "Live-Steuerungsebene",
  description: "Umgebungen, Recovery-Backlog und direkte Verknüpfungen zu den operativen Räumen.",
  openRuntime: "Laufzeit öffnen",
  active: "Aktiv",
  retained: "Aufbewahrt",
  incidents: "Vorfälle",
  loading: "Laufzeit für sichtbare Bots wird geladen...",
  empty: "In der aktuellen Laufzeit wurde keine operative Aufgabe veröffentlicht.",
  live: "Live",
  backlogNotice:
    "In mindestens einem sichtbaren Bot gibt es Cleanup-/Recovery-Backlog. Die Laufzeit-Seite zeigt den vollständigen Status und ermöglicht Handlungen ohne den Fluss zu verlassen.",
};

mutableResources["en-US"].translation.tasks = {
  table: {
    headers: {
      task: "Task",
      status: "Status",
      query: "Query",
      cost: "Cost",
      duration: "Duration",
      attempts: "Attempts",
      created: "Created",
    },
    chat: "Chat {{value}}",
    noDescription: "No description",
    noModel: "no model",
    session: "Session {{value}}",
    noTasksFound: "No task found.",
    adjustFilters: "Adjust the filters or wait for new executions to see activity.",
    futureActivity: "When new executions are registered, they will appear here in chronological order.",
  },
  detail: {
    dialogTitle: "Task details {{id}}",
    close: "Close task details",
    taskEyebrow: "Task #{{id}}",
    executionFallback: "Execution {{id}}",
    copyQuery: "Copy query",
    failure: "Failure",
  },
};

mutableResources["pt-BR"].translation.tasks = {
  table: {
    headers: {
      task: "Tarefa",
      status: "Status",
      query: "Consulta",
      cost: "Custo",
      duration: "Duração",
      attempts: "Tentativas",
      created: "Criada",
    },
    chat: "Chat {{value}}",
    noDescription: "Sem descrição",
    noModel: "sem modelo",
    session: "Sessão {{value}}",
    noTasksFound: "Nenhuma tarefa encontrada.",
    adjustFilters: "Ajuste os filtros ou aguarde novas execuções para visualizar atividade.",
    futureActivity: "Quando novas execuções forem registradas, elas aparecerão aqui em ordem cronológica.",
  },
  detail: {
    dialogTitle: "Detalhes da tarefa {{id}}",
    close: "Fechar detalhes da tarefa",
    taskEyebrow: "Tarefa #{{id}}",
    executionFallback: "Execução {{id}}",
    copyQuery: "Copiar consulta",
    failure: "Falha",
  },
};

mutableResources["es-ES"].translation.tasks = {
  table: {
    headers: {
      task: "Tarea",
      status: "Estado",
      query: "Consulta",
      cost: "Costo",
      duration: "Duración",
      attempts: "Intentos",
      created: "Creada",
    },
    chat: "Chat {{value}}",
    noDescription: "Sin descripción",
    noModel: "sin modelo",
    session: "Sesión {{value}}",
    noTasksFound: "No se encontró ninguna tarea.",
    adjustFilters: "Ajusta los filtros o espera nuevas ejecuciones para ver actividad.",
    futureActivity: "Cuando se registren nuevas ejecuciones, aparecerán aquí en orden cronológico.",
  },
  detail: {
    dialogTitle: "Detalles de la tarea {{id}}",
    close: "Cerrar detalles de la tarea",
    taskEyebrow: "Tarea #{{id}}",
    executionFallback: "Ejecución {{id}}",
    copyQuery: "Copiar consulta",
    failure: "Fallo",
  },
};

mutableResources["fr-FR"].translation.tasks = {
  table: {
    headers: {
      task: "Tâche",
      status: "Statut",
      query: "Requête",
      cost: "Coût",
      duration: "Durée",
      attempts: "Tentatives",
      created: "Créée",
    },
    chat: "Discussion {{value}}",
    noDescription: "Aucune description",
    noModel: "aucun modèle",
    session: "Session {{value}}",
    noTasksFound: "Aucune tâche trouvée.",
    adjustFilters: "Ajustez les filtres ou attendez de nouvelles exécutions pour voir l'activité.",
    futureActivity: "Lorsque de nouvelles exécutions seront enregistrées, elles apparaîtront ici par ordre chronologique.",
  },
  detail: {
    dialogTitle: "Détails de la tâche {{id}}",
    close: "Fermer les détails de la tâche",
    taskEyebrow: "Tâche #{{id}}",
    executionFallback: "Exécution {{id}}",
    copyQuery: "Copier la requête",
    failure: "Échec",
  },
};

mutableResources["de-DE"].translation.tasks = {
  table: {
    headers: {
      task: "Aufgabe",
      status: "Status",
      query: "Abfrage",
      cost: "Kosten",
      duration: "Dauer",
      attempts: "Versuche",
      created: "Erstellt",
    },
    chat: "Chat {{value}}",
    noDescription: "Keine Beschreibung",
    noModel: "kein Modell",
    session: "Sitzung {{value}}",
    noTasksFound: "Keine Aufgabe gefunden.",
    adjustFilters: "Passen Sie die Filter an oder warten Sie auf neue Ausführungen, um Aktivität zu sehen.",
    futureActivity: "Sobald neue Ausführungen erfasst werden, erscheinen sie hier in chronologischer Reihenfolge.",
  },
  detail: {
    dialogTitle: "Aufgabendetails {{id}}",
    close: "Aufgabendetails schließen",
    taskEyebrow: "Aufgabe #{{id}}",
    executionFallback: "Ausführung {{id}}",
    copyQuery: "Abfrage kopieren",
    failure: "Fehler",
  },
};

mutableResources["en-US"].translation.audit = {
  table: {
    dateTime: "Date & time",
    event: "Event",
    context: "Context",
    record: "Record #{{id}}",
    noDetails: "No additional details",
    noEntries: "No audit entry found.",
    noEntriesDescription: "Technical events will appear here as soon as new traces are emitted.",
    noEntriesMobileDescription: "When new technical events are emitted, they will appear here.",
    tool: "Tool {{value}}",
    model: "Model {{value}}",
    success: "successful execution",
    failure: "failed execution",
    attempt: "attempt {{value}}",
    task: "Task {{value}}",
    trace: "Trace {{value}}",
  },
  detail: {
    dialogTitle: "Event details {{id}}",
    close: "Close event details",
    eventTitle: "Event #{{id}}",
    eventDate: "Event date",
    traceability: "Traceability",
    copyJson: "Copy JSON",
  },
};

mutableResources["pt-BR"].translation.audit = {
  table: {
    dateTime: "Data e hora",
    event: "Evento",
    context: "Contexto",
    record: "Registro #{{id}}",
    noDetails: "Sem detalhes adicionais",
    noEntries: "Nenhum registro de auditoria encontrado.",
    noEntriesDescription: "Eventos técnicos aparecerão aqui assim que novos rastros forem emitidos.",
    noEntriesMobileDescription: "Quando novos eventos técnicos forem emitidos, eles aparecerão aqui.",
    tool: "Ferramenta {{value}}",
    model: "Modelo {{value}}",
    success: "execução bem-sucedida",
    failure: "execução com falha",
    attempt: "tentativa {{value}}",
    task: "Task {{value}}",
    trace: "Trace {{value}}",
  },
  detail: {
    dialogTitle: "Detalhes do evento {{id}}",
    close: "Fechar detalhes do evento",
    eventTitle: "Evento #{{id}}",
    eventDate: "Data do evento",
    traceability: "Rastreabilidade",
    copyJson: "Copiar JSON",
  },
};

mutableResources["es-ES"].translation.audit = {
  table: {
    dateTime: "Fecha y hora",
    event: "Evento",
    context: "Contexto",
    record: "Registro #{{id}}",
    noDetails: "Sin detalles adicionales",
    noEntries: "No se encontró ningún registro de auditoría.",
    noEntriesDescription: "Los eventos técnicos aparecerán aquí tan pronto se emitan nuevos rastros.",
    noEntriesMobileDescription: "Cuando se emitan nuevos eventos técnicos, aparecerán aquí.",
    tool: "Herramienta {{value}}",
    model: "Modelo {{value}}",
    success: "ejecución exitosa",
    failure: "ejecución con fallo",
    attempt: "intento {{value}}",
    task: "Tarea {{value}}",
    trace: "Trace {{value}}",
  },
  detail: {
    dialogTitle: "Detalles del evento {{id}}",
    close: "Cerrar detalles del evento",
    eventTitle: "Evento #{{id}}",
    eventDate: "Fecha del evento",
    traceability: "Trazabilidad",
    copyJson: "Copiar JSON",
  },
};

mutableResources["fr-FR"].translation.audit = {
  table: {
    dateTime: "Date et heure",
    event: "Événement",
    context: "Contexte",
    record: "Enregistrement #{{id}}",
    noDetails: "Aucun détail supplémentaire",
    noEntries: "Aucun enregistrement d'audit trouvé.",
    noEntriesDescription: "Les événements techniques apparaîtront ici dès que de nouvelles traces seront émises.",
    noEntriesMobileDescription: "Lorsque de nouveaux événements techniques seront émis, ils apparaîtront ici.",
    tool: "Outil {{value}}",
    model: "Modèle {{value}}",
    success: "exécution réussie",
    failure: "exécution échouée",
    attempt: "tentative {{value}}",
    task: "Tâche {{value}}",
    trace: "Trace {{value}}",
  },
  detail: {
    dialogTitle: "Détails de l'événement {{id}}",
    close: "Fermer les détails de l'événement",
    eventTitle: "Événement #{{id}}",
    eventDate: "Date de l'événement",
    traceability: "Traçabilité",
    copyJson: "Copier le JSON",
  },
};

mutableResources["de-DE"].translation.audit = {
  table: {
    dateTime: "Datum und Uhrzeit",
    event: "Ereignis",
    context: "Kontext",
    record: "Datensatz #{{id}}",
    noDetails: "Keine zusätzlichen Details",
    noEntries: "Kein Audit-Eintrag gefunden.",
    noEntriesDescription: "Technische Ereignisse erscheinen hier, sobald neue Traces emittiert werden.",
    noEntriesMobileDescription: "Wenn neue technische Ereignisse emittiert werden, erscheinen sie hier.",
    tool: "Tool {{value}}",
    model: "Modell {{value}}",
    success: "erfolgreiche Ausführung",
    failure: "fehlgeschlagene Ausführung",
    attempt: "Versuch {{value}}",
    task: "Aufgabe {{value}}",
    trace: "Trace {{value}}",
  },
  detail: {
    dialogTitle: "Ereignisdetails {{id}}",
    close: "Ereignisdetails schließen",
    eventTitle: "Ereignis #{{id}}",
    eventDate: "Ereignisdatum",
    traceability: "Nachverfolgbarkeit",
    copyJson: "JSON kopieren",
  },
};

mutableResources["en-US"].translation.dlq.detail = {
  retryNow: "Can retry now",
  retriedAt: "Retried at {{value}}",
  noRetry: "No retry available",
  empty: "Waiting failure",
  dialogTitle: "DLQ entry details {{id}}",
  close: "Close failure diagnosis",
  originalQuery: "Original query",
  failure: "Failure",
  operationalContext: "Operational context",
  errorClass: "Error class",
  retryStatus: "Retry status",
  failedAt: "Failed at",
  rawPayload: "Raw payload",
  copyJson: "Copy JSON",
  emptyMetadata: "Empty",
};

mutableResources["pt-BR"].translation.dlq.detail = {
  retryNow: "Pode retentar agora",
  retriedAt: "Retentado em {{value}}",
  noRetry: "Sem retentativa disponível",
  empty: "Falha em espera",
  dialogTitle: "Detalhes da entrada DLQ {{id}}",
  close: "Fechar diagnóstico da falha",
  originalQuery: "Consulta original",
  failure: "Falha",
  operationalContext: "Contexto operacional",
  errorClass: "Classe do erro",
  retryStatus: "Status de retentativa",
  failedAt: "Falhou em",
  rawPayload: "Payload bruto",
  copyJson: "Copiar JSON",
  emptyMetadata: "Vazio",
};

mutableResources["es-ES"].translation.dlq.detail = {
  retryNow: "Se puede reintentar ahora",
  retriedAt: "Reintentado en {{value}}",
  noRetry: "Sin reintento disponible",
  empty: "Fallo en espera",
  dialogTitle: "Detalles de la entrada DLQ {{id}}",
  close: "Cerrar diagnóstico del fallo",
  originalQuery: "Consulta original",
  failure: "Fallo",
  operationalContext: "Contexto operacional",
  errorClass: "Clase del error",
  retryStatus: "Estado del reintento",
  failedAt: "Falló en",
  rawPayload: "Payload bruto",
  copyJson: "Copiar JSON",
  emptyMetadata: "Vacío",
};

mutableResources["fr-FR"].translation.dlq.detail = {
  retryNow: "Peut être réessayé maintenant",
  retriedAt: "Réessayé le {{value}}",
  noRetry: "Aucun réessai disponible",
  empty: "Échec en attente",
  dialogTitle: "Détails de l'entrée DLQ {{id}}",
  close: "Fermer le diagnostic de l'échec",
  originalQuery: "Requête d'origine",
  failure: "Échec",
  operationalContext: "Contexte opérationnel",
  errorClass: "Classe d'erreur",
  retryStatus: "Statut du réessai",
  failedAt: "Échoué le",
  rawPayload: "Payload brut",
  copyJson: "Copier le JSON",
  emptyMetadata: "Vide",
};

mutableResources["de-DE"].translation.dlq.detail = {
  retryNow: "Kann jetzt wiederholt werden",
  retriedAt: "Wiederholt am {{value}}",
  noRetry: "Keine Wiederholung verfügbar",
  empty: "Ausstehender Fehler",
  dialogTitle: "Details zum DLQ-Eintrag {{id}}",
  close: "Fehlerdiagnose schließen",
  originalQuery: "Ursprüngliche Abfrage",
  failure: "Fehler",
  operationalContext: "Operativer Kontext",
  errorClass: "Fehlerklasse",
  retryStatus: "Wiederholungsstatus",
  failedAt: "Fehlgeschlagen am",
  rawPayload: "Roh-Payload",
  copyJson: "JSON kopieren",
  emptyMetadata: "Leer",
};

mutableResources["en-US"].translation.executions.detail = {
  traceRich: "Rich trace",
  traceRichDescription: "Execution with full envelope, tools and structured artifacts.",
  reconstructed: "Reconstructed",
  reconstructedDescription: "Details rebuilt from tasks, queries and legacy audit log.",
  noTrace: "No trace",
  noTraceDescription: "Only basic metadata is available for this execution.",
  responseFromTrace: "Trace response",
  responseFallbackQueries: "Queries fallback",
  noResponse: "No response",
  structuredTools: "Structured tools",
  legacyTools: "Legacy tools",
  noTools: "No tools",
  loadErrorTitle: "Could not load execution details",
  failureRecorded: "Recorded failure",
  signals: "Signals",
  traceSource: "Trace source",
  responseSource: "Response source",
  toolsSource: "Tools source",
  stopReason: "Stop reason",
  notProvided: "not provided",
  runtime: "Runtime",
  openRuntimeRoom: "Open operational room",
  input: "Input",
  output: "Output",
  response: "Response",
  steps: "Steps",
  activity: "Activity",
  notes: "Notes",
  files: "Files",
};

mutableResources["pt-BR"].translation.executions.detail = {
  traceRich: "Trace rico",
  traceRichDescription: "Execução com envelope completo, ferramentas e artefatos estruturados.",
  reconstructed: "Reconstruído",
  reconstructedDescription: "Detalhes montados em leitura a partir de tasks, queries e audit_log legado.",
  noTrace: "Sem trace",
  noTraceDescription: "A execução possui apenas metadados básicos disponíveis.",
  responseFromTrace: "Resposta do trace",
  responseFallbackQueries: "Fallback de queries",
  noResponse: "Sem resposta",
  structuredTools: "Ferramentas estruturadas",
  legacyTools: "Ferramentas legadas",
  noTools: "Sem ferramentas",
  loadErrorTitle: "Não foi possível carregar os detalhes da execução",
  failureRecorded: "Falha registrada",
  signals: "Sinais",
  traceSource: "Origem do trace",
  responseSource: "Origem da resposta",
  toolsSource: "Origem das ferramentas",
  stopReason: "Finalização",
  notProvided: "não informado",
  runtime: "Runtime",
  openRuntimeRoom: "Abrir sala operacional",
  input: "Entrada",
  output: "Saída",
  response: "Resposta",
  steps: "Passos",
  activity: "Atividade",
  notes: "Notas",
  files: "Arquivos",
};

mutableResources["es-ES"].translation.executions.detail = {
  traceRich: "Trace rico",
  traceRichDescription: "Ejecución con envoltorio completo, herramientas y artefactos estructurados.",
  reconstructed: "Reconstruido",
  reconstructedDescription: "Detalles reconstruidos a partir de tasks, queries y audit_log legado.",
  noTrace: "Sin trace",
  noTraceDescription: "La ejecución solo tiene metadatos básicos disponibles.",
  responseFromTrace: "Respuesta del trace",
  responseFallbackQueries: "Fallback de queries",
  noResponse: "Sin respuesta",
  structuredTools: "Herramientas estructuradas",
  legacyTools: "Herramientas legadas",
  noTools: "Sin herramientas",
  loadErrorTitle: "No se pudieron cargar los detalles de la ejecución",
  failureRecorded: "Fallo registrado",
  signals: "Señales",
  traceSource: "Origen del trace",
  responseSource: "Origen de la respuesta",
  toolsSource: "Origen de las herramientas",
  stopReason: "Finalización",
  notProvided: "no informado",
  runtime: "Runtime",
  openRuntimeRoom: "Abrir sala operativa",
  input: "Entrada",
  output: "Salida",
  response: "Respuesta",
  steps: "Pasos",
  activity: "Actividad",
  notes: "Notas",
  files: "Archivos",
};

mutableResources["fr-FR"].translation.executions.detail = {
  traceRich: "Trace riche",
  traceRichDescription: "Exécution avec enveloppe complète, outils et artefacts structurés.",
  reconstructed: "Reconstruite",
  reconstructedDescription: "Détails reconstruits à partir des tâches, requêtes et journal d'audit hérité.",
  noTrace: "Aucun trace",
  noTraceDescription: "Seules les métadonnées basiques sont disponibles pour cette exécution.",
  responseFromTrace: "Réponse du trace",
  responseFallbackQueries: "Repli des requêtes",
  noResponse: "Aucune réponse",
  structuredTools: "Outils structurés",
  legacyTools: "Outils hérités",
  noTools: "Aucun outil",
  loadErrorTitle: "Impossible de charger les détails de l'exécution",
  failureRecorded: "Échec enregistré",
  signals: "Signaux",
  traceSource: "Source du trace",
  responseSource: "Source de la réponse",
  toolsSource: "Source des outils",
  stopReason: "Motif d'arrêt",
  notProvided: "non fourni",
  runtime: "Runtime",
  openRuntimeRoom: "Ouvrir la salle opérationnelle",
  input: "Entrée",
  output: "Sortie",
  response: "Réponse",
  steps: "Étapes",
  activity: "Activité",
  notes: "Notes",
  files: "Fichiers",
};

mutableResources["de-DE"].translation.executions.detail = {
  traceRich: "Umfangreicher Trace",
  traceRichDescription: "Ausführung mit vollständigem Envelope, Tools und strukturierten Artefakten.",
  reconstructed: "Rekonstruiert",
  reconstructedDescription: "Details rekonstruiert aus Aufgaben, Abfragen und Legacy-Audit-Log.",
  noTrace: "Kein Trace",
  noTraceDescription: "Nur grundlegende Metadaten sind für diese Ausführung verfügbar.",
  responseFromTrace: "Trace-Antwort",
  responseFallbackQueries: "Abfragen-Fallback",
  noResponse: "Keine Antwort",
  structuredTools: "Strukturierte Tools",
  legacyTools: "Legacy-Tools",
  noTools: "Keine Tools",
  loadErrorTitle: "Ausführungsdetails konnten nicht geladen werden",
  failureRecorded: "Fehler erfasst",
  signals: "Signale",
  traceSource: "Trace-Quelle",
  responseSource: "Antwortquelle",
  toolsSource: "Tool-Quelle",
  stopReason: "Stoppgrund",
  notProvided: "nicht angegeben",
  runtime: "Laufzeit",
  openRuntimeRoom: "Operativen Raum öffnen",
  input: "Eingabe",
  output: "Ausgabe",
  response: "Antwort",
  steps: "Schritte",
  activity: "Aktivität",
  notes: "Notizen",
  files: "Dateien",
};

mutableResources["en-US"].translation.botDetail = {
  unavailable: "Bot unavailable",
  databaseNotInitialized: "Database not initialized yet",
  noPublishedData: "No published data",
  refresh: "Refresh",
  activeTitle: "{{bot}} active",
  stableTitle: "{{bot}} stable",
  metrics: {
    active: "Active",
    completed: "Completed",
    failed: "Failures",
    queries: "Queries",
    todayCost: "Cost today",
    totalCost: "Total cost",
    lastActivity: "Last activity",
    schedules: "Schedules",
  },
  tabs: {
    overview: "Overview",
    tasks: "Executions",
    sessions: "Sessions",
    cron: "Schedules",
  },
  recent: "Recent",
  entriesCount_one: "{{count}} entry",
  entriesCount_other: "{{count}} entries",
  noRecentTasks: "No recent task.",
  situation: "Situation",
  activeSchedules: "Active schedules",
  trackedSessions: "Tracked sessions",
  noTask: "No task.",
  noSession: "No session.",
  noSchedule: "No schedule.",
};

mutableResources["pt-BR"].translation.botDetail = {
  unavailable: "BOT indisponível",
  databaseNotInitialized: "Base ainda não inicializada",
  noPublishedData: "Sem dados publicados",
  refresh: "Atualizar",
  activeTitle: "{{bot}} em atividade",
  stableTitle: "{{bot}} estável",
  metrics: {
    active: "Ativas",
    completed: "Concluídas",
    failed: "Falhas",
    queries: "Consultas",
    todayCost: "Custo hoje",
    totalCost: "Custo total",
    lastActivity: "Última atividade",
    schedules: "Agendamentos",
  },
  tabs: {
    overview: "Visão geral",
    tasks: "Execuções",
    sessions: "Sessões",
    cron: "Agendamentos",
  },
  recent: "Recentes",
  entriesCount_one: "{{count}} entrada",
  entriesCount_other: "{{count}} entradas",
  noRecentTasks: "Nenhuma tarefa recente.",
  situation: "Situação",
  activeSchedules: "Agendamentos ativos",
  trackedSessions: "Sessões rastreadas",
  noTask: "Nenhuma tarefa.",
  noSession: "Nenhuma sessão.",
  noSchedule: "Nenhum agendamento.",
};

mutableResources["es-ES"].translation.botDetail = {
  unavailable: "BOT no disponible",
  databaseNotInitialized: "Base aún no inicializada",
  noPublishedData: "Sin datos publicados",
  refresh: "Actualizar",
  activeTitle: "{{bot}} en actividad",
  stableTitle: "{{bot}} estable",
  metrics: {
    active: "Activas",
    completed: "Completadas",
    failed: "Fallos",
    queries: "Consultas",
    todayCost: "Costo hoy",
    totalCost: "Costo total",
    lastActivity: "Última actividad",
    schedules: "Programaciones",
  },
  tabs: {
    overview: "Visión general",
    tasks: "Ejecuciones",
    sessions: "Sesiones",
    cron: "Programaciones",
  },
  recent: "Recientes",
  entriesCount_one: "{{count}} entrada",
  entriesCount_other: "{{count}} entradas",
  noRecentTasks: "No hay tareas recientes.",
  situation: "Situación",
  activeSchedules: "Programaciones activas",
  trackedSessions: "Sesiones rastreadas",
  noTask: "Ninguna tarea.",
  noSession: "Ninguna sesión.",
  noSchedule: "Ninguna programación.",
};

mutableResources["fr-FR"].translation.botDetail = {
  unavailable: "Bot indisponible",
  databaseNotInitialized: "Base de données non encore initialisée",
  noPublishedData: "Aucune donnée publiée",
  refresh: "Actualiser",
  activeTitle: "{{bot}} actif",
  stableTitle: "{{bot}} stable",
  metrics: {
    active: "Actifs",
    completed: "Terminés",
    failed: "Échecs",
    queries: "Requêtes",
    todayCost: "Coût aujourd'hui",
    totalCost: "Coût total",
    lastActivity: "Dernière activité",
    schedules: "Plannings",
  },
  tabs: {
    overview: "Aperçu",
    tasks: "Exécutions",
    sessions: "Sessions",
    cron: "Plannings",
  },
  recent: "Récents",
  entriesCount_one: "{{count}} entrée",
  entriesCount_other: "{{count}} entrées",
  noRecentTasks: "Aucune tâche récente.",
  situation: "Situation",
  activeSchedules: "Plannings actifs",
  trackedSessions: "Sessions suivies",
  noTask: "Aucune tâche.",
  noSession: "Aucune session.",
  noSchedule: "Aucun planning.",
};

mutableResources["de-DE"].translation.botDetail = {
  unavailable: "Bot nicht verfügbar",
  databaseNotInitialized: "Datenbank noch nicht initialisiert",
  noPublishedData: "Keine veröffentlichten Daten",
  refresh: "Aktualisieren",
  activeTitle: "{{bot}} aktiv",
  stableTitle: "{{bot}} stabil",
  metrics: {
    active: "Aktiv",
    completed: "Abgeschlossen",
    failed: "Fehler",
    queries: "Abfragen",
    todayCost: "Kosten heute",
    totalCost: "Gesamtkosten",
    lastActivity: "Letzte Aktivität",
    schedules: "Zeitpläne",
  },
  tabs: {
    overview: "Übersicht",
    tasks: "Ausführungen",
    sessions: "Sitzungen",
    cron: "Zeitpläne",
  },
  recent: "Aktuell",
  entriesCount_one: "{{count}} Eintrag",
  entriesCount_other: "{{count}} Einträge",
  noRecentTasks: "Keine aktuelle Aufgabe.",
  situation: "Lage",
  activeSchedules: "Aktive Zeitpläne",
  trackedSessions: "Verfolgte Sitzungen",
  noTask: "Keine Aufgabe.",
  noSession: "Keine Sitzung.",
  noSchedule: "Kein Zeitplan.",
};

mutableResources["en-US"].translation.memory.map = {
  ...mutableResources["en-US"].translation.memory.map,
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  reset: "Reset map",
  newMemory: "New memory",
  connectionsTitle: "Connections",
  docToMemory: "Doc -> Memory",
  docSimilarity: "Doc similarity",
  relationsTitle: "Relations",
  relationUpdates: "Updates",
  relationExtends: "Extends",
  relationDerives: "Derives",
  similarityTitle: "Similarity",
  weak: "Weak",
  strong: "Strong",
};

mutableResources["pt-BR"].translation.memory.map = {
  ...mutableResources["pt-BR"].translation.memory.map,
  zoomIn: "Aproximar mapa",
  zoomOut: "Afastar mapa",
  reset: "Resetar mapa",
  newMemory: "Nova memória",
  connectionsTitle: "Conexões",
  docToMemory: "Doc -> Memória",
  docSimilarity: "Similaridade de documentos",
  relationsTitle: "Relações",
  relationUpdates: "Atualiza",
  relationExtends: "Estende",
  relationDerives: "Deriva",
  similarityTitle: "Similaridade",
  weak: "Fraca",
  strong: "Forte",
};

mutableResources["es-ES"].translation.memory.map = {
  ...mutableResources["es-ES"].translation.memory.map,
  zoomIn: "Acercar mapa",
  zoomOut: "Alejar mapa",
  reset: "Restablecer mapa",
  newMemory: "Memoria nueva",
  connectionsTitle: "Conexiones",
  docToMemory: "Doc -> Memoria",
  docSimilarity: "Similitud de documentos",
  relationsTitle: "Relaciones",
  relationUpdates: "Actualiza",
  relationExtends: "Extiende",
  relationDerives: "Deriva",
  similarityTitle: "Similitud",
  weak: "Débil",
  strong: "Fuerte",
};

mutableResources["en-US"].translation.sessions.detail = {
  ...(mutableResources["en-US"].translation.sessions.detail ?? {}),
  dialogTitle: "Session details",
};
mutableResources["en-US"].translation.sessions.generatedStepFailure =
  "Failed to generate a response for this step.";

mutableResources["pt-BR"].translation.sessions.detail = {
  ...(mutableResources["pt-BR"].translation.sessions.detail ?? {}),
  dialogTitle: "Detalhes da sessão",
};
mutableResources["pt-BR"].translation.sessions.generatedStepFailure =
  "Falha ao gerar resposta para esta etapa.";

mutableResources["es-ES"].translation.sessions.detail = {
  ...(mutableResources["es-ES"].translation.sessions.detail ?? {}),
  dialogTitle: "Detalles de la sesión",
};
mutableResources["es-ES"].translation.sessions.generatedStepFailure =
  "No fue posible generar una respuesta para esta etapa.";

mutableResources["fr-FR"].translation.sessions.detail = {
  ...(mutableResources["fr-FR"].translation.sessions.detail ?? {}),
  dialogTitle: "Détails de la session",
};
mutableResources["fr-FR"].translation.sessions.generatedStepFailure =
  "Impossible de générer une réponse pour cette étape.";

mutableResources["de-DE"].translation.sessions.detail = {
  ...(mutableResources["de-DE"].translation.sessions.detail ?? {}),
  dialogTitle: "Sitzungsdetails",
};
mutableResources["de-DE"].translation.sessions.generatedStepFailure =
  "Für diesen Schritt konnte keine Antwort generiert werden.";

Object.assign(literalResources["en-US"], {
  "Nao definidas": "Not set",
  "Nao foi possivel conectar o provider local.": "Could not connect the local provider.",
  "Nao foi possivel conectar o provider via API Key.": "Could not connect the provider via API key.",
  "Nao foi possivel desconectar o provider.": "Could not disconnect the provider.",
  "Nao foi possivel iniciar o download da voz.": "Could not start the voice download.",
  "Nao foi possivel iniciar o login oficial do provider.": "Could not start the provider official login.",
  "Nao foi possivel salvar as configuracoes gerais.": "Could not save the general settings.",
  "Nao foi possivel validar a API Key deste provider.": "Could not validate this provider API key.",
  "Nao foi possivel validar a conexao local deste provider.": "Could not validate this provider local connection.",
  "Nao foi possivel verificar a conexao do provider.": "Could not verify the provider connection.",
  "Nenhum conteudo para visualizar": "No content to preview",
  "Nome do agente": "Agent name",
  "Novo agente": "New agent",
  "O agente nasce pausado e pode ser refinado depois no editor, sem interromper a organizacao dos seus times.": "The agent starts paused and can be refined later in the editor, without interrupting your team organization.",
  "Paleta rápida": "Quick palette",
  "Preview das instrucoes:": "Instructions preview:",
  "Provedor": "Provider",
  "Providers ativos": "Active providers",
  "Pular": "Skip",
  "Recursos compartilhados": "Shared resources",
  "Revisao": "Review",
  "Revise os dados principais antes de publicar o novo agente no catalogo.": "Review the key data before publishing the new agent to the catalog.",
  "Saturação": "Saturation",
  "Segredos exigem grant explicito": "Secrets require explicit grant",
  "Sistema": "System",
  "Status inicial": "Initial status",
  "Subsets por agente continuam governados no editor de cada bot": "Per-agent subsets remain governed in each bot editor",
  "Todos os providers habilitados estao prontos": "All enabled providers are ready",
  "Tools do core": "Core tools",
  "Use o formato hexadecimal #RRGGBB.": "Use the hexadecimal format #RRGGBB.",
  "Valor atual mascarado": "Current value masked",
  "Voce podera ajustar todas as configuracoes apos a criacao.": "You will be able to adjust all settings after creation.",
  "nao": "no",
  "sim": "yes",
  "{{count}} item(s)": "{{count}} item(s)",
  "{{count}} provider(s) com capacidade degradada": "{{count}} provider(s) with degraded capacity",
  "{{variables}} variavel(is) e {{secrets}} segredo(s)": "{{variables}} variable(s) and {{secrets}} secret(s)",
  "Login oficial": "Official login",
  "Chave da API": "API key",
  "Chave configurada": "Configured key",
  "Cole a chave da API": "Paste the API key",
  "Projeto Google": "Google project",
  "Todos os idiomas": "All languages",
  "Configurações globais": "Global settings",
  "Defina o provider principal, o perfil de uso e os limites globais depois de conectar os providers.": "Set the primary provider, the usage profile and the global limits after connecting the providers.",
  "Nenhum provider verificado": "No verified provider",
  "Modelos detectados": "Detected models",
  "{{count}} modelos": "{{count}} models",
  "Nenhum modelo": "No model",
  "Nenhum modelo foi retornado pelo endpoint configurado.": "No model was returned by the configured endpoint.",
  "Conecte o Ollama para carregar a lista real de modelos.": "Connect Ollama to load the real model list.",
  "Operação": "Operation",
  "O Ollama depende apenas do runtime local configurado na máquina.": "Ollama depends only on the local runtime configured on this machine.",
  "Conclua a autenticação no {{provider}}.": "Complete authentication in {{provider}}.",
  "Código:": "Code:",
  "Verificado": "Verified",
  "Ainda não verificado": "Not verified yet",
  "Ocultar valor mascarado": "Hide masked value",
  "Mostrar valor mascarado": "Show masked value",
  "Esconder valor": "Hide value",
  "Visualizar valor": "View value",
  "Alteracoes nao salvas": "Unsaved changes",
  "Base URL": "Base URL",
  "Carregando...": "Loading...",
  "Este provider não exige autenticação manual nesta tela.": "This provider does not require manual authentication on this screen.",
  "New Item": "New Item",
  "Raw JSON ({{count}} items)": "Raw JSON ({{count}} items)",
  "Save": "Save",
  "Saving...": "Saving...",
  "Value must be a JSON object": "Value must be a JSON object",
  "Visualizar": "Preview",
  "meu-projeto-google": "my-google-project",
  "sessão {{value}}": "session {{value}}",
  "tentativa {{value}}": "attempt {{value}}",
  "base {{value}}": "base {{value}}",
  "{{value}} consultas": "{{value}} queries",
  "{{queries}} consultas · {{executions}} execuções · {{resolved}} resolvidas": "{{queries}} queries · {{executions}} executions · {{resolved}} resolved",
  "{{resolved}} resolvidas · {{cost}} por conversa": "{{resolved}} resolved · {{cost}} per conversation",
  "{{count}} ocorrências · {{cost}} em média": "{{count}} occurrences · {{cost}} average",
  "Memória habilitada": "Memory enabled",
  "RAG habilitado": "RAG enabled",
  "Exigir owner": "Require owner",
  "Exigir freshness": "Require freshness",
  "Timeout de recall": "Recall timeout",
  "Itens por extração": "Items per extraction",
  "Recall procedural": "Procedural recall",
  "Dedup semântico": "Semantic dedup",
  "Máx por usuário": "Max per user",
  "Promoção após sucessos": "Promotion after successes",
  "Provider de extração": "Extraction provider",
  "Modelo de extração": "Extraction model",
  "Postura de risco": "Risk posture",
  "Densidade": "Density",
  "Domínios de foco": "Focus domains",
  "Camadas preferidas": "Preferred layers",
  "Camadas proibidas": "Forbidden layers",
  "Camadas permitidas": "Allowed layers",
  "Max resultados": "Max results",
  "Arquivos do workspace": "Workspace files",
  "Idade máxima (dias)": "Max age (days)",
  "Modo de promoção": "Promotion mode",
  "Globs globais": "Global globs",
  "Globs do workspace": "Workspace globs",
  "Approval mode padrão": "Default approval mode",
  "Autonomy tier padrão": "Default autonomy tier",
  "Ativa recall e persistência de memória para o agente.": "Enables recall and persistent memory for the agent.",
  "Memória proativa": "Proactive memory",
  "Permite sugerir contexto útil antes de ser solicitado.": "Allows the agent to suggest useful context before it is requested.",
  "Memória procedural": "Procedural memory",
  "Aprende procedimentos e padrões úteis ao longo do uso.": "Learns useful procedures and patterns over time.",
  "Auto manutenção": "Self-maintenance",
  "Mantém a memória limpa e operacional ao longo do tempo.": "Keeps memory clean and operational over time.",
  "Digest de memória": "Memory digest",
  "Consolida aprendizados recorrentes em resumos úteis.": "Consolidates recurring learnings into useful summaries.",
  "Revisar padrões": "Review patterns",
  "Exige revisão antes de promover padrões observados.": "Requires review before promoting observed patterns.",
  "Quantidade máxima de memórias trazidas por recall.": "Maximum number of memories brought in by recall.",
  "Similaridade mínima para recuperar uma memória.": "Minimum similarity required to retrieve a memory.",
  "Tempo máximo do recall antes de desistir.": "Maximum recall time before giving up.",
  "Orçamento máximo de contexto vindo de memória.": "Maximum context budget coming from memory.",
  "Máximo de itens extraídos por turno.": "Maximum number of items extracted per turn.",
  "Quantos procedimentos podem entrar por recall.": "How many procedures can enter through recall.",
  "Threshold para evitar memórias semanticamente duplicadas.": "Threshold to avoid semantically duplicated memories.",
  "Limite de memórias persistidas por usuário.": "Limit of persisted memories per user.",
  "Peso de recência aplicado no ranking de recall.": "Recency weight applied to recall ranking.",
  "Mínimo de sucessos verificados para promover um padrão.": "Minimum verified successes required to promote a pattern.",
  "Provider usado para extrair memórias do turno.": "Provider used to extract turn memories.",
  "Modelo específico para extração de memória.": "Specific model used for memory extraction.",
  "Quão conservador o agente deve ser ao usar memória.": "How conservative the agent should be when using memory.",
  "Quanto contexto de memória tende a entrar por turno.": "How much memory context tends to be used per turn.",
  "Temas em que o agente deve investir mais retenção.": "Topics where the agent should invest more retention.",
  "Camadas de memória com peso preferencial no ranking.": "Memory layers with preferential weight in ranking.",
  "Camadas que não devem sustentar ações sensíveis.": "Layers that should not support sensitive actions.",
  "Ativa grounding via recuperação de conhecimento.": "Enables grounding through knowledge retrieval.",
  "Bloqueia fontes críticas sem dono definido.": "Blocks critical sources without a defined owner.",
  "Bloqueia fontes críticas sem janela de frescor definida.": "Blocks critical sources without a defined freshness window.",
  "Define a ordem de confiança do grounding operacional.": "Defines the trust order for operational grounding.",
  "Quantidade máxima de trechos trazidos pelo RAG.": "Maximum number of excerpts retrieved by RAG.",
  "Similaridade mínima para um hit de conhecimento.": "Minimum similarity for a knowledge hit.",
  "Tempo máximo de recuperação antes de degradar.": "Maximum retrieval time before degrading.",
  "Orçamento máximo de contexto vindo do conhecimento.": "Maximum context budget coming from knowledge.",
  "Máximo de arquivos dinâmicos avaliados por busca.": "Maximum dynamic files evaluated per search.",
  "Limite de padrões semânticos fracos no grounding.": "Limit for weak semantic patterns in grounding.",
  "Idade máxima aceitável para fontes usadas no contexto.": "Maximum acceptable age for sources used in context.",
  "Hoje a promoção continua governada por fila de revisão.": "Promotion is still governed by the review queue today.",
  "Arquivos globais elegíveis para indexação semântica.": "Global files eligible for semantic indexing.",
  "Arquivos dinâmicos elegíveis no workspace do agente.": "Dynamic files eligible in the agent workspace.",
  "Nível de contenção padrão para execuções do agente.": "Default containment level for agent executions.",
  "Envelope de autonomia padrão para tarefas complexas.": "Default autonomy envelope for complex tasks.",
  "Herdar do padrão global": "Inherit from the global default",
  "Conservadora": "Conservative",
  "Equilibrada": "Balanced",
  "Agressiva": "Aggressive",
  "Esparsa": "Sparse",
  "Focada": "Focused",
  "Densa": "Dense",
  "Conservador": "Conservative",
  "Curado + workspace": "Curated + workspace",
  "Curado + workspace + padrões": "Curated + workspace + patterns",
  "Aprendizado forte": "Strong learning",
  "Curado apenas": "Curated only",
  "Curado + espaço de trabalho": "Curated + workspace",
  "Curado + espaço de trabalho + padrões": "Curated + workspace + patterns",
  "Estrita": "Strict",
  "Padrão": "Standard",
});

Object.assign(literalResources["es-ES"], {
  "Nao definidas": "No definidas",
  "Nao foi possivel conectar o provider local.": "No fue posible conectar el proveedor local.",
  "Nao foi possivel conectar o provider via API Key.": "No fue posible conectar el proveedor mediante API key.",
  "Nao foi possivel desconectar o provider.": "No fue posible desconectar el proveedor.",
  "Nao foi possivel iniciar o download da voz.": "No fue posible iniciar la descarga de la voz.",
  "Nao foi possivel iniciar o login oficial do provider.": "No fue posible iniciar el acceso oficial del proveedor.",
  "Nao foi possivel salvar as configuracoes gerais.": "No fue posible guardar la configuración general.",
  "Nao foi possivel validar a API Key deste provider.": "No fue posible validar la API key de este proveedor.",
  "Nao foi possivel validar a conexao local deste provider.": "No fue posible validar la conexión local de este proveedor.",
  "Nao foi possivel verificar a conexao do provider.": "No fue posible verificar la conexión del proveedor.",
  "Nenhum conteudo para visualizar": "No hay contenido para previsualizar",
  "Nome do agente": "Nombre del agente",
  "Novo agente": "Nuevo agente",
  "O agente nasce pausado e pode ser refinado depois no editor, sem interromper a organizacao dos seus times.": "El agente nace pausado y puede refinarse después en el editor, sin interrumpir la organización de tus equipos.",
  "Paleta rápida": "Paleta rápida",
  "Preview das instrucoes:": "Vista previa de las instrucciones:",
  "Provedor": "Proveedor",
  "Providers ativos": "Proveedores activos",
  "Pular": "Saltar",
  "Recursos compartilhados": "Recursos compartidos",
  "Revisao": "Revisión",
  "Revise os dados principais antes de publicar o novo agente no catalogo.": "Revisa los datos principales antes de publicar el nuevo agente en el catálogo.",
  "Saturação": "Saturación",
  "Segredos exigem grant explicito": "Los secretos requieren un grant explícito",
  "Sistema": "Sistema",
  "Status inicial": "Estado inicial",
  "Subsets por agente continuam governados no editor de cada bot": "Los subconjuntos por agente siguen gobernados en el editor de cada bot",
  "Todos os providers habilitados estao prontos": "Todos los proveedores habilitados están listos",
  "Tools do core": "Herramientas del core",
  "Use o formato hexadecimal #RRGGBB.": "Usa el formato hexadecimal #RRGGBB.",
  "Valor atual mascarado": "Valor actual enmascarado",
  "Voce podera ajustar todas as configuracoes apos a criacao.": "Podrás ajustar toda la configuración después de la creación.",
  "nao": "no",
  "sim": "sí",
  "{{count}} item(s)": "{{count}} elemento(s)",
  "{{count}} provider(s) com capacidade degradada": "{{count}} proveedor(es) con capacidad degradada",
  "{{variables}} variavel(is) e {{secrets}} segredo(s)": "{{variables}} variable(s) y {{secrets}} secreto(s)",
  "Login oficial": "Acceso oficial",
  "Chave da API": "API key",
  "Chave configurada": "Clave configurada",
  "Cole a chave da API": "Pega la API key",
  "Projeto Google": "Proyecto de Google",
  "Todos os idiomas": "Todos los idiomas",
  "Configurações globais": "Configuración global",
  "Defina o provider principal, o perfil de uso e os limites globais depois de conectar os providers.": "Define el proveedor principal, el perfil de uso y los límites globales después de conectar los proveedores.",
  "Nenhum provider verificado": "Ningún proveedor verificado",
  "Modelos detectados": "Modelos detectados",
  "{{count}} modelos": "{{count}} modelos",
  "Nenhum modelo": "Ningún modelo",
  "Nenhum modelo foi retornado pelo endpoint configurado.": "Ningún modelo fue devuelto por el endpoint configurado.",
  "Conecte o Ollama para carregar a lista real de modelos.": "Conecta Ollama para cargar la lista real de modelos.",
  "Operação": "Operación",
  "O Ollama depende apenas do runtime local configurado na máquina.": "Ollama depende solo del runtime local configurado en la máquina.",
  "Conclua a autenticação no {{provider}}.": "Completa la autenticación en {{provider}}.",
  "Código:": "Código:",
  "Verificado": "Verificado",
  "Ainda não verificado": "Aún no verificado",
  "Ocultar valor mascarado": "Ocultar valor enmascarado",
  "Mostrar valor mascarado": "Mostrar valor enmascarado",
  "Esconder valor": "Ocultar valor",
  "Visualizar valor": "Ver valor",
  "Alteracoes nao salvas": "Cambios no guardados",
  "Base URL": "URL base",
  "Carregando...": "Cargando...",
  "Este provider não exige autenticação manual nesta tela.": "Este proveedor no requiere autenticación manual en esta pantalla.",
  "New Item": "Nuevo elemento",
  "Raw JSON ({{count}} items)": "JSON sin procesar ({{count}} elementos)",
  "Save": "Guardar",
  "Saving...": "Guardando...",
  "Value must be a JSON object": "El valor debe ser un objeto JSON",
  "Visualizar": "Previsualizar",
  "meu-projeto-google": "mi-proyecto-google",
  "sessão {{value}}": "sesión {{value}}",
  "tentativa {{value}}": "intento {{value}}",
  "base {{value}}": "base {{value}}",
  "{{value}} consultas": "{{value}} consultas",
  "{{queries}} consultas · {{executions}} execuções · {{resolved}} resolvidas": "{{queries}} consultas · {{executions}} ejecuciones · {{resolved}} resueltas",
  "{{resolved}} resolvidas · {{cost}} por conversa": "{{resolved}} resueltas · {{cost}} por conversación",
  "{{count}} ocorrências · {{cost}} em média": "{{count}} ocurrencias · {{cost}} de promedio",
  "Memória habilitada": "Memoria habilitada",
  "RAG habilitado": "RAG habilitado",
  "Exigir owner": "Exigir responsable",
  "Exigir freshness": "Exigir frescura",
  "Timeout de recall": "Timeout de recall",
  "Itens por extração": "Elementos por extracción",
  "Recall procedural": "Recall procedural",
  "Dedup semântico": "Deduplicación semántica",
  "Máx por usuário": "Máx. por usuario",
  "Promoção após sucessos": "Promoción tras éxitos",
  "Provider de extração": "Proveedor de extracción",
  "Modelo de extração": "Modelo de extracción",
  "Postura de risco": "Postura de riesgo",
  "Densidade": "Densidad",
  "Domínios de foco": "Dominios de foco",
  "Camadas preferidas": "Capas preferidas",
  "Camadas proibidas": "Capas prohibidas",
  "Camadas permitidas": "Capas permitidas",
  "Max resultados": "Máx. resultados",
  "Arquivos do workspace": "Archivos del espacio de trabajo",
  "Idade máxima (dias)": "Edad máxima (días)",
  "Modo de promoção": "Modo de promoción",
  "Globs globais": "Globs globales",
  "Globs do workspace": "Globs del espacio de trabajo",
  "Approval mode padrão": "Modo de aprobación predeterminado",
  "Autonomy tier padrão": "Nivel de autonomía predeterminado",
  "Ativa recall e persistência de memória para o agente.": "Activa el recall y la persistencia de memoria para el agente.",
  "Memória proativa": "Memoria proactiva",
  "Permite sugerir contexto útil antes de ser solicitado.": "Permite sugerir contexto útil antes de que se solicite.",
  "Memória procedural": "Memoria procedural",
  "Aprende procedimentos e padrões úteis ao longo do uso.": "Aprende procedimientos y patrones útiles con el uso.",
  "Auto manutenção": "Auto-mantenimiento",
  "Mantém a memória limpa e operacional ao longo do tempo.": "Mantiene la memoria limpia y operativa con el tiempo.",
  "Digest de memória": "Digest de memoria",
  "Consolida aprendizados recorrentes em resumos úteis.": "Consolida aprendizajes recurrentes en resúmenes útiles.",
  "Revisar padrões": "Revisar patrones",
  "Exige revisão antes de promover padrões observados.": "Exige revisión antes de promover patrones observados.",
  "Quantidade máxima de memórias trazidas por recall.": "Cantidad máxima de memorias recuperadas por recall.",
  "Similaridade mínima para recuperar uma memória.": "Similitud mínima para recuperar una memoria.",
  "Tempo máximo do recall antes de desistir.": "Tiempo máximo del recall antes de desistir.",
  "Orçamento máximo de contexto vindo de memória.": "Presupuesto máximo de contexto proveniente de memoria.",
  "Máximo de itens extraídos por turno.": "Máximo de elementos extraídos por turno.",
  "Quantos procedimentos podem entrar por recall.": "Cuántos procedimientos pueden entrar por recall.",
  "Threshold para evitar memórias semanticamente duplicadas.": "Umbral para evitar memorias semánticamente duplicadas.",
  "Limite de memórias persistidas por usuário.": "Límite de memorias persistidas por usuario.",
  "Peso de recência aplicado no ranking de recall.": "Peso de recencia aplicado al ranking de recall.",
  "Mínimo de sucessos verificados para promover um padrão.": "Mínimo de éxitos verificados para promover un patrón.",
  "Provider usado para extrair memórias do turno.": "Proveedor usado para extraer memorias del turno.",
  "Modelo específico para extração de memória.": "Modelo específico para extracción de memoria.",
  "Quão conservador o agente deve ser ao usar memória.": "Qué tan conservador debe ser el agente al usar memoria.",
  "Quanto contexto de memória tende a entrar por turno.": "Cuánto contexto de memoria tiende a entrar por turno.",
  "Temas em que o agente deve investir mais retenção.": "Temas en los que el agente debe invertir más retención.",
  "Camadas de memória com peso preferencial no ranking.": "Capas de memoria con peso preferencial en el ranking.",
  "Camadas que não devem sustentar ações sensíveis.": "Capas que no deben sostener acciones sensibles.",
  "Ativa grounding via recuperação de conhecimento.": "Activa el grounding mediante recuperación de conocimiento.",
  "Bloqueia fontes críticas sem dono definido.": "Bloquea fuentes críticas sin responsable definido.",
  "Bloqueia fontes críticas sem janela de frescor definida.": "Bloquea fuentes críticas sin ventana de frescura definida.",
  "Define a ordem de confiança do grounding operacional.": "Define el orden de confianza del grounding operacional.",
  "Quantidade máxima de trechos trazidos pelo RAG.": "Cantidad máxima de fragmentos recuperados por el RAG.",
  "Similaridade mínima para um hit de conhecimento.": "Similitud mínima para un hallazgo de conocimiento.",
  "Tempo máximo de recuperação antes de degradar.": "Tiempo máximo de recuperación antes de degradar.",
  "Orçamento máximo de contexto vindo do conhecimento.": "Presupuesto máximo de contexto proveniente del conocimiento.",
  "Máximo de arquivos dinâmicos avaliados por busca.": "Máximo de archivos dinámicos evaluados por búsqueda.",
  "Limite de padrões semânticos fracos no grounding.": "Límite de patrones semánticos débiles en el grounding.",
  "Idade máxima aceitável para fontes usadas no contexto.": "Edad máxima aceptable para fuentes usadas en el contexto.",
  "Hoje a promoção continua governada por fila de revisão.": "Hoy la promoción sigue gobernada por una cola de revisión.",
  "Arquivos globais elegíveis para indexação semântica.": "Archivos globales elegibles para indexación semántica.",
  "Arquivos dinâmicos elegíveis no workspace do agente.": "Archivos dinámicos elegibles en el workspace del agente.",
  "Nível de contenção padrão para execuções do agente.": "Nivel de contención predeterminado para las ejecuciones del agente.",
  "Envelope de autonomia padrão para tarefas complexas.": "Envelope de autonomía predeterminado para tareas complejas.",
  "Herdar do padrão global": "Heredar del estándar global",
  "Conservadora": "Conservadora",
  "Equilibrada": "Equilibrada",
  "Agressiva": "Agresiva",
  "Esparsa": "Dispersa",
  "Focada": "Enfocada",
  "Densa": "Densa",
  "Conservador": "Conservador",
  "Curado + workspace": "Curado + espacio de trabajo",
  "Curado + workspace + padrões": "Curado + espacio de trabajo + patrones",
  "Aprendizado forte": "Aprendizaje fuerte",
  "Curado apenas": "Solo curado",
  "Curado + espaço de trabalho": "Curado + workspace",
  "Curado + espaço de trabalho + padrões": "Curado + workspace + patrones",
  "Estrita": "Estricta",
  "Padrão": "Estándar",
});

Object.assign(literalResources["en-US"], {
  "Resolvida": "Resolved",
  "Executando": "Running",
  "Falhou": "Failed",
  "Na fila": "Queued",
  "Aberta": "Open",
  "Resposta": "Reply",
  "Pesquisa": "Research",
  "Resumo": "Summary",
  "Jira": "Jira",
  "Triagem": "Triage",
  "Memória": "Memory",
  "Geração": "Generation",
  "Outro": "Other",
  "Outros": "Others",
  "Sem modelo": "No model",
  "Comportamento": "Behavior",
  "Recursos": "Resources",
  "Publicacao": "Publishing",
  "Participação no recorte": "Share in current range",
  "{{count}} origens consolidadas": "{{count}} consolidated sources",
  "{{count}} ambiente(s) sem heartbeat recente": "{{count}} environment(s) without a recent heartbeat",
  "{{count}} ambiente(s) aguardando recovery": "{{count}} environment(s) waiting for recovery",
  "{{count}} ambiente(s) aguardando cleanup": "{{count}} environment(s) waiting for cleanup",
  "Runtime frontend desabilitado": "Runtime frontend disabled",
  "Runtime frontend degradado": "Runtime frontend degraded",
  "Runtime indisponível": "Runtime unavailable",
});

Object.assign(literalResources["es-ES"], {
  "Resolvida": "Resuelta",
  "Executando": "Ejecutando",
  "Falhou": "Falló",
  "Na fila": "En cola",
  "Aberta": "Abierta",
  "Resposta": "Respuesta",
  "Pesquisa": "Investigación",
  "Resumo": "Resumen",
  "Jira": "Jira",
  "Triagem": "Triaje",
  "Memória": "Memoria",
  "Geração": "Generación",
  "Outro": "Otro",
  "Outros": "Otros",
  "Sem modelo": "Sin modelo",
  "Comportamento": "Comportamiento",
  "Recursos": "Recursos",
  "Publicacao": "Publicación",
  "Participação no recorte": "Participación en el recorte",
  "{{count}} origens consolidadas": "{{count}} orígenes consolidados",
  "{{count}} ambiente(s) sem heartbeat recente": "{{count}} entorno(s) sin heartbeat reciente",
  "{{count}} ambiente(s) aguardando recovery": "{{count}} entorno(s) esperando recovery",
  "{{count}} ambiente(s) aguardando cleanup": "{{count}} entorno(s) esperando cleanup",
  "Runtime frontend desabilitado": "Runtime frontend deshabilitado",
  "Runtime frontend degradado": "Runtime frontend degradado",
  "Runtime indisponível": "Runtime no disponible",
});

Object.assign(literalResources["en-US"], {
  "Anthropic via API Key ou login oficial do Claude Code.": "Anthropic via API key or official Claude Code sign-in.",
  "OpenAI via API Key ou login oficial do Codex.": "OpenAI via API key or official Codex sign-in.",
  "Google via GEMINI_API_KEY ou login oficial do Gemini CLI.": "Google via GEMINI_API_KEY or official Gemini CLI sign-in.",
  "Voz premium com API Key, idioma padrão e seleção de vozes.": "Premium voice with API key, default language and voice selection.",
  "Provider de mídia com autenticação pela plataforma OpenAI.": "Media provider with authentication through the OpenAI platform.",
  "Servidor Ollama local ou cloud com API Key, usando o catálogo real de modelos.": "Local or cloud Ollama server with API key, using the real model catalog.",
  "Provider multimodal focado em voz e áudio.": "Multimodal provider focused on voice and audio.",
  "Provider multimídia disponível para fluxos especializados.": "Multimedia provider available for specialized flows.",
  "Provider disponível no catálogo global do sistema.": "Provider available in the global system catalog.",
  "Use o login oficial do Claude Code para conectar sua assinatura Anthropic.": "Use the official Claude Code sign-in to connect your Anthropic subscription.",
  "Use o login oficial do Codex com sua conta OpenAI/ChatGPT. A cobrança da API continua separada da assinatura.": "Use the official Codex sign-in with your OpenAI/ChatGPT account. API billing remains separate from the subscription.",
  "Use o login oficial do Gemini CLI com sua conta Google.": "Use the official Gemini CLI sign-in with your Google account.",
  "Claude Code": "Claude Code",
  "Codex": "Codex",
  "Gemini CLI": "Gemini CLI",
  "Desconectar": "Disconnect",
  "Conectar": "Connect",
  "Desconectando": "Disconnecting",
  "Aguardando": "Waiting",
  "Conectando": "Connecting",
  "Recolher {{provider}}": "Collapse {{provider}}",
  "Expandir {{provider}}": "Expand {{provider}}",
  "O runtime oficial deste provider não está disponível neste ambiente. Instale o CLI correspondente antes de concluir a conexão.": "The official runtime for this provider is not available in this environment. Install the corresponding CLI before finishing the connection.",
  "Carregando vozes oficiais...": "Loading official voices...",
  "Carregando vozes...": "Loading voices...",
  "baixada": "downloaded",
  "Baixando": "Downloading",
  "Voz baixada": "Voice downloaded",
  "Baixar voz": "Download voice",
  "Feminina": "Female",
  "Masculina": "Male",
  "Selecione uma voz para baixar sob demanda.": "Select a voice to download on demand.",
  "Download da voz em andamento.": "Voice download in progress.",
  "Formas de autenticação de {{provider}}": "Authentication methods for {{provider}}",
  "Busca e operações governadas de issues": "Governed issue search and operations",
  "Leitura governada de páginas e espaços": "Governed reading of pages and spaces",
  "Operações via credencial de serviço": "Operations through service credentials",
  "Consultas governadas e inspeção de schema": "Governed queries and schema inspection",
  "Operações cloud com perfis e região": "Cloud operations with profiles and region",
  "CLI para repos, PRs e issues": "CLI for repos, PRs and issues",
  "CLI para repos, MRs e pipelines": "CLI for repos, MRs and pipelines",
  "Memória sem conteúdo": "Memory without content",
  "Usuário {{id}}": "User {{id}}",
  "Afinidade semântica {{pct}}%": "Semantic affinity {{pct}}%",
  "Compartilha a mesma sessão operacional": "Shares the same operational session",
  "Compartilha a mesma origem de contexto": "Shares the same context source",
  'Agrupa {{count}} memórias conectadas por contexto, semântica ou origem operacional em torno de "{{content}}".': 'Groups {{count}} memories connected by context, semantics or operational origin around "{{content}}".',
  "Destaca uma memória de alta importância que vem guiando o comportamento recente do bot.": "Highlights a high-importance memory that has been driving the bot's recent behavior.",
  "Ligação sintética do aprendizado com a memória-base": "Synthetic learning link to the base memory",
  "Aprendizado": "Learning",
  "Pendentes": "Pending",
  "Aprovadas": "Approved",
  "Mescladas": "Merged",
  "Descartadas": "Discarded",
  "Expiradas": "Expired",
  "Arquivadas": "Archived",
  "Banco de dados indisponível.": "Database unavailable.",
  "Nenhum alvo informado.": "No target provided.",
  "Mescla só é suportada para memórias.": "Merge is only supported for memories.",
  "Mescla requer uma memória destino.": "Merge requires a target memory.",
  "Selecione ao menos uma memória para unir.": "Select at least one memory to merge.",
  "Tipo de alvo inválido.": "Invalid target type.",
  "Ação inválida.": "Invalid action.",
  "Selecione ao menos um item.": "Select at least one item.",
  "Não foi possível aplicar a ação.": "Could not apply the action.",
  "Criada em": "Created at",
  "User / chat": "User / chat",
  "Início": "Start",
  "Fim": "End",
  "Categoria": "Category",
  "Comando CLI": "CLI command",
  "Consulta SQL": "SQL query",
  "Ambiente": "Environment",
  "Limite de linhas": "Line limit",
  "Analyze": "Analyze",
  "Sim": "Yes",
  "Não": "No",
  "Código de saída": "Exit code",
  "Saída truncada": "Truncated output",
  "Parâmetros enviados": "Sent parameters",
  "Saída da ferramenta": "Tool output",
  "Metadados adicionais": "Additional metadata",
  "Copiar saída": "Copy output",
  "Expanded execution {{id}}": "Expanded execution {{id}}",
});

Object.assign(literalResources["es-ES"], {
  "Anthropic via API Key ou login oficial do Claude Code.": "Anthropic mediante API key o acceso oficial de Claude Code.",
  "OpenAI via API Key ou login oficial do Codex.": "OpenAI mediante API key o acceso oficial de Codex.",
  "Google via GEMINI_API_KEY ou login oficial do Gemini CLI.": "Google mediante GEMINI_API_KEY o acceso oficial de Gemini CLI.",
  "Voz premium com API Key, idioma padrão e seleção de vozes.": "Voz premium con API key, idioma predeterminado y selección de voces.",
  "Provider de mídia com autenticação pela plataforma OpenAI.": "Proveedor de medios con autenticación mediante la plataforma OpenAI.",
  "Servidor Ollama local ou cloud com API Key, usando o catálogo real de modelos.": "Servidor Ollama local o cloud con API key, usando el catálogo real de modelos.",
  "Provider multimodal focado em voz e áudio.": "Proveedor multimodal enfocado en voz y audio.",
  "Provider multimídia disponível para fluxos especializados.": "Proveedor multimedia disponible para flujos especializados.",
  "Provider disponível no catálogo global do sistema.": "Proveedor disponible en el catálogo global del sistema.",
  "Use o login oficial do Claude Code para conectar sua assinatura Anthropic.": "Usa el acceso oficial de Claude Code para conectar tu suscripción de Anthropic.",
  "Use o login oficial do Codex com sua conta OpenAI/ChatGPT. A cobrança da API continua separada da assinatura.": "Usa el acceso oficial de Codex con tu cuenta de OpenAI/ChatGPT. La facturación de la API sigue separada de la suscripción.",
  "Use o login oficial do Gemini CLI com sua conta Google.": "Usa el acceso oficial de Gemini CLI con tu cuenta de Google.",
  "Claude Code": "Claude Code",
  "Codex": "Codex",
  "Gemini CLI": "Gemini CLI",
  "Desconectar": "Desconectar",
  "Conectar": "Conectar",
  "Desconectando": "Desconectando",
  "Aguardando": "Esperando",
  "Conectando": "Conectando",
  "Recolher {{provider}}": "Contraer {{provider}}",
  "Expandir {{provider}}": "Expandir {{provider}}",
  "O runtime oficial deste provider não está disponível neste ambiente. Instale o CLI correspondente antes de concluir a conexão.": "El runtime oficial de este proveedor no está disponible en este entorno. Instala el CLI correspondiente antes de completar la conexión.",
  "Carregando vozes oficiais...": "Cargando voces oficiales...",
  "Carregando vozes...": "Cargando voces...",
  "baixada": "descargada",
  "Baixando": "Descargando",
  "Voz baixada": "Voz descargada",
  "Baixar voz": "Descargar voz",
  "Feminina": "Femenina",
  "Masculina": "Masculina",
  "Selecione uma voz para baixar sob demanda.": "Selecciona una voz para descargar bajo demanda.",
  "Download da voz em andamento.": "Descarga de voz en curso.",
  "Formas de autenticação de {{provider}}": "Métodos de autenticación de {{provider}}",
  "Busca e operações governadas de issues": "Búsqueda y operaciones gobernadas de issues",
  "Leitura governada de páginas e espaços": "Lectura gobernada de páginas y espacios",
  "Operações via credencial de serviço": "Operaciones mediante credenciales de servicio",
  "Consultas governadas e inspeção de schema": "Consultas gobernadas e inspección de schema",
  "Operações cloud com perfis e região": "Operaciones cloud con perfiles y región",
  "CLI para repos, PRs e issues": "CLI para repos, PRs e issues",
  "CLI para repos, MRs e pipelines": "CLI para repos, MRs y pipelines",
  "Memória sem conteúdo": "Memoria sin contenido",
  "Usuário {{id}}": "Usuario {{id}}",
  "Afinidade semântica {{pct}}%": "Afinidad semántica {{pct}}%",
  "Compartilha a mesma sessão operacional": "Comparte la misma sesión operativa",
  "Compartilha a mesma origem de contexto": "Comparte el mismo origen de contexto",
  'Agrupa {{count}} memórias conectadas por contexto, semântica ou origem operacional em torno de "{{content}}".': 'Agrupa {{count}} memorias conectadas por contexto, semántica u origen operativo alrededor de "{{content}}".',
  "Destaca uma memória de alta importância que vem guiando o comportamento recente do bot.": "Destaca una memoria de alta importancia que ha guiado el comportamiento reciente del bot.",
  "Ligação sintética do aprendizado com a memória-base": "Vínculo sintético del aprendizaje con la memoria base",
  "Aprendizado": "Aprendizaje",
  "Pendentes": "Pendientes",
  "Aprovadas": "Aprobadas",
  "Mescladas": "Fusionadas",
  "Descartadas": "Descartadas",
  "Expiradas": "Expiradas",
  "Arquivadas": "Archivadas",
  "Banco de dados indisponível.": "Base de datos no disponible.",
  "Nenhum alvo informado.": "No se informó ningún objetivo.",
  "Mescla só é suportada para memórias.": "La fusión solo está soportada para memorias.",
  "Mescla requer uma memória destino.": "La fusión requiere una memoria destino.",
  "Selecione ao menos uma memória para unir.": "Selecciona al menos una memoria para unir.",
  "Tipo de alvo inválido.": "Tipo de objetivo inválido.",
  "Ação inválida.": "Acción inválida.",
  "Selecione ao menos um item.": "Selecciona al menos un elemento.",
  "Não foi possível aplicar a ação.": "No se pudo aplicar la acción.",
  "Criada em": "Creada en",
  "User / chat": "Usuario / chat",
  "Início": "Inicio",
  "Fim": "Fin",
  "Categoria": "Categoría",
  "Comando CLI": "Comando CLI",
  "Consulta SQL": "Consulta SQL",
  "Ambiente": "Entorno",
  "Limite de linhas": "Límite de líneas",
  "Analyze": "Analyze",
  "Sim": "Sí",
  "Não": "No",
  "Código de saída": "Código de salida",
  "Saída truncada": "Salida truncada",
  "Parâmetros enviados": "Parámetros enviados",
  "Saída da ferramenta": "Salida de la herramienta",
  "Metadados adicionais": "Metadatos adicionales",
  "Copiar saída": "Copiar salida",
  "Expanded execution {{id}}": "Ejecución expandida {{id}}",
});

Object.assign(literalResources["en-US"], {
  "Abrir página de autorização": "Open authorization page",
  'Agente "{{name}}" criado!': 'Agent "{{name}}" created!',
  'Ao remover "{{name}}", os bots vinculados continuam no workspace atual e voltam para Sem squad.':
    'When removing "{{name}}", linked bots remain in the current workspace and return to No squad.',
  'Ao remover "{{name}}", os bots vinculados voltam para Sem workspace.':
    'When removing "{{name}}", linked bots return to No workspace.',
  "Autenticação": "Authentication",
  "cada item precisa ser um objeto JSON (indice {{index}})": "each item must be a JSON object (index {{index}})",
  "Display name e obrigatorio.": "Display name is required.",
  "Estes defaults valem para todo o sistema. Cada bot ainda pode sobrescrever isso no seu próprio envelope de recursos.":
    "These defaults apply to the entire system. Each bot can still override them in its own resource envelope.",
  "Health port e obrigatorio.": "Health port is required.",
  "Health port precisa ser um inteiro entre 1 e 65535.": "Health port must be an integer between 1 and 65535.",
  "indisponível no momento": "unavailable right now",
  "JSON invalido": "Invalid JSON",
  "Modelos padrão por funcionalidade": "Default models by function",
  "o valor precisa ser um array JSON": "the value must be a JSON array",
  "o valor precisa ser um objeto JSON": "the value must be a JSON object",
  "Padrão do sistema": "System default",
  "Personalizado": "Custom",
  'Segredo "{{key}}" removido.': 'Secret "{{key}}" removed.',
  'Segredo "{{key}}" salvo.': 'Secret "{{key}}" saved.',
  'Segredo local "{{key}}" preparada no rascunho.': 'Local secret "{{key}}" prepared in draft.',
  'Segredo local "{{key}}" removido.': 'Local secret "{{key}}" removed.',
  'Segredo local "{{key}}" salvo.': 'Local secret "{{key}}" saved.',
  "Selecione a voz padrão": "Select the default voice",
  "Selecione um modelo padrão": "Select a default model",
  "Servidor local": "Local server",
  "Servidor Ollama": "Ollama server",
  "Storage namespace e obrigatorio.": "Storage namespace is required.",
  'Tem certeza que deseja remover "{{name}}"? Todas as configuracoes, documentos e versoes serao permanentemente excluidos. Esta acao nao pode ser desfeita.':
    'Are you sure you want to remove "{{name}}"? All settings, documents and versions will be permanently deleted. This action cannot be undone.',
  "Timeout": "Timeout",
  "Use um endpoint local ou remoto compatível com a API do Ollama para listar e executar modelos.":
    "Use a local or remote endpoint compatible with the Ollama API to list and run models.",
  'Variável local "{{key}}" preparada no rascunho.': 'Local variable "{{key}}" prepared in draft.',
  'Variável local "{{key}}" removida do rascunho.': 'Local variable "{{key}}" removed from draft.',
  "Vindo do .env": "From .env",
  "Voce e um assistente especializado em...\n\nSeu objetivo e ajudar usuarios a...\n\nRegras:\n- Seja claro e objetivo\n- Responda sempre em portugues":
    "You are an assistant specialized in...\n\nYour goal is to help users with...\n\nRules:\n- Be clear and objective\n- Always respond in English",
  "Identidade operacional, diretórios e timezone padrão.": "Operational identity, directories and default timezone.",
  "Providers, fallback e orçamento global.": "Providers, fallback and global budget.",
  "Marketplace de serviços e credenciais guiadas.": "Service marketplace and guided credentials.",
  "Memória persistente, RAG grounded e autonomia operacional.": "Persistent memory, grounded RAG and operational autonomy.",
  "Variáveis e segredos globais customizados.": "Custom global variables and secrets.",
  "Resumo executivo, avisos e aplicação das mudanças.": "Executive summary, warnings and change application.",
  "Bot not found": "Bot not found",
  "Invalid task id": "Invalid task id",
  "Execution not found": "Execution not found",
  "Consulta {{tool}} executada com falha.": "Query {{tool}} executed with failure.",
  "Consulta {{tool}} executada.": "Query {{tool}} executed.",
  "Ferramenta {{tool}}.": "Tool {{tool}}.",
  "Comando {{tool}} falhou: {{args}}": "Command {{tool}} failed: {{args}}",
  "Comando {{tool}} executado: {{args}}": "Command {{tool}} executed: {{args}}",
  "Ferramenta {{tool}} finalizou com erro.": "Tool {{tool}} finished with an error.",
  "Ferramenta {{tool}} executada.": "Tool {{tool}} executed.",
  "Evento": "Event",
  "Execução criada": "Execution created",
  "A tarefa foi registrada na fila.": "The task was registered in the queue.",
  "Processamento iniciado": "Processing started",
  "A tarefa entrou em execução.": "The task entered execution.",
  "ferramenta": "tool",
  "Ferramenta {{tool}}": "Tool {{tool}}",
  "Tarefa atribuída": "Task assigned",
  "Nova tentativa": "New attempt",
  "Execução falhou": "Execution failed",
  "Execução concluída": "Execution completed",
  "Enviada para DLQ": "Sent to DLQ",
  "Custo registrado": "Cost recorded",
  "Execução encerrada": "Execution closed",
  "A execução utilizou o modelo {{model}}.": "The execution used the {{model}} model.",
  "O fluxo acionou {{count}} ferramenta(s) durante a resolução.": "The flow triggered {{count}} tool(s) during resolution.",
  "A resposta foi gerada sem ferramentas auxiliares registradas.": "The response was generated without registered auxiliary tools.",
  "O ciclo do assistente terminou com stop reason '{{reason}}'.": "The assistant cycle ended with stop reason '{{reason}}'.",
  "Foram detectados {{count}} warning(s) operacionais.": "{{count}} operational warning(s) were detected.",
  "A execução concluiu na tentativa {{attempt}} de {{maxAttempts}}.": "The execution completed on attempt {{attempt}} of {{maxAttempts}}.",
  "A execução terminou em {{status}} após {{attempt}} tentativa(s).": "The execution ended in {{status}} after {{attempt}} attempt(s).",
  "Trace consolidado": "Consolidated trace",
  "Envelope completo persistido em task.execution_trace.": "Full envelope persisted in task.execution_trace.",
  "Registro da tabela queries": "Queries table record",
  "Entrada de fallback usada para recuperar a resposta final.": "Fallback entry used to recover the final response.",
  "Payload bruto legado usado para reconstrução best-effort.": "Legacy raw payload used for best-effort reconstruction.",
});

Object.assign(literalResources["es-ES"], {
  "Abrir página de autorização": "Abrir página de autorización",
  'Agente "{{name}}" criado!': '¡Agente "{{name}}" creado!',
  'Ao remover "{{name}}", os bots vinculados continuam no workspace atual e voltam para Sem squad.':
    'Al eliminar "{{name}}", los bots vinculados permanecen en el workspace actual y vuelven a Sin equipo.',
  'Ao remover "{{name}}", os bots vinculados voltam para Sem workspace.':
    'Al eliminar "{{name}}", los bots vinculados vuelven a Sin workspace.',
  "Autenticação": "Autenticación",
  "cada item precisa ser um objeto JSON (indice {{index}})": "cada elemento debe ser un objeto JSON (índice {{index}})",
  "Display name e obrigatorio.": "El display name es obligatorio.",
  "Estes defaults valem para todo o sistema. Cada bot ainda pode sobrescrever isso no seu próprio envelope de recursos.":
    "Estos defaults aplican a todo el sistema. Cada bot aún puede sobrescribirlos en su propio envelope de recursos.",
  "Health port e obrigatorio.": "El health port es obligatorio.",
  "Health port precisa ser um inteiro entre 1 e 65535.": "El health port debe ser un entero entre 1 y 65535.",
  "indisponível no momento": "no disponible en este momento",
  "JSON invalido": "JSON inválido",
  "Modelos padrão por funcionalidade": "Modelos predeterminados por funcionalidad",
  "o valor precisa ser um array JSON": "el valor debe ser un array JSON",
  "o valor precisa ser um objeto JSON": "el valor debe ser un objeto JSON",
  "Padrão do sistema": "Predeterminado del sistema",
  "Personalizado": "Personalizado",
  'Segredo "{{key}}" removido.': 'Secreto "{{key}}" eliminado.',
  'Segredo "{{key}}" salvo.': 'Secreto "{{key}}" guardado.',
  'Segredo local "{{key}}" preparada no rascunho.': 'Secreto local "{{key}}" preparado en el borrador.',
  'Segredo local "{{key}}" removido.': 'Secreto local "{{key}}" eliminado.',
  'Segredo local "{{key}}" salvo.': 'Secreto local "{{key}}" guardado.',
  "Selecione a voz padrão": "Selecciona la voz predeterminada",
  "Selecione um modelo padrão": "Selecciona un modelo predeterminado",
  "Servidor local": "Servidor local",
  "Servidor Ollama": "Servidor Ollama",
  "Storage namespace e obrigatorio.": "El storage namespace es obligatorio.",
  'Tem certeza que deseja remover "{{name}}"? Todas as configuracoes, documentos e versoes serao permanentemente excluidos. Esta acao nao pode ser desfeita.':
    '¿Seguro que quieres eliminar "{{name}}"? Todas las configuraciones, documentos y versiones se eliminarán permanentemente. Esta acción no se puede deshacer.',
  "Timeout": "Tiempo de espera",
  "Use um endpoint local ou remoto compatível com a API do Ollama para listar e executar modelos.":
    "Usa un endpoint local o remoto compatible con la API de Ollama para listar y ejecutar modelos.",
  'Variável local "{{key}}" preparada no rascunho.': 'Variable local "{{key}}" preparada en el borrador.',
  'Variável local "{{key}}" removida do rascunho.': 'Variable local "{{key}}" eliminada del borrador.',
  "Vindo do .env": "Desde .env",
  "Voce e um assistente especializado em...\n\nSeu objetivo e ajudar usuarios a...\n\nRegras:\n- Seja claro e objetivo\n- Responda sempre em portugues":
    "Eres un asistente especializado en...\n\nTu objetivo es ayudar a los usuarios a...\n\nReglas:\n- Sé claro y objetivo\n- Responde siempre en español",
  "Identidade operacional, diretórios e timezone padrão.": "Identidad operativa, directorios y zona horaria predeterminada.",
  "Providers, fallback e orçamento global.": "Providers, fallback y presupuesto global.",
  "Marketplace de serviços e credenciais guiadas.": "Marketplace de servicios y credenciales guiadas.",
  "Memória persistente, RAG grounded e autonomia operacional.": "Memoria persistente, RAG grounded y autonomía operativa.",
  "Variáveis e segredos globais customizados.": "Variables y secretos globales personalizados.",
  "Resumo executivo, avisos e aplicação das mudanças.": "Resumen ejecutivo, avisos y aplicación de cambios.",
  "Bot not found": "Bot no encontrado",
  "Invalid task id": "ID de ejecución inválido",
  "Execution not found": "Ejecución no encontrada",
  "Consulta {{tool}} executada com falha.": "Consulta {{tool}} ejecutada con fallo.",
  "Consulta {{tool}} executada.": "Consulta {{tool}} ejecutada.",
  "Ferramenta {{tool}}.": "Herramienta {{tool}}.",
  "Comando {{tool}} falhou: {{args}}": "El comando {{tool}} falló: {{args}}",
  "Comando {{tool}} executado: {{args}}": "Comando {{tool}} ejecutado: {{args}}",
  "Ferramenta {{tool}} finalizou com erro.": "La herramienta {{tool}} finalizó con error.",
  "Ferramenta {{tool}} executada.": "Herramienta {{tool}} ejecutada.",
  "Evento": "Evento",
  "Execução criada": "Ejecución creada",
  "A tarefa foi registrada na fila.": "La tarea se registró en la cola.",
  "Processamento iniciado": "Procesamiento iniciado",
  "A tarefa entrou em execução.": "La tarea entró en ejecución.",
  "ferramenta": "herramienta",
  "Ferramenta {{tool}}": "Herramienta {{tool}}",
  "Tarefa atribuída": "Tarea asignada",
  "Nova tentativa": "Nuevo intento",
  "Execução falhou": "La ejecución falló",
  "Execução concluída": "Ejecución concluida",
  "Enviada para DLQ": "Enviada a DLQ",
  "Custo registrado": "Costo registrado",
  "Execução encerrada": "Ejecución cerrada",
  "A execução utilizou o modelo {{model}}.": "La ejecución utilizó el modelo {{model}}.",
  "O fluxo acionou {{count}} ferramenta(s) durante a resolução.": "El flujo activó {{count}} herramienta(s) durante la resolución.",
  "A resposta foi gerada sem ferramentas auxiliares registradas.": "La respuesta se generó sin herramientas auxiliares registradas.",
  "O ciclo do assistente terminou com stop reason '{{reason}}'.": "El ciclo del asistente terminó con stop reason '{{reason}}'.",
  "Foram detectados {{count}} warning(s) operacionais.": "Se detectaron {{count}} warning(s) operativos.",
  "A execução concluiu na tentativa {{attempt}} de {{maxAttempts}}.": "La ejecución concluyó en el intento {{attempt}} de {{maxAttempts}}.",
  "A execução terminou em {{status}} após {{attempt}} tentativa(s).": "La ejecución terminó en estado {{status}} después de {{attempt}} intento(s).",
  "Trace consolidado": "Trace consolidado",
  "Envelope completo persistido em task.execution_trace.": "Envelope completo persistido en task.execution_trace.",
  "Registro da tabela queries": "Registro de la tabla queries",
  "Entrada de fallback usada para recuperar a resposta final.": "Entrada de fallback utilizada para recuperar la respuesta final.",
  "Payload bruto legado usado para reconstrução best-effort.": "Payload bruto legado utilizado para reconstrucción best-effort.",
});

mutableResources["en-US"].translation.setup = {
  stepper: { of: "{{current}} of {{total}}" },
  setupCode: {
    title: "Paste your setup code",
    subtitle: "The installer printed it when you ran the bootstrap command.",
    placeholder: "ABCD-EFGH-JKLM",
    submit: "Continue",
    submitting: "Connecting…",
    recoveryLink: "Use recovery token instead",
  },
  registerOwner: {
    title: "Create the owner account",
    subtitle: "This account will sign in to the operator console.",
    displayName: "Display name",
    username: "Username",
    email: "Email",
    password: "Password",
    submit: "Create account",
    submitting: "Creating account…",
    showPassword: "Show password",
    hidePassword: "Hide password",
  },
  login: {
    title: "Sign in to continue",
    subtitle: "Use your owner account credentials.",
    identifier: "Username or email",
    password: "Password",
    submit: "Sign in",
    submitting: "Signing in…",
    recoveryLink: "Use recovery token instead",
  },
  finishPlatform: {
    title: "Finish platform setup",
    subtitle: "Set access, provider, and optionally your first agent.",
    submit: "Finish setup",
    submitting: "Finishing…",
    providerConfigured: "Configured",
    providerVerified: "Verified",
    sections: { access: "Access", provider: "Provider", agent: "First agent" },
    fields: {
      allowedUserIds: "Allowed user IDs",
      ownerName: "Owner name",
      ownerEmail: "Owner email",
      ownerGithub: "GitHub handle",
      provider: "Provider",
      authMode: "Authentication",
      apiKey: "API key",
      projectId: "Project ID",
      baseUrl: "Base URL",
      createAgentNow: "Create the first agent now",
      agentId: "Agent ID",
      agentDisplayName: "Agent name",
      agentTelegramToken: "Telegram token",
    },
    authModes: { api_key: "API key", local: "Local" },
    hints: {
      allowedUserIds: "Comma-separated Telegram user IDs permitted to operate agents.",
      apiKeyOptionalWhenConfigured: "Leave blank to keep the currently configured key.",
      agentOptional: "You can create agents later from the Agents console.",
    },
  },
  recoveryToken: {
    title: "Use recovery token",
    subtitle: "Paste the full recovery token printed by the installer.",
    placeholder: "koda-recovery-…",
    submit: "Exchange token",
    submitting: "Exchanging…",
    backToSetupCode: "Use setup code instead",
  },
  errors: {
    codeRequired: "Enter the setup code first.",
    codeInvalid: "That setup code didn't work. Try again or regenerate one.",
    passwordTooShort: "Password must be at least 8 characters.",
    emailInvalid: "That doesn't look like a valid email.",
    usernameRequired: "Username is required.",
    credentialsRequired: "Fill in both identifier and password.",
    bootstrapIncomplete: "Complete access and provider before finishing.",
    storageNotReady: "Storage is not fully ready. Check the installer output before continuing.",
    generic: "Something went wrong. Please try again.",
  },
};

mutableResources["pt-BR"].translation.setup = {
  stepper: { of: "{{current}} de {{total}}" },
  setupCode: {
    title: "Cole seu código de setup",
    subtitle: "O instalador imprimiu-o ao rodar o comando de bootstrap.",
    placeholder: "ABCD-EFGH-JKLM",
    submit: "Continuar",
    submitting: "Conectando…",
    recoveryLink: "Usar token de recuperação",
  },
  registerOwner: {
    title: "Crie a conta owner",
    subtitle: "Esta conta fará login no console de operação.",
    displayName: "Nome de exibição",
    username: "Usuário",
    email: "Email",
    password: "Senha",
    submit: "Criar conta",
    submitting: "Criando conta…",
    showPassword: "Mostrar senha",
    hidePassword: "Ocultar senha",
  },
  login: {
    title: "Entre para continuar",
    subtitle: "Use as credenciais da conta owner.",
    identifier: "Usuário ou email",
    password: "Senha",
    submit: "Entrar",
    submitting: "Entrando…",
    recoveryLink: "Usar token de recuperação",
  },
  finishPlatform: {
    title: "Finalize a configuração",
    subtitle: "Defina acesso, provedor e opcionalmente o primeiro agente.",
    submit: "Finalizar setup",
    submitting: "Finalizando…",
    providerConfigured: "Configurado",
    providerVerified: "Verificado",
    sections: { access: "Acesso", provider: "Provedor", agent: "Primeiro agente" },
    fields: {
      allowedUserIds: "IDs de usuário permitidos",
      ownerName: "Nome do owner",
      ownerEmail: "Email do owner",
      ownerGithub: "GitHub",
      provider: "Provedor",
      authMode: "Autenticação",
      apiKey: "API key",
      projectId: "Project ID",
      baseUrl: "Base URL",
      createAgentNow: "Criar o primeiro agente agora",
      agentId: "ID do agente",
      agentDisplayName: "Nome do agente",
      agentTelegramToken: "Telegram token",
    },
    authModes: { api_key: "API key", local: "Local" },
    hints: {
      allowedUserIds: "IDs de usuário do Telegram autorizados (separados por vírgula).",
      apiKeyOptionalWhenConfigured: "Deixe em branco para manter a chave configurada atualmente.",
      agentOptional: "Você pode criar agentes depois pelo console de Agentes.",
    },
  },
  recoveryToken: {
    title: "Usar token de recuperação",
    subtitle: "Cole o token de recuperação completo impresso pelo instalador.",
    placeholder: "koda-recovery-…",
    submit: "Trocar token",
    submitting: "Trocando…",
    backToSetupCode: "Usar código de setup",
  },
  errors: {
    codeRequired: "Informe o código primeiro.",
    codeInvalid: "Esse código não funcionou. Tente novamente ou gere outro.",
    passwordTooShort: "A senha precisa ter ao menos 8 caracteres.",
    emailInvalid: "Email inválido.",
    usernameRequired: "Usuário é obrigatório.",
    credentialsRequired: "Preencha usuário/email e senha.",
    bootstrapIncomplete: "Complete acesso e provedor antes de finalizar.",
    storageNotReady: "Storage não está totalmente pronto. Verifique o instalador.",
    generic: "Algo deu errado. Tente novamente.",
  },
};

mutableResources["es-ES"].translation.setup = {
  stepper: { of: "{{current}} de {{total}}" },
  setupCode: {
    title: "Pega tu código de setup",
    subtitle: "El instalador lo imprimió al ejecutar el comando de bootstrap.",
    placeholder: "ABCD-EFGH-JKLM",
    submit: "Continuar",
    submitting: "Conectando…",
    recoveryLink: "Usar token de recuperación",
  },
  registerOwner: {
    title: "Crea la cuenta owner",
    subtitle: "Esta cuenta iniciará sesión en la consola de operación.",
    displayName: "Nombre visible",
    username: "Usuario",
    email: "Correo",
    password: "Contraseña",
    submit: "Crear cuenta",
    submitting: "Creando cuenta…",
    showPassword: "Mostrar contraseña",
    hidePassword: "Ocultar contraseña",
  },
  login: {
    title: "Inicia sesión para continuar",
    subtitle: "Usa las credenciales de la cuenta owner.",
    identifier: "Usuario o correo",
    password: "Contraseña",
    submit: "Entrar",
    submitting: "Entrando…",
    recoveryLink: "Usar token de recuperación",
  },
  finishPlatform: {
    title: "Termina la configuración",
    subtitle: "Define acceso, proveedor y opcionalmente el primer agente.",
    submit: "Finalizar setup",
    submitting: "Finalizando…",
    providerConfigured: "Configurado",
    providerVerified: "Verificado",
    sections: { access: "Acceso", provider: "Proveedor", agent: "Primer agente" },
    fields: {
      allowedUserIds: "IDs de usuario permitidos",
      ownerName: "Nombre del owner",
      ownerEmail: "Correo del owner",
      ownerGithub: "GitHub",
      provider: "Proveedor",
      authMode: "Autenticación",
      apiKey: "API key",
      projectId: "Project ID",
      baseUrl: "Base URL",
      createAgentNow: "Crear el primer agente ahora",
      agentId: "ID del agente",
      agentDisplayName: "Nombre del agente",
      agentTelegramToken: "Telegram token",
    },
    authModes: { api_key: "API key", local: "Local" },
    hints: {
      allowedUserIds: "IDs de Telegram autorizados (separados por coma).",
      apiKeyOptionalWhenConfigured: "Déjalo vacío para mantener la clave actual.",
      agentOptional: "Puedes crear agentes luego desde la consola de Agentes.",
    },
  },
  recoveryToken: {
    title: "Usar token de recuperación",
    subtitle: "Pega el token de recuperación completo impreso por el instalador.",
    placeholder: "koda-recovery-…",
    submit: "Canjear token",
    submitting: "Canjeando…",
    backToSetupCode: "Usar código de setup",
  },
  errors: {
    codeRequired: "Introduce el código primero.",
    codeInvalid: "Ese código no funcionó. Intenta de nuevo o genera otro.",
    passwordTooShort: "La contraseña debe tener al menos 8 caracteres.",
    emailInvalid: "Correo inválido.",
    usernameRequired: "Se requiere usuario.",
    credentialsRequired: "Completa usuario/correo y contraseña.",
    bootstrapIncomplete: "Completa acceso y proveedor antes de finalizar.",
    storageNotReady: "El almacenamiento no está listo. Verifica el instalador.",
    generic: "Algo falló. Intenta de nuevo.",
  },
};

mutableResources["fr-FR"].translation.setup = {
  stepper: { of: "{{current}} sur {{total}}" },
  setupCode: {
    title: "Collez votre code d'installation",
    subtitle: "L'installeur l'a imprimé lorsque vous avez exécuté la commande bootstrap.",
    placeholder: "ABCD-EFGH-JKLM",
    submit: "Continuer",
    submitting: "Connexion en cours…",
    recoveryLink: "Utiliser un jeton de récupération à la place",
  },
  registerOwner: {
    title: "Créer le compte propriétaire",
    subtitle: "Ce compte se connectera à la console opérateur.",
    displayName: "Nom affiché",
    username: "Nom d'utilisateur",
    email: "E-mail",
    password: "Mot de passe",
    submit: "Créer le compte",
    submitting: "Création du compte…",
    showPassword: "Afficher le mot de passe",
    hidePassword: "Masquer le mot de passe",
  },
  login: {
    title: "Connectez-vous pour continuer",
    subtitle: "Utilisez les identifiants de votre compte propriétaire.",
    identifier: "Nom d'utilisateur ou e-mail",
    password: "Mot de passe",
    submit: "Se connecter",
    submitting: "Connexion…",
    recoveryLink: "Utiliser un jeton de récupération à la place",
  },
  finishPlatform: {
    title: "Finaliser la configuration de la plateforme",
    subtitle: "Définissez accès, fournisseur et éventuellement votre premier agent.",
    submit: "Terminer la configuration",
    submitting: "Finalisation…",
    providerConfigured: "Configuré",
    providerVerified: "Vérifié",
    sections: { access: "Accès", provider: "Fournisseur", agent: "Premier agent" },
    fields: {
      allowedUserIds: "IDs d'utilisateurs autorisés",
      ownerName: "Nom du propriétaire",
      ownerEmail: "E-mail du propriétaire",
      ownerGithub: "Identifiant GitHub",
      provider: "Fournisseur",
      authMode: "Authentification",
      apiKey: "Clé API",
      projectId: "ID du projet",
      baseUrl: "URL de base",
      createAgentNow: "Créer le premier agent maintenant",
      agentId: "ID de l'agent",
      agentDisplayName: "Nom de l'agent",
      agentTelegramToken: "Jeton Telegram",
    },
    authModes: { api_key: "Clé API", local: "Local" },
    hints: {
      allowedUserIds: "IDs d'utilisateurs Telegram autorisés à opérer les agents, séparés par des virgules.",
      apiKeyOptionalWhenConfigured: "Laissez vide pour conserver la clé actuellement configurée.",
      agentOptional: "Vous pourrez créer des agents plus tard depuis la console Agents.",
    },
  },
  recoveryToken: {
    title: "Utiliser un jeton de récupération",
    subtitle: "Collez le jeton de récupération complet imprimé par l'installeur.",
    placeholder: "koda-recovery-…",
    submit: "Échanger le jeton",
    submitting: "Échange en cours…",
    backToSetupCode: "Utiliser le code d'installation à la place",
  },
  errors: {
    codeRequired: "Saisissez d'abord le code d'installation.",
    codeInvalid: "Ce code d'installation n'a pas fonctionné. Réessayez ou régénérez-en un.",
    passwordTooShort: "Le mot de passe doit contenir au moins 8 caractères.",
    emailInvalid: "Cela ne ressemble pas à un e-mail valide.",
    usernameRequired: "Le nom d'utilisateur est requis.",
    credentialsRequired: "Remplissez à la fois l'identifiant et le mot de passe.",
    bootstrapIncomplete: "Complétez accès et fournisseur avant de terminer.",
    storageNotReady: "Le stockage n'est pas prêt. Vérifiez la sortie de l'installeur avant de continuer.",
    generic: "Une erreur est survenue. Veuillez réessayer.",
  },
};

mutableResources["de-DE"].translation.setup = {
  stepper: { of: "{{current}} von {{total}}" },
  setupCode: {
    title: "Fügen Sie Ihren Installationscode ein",
    subtitle: "Der Installer hat ihn ausgegeben, als Sie den Bootstrap-Befehl ausgeführt haben.",
    placeholder: "ABCD-EFGH-JKLM",
    submit: "Weiter",
    submitting: "Verbindung…",
    recoveryLink: "Stattdessen Wiederherstellungstoken verwenden",
  },
  registerOwner: {
    title: "Besitzerkonto erstellen",
    subtitle: "Dieses Konto meldet sich an der Operator-Konsole an.",
    displayName: "Anzeigename",
    username: "Benutzername",
    email: "E-Mail",
    password: "Passwort",
    submit: "Konto erstellen",
    submitting: "Konto wird erstellt…",
    showPassword: "Passwort anzeigen",
    hidePassword: "Passwort ausblenden",
  },
  login: {
    title: "Melden Sie sich zum Fortfahren an",
    subtitle: "Verwenden Sie die Zugangsdaten Ihres Besitzerkontos.",
    identifier: "Benutzername oder E-Mail",
    password: "Passwort",
    submit: "Anmelden",
    submitting: "Anmeldung…",
    recoveryLink: "Stattdessen Wiederherstellungstoken verwenden",
  },
  finishPlatform: {
    title: "Plattform-Setup abschließen",
    subtitle: "Legen Sie Zugang, Anbieter und optional Ihren ersten Agenten fest.",
    submit: "Setup abschließen",
    submitting: "Abschluss…",
    providerConfigured: "Konfiguriert",
    providerVerified: "Verifiziert",
    sections: { access: "Zugang", provider: "Anbieter", agent: "Erster Agent" },
    fields: {
      allowedUserIds: "Zulässige Benutzer-IDs",
      ownerName: "Name des Besitzers",
      ownerEmail: "E-Mail des Besitzers",
      ownerGithub: "GitHub-Benutzername",
      provider: "Anbieter",
      authMode: "Authentifizierung",
      apiKey: "API-Schlüssel",
      projectId: "Projekt-ID",
      baseUrl: "Basis-URL",
      createAgentNow: "Ersten Agenten jetzt erstellen",
      agentId: "Agent-ID",
      agentDisplayName: "Agent-Name",
      agentTelegramToken: "Telegram-Token",
    },
    authModes: { api_key: "API-Schlüssel", local: "Lokal" },
    hints: {
      allowedUserIds: "Durch Kommas getrennte Telegram-Benutzer-IDs, die Agenten bedienen dürfen.",
      apiKeyOptionalWhenConfigured: "Leer lassen, um den aktuell konfigurierten Schlüssel zu behalten.",
      agentOptional: "Sie können Agenten später in der Agenten-Konsole erstellen.",
    },
  },
  recoveryToken: {
    title: "Wiederherstellungstoken verwenden",
    subtitle: "Fügen Sie das vollständige Wiederherstellungstoken ein, das der Installer ausgegeben hat.",
    placeholder: "koda-recovery-…",
    submit: "Token austauschen",
    submitting: "Austausch…",
    backToSetupCode: "Stattdessen Installationscode verwenden",
  },
  errors: {
    codeRequired: "Geben Sie zuerst den Installationscode ein.",
    codeInvalid: "Dieser Installationscode hat nicht funktioniert. Versuchen Sie es erneut oder generieren Sie einen neuen.",
    passwordTooShort: "Das Passwort muss mindestens 8 Zeichen lang sein.",
    emailInvalid: "Das sieht nicht wie eine gültige E-Mail aus.",
    usernameRequired: "Benutzername ist erforderlich.",
    credentialsRequired: "Füllen Sie sowohl Kennung als auch Passwort aus.",
    bootstrapIncomplete: "Schließen Sie Zugang und Anbieter ab, bevor Sie fertigstellen.",
    storageNotReady: "Der Speicher ist nicht bereit. Prüfen Sie die Installer-Ausgabe, bevor Sie fortfahren.",
    generic: "Etwas ist schiefgelaufen. Bitte versuchen Sie es erneut.",
  },
};

// Memory area translation completeness — added for the neural memory map redesign.
const MEMORY_SHARED_I18N = {
  "en-US": {
    common: { allSessions: "All sessions", allUsers: "All users", filters: "Filters", session: "Session" },
    empty: {
      title: "No memories yet",
      description:
        "Memories will appear here as a network of connected dots as this agent converses.",
    },
    filters: {
      title: "Filters",
      search: "Search",
      searchPlaceholder: "keywords",
      timeWindow: "Window",
      includeInactive: "Include inactive",
      edges: { semantic: "Semantic", session: "Session", source: "Origin" },
    },
    page: {
      noAgentsTitle: "No agents available",
      noAgentsDescription: "Create or publish at least one agent before opening the map.",
    },
    views: { map: "Map", curation: "Curation" },
    mapExt: { canvasAriaLabel: "Neural memory map", clusters: "Clusters" },
    inspectorExt: {
      content: "Content",
      details: "Details",
      empty: "No node selected. Explore the map to start.",
      expiresAt: "Expires",
      members: "Members",
      never: "No expiration",
      recenter: "Recenter",
      selectPointHint: "Click a point on the graph to see its details here.",
    },
  },
  "pt-BR": {
    common: {
      allSessions: "Todas as sessões",
      allUsers: "Todos os usuários",
      filters: "Filtros",
      session: "Sessão",
    },
    empty: {
      title: "Sem memórias ainda",
      description:
        "As memórias aparecerão aqui como uma rede de pontos conectados conforme este agente conversa.",
    },
    filters: {
      title: "Filtros",
      search: "Buscar",
      searchPlaceholder: "palavras-chave",
      timeWindow: "Janela",
      includeInactive: "Incluir inativas",
      edges: { semantic: "Semânticas", session: "Sessão", source: "Origem" },
    },
    page: {
      noAgentsTitle: "Sem agentes disponíveis",
      noAgentsDescription: "Crie ou publique ao menos um agente antes de abrir o mapa.",
    },
    views: { map: "Mapa", curation: "Curadoria" },
    mapExt: { canvasAriaLabel: "Mapa neural de memórias", clusters: "Clusters" },
    inspectorExt: {
      content: "Conteúdo",
      details: "Detalhes",
      empty: "Nenhum nó selecionado. Explore o mapa para começar.",
      expiresAt: "Expira",
      members: "Membros",
      never: "Sem prazo",
      recenter: "Centralizar",
      selectPointHint: "Clique em um ponto do grafo para ver seus detalhes aqui.",
    },
  },
  "es-ES": {
    common: {
      allSessions: "Todas las sesiones",
      allUsers: "Todos los usuarios",
      filters: "Filtros",
      session: "Sesión",
    },
    empty: {
      title: "Aún no hay memorias",
      description:
        "Las memorias aparecerán aquí como una red de puntos conectados a medida que este agente conversa.",
    },
    filters: {
      title: "Filtros",
      search: "Buscar",
      searchPlaceholder: "palabras clave",
      timeWindow: "Ventana",
      includeInactive: "Incluir inactivas",
      edges: { semantic: "Semánticas", session: "Sesión", source: "Origen" },
    },
    page: {
      noAgentsTitle: "No hay agentes disponibles",
      noAgentsDescription: "Crea o publica al menos un agente antes de abrir el mapa.",
    },
    views: { map: "Mapa", curation: "Curación" },
    mapExt: { canvasAriaLabel: "Mapa neuronal de memorias", clusters: "Clústeres" },
    inspectorExt: {
      content: "Contenido",
      details: "Detalles",
      empty: "Ningún nodo seleccionado. Explora el mapa para empezar.",
      expiresAt: "Expira",
      members: "Miembros",
      never: "Sin expiración",
      recenter: "Recentrar",
      selectPointHint: "Haz clic en un punto del grafo para ver sus detalles aquí.",
    },
  },
  "fr-FR": {
    common: {
      allSessions: "Toutes les sessions",
      allUsers: "Tous les utilisateurs",
      close: "Fermer",
      filters: "Filtres",
      session: "Session",
    },
    empty: {
      title: "Aucune mémoire pour l'instant",
      description:
        "Les mémoires apparaîtront ici sous forme de réseau de points connectés à mesure que cet agent converse.",
    },
    filters: {
      title: "Filtres",
      search: "Rechercher",
      searchPlaceholder: "mots-clés",
      timeWindow: "Fenêtre",
      includeInactive: "Inclure inactives",
      edges: { semantic: "Sémantique", session: "Session", source: "Origine" },
    },
    page: {
      noAgentsTitle: "Aucun agent disponible",
      noAgentsDescription: "Créez ou publiez au moins un agent avant d'ouvrir la carte.",
    },
    views: { map: "Carte", curation: "Curation" },
    mapExt: {
      canvasAriaLabel: "Carte neurale des mémoires",
      clusters: "Groupes",
      zoomIn: "Zoomer",
      zoomOut: "Dézoomer",
      reset: "Recentrer",
    },
    inspectorExt: {
      content: "Contenu",
      details: "Détails",
      empty: "Aucun nœud sélectionné. Explorez la carte pour commencer.",
      expiresAt: "Expire",
      members: "Membres",
      never: "Sans expiration",
      recenter: "Recentrer",
      selectPointHint: "Cliquez sur un point du graphe pour voir ses détails ici.",
    },
  },
  "de-DE": {
    common: {
      allSessions: "Alle Sitzungen",
      allUsers: "Alle Nutzer",
      close: "Schließen",
      filters: "Filter",
      session: "Sitzung",
    },
    empty: {
      title: "Noch keine Erinnerungen",
      description:
        "Erinnerungen erscheinen hier als Netz verbundener Punkte, während dieser Agent kommuniziert.",
    },
    filters: {
      title: "Filter",
      search: "Suchen",
      searchPlaceholder: "Stichwörter",
      timeWindow: "Zeitraum",
      includeInactive: "Inaktive einbeziehen",
      edges: { semantic: "Semantisch", session: "Sitzung", source: "Quelle" },
    },
    page: {
      noAgentsTitle: "Keine Agenten verfügbar",
      noAgentsDescription: "Erstellen oder veröffentlichen Sie mindestens einen Agenten, bevor Sie die Karte öffnen.",
    },
    views: { map: "Karte", curation: "Kuration" },
    mapExt: {
      canvasAriaLabel: "Neuronale Gedächtniskarte",
      clusters: "Cluster",
      zoomIn: "Vergrößern",
      zoomOut: "Verkleinern",
      reset: "Zentrieren",
    },
    inspectorExt: {
      content: "Inhalt",
      details: "Details",
      empty: "Kein Knoten ausgewählt. Erkunden Sie die Karte, um zu beginnen.",
      expiresAt: "Läuft ab",
      members: "Mitglieder",
      never: "Kein Ablauf",
      recenter: "Zentrieren",
      selectPointHint: "Klicken Sie auf einen Punkt im Graph, um seine Details hier zu sehen.",
    },
  },
} as const;

(Object.keys(MEMORY_SHARED_I18N) as Array<keyof typeof MEMORY_SHARED_I18N>).forEach((lang) => {
  const pack = MEMORY_SHARED_I18N[lang];
  const tr = mutableResources[lang].translation as Record<string, unknown>;
  const common = (tr.common ?? {}) as Record<string, unknown>;
  tr.common = { ...common, ...pack.common };
  const memory = (tr.memory ?? {}) as Record<string, unknown>;
  memory.empty = { ...((memory.empty ?? {}) as Record<string, unknown>), ...pack.empty };
  memory.filters = { ...((memory.filters ?? {}) as Record<string, unknown>), ...pack.filters };
  memory.page = { ...((memory.page ?? {}) as Record<string, unknown>), ...pack.page };
  memory.views = { ...((memory.views ?? {}) as Record<string, unknown>), ...pack.views };
  memory.map = { ...((memory.map ?? {}) as Record<string, unknown>), ...pack.mapExt };
  memory.inspector = {
    ...((memory.inspector ?? {}) as Record<string, unknown>),
    ...pack.inspectorExt,
  };
  tr.memory = memory;
});

const COMMAND_BAR_I18N = {
  "en-US": {
    placeholder: "Search agents, pages, actions…",
    emptyState: "No matches for that query",
    shortcutHint: "⌘K",
    modalTitle: "Command bar",
    agent: { description: "Open agent" },
    groups: { agents: "Agents", pages: "Pages", actions: "Actions", recents: "Recent" },
    pages: {
      home: "Home",
      controlPlane: "Agents catalog",
      memory: "Memory",
      schedules: "Schedules",
      sessions: "Sessions",
      tasks: "Tasks",
      runtime: "Runtime",
      executions: "Executions",
      costs: "Costs",
      dlq: "Dead letter queue",
    },
    recents: { noQuery: "Untitled task" },
  },
  "pt-BR": {
    placeholder: "Buscar agentes, páginas, ações…",
    emptyState: "Nenhum resultado para essa busca",
    shortcutHint: "⌘K",
    modalTitle: "Barra de comandos",
    agent: { description: "Abrir agente" },
    groups: { agents: "Agentes", pages: "Páginas", actions: "Ações", recents: "Recentes" },
    pages: {
      home: "Início",
      controlPlane: "Catálogo de agentes",
      memory: "Memória",
      schedules: "Rotinas",
      sessions: "Sessões",
      tasks: "Tarefas",
      runtime: "Runtime",
      executions: "Execuções",
      costs: "Custos",
      dlq: "Fila de falhas",
    },
    recents: { noQuery: "Tarefa sem título" },
  },
  "es-ES": {
    placeholder: "Buscar agentes, páginas, acciones…",
    emptyState: "Sin resultados para esta búsqueda",
    shortcutHint: "⌘K",
    modalTitle: "Barra de comandos",
    agent: { description: "Abrir agente" },
    groups: { agents: "Agentes", pages: "Páginas", actions: "Acciones", recents: "Recientes" },
    pages: {
      home: "Inicio",
      controlPlane: "Catálogo de agentes",
      memory: "Memoria",
      schedules: "Rutinas",
      sessions: "Sesiones",
      tasks: "Tareas",
      runtime: "Runtime",
      executions: "Ejecuciones",
      costs: "Costos",
      dlq: "Cola de fallos",
    },
    recents: { noQuery: "Tarea sin título" },
  },
  "fr-FR": {
    placeholder: "Rechercher agents, pages, actions…",
    emptyState: "Aucun résultat pour cette recherche",
    shortcutHint: "⌘K",
    modalTitle: "Barre de commandes",
    agent: { description: "Ouvrir l'agent" },
    groups: { agents: "Agents", pages: "Pages", actions: "Actions", recents: "Récents" },
    pages: {
      home: "Accueil",
      controlPlane: "Catalogue d'agents",
      memory: "Mémoire",
      schedules: "Routines",
      sessions: "Sessions",
      tasks: "Tâches",
      runtime: "Runtime",
      executions: "Exécutions",
      costs: "Coûts",
      dlq: "File d'échecs",
    },
    recents: { noQuery: "Tâche sans titre" },
  },
  "de-DE": {
    placeholder: "Agents, Seiten, Aktionen suchen…",
    emptyState: "Keine Ergebnisse für diese Suche",
    shortcutHint: "⌘K",
    modalTitle: "Befehlsleiste",
    agent: { description: "Agent öffnen" },
    groups: { agents: "Agents", pages: "Seiten", actions: "Aktionen", recents: "Zuletzt" },
    pages: {
      home: "Start",
      controlPlane: "Agent-Katalog",
      memory: "Gedächtnis",
      schedules: "Zeitpläne",
      sessions: "Sitzungen",
      tasks: "Aufgaben",
      runtime: "Laufzeit",
      executions: "Ausführungen",
      costs: "Kosten",
      dlq: "Fehlerwarteschlange",
    },
    recents: { noQuery: "Unbenannte Aufgabe" },
  },
} as const;

(Object.keys(COMMAND_BAR_I18N) as Array<keyof typeof COMMAND_BAR_I18N>).forEach((lang) => {
  const tr = mutableResources[lang].translation as Record<string, unknown>;
  tr.commandBar = COMMAND_BAR_I18N[lang];
});


// Auto-appended by fill_v2.py — missing agent-rename aliases and new namespaces.
mutableResources["en-US"].translation.agentDetail ??= {};
mutableResources["en-US"].translation.agentSwitcher ??= {};
mutableResources["en-US"].translation.chat ??= {};
mutableResources["en-US"].translation.commandBar ??= {};
mutableResources["en-US"].translation.common ??= {};
mutableResources["en-US"].translation.controlPlane ??= {};
mutableResources["en-US"].translation.costs ??= {};
mutableResources["en-US"].translation.dashboard ??= {};
mutableResources["en-US"].translation.dlq ??= {};
mutableResources["en-US"].translation.executions ??= {};
mutableResources["en-US"].translation.memory ??= {};
mutableResources["en-US"].translation.overview ??= {};
mutableResources["en-US"].translation.runtime ??= {};
mutableResources["en-US"].translation.schedules ??= {};
mutableResources["en-US"].translation.screenTime ??= {};
mutableResources["en-US"].translation.sessions ??= {};
mutableResources["en-US"].translation.settings ??= {};
mutableResources["en-US"].translation.agentDetail.metrics ??= {};
mutableResources["en-US"].translation.agentDetail.tabs ??= {};
mutableResources["en-US"].translation.chat.composer ??= {};
mutableResources["en-US"].translation.chat.header ??= {};
mutableResources["en-US"].translation.chat.rail ??= {};
mutableResources["en-US"].translation.chat.reasoning ??= {};
mutableResources["en-US"].translation.chat.thread ??= {};
mutableResources["en-US"].translation.chat.timestamp ??= {};
mutableResources["en-US"].translation.chat.toolCall ??= {};
mutableResources["en-US"].translation.commandBar.agent ??= {};
mutableResources["en-US"].translation.commandBar.groups ??= {};
mutableResources["en-US"].translation.commandBar.recents ??= {};
mutableResources["en-US"].translation.controlPlane.create ??= {};
mutableResources["en-US"].translation.controlPlane.policy ??= {};
mutableResources["en-US"].translation.controlPlane.prompt ??= {};
mutableResources["en-US"].translation.controlPlane.saveBar ??= {};
mutableResources["en-US"].translation.costs.page ??= {};
mutableResources["en-US"].translation.dashboard.checklist ??= {};
mutableResources["en-US"].translation.dlq.page ??= {};
mutableResources["en-US"].translation.dlq.table ??= {};
mutableResources["en-US"].translation.executions.page ??= {};
mutableResources["en-US"].translation.memory.curation ??= {};
mutableResources["en-US"].translation.memory.inspector ??= {};
mutableResources["en-US"].translation.memory.map ??= {};
mutableResources["en-US"].translation.memory.page ??= {};
mutableResources["en-US"].translation.overview.activity ??= {};
mutableResources["en-US"].translation.runtime.overview ??= {};
mutableResources["en-US"].translation.schedules.page ??= {};
mutableResources["en-US"].translation.schedules.table ??= {};
mutableResources["en-US"].translation.sessions.composer ??= {};
mutableResources["en-US"].translation.sessions.context ??= {};
mutableResources["en-US"].translation.sessions.detail ??= {};
mutableResources["en-US"].translation.sessions.thread ??= {};
mutableResources["en-US"].translation.settings.sections ??= {};
mutableResources["en-US"].translation.controlPlane.create.name ??= {};
mutableResources["en-US"].translation.costs.page.allocationModes ??= {};
mutableResources["en-US"].translation.costs.page.breakdowns ??= {};
mutableResources["en-US"].translation.costs.page.kpiContexts ??= {};
mutableResources["en-US"].translation.costs.page.timeChart ??= {};
mutableResources["en-US"].translation.executions.page.metrics ??= {};
mutableResources["en-US"].translation.memory.curation.detail ??= {};
mutableResources["en-US"].translation.memory.curation.row ??= {};
mutableResources["en-US"].translation.runtime.overview.metrics ??= {};
mutableResources["en-US"].translation.sessions.context.artifacts ??= {};

mutableResources["pt-BR"].translation.agentDetail ??= {};
mutableResources["pt-BR"].translation.agentSwitcher ??= {};
mutableResources["pt-BR"].translation.chat ??= {};
mutableResources["pt-BR"].translation.commandBar ??= {};
mutableResources["pt-BR"].translation.common ??= {};
mutableResources["pt-BR"].translation.controlPlane ??= {};
mutableResources["pt-BR"].translation.costs ??= {};
mutableResources["pt-BR"].translation.dashboard ??= {};
mutableResources["pt-BR"].translation.dlq ??= {};
mutableResources["pt-BR"].translation.executions ??= {};
mutableResources["pt-BR"].translation.memory ??= {};
mutableResources["pt-BR"].translation.overview ??= {};
mutableResources["pt-BR"].translation.runtime ??= {};
mutableResources["pt-BR"].translation.schedules ??= {};
mutableResources["pt-BR"].translation.screenTime ??= {};
mutableResources["pt-BR"].translation.sessions ??= {};
mutableResources["pt-BR"].translation.settings ??= {};
mutableResources["pt-BR"].translation.agentDetail.metrics ??= {};
mutableResources["pt-BR"].translation.agentDetail.tabs ??= {};
mutableResources["pt-BR"].translation.chat.composer ??= {};
mutableResources["pt-BR"].translation.chat.header ??= {};
mutableResources["pt-BR"].translation.chat.rail ??= {};
mutableResources["pt-BR"].translation.chat.reasoning ??= {};
mutableResources["pt-BR"].translation.chat.thread ??= {};
mutableResources["pt-BR"].translation.chat.timestamp ??= {};
mutableResources["pt-BR"].translation.chat.toolCall ??= {};
mutableResources["pt-BR"].translation.commandBar.agent ??= {};
mutableResources["pt-BR"].translation.commandBar.groups ??= {};
mutableResources["pt-BR"].translation.commandBar.recents ??= {};
mutableResources["pt-BR"].translation.controlPlane.create ??= {};
mutableResources["pt-BR"].translation.controlPlane.policy ??= {};
mutableResources["pt-BR"].translation.controlPlane.prompt ??= {};
mutableResources["pt-BR"].translation.controlPlane.saveBar ??= {};
mutableResources["pt-BR"].translation.costs.page ??= {};
mutableResources["pt-BR"].translation.dashboard.checklist ??= {};
mutableResources["pt-BR"].translation.dlq.page ??= {};
mutableResources["pt-BR"].translation.dlq.table ??= {};
mutableResources["pt-BR"].translation.executions.page ??= {};
mutableResources["pt-BR"].translation.memory.curation ??= {};
mutableResources["pt-BR"].translation.memory.inspector ??= {};
mutableResources["pt-BR"].translation.memory.map ??= {};
mutableResources["pt-BR"].translation.memory.page ??= {};
mutableResources["pt-BR"].translation.overview.activity ??= {};
mutableResources["pt-BR"].translation.runtime.overview ??= {};
mutableResources["pt-BR"].translation.schedules.page ??= {};
mutableResources["pt-BR"].translation.schedules.table ??= {};
mutableResources["pt-BR"].translation.sessions.composer ??= {};
mutableResources["pt-BR"].translation.sessions.context ??= {};
mutableResources["pt-BR"].translation.sessions.detail ??= {};
mutableResources["pt-BR"].translation.sessions.thread ??= {};
mutableResources["pt-BR"].translation.settings.sections ??= {};
mutableResources["pt-BR"].translation.controlPlane.create.name ??= {};
mutableResources["pt-BR"].translation.costs.page.allocationModes ??= {};
mutableResources["pt-BR"].translation.costs.page.breakdowns ??= {};
mutableResources["pt-BR"].translation.costs.page.kpiContexts ??= {};
mutableResources["pt-BR"].translation.costs.page.timeChart ??= {};
mutableResources["pt-BR"].translation.executions.page.metrics ??= {};
mutableResources["pt-BR"].translation.memory.curation.detail ??= {};
mutableResources["pt-BR"].translation.memory.curation.row ??= {};
mutableResources["pt-BR"].translation.runtime.overview.metrics ??= {};
mutableResources["pt-BR"].translation.sessions.context.artifacts ??= {};

mutableResources["es-ES"].translation.agentDetail ??= {};
mutableResources["es-ES"].translation.agentSwitcher ??= {};
mutableResources["es-ES"].translation.chat ??= {};
mutableResources["es-ES"].translation.commandBar ??= {};
mutableResources["es-ES"].translation.common ??= {};
mutableResources["es-ES"].translation.controlPlane ??= {};
mutableResources["es-ES"].translation.costs ??= {};
mutableResources["es-ES"].translation.dashboard ??= {};
mutableResources["es-ES"].translation.dlq ??= {};
mutableResources["es-ES"].translation.executions ??= {};
mutableResources["es-ES"].translation.memory ??= {};
mutableResources["es-ES"].translation.overview ??= {};
mutableResources["es-ES"].translation.runtime ??= {};
mutableResources["es-ES"].translation.schedules ??= {};
mutableResources["es-ES"].translation.screenTime ??= {};
mutableResources["es-ES"].translation.sessions ??= {};
mutableResources["es-ES"].translation.settings ??= {};
mutableResources["es-ES"].translation.agentDetail.metrics ??= {};
mutableResources["es-ES"].translation.agentDetail.tabs ??= {};
mutableResources["es-ES"].translation.chat.composer ??= {};
mutableResources["es-ES"].translation.chat.header ??= {};
mutableResources["es-ES"].translation.chat.rail ??= {};
mutableResources["es-ES"].translation.chat.reasoning ??= {};
mutableResources["es-ES"].translation.chat.thread ??= {};
mutableResources["es-ES"].translation.chat.timestamp ??= {};
mutableResources["es-ES"].translation.chat.toolCall ??= {};
mutableResources["es-ES"].translation.commandBar.agent ??= {};
mutableResources["es-ES"].translation.commandBar.groups ??= {};
mutableResources["es-ES"].translation.commandBar.recents ??= {};
mutableResources["es-ES"].translation.controlPlane.create ??= {};
mutableResources["es-ES"].translation.controlPlane.policy ??= {};
mutableResources["es-ES"].translation.controlPlane.prompt ??= {};
mutableResources["es-ES"].translation.controlPlane.saveBar ??= {};
mutableResources["es-ES"].translation.costs.page ??= {};
mutableResources["es-ES"].translation.dashboard.checklist ??= {};
mutableResources["es-ES"].translation.dlq.page ??= {};
mutableResources["es-ES"].translation.dlq.table ??= {};
mutableResources["es-ES"].translation.executions.page ??= {};
mutableResources["es-ES"].translation.memory.curation ??= {};
mutableResources["es-ES"].translation.memory.inspector ??= {};
mutableResources["es-ES"].translation.memory.map ??= {};
mutableResources["es-ES"].translation.memory.page ??= {};
mutableResources["es-ES"].translation.overview.activity ??= {};
mutableResources["es-ES"].translation.runtime.overview ??= {};
mutableResources["es-ES"].translation.schedules.page ??= {};
mutableResources["es-ES"].translation.schedules.table ??= {};
mutableResources["es-ES"].translation.sessions.composer ??= {};
mutableResources["es-ES"].translation.sessions.context ??= {};
mutableResources["es-ES"].translation.sessions.detail ??= {};
mutableResources["es-ES"].translation.sessions.thread ??= {};
mutableResources["es-ES"].translation.settings.sections ??= {};
mutableResources["es-ES"].translation.controlPlane.create.name ??= {};
mutableResources["es-ES"].translation.costs.page.allocationModes ??= {};
mutableResources["es-ES"].translation.costs.page.breakdowns ??= {};
mutableResources["es-ES"].translation.costs.page.kpiContexts ??= {};
mutableResources["es-ES"].translation.costs.page.timeChart ??= {};
mutableResources["es-ES"].translation.executions.page.metrics ??= {};
mutableResources["es-ES"].translation.memory.curation.detail ??= {};
mutableResources["es-ES"].translation.memory.curation.row ??= {};
mutableResources["es-ES"].translation.runtime.overview.metrics ??= {};
mutableResources["es-ES"].translation.sessions.context.artifacts ??= {};

mutableResources["fr-FR"].translation.agentDetail ??= {};
mutableResources["fr-FR"].translation.agentSwitcher ??= {};
mutableResources["fr-FR"].translation.chat ??= {};
mutableResources["fr-FR"].translation.commandBar ??= {};
mutableResources["fr-FR"].translation.common ??= {};
mutableResources["fr-FR"].translation.controlPlane ??= {};
mutableResources["fr-FR"].translation.costs ??= {};
mutableResources["fr-FR"].translation.dashboard ??= {};
mutableResources["fr-FR"].translation.dlq ??= {};
mutableResources["fr-FR"].translation.executions ??= {};
mutableResources["fr-FR"].translation.memory ??= {};
mutableResources["fr-FR"].translation.overview ??= {};
mutableResources["fr-FR"].translation.runtime ??= {};
mutableResources["fr-FR"].translation.schedules ??= {};
mutableResources["fr-FR"].translation.screenTime ??= {};
mutableResources["fr-FR"].translation.sessions ??= {};
mutableResources["fr-FR"].translation.settings ??= {};
mutableResources["fr-FR"].translation.agentDetail.metrics ??= {};
mutableResources["fr-FR"].translation.agentDetail.tabs ??= {};
mutableResources["fr-FR"].translation.chat.composer ??= {};
mutableResources["fr-FR"].translation.chat.header ??= {};
mutableResources["fr-FR"].translation.chat.rail ??= {};
mutableResources["fr-FR"].translation.chat.reasoning ??= {};
mutableResources["fr-FR"].translation.chat.thread ??= {};
mutableResources["fr-FR"].translation.chat.timestamp ??= {};
mutableResources["fr-FR"].translation.chat.toolCall ??= {};
mutableResources["fr-FR"].translation.commandBar.agent ??= {};
mutableResources["fr-FR"].translation.commandBar.groups ??= {};
mutableResources["fr-FR"].translation.commandBar.recents ??= {};
mutableResources["fr-FR"].translation.controlPlane.create ??= {};
mutableResources["fr-FR"].translation.controlPlane.policy ??= {};
mutableResources["fr-FR"].translation.controlPlane.prompt ??= {};
mutableResources["fr-FR"].translation.controlPlane.saveBar ??= {};
mutableResources["fr-FR"].translation.costs.page ??= {};
mutableResources["fr-FR"].translation.dashboard.checklist ??= {};
mutableResources["fr-FR"].translation.dlq.page ??= {};
mutableResources["fr-FR"].translation.dlq.table ??= {};
mutableResources["fr-FR"].translation.executions.page ??= {};
mutableResources["fr-FR"].translation.memory.curation ??= {};
mutableResources["fr-FR"].translation.memory.inspector ??= {};
mutableResources["fr-FR"].translation.memory.map ??= {};
mutableResources["fr-FR"].translation.memory.page ??= {};
mutableResources["fr-FR"].translation.overview.activity ??= {};
mutableResources["fr-FR"].translation.runtime.overview ??= {};
mutableResources["fr-FR"].translation.schedules.page ??= {};
mutableResources["fr-FR"].translation.schedules.table ??= {};
mutableResources["fr-FR"].translation.sessions.composer ??= {};
mutableResources["fr-FR"].translation.sessions.context ??= {};
mutableResources["fr-FR"].translation.sessions.detail ??= {};
mutableResources["fr-FR"].translation.sessions.thread ??= {};
mutableResources["fr-FR"].translation.settings.sections ??= {};
mutableResources["fr-FR"].translation.controlPlane.create.name ??= {};
mutableResources["fr-FR"].translation.costs.page.allocationModes ??= {};
mutableResources["fr-FR"].translation.costs.page.breakdowns ??= {};
mutableResources["fr-FR"].translation.costs.page.kpiContexts ??= {};
mutableResources["fr-FR"].translation.costs.page.timeChart ??= {};
mutableResources["fr-FR"].translation.executions.page.metrics ??= {};
mutableResources["fr-FR"].translation.memory.curation.detail ??= {};
mutableResources["fr-FR"].translation.memory.curation.row ??= {};
mutableResources["fr-FR"].translation.runtime.overview.metrics ??= {};
mutableResources["fr-FR"].translation.sessions.context.artifacts ??= {};

mutableResources["de-DE"].translation.agentDetail ??= {};
mutableResources["de-DE"].translation.agentSwitcher ??= {};
mutableResources["de-DE"].translation.chat ??= {};
mutableResources["de-DE"].translation.commandBar ??= {};
mutableResources["de-DE"].translation.common ??= {};
mutableResources["de-DE"].translation.controlPlane ??= {};
mutableResources["de-DE"].translation.costs ??= {};
mutableResources["de-DE"].translation.dashboard ??= {};
mutableResources["de-DE"].translation.dlq ??= {};
mutableResources["de-DE"].translation.executions ??= {};
mutableResources["de-DE"].translation.memory ??= {};
mutableResources["de-DE"].translation.overview ??= {};
mutableResources["de-DE"].translation.runtime ??= {};
mutableResources["de-DE"].translation.schedules ??= {};
mutableResources["de-DE"].translation.screenTime ??= {};
mutableResources["de-DE"].translation.sessions ??= {};
mutableResources["de-DE"].translation.settings ??= {};
mutableResources["de-DE"].translation.agentDetail.metrics ??= {};
mutableResources["de-DE"].translation.agentDetail.tabs ??= {};
mutableResources["de-DE"].translation.chat.composer ??= {};
mutableResources["de-DE"].translation.chat.header ??= {};
mutableResources["de-DE"].translation.chat.rail ??= {};
mutableResources["de-DE"].translation.chat.reasoning ??= {};
mutableResources["de-DE"].translation.chat.thread ??= {};
mutableResources["de-DE"].translation.chat.timestamp ??= {};
mutableResources["de-DE"].translation.chat.toolCall ??= {};
mutableResources["de-DE"].translation.commandBar.agent ??= {};
mutableResources["de-DE"].translation.commandBar.groups ??= {};
mutableResources["de-DE"].translation.commandBar.recents ??= {};
mutableResources["de-DE"].translation.controlPlane.create ??= {};
mutableResources["de-DE"].translation.controlPlane.policy ??= {};
mutableResources["de-DE"].translation.controlPlane.prompt ??= {};
mutableResources["de-DE"].translation.controlPlane.saveBar ??= {};
mutableResources["de-DE"].translation.costs.page ??= {};
mutableResources["de-DE"].translation.dashboard.checklist ??= {};
mutableResources["de-DE"].translation.dlq.page ??= {};
mutableResources["de-DE"].translation.dlq.table ??= {};
mutableResources["de-DE"].translation.executions.page ??= {};
mutableResources["de-DE"].translation.memory.curation ??= {};
mutableResources["de-DE"].translation.memory.inspector ??= {};
mutableResources["de-DE"].translation.memory.map ??= {};
mutableResources["de-DE"].translation.memory.page ??= {};
mutableResources["de-DE"].translation.overview.activity ??= {};
mutableResources["de-DE"].translation.runtime.overview ??= {};
mutableResources["de-DE"].translation.schedules.page ??= {};
mutableResources["de-DE"].translation.schedules.table ??= {};
mutableResources["de-DE"].translation.sessions.composer ??= {};
mutableResources["de-DE"].translation.sessions.context ??= {};
mutableResources["de-DE"].translation.sessions.detail ??= {};
mutableResources["de-DE"].translation.sessions.thread ??= {};
mutableResources["de-DE"].translation.settings.sections ??= {};
mutableResources["de-DE"].translation.controlPlane.create.name ??= {};
mutableResources["de-DE"].translation.costs.page.allocationModes ??= {};
mutableResources["de-DE"].translation.costs.page.breakdowns ??= {};
mutableResources["de-DE"].translation.costs.page.kpiContexts ??= {};
mutableResources["de-DE"].translation.costs.page.timeChart ??= {};
mutableResources["de-DE"].translation.executions.page.metrics ??= {};
mutableResources["de-DE"].translation.memory.curation.detail ??= {};
mutableResources["de-DE"].translation.memory.curation.row ??= {};
mutableResources["de-DE"].translation.runtime.overview.metrics ??= {};
mutableResources["de-DE"].translation.sessions.context.artifacts ??= {};

mutableResources["en-US"].translation.agentDetail = {
  ...(mutableResources["en-US"].translation.agentDetail ?? {}),
  activeSchedules: "Active schedules",
  activeTitle: "{{agent}} active",
  databaseNotInitialized: "Database not initialized yet",
  entriesCount: "{{count}} entries",
  noPublishedData: "No published data",
  noRecentTasks: "No recent task.",
  noSchedule: "No schedule.",
  noSession: "No session.",
  noTask: "No task.",
  recent: "Recent",
  refresh: "Refresh",
  situation: "Situation",
  stableTitle: "{{agent}} stable",
  trackedSessions: "Tracked sessions",
  unavailable: "Agent unavailable",
};

mutableResources["en-US"].translation.agentDetail.metrics = {
  ...(mutableResources["en-US"].translation.agentDetail.metrics ?? {}),
  active: "Active",
  completed: "Completed",
  failed: "Failures",
  lastActivity: "Last activity",
  queries: "Queries",
  schedules: "Schedules",
  todayCost: "Cost today",
  totalCost: "Total cost",
};

mutableResources["en-US"].translation.agentDetail.tabs = {
  ...(mutableResources["en-US"].translation.agentDetail.tabs ?? {}),
  cron: "Schedules",
  overview: "Overview",
  sessions: "Sessions",
  tasks: "Executions",
};

mutableResources["en-US"].translation.agentSwitcher = {
  ...(mutableResources["en-US"].translation.agentSwitcher ?? {}),
  createAria: "Create new agent",
};

mutableResources["en-US"].translation.chat.composer = {
  ...(mutableResources["en-US"].translation.chat.composer ?? {}),
  placeholder: "Write a message...",
  send: "Send",
  sendHint: "Enter to send • Shift + Enter for a new line",
};

mutableResources["en-US"].translation.chat.header = {
  ...(mutableResources["en-US"].translation.chat.header ?? {}),
  viewDetails: "View details",
};

mutableResources["en-US"].translation.chat.rail = {
  ...(mutableResources["en-US"].translation.chat.rail ?? {}),
  clearSearch: "Clear search",
  close: "Close conversation list",
  empty: "No conversations yet",
  emptyHelper: "Start a new session to see it here.",
  newSession: "New session",
  noResults: "No results",
  openLabel: "Open conversation list",
  search: "Search",
  title: "Conversations",
  unavailable: "History unavailable",
};

mutableResources["en-US"].translation.chat.reasoning = {
  ...(mutableResources["en-US"].translation.chat.reasoning ?? {}),
  expandLabelDone: "Thought for {{duration}}",
  expandLabelDoneNoDuration: "Reasoning",
  expandLabelStreaming: "Thinking…",
};

mutableResources["en-US"].translation.chat.thread = {
  ...(mutableResources["en-US"].translation.chat.thread ?? {}),
  empty: "No messages yet.",
  errorGeneric: "Something went wrong. Please try again.",
  failed: "Failed to send",
  newMessages: "New messages",
  retry: "Retry",
  thinking: "Thinking…",
};

mutableResources["en-US"].translation.chat.timestamp = {
  ...(mutableResources["en-US"].translation.chat.timestamp ?? {}),
  lastActivity: "Last activity",
};

mutableResources["en-US"].translation.chat.toolCall = {
  ...(mutableResources["en-US"].translation.chat.toolCall ?? {}),
  completed: "Completed",
  cost: "cost",
  failed: "Failed",
  queued: "Queued",
  retrying: "Retrying",
  running: "Running",
  tools: "tools",
  viewArgs: "Arguments",
  viewExecution: "View execution",
};

mutableResources["en-US"].translation.commandBar = {
  ...(mutableResources["en-US"].translation.commandBar ?? {}),
  emptyState: "No matching commands or agents.",
  modalTitle: "Command bar",
  placeholder: "Search commands, agents, and actions…",
  shortcutHint: "⌘K",
};

mutableResources["en-US"].translation.commandBar.agent = {
  ...(mutableResources["en-US"].translation.commandBar.agent ?? {}),
  description: "Open agent detail",
};

mutableResources["en-US"].translation.commandBar.groups = {
  ...(mutableResources["en-US"].translation.commandBar.groups ?? {}),
  actions: "Actions",
  agents: "Agents",
  approvals: "Approvals",
  pages: "Pages",
  recents: "Recent",
  skills: "Skills",
  tools: "Tools",
};

mutableResources["en-US"].translation.commandBar.recents = {
  ...(mutableResources["en-US"].translation.commandBar.recents ?? {}),
  noQuery: "No recent query",
};

mutableResources["en-US"].translation.common = {
  ...(mutableResources["en-US"].translation.common ?? {}),
  actions: "Actions",
  attempts: "Attempts",
  back: "Back",
  cancel: "Cancel",
  clear: "Clear",
  close: "Close",
  code: "Code",
  completedAt: "Completed at",
  copy: "Copy",
  details: "Details",
  display: "Display",
  edit: "Edit",
  executions: "Executions",
  expand: "Expand",
  filters: "Filters",
  lines: "Lines",
  message: "Message",
  mode: "Mode",
  model: "Model",
  noAgent: "No agent",
  noHistory: "No history",
  off: "Off",
  on: "On",
  open: "Open",
  payload: "Payload",
  phase: "Phase",
  pod: "Pod",
  preview: "Preview",
  reconnect: "Reconnect",
  refresh: "Refresh",
  save: "Save",
  schedules: "Schedules",
  sessions: "Sessions",
  startedAt: "Started at",
  task: "Task",
  timing: "Timing",
  totalTime: "Total time",
  user: "User",
  visual: "Visual",
  workspaceDirectory: "Workspace directory",
};

mutableResources["en-US"].translation.controlPlane.create = {
  ...(mutableResources["en-US"].translation.controlPlane.create ?? {}),
  agentIdHint: "Lowercase, no spaces. Used as canonical identifier.",
  agentIdLabel: "Agent ID",
  agentIdPlaceholder: "e.g. sales-assistant",
  cancel: "Cancel",
  colorLabel: "Color",
  descriptionLabel: "Description",
  descriptionPlaceholder: "Optional short description",
  genericError: "Could not create the resource. Please try again.",
  nameLabel: "Name",
  parentWorkspace: "Parent workspace",
  squadNone: "No squad",
  squadOptional: "Squad (optional)",
  submit: "Create",
  subtitle: "Fill the fields below to publish.",
  typeLabel: "Type",
  workspaceChoose: "Choose a workspace",
  workspaceNone: "No workspace",
  workspaceOptional: "Workspace (optional)",
};

mutableResources["en-US"].translation.controlPlane.create.name = {
  ...(mutableResources["en-US"].translation.controlPlane.create.name ?? {}),
  agent: "Agent name",
  squad: "Squad name",
  workspace: "Workspace name",
};

mutableResources["en-US"].translation.controlPlane.policy = {
  ...(mutableResources["en-US"].translation.controlPlane.policy ?? {}),
  add: "Add",
  addPlaceholder: "Add new item…",
  empty: "No items yet.",
  remove: "Remove",
};

mutableResources["en-US"].translation.controlPlane.prompt = {
  ...(mutableResources["en-US"].translation.controlPlane.prompt ?? {}),
  edit: "Edit",
  placeholder: "Write the system prompt for this agent…",
  preview: "Preview",
};

mutableResources["en-US"].translation.controlPlane.saveBar = {
  ...(mutableResources["en-US"].translation.controlPlane.saveBar ?? {}),
  dirty: "Unsaved changes",
  dirtyMany: "{{count}} unsaved changes",
  discard: "Discard",
  save: "Save",
  saved: "Saved",
};

mutableResources["en-US"].translation.costs.page = {
  ...(mutableResources["en-US"].translation.costs.page ?? {}),
  allocationDominant: "Dominant:",
  allocationFooter: "{{label}} accounts for {{value}} of the current cut and leads the observed distribution.",
  emptyBreakdownShort: "Not enough data",
  executionsCount: "{{count}} executions",
  loadError: "Could not load costs.",
  noConversations: "No conversations in the current filter.",
  noDominantAllocation: "No dominant concentration",
  noDominantModel: "No dominant model",
  noDominantOrigin: "No dominant origin",
  noModel: "No model",
  noPeak: "No highlighted peak in the period",
  noRecentPreview: "No recent preview",
  queriesCount: "{{count}} queries",
  shareInPeriod: "Share in period",
  unavailable: "Costs unavailable",
};

mutableResources["en-US"].translation.costs.page.allocationModes = {
  ...(mutableResources["en-US"].translation.costs.page.allocationModes ?? {}),
  task: "By task",
};

mutableResources["en-US"].translation.costs.page.breakdowns = {
  ...(mutableResources["en-US"].translation.costs.page.breakdowns ?? {}),
  byAgentTitle: "Distribution by agent",
  byModelTitle: "Distribution by model",
  byTaskTitle: "Distribution by task type",
};

mutableResources["en-US"].translation.costs.page.kpiContexts = {
  ...(mutableResources["en-US"].translation.costs.page.kpiContexts ?? {}),
  noComparableBase: "No comparable baseline",
  previousBase: "Previous base {{value}}",
  resolvedConversations: "{{count}} resolved conversations",
  totalPeriod: "{{queries}} queries · {{executions}} executions",
};

mutableResources["en-US"].translation.costs.page.timeChart = {
  ...(mutableResources["en-US"].translation.costs.page.timeChart ?? {}),
  base: "Base:",
  buckets: "Buckets:",
  driver: "Driver · {{value}}",
  emptyShort: "Not enough data",
  modeLabel: "Mode",
  noBucket: "No bucket",
  noDriver: "No dominant driver",
  peak: "Peak:",
  variation: "Variation:",
};

mutableResources["en-US"].translation.dashboard.checklist = {
  ...(mutableResources["en-US"].translation.dashboard.checklist ?? {}),
  agent: "Create your first agent",
  dismiss: "Dismiss",
  provider: "Configure a provider",
  subtitle: "Finish the workspace setup to unlock automations.",
  telegram: "Connect Telegram",
  title: "Getting started",
};

mutableResources["en-US"].translation.dlq.page = {
  ...(mutableResources["en-US"].translation.dlq.page ?? {}),
  affectedAgents: "Affected agents",
};

mutableResources["en-US"].translation.dlq.table = {
  ...(mutableResources["en-US"].translation.dlq.table ?? {}),
  noAgent: "No agent linked",
};

mutableResources["en-US"].translation.executions.page = {
  ...(mutableResources["en-US"].translation.executions.page ?? {}),
  loadError: "Could not load execution details.",
};

mutableResources["en-US"].translation.executions.page.metrics = {
  ...(mutableResources["en-US"].translation.executions.page.metrics ?? {}),
  avgDurationHint: "Average run time across the current filter",
  costHint: "Total cost for the current cut",
  toolsHint: "Number of tool invocations observed",
  warningsHint: "Tasks that required retries or flagged warnings",
};

mutableResources["en-US"].translation.memory.curation = {
  ...(mutableResources["en-US"].translation.memory.curation ?? {}),
  selectedCount: "{{count}} items selected",
};

mutableResources["en-US"].translation.memory.curation.detail = {
  ...(mutableResources["en-US"].translation.memory.curation.detail ?? {}),
  memoriesConnected: "{{count}} connected memories",
};

mutableResources["en-US"].translation.memory.curation.row = {
  ...(mutableResources["en-US"].translation.memory.curation.row ?? {}),
  sessionCount: "{{count}} sessions",
};

mutableResources["en-US"].translation.memory.inspector = {
  ...(mutableResources["en-US"].translation.memory.inspector ?? {}),
  content: "Content",
  details: "Details",
  empty: "Select a point on the map",
  expiresAt: "Expires at",
  members: "Members",
  never: "Never",
  recenter: "Recenter",
  selectPointHint: "Click a memory on the map to inspect it.",
};

mutableResources["en-US"].translation.memory.map = {
  ...(mutableResources["en-US"].translation.memory.map ?? {}),
  canvasAriaLabel: "Memory map canvas",
  clusters: "Clusters",
  memoryCount: "{{count}} memories",
  reset: "Reset map",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
};

mutableResources["en-US"].translation.memory.page = {
  ...(mutableResources["en-US"].translation.memory.page ?? {}),
  noAgentsDescription: "Create or publish at least one agent before opening the map.",
  noAgentsTitle: "No agents available",
};

mutableResources["en-US"].translation.overview.activity = {
  ...(mutableResources["en-US"].translation.overview.activity ?? {}),
  deploy: "Deploy",
  events: "{{count}} events",
  latestExecutions: "Latest executions",
  noRecent: "No recent activity",
  retry: "Retry",
  showingRecent: "Showing the most recent events",
  taskCompleted: "Task completed",
  taskFailed: "Task failed",
  taskQueued: "Task queued",
  taskStarted: "Task started",
};

mutableResources["en-US"].translation.runtime.overview.metrics = {
  ...(mutableResources["en-US"].translation.runtime.overview.metrics ?? {}),
  attentionHint: "Executions requiring review or retries",
  executionsHint: "Live executions across visible agents",
  onlineAgents: "Agents online",
  onlineAgentsHint: "Agents with a healthy runtime heartbeat",
};

mutableResources["en-US"].translation.schedules.page = {
  ...(mutableResources["en-US"].translation.schedules.page ?? {}),
  unavailable: "Schedules unavailable",
  unavailableDescription: "Unable to load canonical schedules.",
  visibleAgents: "Visible agents",
};

mutableResources["en-US"].translation.schedules.table = {
  ...(mutableResources["en-US"].translation.schedules.table ?? {}),
  nextRun: "Next run",
};

mutableResources["en-US"].translation.screenTime = {
  ...(mutableResources["en-US"].translation.screenTime ?? {}),
  focusAgents: "Agents in focus",
};

mutableResources["en-US"].translation.sessions.composer = {
  ...(mutableResources["en-US"].translation.sessions.composer ?? {}),
  selectAgentToStart: "Select a specific agent here to start a chat.",
};

mutableResources["en-US"].translation.sessions.context = {
  ...(mutableResources["en-US"].translation.sessions.context ?? {}),
  summaryLabel: "Summary",
};

mutableResources["en-US"].translation.sessions.context.artifacts = {
  ...(mutableResources["en-US"].translation.sessions.context.artifacts ?? {}),
  executionFallback: "Execution artifact",
  label: "Artifacts",
  openExternal: "Open externally",
  previewUnavailable: "Preview unavailable",
};

mutableResources["en-US"].translation.sessions.detail = {
  ...(mutableResources["en-US"].translation.sessions.detail ?? {}),
  agent: "Agent",
  model: "Model",
};

mutableResources["en-US"].translation.sessions.thread = {
  ...(mutableResources["en-US"].translation.sessions.thread ?? {}),
  heroHelper: "Pick an agent in the composer and send the first message.",
  heroTitle: "Start a new conversation",
  newChatEyebrow: "New chat",
};

mutableResources["en-US"].translation.settings.sections = {
  ...(mutableResources["en-US"].translation.settings.sections ?? {}),
  navigation: "Navigation",
};

mutableResources["pt-BR"].translation.agentDetail = {
  ...(mutableResources["pt-BR"].translation.agentDetail ?? {}),
  activeSchedules: "Agendamentos ativos",
  activeTitle: "{{agent}} em atividade",
  databaseNotInitialized: "Base ainda não inicializada",
  entriesCount: "{{count}} entradas",
  noPublishedData: "Sem dados publicados",
  noRecentTasks: "Nenhuma tarefa recente.",
  noSchedule: "Nenhum agendamento.",
  noSession: "Nenhuma sessão.",
  noTask: "Nenhuma tarefa.",
  recent: "Recentes",
  refresh: "Atualizar",
  situation: "Situação",
  stableTitle: "{{agent}} estável",
  trackedSessions: "Sessões rastreadas",
  unavailable: "Agente indisponível",
};

mutableResources["pt-BR"].translation.agentDetail.metrics = {
  ...(mutableResources["pt-BR"].translation.agentDetail.metrics ?? {}),
  active: "Ativas",
  completed: "Concluídas",
  failed: "Falhas",
  lastActivity: "Última atividade",
  queries: "Consultas",
  schedules: "Agendamentos",
  todayCost: "Custo hoje",
  totalCost: "Custo total",
};

mutableResources["pt-BR"].translation.agentDetail.tabs = {
  ...(mutableResources["pt-BR"].translation.agentDetail.tabs ?? {}),
  cron: "Agendamentos",
  overview: "Visão geral",
  sessions: "Sessões",
  tasks: "Execuções",
};

mutableResources["pt-BR"].translation.agentSwitcher = {
  ...(mutableResources["pt-BR"].translation.agentSwitcher ?? {}),
  createAria: "Criar novo agente",
};

mutableResources["pt-BR"].translation.chat.composer = {
  ...(mutableResources["pt-BR"].translation.chat.composer ?? {}),
  placeholder: "Escreva uma mensagem...",
  send: "Enviar",
  sendHint: "Enter para enviar • Shift + Enter para nova linha",
};

mutableResources["pt-BR"].translation.chat.header = {
  ...(mutableResources["pt-BR"].translation.chat.header ?? {}),
  viewDetails: "Ver detalhes",
};

mutableResources["pt-BR"].translation.chat.rail = {
  ...(mutableResources["pt-BR"].translation.chat.rail ?? {}),
  clearSearch: "Limpar busca",
  close: "Fechar lista de conversas",
  empty: "Nenhuma conversa ainda",
  emptyHelper: "Inicie uma nova sessão para vê-la aqui.",
  newSession: "Nova sessão",
  noResults: "Nenhum resultado",
  openLabel: "Abrir lista de conversas",
  search: "Buscar",
  title: "Conversas",
  unavailable: "Histórico indisponível",
};

mutableResources["pt-BR"].translation.chat.reasoning = {
  ...(mutableResources["pt-BR"].translation.chat.reasoning ?? {}),
  expandLabelDone: "Pensou por {{duration}}",
  expandLabelDoneNoDuration: "Raciocínio",
  expandLabelStreaming: "Pensando…",
};

mutableResources["pt-BR"].translation.chat.thread = {
  ...(mutableResources["pt-BR"].translation.chat.thread ?? {}),
  empty: "Sem mensagens ainda.",
  errorGeneric: "Algo deu errado. Tente novamente.",
  failed: "Falha no envio",
  newMessages: "Novas mensagens",
  retry: "Tentar novamente",
  thinking: "Pensando…",
};

mutableResources["pt-BR"].translation.chat.timestamp = {
  ...(mutableResources["pt-BR"].translation.chat.timestamp ?? {}),
  lastActivity: "Última atividade",
};

mutableResources["pt-BR"].translation.chat.toolCall = {
  ...(mutableResources["pt-BR"].translation.chat.toolCall ?? {}),
  completed: "Concluído",
  cost: "custo",
  failed: "Falhou",
  queued: "Em fila",
  retrying: "Retentando",
  running: "Executando",
  tools: "ferramentas",
  viewArgs: "Argumentos",
  viewExecution: "Ver execução",
};

mutableResources["pt-BR"].translation.commandBar = {
  ...(mutableResources["pt-BR"].translation.commandBar ?? {}),
  emptyState: "Nenhum comando ou agente correspondente.",
  modalTitle: "Barra de comandos",
  placeholder: "Buscar comandos, agentes e ações…",
  shortcutHint: "⌘K",
};

mutableResources["pt-BR"].translation.commandBar.agent = {
  ...(mutableResources["pt-BR"].translation.commandBar.agent ?? {}),
  description: "Abrir detalhe do agente",
};

mutableResources["pt-BR"].translation.commandBar.groups = {
  ...(mutableResources["pt-BR"].translation.commandBar.groups ?? {}),
  actions: "Ações",
  agents: "Agentes",
  approvals: "Aprovações",
  pages: "Páginas",
  recents: "Recentes",
  skills: "Habilidades",
  tools: "Ferramentas",
};

mutableResources["pt-BR"].translation.commandBar.recents = {
  ...(mutableResources["pt-BR"].translation.commandBar.recents ?? {}),
  noQuery: "Sem consulta recente",
};

mutableResources["pt-BR"].translation.common = {
  ...(mutableResources["pt-BR"].translation.common ?? {}),
  actions: "Ações",
  attempts: "Tentativas",
  back: "Voltar",
  cancel: "Cancelar",
  clear: "Limpar",
  close: "Fechar",
  code: "Código",
  completedAt: "Concluído em",
  copy: "Copiar",
  details: "Detalhes",
  display: "Exibição",
  edit: "Editar",
  executions: "Execuções",
  expand: "Expandir",
  filters: "Filtros",
  lines: "Linhas",
  message: "Mensagem",
  mode: "Modo",
  model: "Modelo",
  noAgent: "Sem agente",
  noHistory: "Sem histórico",
  off: "Desligado",
  on: "Ligado",
  open: "Abrir",
  payload: "Payload",
  phase: "Fase",
  pod: "Pod",
  preview: "Prévia",
  reconnect: "Reconectar",
  refresh: "Atualizar",
  save: "Salvar",
  schedules: "Agendamentos",
  sessions: "Sessões",
  startedAt: "Iniciado em",
  task: "Tarefa",
  timing: "Tempo",
  totalTime: "Tempo total",
  user: "Usuário",
  visual: "Visual",
  workspaceDirectory: "Diretório do workspace",
};

mutableResources["pt-BR"].translation.controlPlane.create = {
  ...(mutableResources["pt-BR"].translation.controlPlane.create ?? {}),
  agentIdHint: "Minúsculas, sem espaços. Usado como identificador canônico.",
  agentIdLabel: "ID do agente",
  agentIdPlaceholder: "ex.: assistente-vendas",
  cancel: "Cancelar",
  colorLabel: "Cor",
  descriptionLabel: "Descrição",
  descriptionPlaceholder: "Descrição curta opcional",
  genericError: "Não foi possível criar o recurso. Tente novamente.",
  nameLabel: "Nome",
  parentWorkspace: "Workspace pai",
  squadNone: "Sem time",
  squadOptional: "Time (opcional)",
  submit: "Criar",
  subtitle: "Preencha os campos abaixo para publicar.",
  typeLabel: "Tipo",
  workspaceChoose: "Escolha um workspace",
  workspaceNone: "Sem workspace",
  workspaceOptional: "Workspace (opcional)",
};

mutableResources["pt-BR"].translation.controlPlane.create.name = {
  ...(mutableResources["pt-BR"].translation.controlPlane.create.name ?? {}),
  agent: "Nome do agente",
  squad: "Nome do time",
  workspace: "Nome do workspace",
};

mutableResources["pt-BR"].translation.controlPlane.policy = {
  ...(mutableResources["pt-BR"].translation.controlPlane.policy ?? {}),
  add: "Adicionar",
  addPlaceholder: "Adicionar novo item…",
  empty: "Nenhum item ainda.",
  remove: "Remover",
};

mutableResources["pt-BR"].translation.controlPlane.prompt = {
  ...(mutableResources["pt-BR"].translation.controlPlane.prompt ?? {}),
  edit: "Editar",
  placeholder: "Escreva o system prompt para este agente…",
  preview: "Prévia",
};

mutableResources["pt-BR"].translation.controlPlane.saveBar = {
  ...(mutableResources["pt-BR"].translation.controlPlane.saveBar ?? {}),
  dirty: "Alterações não salvas",
  dirtyMany: "{{count}} alterações não salvas",
  discard: "Descartar",
  save: "Salvar",
  saved: "Salvo",
};

mutableResources["pt-BR"].translation.costs.page = {
  ...(mutableResources["pt-BR"].translation.costs.page ?? {}),
  allocationDominant: "Dominante:",
  allocationFooter: "{{label}} responde por {{value}} do recorte atual e lidera a distribuição observada.",
  emptyBreakdownShort: "Dados insuficientes",
  executionsCount: "{{count}} execuções",
  loadError: "Não foi possível carregar custos.",
  noConversations: "Nenhuma conversa no filtro atual.",
  noDominantAllocation: "Sem concentração dominante",
  noDominantModel: "Sem modelo dominante",
  noDominantOrigin: "Sem origem dominante",
  noModel: "Sem modelo",
  noPeak: "Nenhum pico destacado no período",
  noRecentPreview: "Sem prévia recente",
  queriesCount: "{{count}} consultas",
  shareInPeriod: "Participação no período",
  unavailable: "Custos indisponíveis",
};

mutableResources["pt-BR"].translation.costs.page.allocationModes = {
  ...(mutableResources["pt-BR"].translation.costs.page.allocationModes ?? {}),
  task: "Por tarefa",
};

mutableResources["pt-BR"].translation.costs.page.breakdowns = {
  ...(mutableResources["pt-BR"].translation.costs.page.breakdowns ?? {}),
  byAgentTitle: "Distribuição por agente",
  byModelTitle: "Distribuição por modelo",
  byTaskTitle: "Distribuição por tipo de tarefa",
};

mutableResources["pt-BR"].translation.costs.page.kpiContexts = {
  ...(mutableResources["pt-BR"].translation.costs.page.kpiContexts ?? {}),
  noComparableBase: "Sem baseline comparável",
  previousBase: "Base anterior {{value}}",
  resolvedConversations: "{{count}} conversas resolvidas",
  totalPeriod: "{{queries}} consultas · {{executions}} execuções",
};

mutableResources["pt-BR"].translation.costs.page.timeChart = {
  ...(mutableResources["pt-BR"].translation.costs.page.timeChart ?? {}),
  base: "Base:",
  buckets: "Blocos:",
  driver: "Motor · {{value}}",
  emptyShort: "Dados insuficientes",
  modeLabel: "Modo",
  noBucket: "Sem bloco",
  noDriver: "Sem motor dominante",
  peak: "Pico:",
  variation: "Variação:",
};

mutableResources["pt-BR"].translation.dashboard.checklist = {
  ...(mutableResources["pt-BR"].translation.dashboard.checklist ?? {}),
  agent: "Crie seu primeiro agente",
  dismiss: "Dispensar",
  provider: "Configure um provedor",
  subtitle: "Finalize a configuração do workspace para liberar automações.",
  telegram: "Conectar Telegram",
  title: "Primeiros passos",
};

mutableResources["pt-BR"].translation.dlq.page = {
  ...(mutableResources["pt-BR"].translation.dlq.page ?? {}),
  affectedAgents: "Agentes afetados",
};

mutableResources["pt-BR"].translation.dlq.table = {
  ...(mutableResources["pt-BR"].translation.dlq.table ?? {}),
  noAgent: "Sem agente associado",
};

mutableResources["pt-BR"].translation.executions.page = {
  ...(mutableResources["pt-BR"].translation.executions.page ?? {}),
  loadError: "Não foi possível carregar os detalhes da execução.",
};

mutableResources["pt-BR"].translation.executions.page.metrics = {
  ...(mutableResources["pt-BR"].translation.executions.page.metrics ?? {}),
  avgDurationHint: "Tempo médio de execução no filtro atual",
  costHint: "Custo total no recorte atual",
  toolsHint: "Número de invocações de ferramentas observadas",
  warningsHint: "Tarefas que exigiram retentativas ou levantaram avisos",
};

mutableResources["pt-BR"].translation.memory.curation = {
  ...(mutableResources["pt-BR"].translation.memory.curation ?? {}),
  selectedCount: "{{count}} itens selecionados",
};

mutableResources["pt-BR"].translation.memory.curation.detail = {
  ...(mutableResources["pt-BR"].translation.memory.curation.detail ?? {}),
  memoriesConnected: "{{count}} memórias conectadas",
};

mutableResources["pt-BR"].translation.memory.curation.row = {
  ...(mutableResources["pt-BR"].translation.memory.curation.row ?? {}),
  sessionCount: "{{count}} sessões",
};

mutableResources["pt-BR"].translation.memory.inspector = {
  ...(mutableResources["pt-BR"].translation.memory.inspector ?? {}),
  content: "Conteúdo",
  details: "Detalhes",
  empty: "Selecione um ponto no mapa",
  expiresAt: "Expira em",
  members: "Membros",
  never: "Nunca",
  recenter: "Recentralizar",
  selectPointHint: "Clique em uma memória no mapa para inspecioná-la.",
};

mutableResources["pt-BR"].translation.memory.map = {
  ...(mutableResources["pt-BR"].translation.memory.map ?? {}),
  canvasAriaLabel: "Canvas do mapa de memória",
  clusters: "Clusters",
  memoryCount: "{{count}} memórias",
  reset: "Resetar mapa",
  zoomIn: "Aproximar",
  zoomOut: "Afastar",
};

mutableResources["pt-BR"].translation.memory.page = {
  ...(mutableResources["pt-BR"].translation.memory.page ?? {}),
  noAgentsDescription: "Crie ou publique ao menos um agente antes de abrir o mapa.",
  noAgentsTitle: "Nenhum agente disponível",
};

mutableResources["pt-BR"].translation.overview.activity = {
  ...(mutableResources["pt-BR"].translation.overview.activity ?? {}),
  deploy: "Deploy",
  events: "{{count}} eventos",
  latestExecutions: "Últimas execuções",
  noRecent: "Sem atividade recente",
  retry: "Tentar novamente",
  showingRecent: "Mostrando os eventos mais recentes",
  taskCompleted: "Tarefa concluída",
  taskFailed: "Tarefa falhou",
  taskQueued: "Tarefa em fila",
  taskStarted: "Tarefa iniciada",
};

mutableResources["pt-BR"].translation.runtime.overview.metrics = {
  ...(mutableResources["pt-BR"].translation.runtime.overview.metrics ?? {}),
  attentionHint: "Execuções que exigem revisão ou retentativas",
  executionsHint: "Execuções ao vivo entre os agentes visíveis",
  onlineAgents: "Agentes online",
  onlineAgentsHint: "Agentes com heartbeat do runtime saudável",
};

mutableResources["pt-BR"].translation.schedules.page = {
  ...(mutableResources["pt-BR"].translation.schedules.page ?? {}),
  unavailable: "Agendamentos indisponíveis",
  unavailableDescription: "Não foi possível carregar os agendamentos canônicos.",
  visibleAgents: "Agentes visíveis",
};

mutableResources["pt-BR"].translation.schedules.table = {
  ...(mutableResources["pt-BR"].translation.schedules.table ?? {}),
  nextRun: "Próxima execução",
};

mutableResources["pt-BR"].translation.screenTime = {
  ...(mutableResources["pt-BR"].translation.screenTime ?? {}),
  focusAgents: "Agentes em foco",
};

mutableResources["pt-BR"].translation.sessions.composer = {
  ...(mutableResources["pt-BR"].translation.sessions.composer ?? {}),
  selectAgentToStart: "Selecione um agente específico aqui para iniciar uma conversa.",
};

mutableResources["pt-BR"].translation.sessions.context = {
  ...(mutableResources["pt-BR"].translation.sessions.context ?? {}),
  summaryLabel: "Resumo",
};

mutableResources["pt-BR"].translation.sessions.context.artifacts = {
  ...(mutableResources["pt-BR"].translation.sessions.context.artifacts ?? {}),
  executionFallback: "Artefato da execução",
  label: "Artefatos",
  openExternal: "Abrir externamente",
  previewUnavailable: "Prévia indisponível",
};

mutableResources["pt-BR"].translation.sessions.detail = {
  ...(mutableResources["pt-BR"].translation.sessions.detail ?? {}),
  agent: "Agente",
  model: "Modelo",
};

mutableResources["pt-BR"].translation.sessions.thread = {
  ...(mutableResources["pt-BR"].translation.sessions.thread ?? {}),
  heroHelper: "Escolha um agente no composer e envie a primeira mensagem.",
  heroTitle: "Inicie uma nova conversa",
  newChatEyebrow: "Nova conversa",
};

mutableResources["pt-BR"].translation.settings.sections = {
  ...(mutableResources["pt-BR"].translation.settings.sections ?? {}),
  navigation: "Navegação",
};

mutableResources["es-ES"].translation.agentDetail = {
  ...(mutableResources["es-ES"].translation.agentDetail ?? {}),
  activeSchedules: "Active schedules",
  activeTitle: "{{agent}} active",
  databaseNotInitialized: "Database not initialized yet",
  entriesCount: "{{count}} entries",
  noPublishedData: "No published data",
  noRecentTasks: "No recent task.",
  noSchedule: "No schedule.",
  noSession: "No session.",
  noTask: "No task.",
  recent: "Recent",
  refresh: "Refresh",
  situation: "Situation",
  stableTitle: "{{agent}} stable",
  trackedSessions: "Tracked sessions",
  unavailable: "Agent unavailable",
};

mutableResources["es-ES"].translation.agentDetail.metrics = {
  ...(mutableResources["es-ES"].translation.agentDetail.metrics ?? {}),
  active: "Active",
  completed: "Completed",
  failed: "Failures",
  lastActivity: "Last activity",
  queries: "Queries",
  schedules: "Schedules",
  todayCost: "Cost today",
  totalCost: "Total cost",
};

mutableResources["es-ES"].translation.agentDetail.tabs = {
  ...(mutableResources["es-ES"].translation.agentDetail.tabs ?? {}),
  cron: "Schedules",
  overview: "Overview",
  sessions: "Sessions",
  tasks: "Executions",
};

mutableResources["es-ES"].translation.agentSwitcher = {
  ...(mutableResources["es-ES"].translation.agentSwitcher ?? {}),
  createAria: "Create new agent",
};

mutableResources["es-ES"].translation.chat.composer = {
  ...(mutableResources["es-ES"].translation.chat.composer ?? {}),
  placeholder: "Write a message...",
  send: "Send",
  sendHint: "Enter to send • Shift + Enter for a new line",
};

mutableResources["es-ES"].translation.chat.header = {
  ...(mutableResources["es-ES"].translation.chat.header ?? {}),
  viewDetails: "View details",
};

mutableResources["es-ES"].translation.chat.rail = {
  ...(mutableResources["es-ES"].translation.chat.rail ?? {}),
  clearSearch: "Clear search",
  close: "Close conversation list",
  empty: "No conversations yet",
  emptyHelper: "Start a new session to see it here.",
  newSession: "New session",
  noResults: "No results",
  openLabel: "Open conversation list",
  search: "Search",
  title: "Conversations",
  unavailable: "History unavailable",
};

mutableResources["es-ES"].translation.chat.reasoning = {
  ...(mutableResources["es-ES"].translation.chat.reasoning ?? {}),
  expandLabelDone: "Thought for {{duration}}",
  expandLabelDoneNoDuration: "Reasoning",
  expandLabelStreaming: "Thinking…",
};

mutableResources["es-ES"].translation.chat.thread = {
  ...(mutableResources["es-ES"].translation.chat.thread ?? {}),
  empty: "No messages yet.",
  errorGeneric: "Something went wrong. Please try again.",
  failed: "Failed to send",
  newMessages: "New messages",
  retry: "Retry",
  thinking: "Thinking…",
};

mutableResources["es-ES"].translation.chat.timestamp = {
  ...(mutableResources["es-ES"].translation.chat.timestamp ?? {}),
  lastActivity: "Last activity",
};

mutableResources["es-ES"].translation.chat.toolCall = {
  ...(mutableResources["es-ES"].translation.chat.toolCall ?? {}),
  completed: "Completed",
  cost: "cost",
  failed: "Failed",
  queued: "Queued",
  retrying: "Retrying",
  running: "Running",
  tools: "tools",
  viewArgs: "Arguments",
  viewExecution: "View execution",
};

mutableResources["es-ES"].translation.commandBar = {
  ...(mutableResources["es-ES"].translation.commandBar ?? {}),
  emptyState: "No matching commands or agents.",
  modalTitle: "Command bar",
  placeholder: "Search commands, agents, and actions…",
  shortcutHint: "⌘K",
};

mutableResources["es-ES"].translation.commandBar.agent = {
  ...(mutableResources["es-ES"].translation.commandBar.agent ?? {}),
  description: "Open agent detail",
};

mutableResources["es-ES"].translation.commandBar.groups = {
  ...(mutableResources["es-ES"].translation.commandBar.groups ?? {}),
  actions: "Actions",
  agents: "Agents",
  approvals: "Approvals",
  pages: "Pages",
  recents: "Recent",
  skills: "Skills",
  tools: "Tools",
};

mutableResources["es-ES"].translation.commandBar.recents = {
  ...(mutableResources["es-ES"].translation.commandBar.recents ?? {}),
  noQuery: "No recent query",
};

mutableResources["es-ES"].translation.common = {
  ...(mutableResources["es-ES"].translation.common ?? {}),
  actions: "Actions",
  attempts: "Attempts",
  back: "Back",
  cancel: "Cancel",
  clear: "Clear",
  close: "Close",
  code: "Code",
  completedAt: "Completed at",
  copy: "Copy",
  details: "Details",
  display: "Display",
  edit: "Edit",
  executions: "Executions",
  expand: "Expand",
  filters: "Filters",
  lines: "Lines",
  message: "Message",
  mode: "Mode",
  model: "Model",
  noAgent: "No agent",
  noHistory: "No history",
  off: "Off",
  on: "On",
  open: "Open",
  payload: "Payload",
  phase: "Phase",
  pod: "Pod",
  preview: "Preview",
  reconnect: "Reconnect",
  refresh: "Refresh",
  save: "Save",
  schedules: "Schedules",
  sessions: "Sessions",
  startedAt: "Started at",
  task: "Task",
  timing: "Timing",
  totalTime: "Total time",
  user: "User",
  visual: "Visual",
  workspaceDirectory: "Workspace directory",
};

mutableResources["es-ES"].translation.controlPlane.create = {
  ...(mutableResources["es-ES"].translation.controlPlane.create ?? {}),
  agentIdHint: "Lowercase, no spaces. Used as canonical identifier.",
  agentIdLabel: "Agent ID",
  agentIdPlaceholder: "e.g. sales-assistant",
  cancel: "Cancel",
  colorLabel: "Color",
  descriptionLabel: "Description",
  descriptionPlaceholder: "Optional short description",
  genericError: "Could not create the resource. Please try again.",
  nameLabel: "Name",
  parentWorkspace: "Parent workspace",
  squadNone: "No squad",
  squadOptional: "Squad (optional)",
  submit: "Create",
  subtitle: "Fill the fields below to publish.",
  typeLabel: "Type",
  workspaceChoose: "Choose a workspace",
  workspaceNone: "No workspace",
  workspaceOptional: "Workspace (optional)",
};

mutableResources["es-ES"].translation.controlPlane.create.name = {
  ...(mutableResources["es-ES"].translation.controlPlane.create.name ?? {}),
  agent: "Agent name",
  squad: "Squad name",
  workspace: "Workspace name",
};

mutableResources["es-ES"].translation.controlPlane.policy = {
  ...(mutableResources["es-ES"].translation.controlPlane.policy ?? {}),
  add: "Add",
  addPlaceholder: "Add new item…",
  empty: "No items yet.",
  remove: "Remove",
};

mutableResources["es-ES"].translation.controlPlane.prompt = {
  ...(mutableResources["es-ES"].translation.controlPlane.prompt ?? {}),
  edit: "Edit",
  placeholder: "Write the system prompt for this agent…",
  preview: "Preview",
};

mutableResources["es-ES"].translation.controlPlane.saveBar = {
  ...(mutableResources["es-ES"].translation.controlPlane.saveBar ?? {}),
  dirty: "Unsaved changes",
  dirtyMany: "{{count}} unsaved changes",
  discard: "Discard",
  save: "Save",
  saved: "Saved",
};

mutableResources["es-ES"].translation.costs.page = {
  ...(mutableResources["es-ES"].translation.costs.page ?? {}),
  allocationDominant: "Dominant:",
  allocationFooter: "{{label}} accounts for {{value}} of the current cut and leads the observed distribution.",
  emptyBreakdownShort: "Not enough data",
  executionsCount: "{{count}} executions",
  loadError: "Could not load costs.",
  noConversations: "No conversations in the current filter.",
  noDominantAllocation: "No dominant concentration",
  noDominantModel: "No dominant model",
  noDominantOrigin: "No dominant origin",
  noModel: "No model",
  noPeak: "No highlighted peak in the period",
  noRecentPreview: "No recent preview",
  queriesCount: "{{count}} queries",
  shareInPeriod: "Share in period",
  unavailable: "Costs unavailable",
};

mutableResources["es-ES"].translation.costs.page.allocationModes = {
  ...(mutableResources["es-ES"].translation.costs.page.allocationModes ?? {}),
  task: "By task",
};

mutableResources["es-ES"].translation.costs.page.breakdowns = {
  ...(mutableResources["es-ES"].translation.costs.page.breakdowns ?? {}),
  byAgentTitle: "Distribution by agent",
  byModelTitle: "Distribution by model",
  byTaskTitle: "Distribution by task type",
};

mutableResources["es-ES"].translation.costs.page.kpiContexts = {
  ...(mutableResources["es-ES"].translation.costs.page.kpiContexts ?? {}),
  noComparableBase: "No comparable baseline",
  previousBase: "Previous base {{value}}",
  resolvedConversations: "{{count}} resolved conversations",
  totalPeriod: "{{queries}} queries · {{executions}} executions",
};

mutableResources["es-ES"].translation.costs.page.timeChart = {
  ...(mutableResources["es-ES"].translation.costs.page.timeChart ?? {}),
  base: "Base:",
  buckets: "Buckets:",
  driver: "Driver · {{value}}",
  emptyShort: "Not enough data",
  modeLabel: "Mode",
  noBucket: "No bucket",
  noDriver: "No dominant driver",
  peak: "Peak:",
  variation: "Variation:",
};

mutableResources["es-ES"].translation.dashboard.checklist = {
  ...(mutableResources["es-ES"].translation.dashboard.checklist ?? {}),
  agent: "Create your first agent",
  dismiss: "Dismiss",
  provider: "Configure a provider",
  subtitle: "Finish the workspace setup to unlock automations.",
  telegram: "Connect Telegram",
  title: "Getting started",
};

mutableResources["es-ES"].translation.dlq.page = {
  ...(mutableResources["es-ES"].translation.dlq.page ?? {}),
  affectedAgents: "Affected agents",
};

mutableResources["es-ES"].translation.dlq.table = {
  ...(mutableResources["es-ES"].translation.dlq.table ?? {}),
  noAgent: "No agent linked",
};

mutableResources["es-ES"].translation.executions.page = {
  ...(mutableResources["es-ES"].translation.executions.page ?? {}),
  loadError: "Could not load execution details.",
};

mutableResources["es-ES"].translation.executions.page.metrics = {
  ...(mutableResources["es-ES"].translation.executions.page.metrics ?? {}),
  avgDurationHint: "Average run time across the current filter",
  costHint: "Total cost for the current cut",
  toolsHint: "Number of tool invocations observed",
  warningsHint: "Tasks that required retries or flagged warnings",
};

mutableResources["es-ES"].translation.memory.curation = {
  ...(mutableResources["es-ES"].translation.memory.curation ?? {}),
  selectedCount: "{{count}} items selected",
};

mutableResources["es-ES"].translation.memory.curation.detail = {
  ...(mutableResources["es-ES"].translation.memory.curation.detail ?? {}),
  memoriesConnected: "{{count}} connected memories",
};

mutableResources["es-ES"].translation.memory.curation.row = {
  ...(mutableResources["es-ES"].translation.memory.curation.row ?? {}),
  sessionCount: "{{count}} sessions",
};

mutableResources["es-ES"].translation.memory.inspector = {
  ...(mutableResources["es-ES"].translation.memory.inspector ?? {}),
  content: "Content",
  details: "Details",
  empty: "Select a point on the map",
  expiresAt: "Expires at",
  members: "Members",
  never: "Never",
  recenter: "Recenter",
  selectPointHint: "Click a memory on the map to inspect it.",
};

mutableResources["es-ES"].translation.memory.map = {
  ...(mutableResources["es-ES"].translation.memory.map ?? {}),
  canvasAriaLabel: "Memory map canvas",
  clusters: "Clusters",
  memoryCount: "{{count}} memories",
  reset: "Reset map",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
};

mutableResources["es-ES"].translation.memory.page = {
  ...(mutableResources["es-ES"].translation.memory.page ?? {}),
  noAgentsDescription: "Create or publish at least one agent before opening the map.",
  noAgentsTitle: "No agents available",
};

mutableResources["es-ES"].translation.overview.activity = {
  ...(mutableResources["es-ES"].translation.overview.activity ?? {}),
  deploy: "Deploy",
  events: "{{count}} events",
  latestExecutions: "Latest executions",
  noRecent: "No recent activity",
  retry: "Retry",
  showingRecent: "Showing the most recent events",
  taskCompleted: "Task completed",
  taskFailed: "Task failed",
  taskQueued: "Task queued",
  taskStarted: "Task started",
};

mutableResources["es-ES"].translation.runtime.overview.metrics = {
  ...(mutableResources["es-ES"].translation.runtime.overview.metrics ?? {}),
  attentionHint: "Executions requiring review or retries",
  executionsHint: "Live executions across visible agents",
  onlineAgents: "Agents online",
  onlineAgentsHint: "Agents with a healthy runtime heartbeat",
};

mutableResources["es-ES"].translation.schedules.page = {
  ...(mutableResources["es-ES"].translation.schedules.page ?? {}),
  unavailable: "Schedules unavailable",
  unavailableDescription: "Unable to load canonical schedules.",
  visibleAgents: "Visible agents",
};

mutableResources["es-ES"].translation.schedules.table = {
  ...(mutableResources["es-ES"].translation.schedules.table ?? {}),
  nextRun: "Next run",
};

mutableResources["es-ES"].translation.screenTime = {
  ...(mutableResources["es-ES"].translation.screenTime ?? {}),
  focusAgents: "Agents in focus",
};

mutableResources["es-ES"].translation.sessions.composer = {
  ...(mutableResources["es-ES"].translation.sessions.composer ?? {}),
  selectAgentToStart: "Select a specific agent here to start a chat.",
};

mutableResources["es-ES"].translation.sessions.context = {
  ...(mutableResources["es-ES"].translation.sessions.context ?? {}),
  summaryLabel: "Summary",
};

mutableResources["es-ES"].translation.sessions.context.artifacts = {
  ...(mutableResources["es-ES"].translation.sessions.context.artifacts ?? {}),
  executionFallback: "Execution artifact",
  label: "Artifacts",
  openExternal: "Open externally",
  previewUnavailable: "Preview unavailable",
};

mutableResources["es-ES"].translation.sessions.detail = {
  ...(mutableResources["es-ES"].translation.sessions.detail ?? {}),
  agent: "Agent",
  model: "Model",
};

mutableResources["es-ES"].translation.sessions.thread = {
  ...(mutableResources["es-ES"].translation.sessions.thread ?? {}),
  heroHelper: "Pick an agent in the composer and send the first message.",
  heroTitle: "Start a new conversation",
  newChatEyebrow: "New chat",
};

mutableResources["es-ES"].translation.settings.sections = {
  ...(mutableResources["es-ES"].translation.settings.sections ?? {}),
  navigation: "Navigation",
};

mutableResources["fr-FR"].translation.agentDetail = {
  ...(mutableResources["fr-FR"].translation.agentDetail ?? {}),
  activeSchedules: "Active schedules",
  activeTitle: "{{agent}} active",
  databaseNotInitialized: "Database not initialized yet",
  entriesCount: "{{count}} entries",
  noPublishedData: "No published data",
  noRecentTasks: "No recent task.",
  noSchedule: "No schedule.",
  noSession: "No session.",
  noTask: "No task.",
  recent: "Recent",
  refresh: "Refresh",
  situation: "Situation",
  stableTitle: "{{agent}} stable",
  trackedSessions: "Tracked sessions",
  unavailable: "Agent unavailable",
};

mutableResources["fr-FR"].translation.agentDetail.metrics = {
  ...(mutableResources["fr-FR"].translation.agentDetail.metrics ?? {}),
  active: "Active",
  completed: "Completed",
  failed: "Failures",
  lastActivity: "Last activity",
  queries: "Queries",
  schedules: "Schedules",
  todayCost: "Cost today",
  totalCost: "Total cost",
};

mutableResources["fr-FR"].translation.agentDetail.tabs = {
  ...(mutableResources["fr-FR"].translation.agentDetail.tabs ?? {}),
  cron: "Schedules",
  overview: "Overview",
  sessions: "Sessions",
  tasks: "Executions",
};

mutableResources["fr-FR"].translation.agentSwitcher = {
  ...(mutableResources["fr-FR"].translation.agentSwitcher ?? {}),
  createAria: "Create new agent",
};

mutableResources["fr-FR"].translation.chat.composer = {
  ...(mutableResources["fr-FR"].translation.chat.composer ?? {}),
  placeholder: "Write a message...",
  send: "Send",
  sendHint: "Enter to send • Shift + Enter for a new line",
};

mutableResources["fr-FR"].translation.chat.header = {
  ...(mutableResources["fr-FR"].translation.chat.header ?? {}),
  viewDetails: "View details",
};

mutableResources["fr-FR"].translation.chat.rail = {
  ...(mutableResources["fr-FR"].translation.chat.rail ?? {}),
  clearSearch: "Clear search",
  close: "Close conversation list",
  empty: "No conversations yet",
  emptyHelper: "Start a new session to see it here.",
  newSession: "New session",
  noResults: "No results",
  openLabel: "Open conversation list",
  search: "Search",
  title: "Conversations",
  unavailable: "History unavailable",
};

mutableResources["fr-FR"].translation.chat.reasoning = {
  ...(mutableResources["fr-FR"].translation.chat.reasoning ?? {}),
  expandLabelDone: "Thought for {{duration}}",
  expandLabelDoneNoDuration: "Reasoning",
  expandLabelStreaming: "Thinking…",
};

mutableResources["fr-FR"].translation.chat.thread = {
  ...(mutableResources["fr-FR"].translation.chat.thread ?? {}),
  empty: "No messages yet.",
  errorGeneric: "Something went wrong. Please try again.",
  failed: "Failed to send",
  newMessages: "New messages",
  retry: "Retry",
  thinking: "Thinking…",
};

mutableResources["fr-FR"].translation.chat.timestamp = {
  ...(mutableResources["fr-FR"].translation.chat.timestamp ?? {}),
  lastActivity: "Last activity",
};

mutableResources["fr-FR"].translation.chat.toolCall = {
  ...(mutableResources["fr-FR"].translation.chat.toolCall ?? {}),
  completed: "Completed",
  cost: "cost",
  failed: "Failed",
  queued: "Queued",
  retrying: "Retrying",
  running: "Running",
  tools: "tools",
  viewArgs: "Arguments",
  viewExecution: "View execution",
};

mutableResources["fr-FR"].translation.commandBar = {
  ...(mutableResources["fr-FR"].translation.commandBar ?? {}),
  emptyState: "No matching commands or agents.",
  modalTitle: "Command bar",
  placeholder: "Search commands, agents, and actions…",
  shortcutHint: "⌘K",
};

mutableResources["fr-FR"].translation.commandBar.agent = {
  ...(mutableResources["fr-FR"].translation.commandBar.agent ?? {}),
  description: "Open agent detail",
};

mutableResources["fr-FR"].translation.commandBar.groups = {
  ...(mutableResources["fr-FR"].translation.commandBar.groups ?? {}),
  actions: "Actions",
  agents: "Agents",
  approvals: "Approvals",
  pages: "Pages",
  recents: "Recent",
  skills: "Skills",
  tools: "Tools",
};

mutableResources["fr-FR"].translation.commandBar.recents = {
  ...(mutableResources["fr-FR"].translation.commandBar.recents ?? {}),
  noQuery: "No recent query",
};

mutableResources["fr-FR"].translation.common = {
  ...(mutableResources["fr-FR"].translation.common ?? {}),
  actions: "Actions",
  attempts: "Attempts",
  back: "Back",
  cancel: "Cancel",
  clear: "Clear",
  close: "Close",
  code: "Code",
  completedAt: "Completed at",
  copy: "Copy",
  details: "Details",
  display: "Display",
  edit: "Edit",
  executions: "Executions",
  expand: "Expand",
  filters: "Filters",
  lines: "Lines",
  message: "Message",
  mode: "Mode",
  model: "Model",
  noAgent: "No agent",
  noHistory: "No history",
  off: "Off",
  on: "On",
  open: "Open",
  payload: "Payload",
  phase: "Phase",
  pod: "Pod",
  preview: "Preview",
  reconnect: "Reconnect",
  refresh: "Refresh",
  save: "Save",
  schedules: "Schedules",
  sessions: "Sessions",
  startedAt: "Started at",
  task: "Task",
  timing: "Timing",
  totalTime: "Total time",
  user: "User",
  visual: "Visual",
  workspaceDirectory: "Workspace directory",
};

mutableResources["fr-FR"].translation.controlPlane.create = {
  ...(mutableResources["fr-FR"].translation.controlPlane.create ?? {}),
  agentIdHint: "Lowercase, no spaces. Used as canonical identifier.",
  agentIdLabel: "Agent ID",
  agentIdPlaceholder: "e.g. sales-assistant",
  cancel: "Cancel",
  colorLabel: "Color",
  descriptionLabel: "Description",
  descriptionPlaceholder: "Optional short description",
  genericError: "Could not create the resource. Please try again.",
  nameLabel: "Name",
  parentWorkspace: "Parent workspace",
  squadNone: "No squad",
  squadOptional: "Squad (optional)",
  submit: "Create",
  subtitle: "Fill the fields below to publish.",
  typeLabel: "Type",
  workspaceChoose: "Choose a workspace",
  workspaceNone: "No workspace",
  workspaceOptional: "Workspace (optional)",
};

mutableResources["fr-FR"].translation.controlPlane.create.name = {
  ...(mutableResources["fr-FR"].translation.controlPlane.create.name ?? {}),
  agent: "Agent name",
  squad: "Squad name",
  workspace: "Workspace name",
};

mutableResources["fr-FR"].translation.controlPlane.policy = {
  ...(mutableResources["fr-FR"].translation.controlPlane.policy ?? {}),
  add: "Add",
  addPlaceholder: "Add new item…",
  empty: "No items yet.",
  remove: "Remove",
};

mutableResources["fr-FR"].translation.controlPlane.prompt = {
  ...(mutableResources["fr-FR"].translation.controlPlane.prompt ?? {}),
  edit: "Edit",
  placeholder: "Write the system prompt for this agent…",
  preview: "Preview",
};

mutableResources["fr-FR"].translation.controlPlane.saveBar = {
  ...(mutableResources["fr-FR"].translation.controlPlane.saveBar ?? {}),
  dirty: "Unsaved changes",
  dirtyMany: "{{count}} unsaved changes",
  discard: "Discard",
  save: "Save",
  saved: "Saved",
};

mutableResources["fr-FR"].translation.costs.page = {
  ...(mutableResources["fr-FR"].translation.costs.page ?? {}),
  allocationDominant: "Dominant:",
  allocationFooter: "{{label}} accounts for {{value}} of the current cut and leads the observed distribution.",
  emptyBreakdownShort: "Not enough data",
  executionsCount: "{{count}} executions",
  loadError: "Could not load costs.",
  noConversations: "No conversations in the current filter.",
  noDominantAllocation: "No dominant concentration",
  noDominantModel: "No dominant model",
  noDominantOrigin: "No dominant origin",
  noModel: "No model",
  noPeak: "No highlighted peak in the period",
  noRecentPreview: "No recent preview",
  queriesCount: "{{count}} queries",
  shareInPeriod: "Share in period",
  unavailable: "Costs unavailable",
};

mutableResources["fr-FR"].translation.costs.page.allocationModes = {
  ...(mutableResources["fr-FR"].translation.costs.page.allocationModes ?? {}),
  task: "By task",
};

mutableResources["fr-FR"].translation.costs.page.breakdowns = {
  ...(mutableResources["fr-FR"].translation.costs.page.breakdowns ?? {}),
  byAgentTitle: "Distribution by agent",
  byModelTitle: "Distribution by model",
  byTaskTitle: "Distribution by task type",
};

mutableResources["fr-FR"].translation.costs.page.kpiContexts = {
  ...(mutableResources["fr-FR"].translation.costs.page.kpiContexts ?? {}),
  noComparableBase: "No comparable baseline",
  previousBase: "Previous base {{value}}",
  resolvedConversations: "{{count}} resolved conversations",
  totalPeriod: "{{queries}} queries · {{executions}} executions",
};

mutableResources["fr-FR"].translation.costs.page.timeChart = {
  ...(mutableResources["fr-FR"].translation.costs.page.timeChart ?? {}),
  base: "Base:",
  buckets: "Buckets:",
  driver: "Driver · {{value}}",
  emptyShort: "Not enough data",
  modeLabel: "Mode",
  noBucket: "No bucket",
  noDriver: "No dominant driver",
  peak: "Peak:",
  variation: "Variation:",
};

mutableResources["fr-FR"].translation.dashboard.checklist = {
  ...(mutableResources["fr-FR"].translation.dashboard.checklist ?? {}),
  agent: "Create your first agent",
  dismiss: "Dismiss",
  provider: "Configure a provider",
  subtitle: "Finish the workspace setup to unlock automations.",
  telegram: "Connect Telegram",
  title: "Getting started",
};

mutableResources["fr-FR"].translation.dlq.page = {
  ...(mutableResources["fr-FR"].translation.dlq.page ?? {}),
  affectedAgents: "Affected agents",
};

mutableResources["fr-FR"].translation.dlq.table = {
  ...(mutableResources["fr-FR"].translation.dlq.table ?? {}),
  noAgent: "No agent linked",
};

mutableResources["fr-FR"].translation.executions.page = {
  ...(mutableResources["fr-FR"].translation.executions.page ?? {}),
  loadError: "Could not load execution details.",
};

mutableResources["fr-FR"].translation.executions.page.metrics = {
  ...(mutableResources["fr-FR"].translation.executions.page.metrics ?? {}),
  avgDurationHint: "Average run time across the current filter",
  costHint: "Total cost for the current cut",
  toolsHint: "Number of tool invocations observed",
  warningsHint: "Tasks that required retries or flagged warnings",
};

mutableResources["fr-FR"].translation.memory.curation = {
  ...(mutableResources["fr-FR"].translation.memory.curation ?? {}),
  selectedCount: "{{count}} items selected",
};

mutableResources["fr-FR"].translation.memory.curation.detail = {
  ...(mutableResources["fr-FR"].translation.memory.curation.detail ?? {}),
  memoriesConnected: "{{count}} connected memories",
};

mutableResources["fr-FR"].translation.memory.curation.row = {
  ...(mutableResources["fr-FR"].translation.memory.curation.row ?? {}),
  sessionCount: "{{count}} sessions",
};

mutableResources["fr-FR"].translation.memory.inspector = {
  ...(mutableResources["fr-FR"].translation.memory.inspector ?? {}),
  content: "Content",
  details: "Details",
  empty: "Select a point on the map",
  expiresAt: "Expires at",
  members: "Members",
  never: "Never",
  recenter: "Recenter",
  selectPointHint: "Click a memory on the map to inspect it.",
};

mutableResources["fr-FR"].translation.memory.map = {
  ...(mutableResources["fr-FR"].translation.memory.map ?? {}),
  canvasAriaLabel: "Memory map canvas",
  clusters: "Clusters",
  memoryCount: "{{count}} memories",
  reset: "Reset map",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
};

mutableResources["fr-FR"].translation.memory.page = {
  ...(mutableResources["fr-FR"].translation.memory.page ?? {}),
  noAgentsDescription: "Create or publish at least one agent before opening the map.",
  noAgentsTitle: "No agents available",
};

mutableResources["fr-FR"].translation.overview.activity = {
  ...(mutableResources["fr-FR"].translation.overview.activity ?? {}),
  deploy: "Deploy",
  events: "{{count}} events",
  latestExecutions: "Latest executions",
  noRecent: "No recent activity",
  retry: "Retry",
  showingRecent: "Showing the most recent events",
  taskCompleted: "Task completed",
  taskFailed: "Task failed",
  taskQueued: "Task queued",
  taskStarted: "Task started",
};

mutableResources["fr-FR"].translation.runtime.overview.metrics = {
  ...(mutableResources["fr-FR"].translation.runtime.overview.metrics ?? {}),
  attentionHint: "Executions requiring review or retries",
  executionsHint: "Live executions across visible agents",
  onlineAgents: "Agents online",
  onlineAgentsHint: "Agents with a healthy runtime heartbeat",
};

mutableResources["fr-FR"].translation.schedules.page = {
  ...(mutableResources["fr-FR"].translation.schedules.page ?? {}),
  unavailable: "Schedules unavailable",
  unavailableDescription: "Unable to load canonical schedules.",
  visibleAgents: "Visible agents",
};

mutableResources["fr-FR"].translation.schedules.table = {
  ...(mutableResources["fr-FR"].translation.schedules.table ?? {}),
  nextRun: "Next run",
};

mutableResources["fr-FR"].translation.screenTime = {
  ...(mutableResources["fr-FR"].translation.screenTime ?? {}),
  focusAgents: "Agents in focus",
};

mutableResources["fr-FR"].translation.sessions.composer = {
  ...(mutableResources["fr-FR"].translation.sessions.composer ?? {}),
  selectAgentToStart: "Select a specific agent here to start a chat.",
};

mutableResources["fr-FR"].translation.sessions.context = {
  ...(mutableResources["fr-FR"].translation.sessions.context ?? {}),
  summaryLabel: "Summary",
};

mutableResources["fr-FR"].translation.sessions.context.artifacts = {
  ...(mutableResources["fr-FR"].translation.sessions.context.artifacts ?? {}),
  executionFallback: "Execution artifact",
  label: "Artifacts",
  openExternal: "Open externally",
  previewUnavailable: "Preview unavailable",
};

mutableResources["fr-FR"].translation.sessions.detail = {
  ...(mutableResources["fr-FR"].translation.sessions.detail ?? {}),
  agent: "Agent",
  model: "Model",
};

mutableResources["fr-FR"].translation.sessions.thread = {
  ...(mutableResources["fr-FR"].translation.sessions.thread ?? {}),
  heroHelper: "Pick an agent in the composer and send the first message.",
  heroTitle: "Start a new conversation",
  newChatEyebrow: "New chat",
};

mutableResources["fr-FR"].translation.settings.sections = {
  ...(mutableResources["fr-FR"].translation.settings.sections ?? {}),
  navigation: "Navigation",
};

mutableResources["de-DE"].translation.agentDetail = {
  ...(mutableResources["de-DE"].translation.agentDetail ?? {}),
  activeSchedules: "Active schedules",
  activeTitle: "{{agent}} active",
  databaseNotInitialized: "Database not initialized yet",
  entriesCount: "{{count}} entries",
  noPublishedData: "No published data",
  noRecentTasks: "No recent task.",
  noSchedule: "No schedule.",
  noSession: "No session.",
  noTask: "No task.",
  recent: "Recent",
  refresh: "Refresh",
  situation: "Situation",
  stableTitle: "{{agent}} stable",
  trackedSessions: "Tracked sessions",
  unavailable: "Agent unavailable",
};

mutableResources["de-DE"].translation.agentDetail.metrics = {
  ...(mutableResources["de-DE"].translation.agentDetail.metrics ?? {}),
  active: "Active",
  completed: "Completed",
  failed: "Failures",
  lastActivity: "Last activity",
  queries: "Queries",
  schedules: "Schedules",
  todayCost: "Cost today",
  totalCost: "Total cost",
};

mutableResources["de-DE"].translation.agentDetail.tabs = {
  ...(mutableResources["de-DE"].translation.agentDetail.tabs ?? {}),
  cron: "Schedules",
  overview: "Overview",
  sessions: "Sessions",
  tasks: "Executions",
};

mutableResources["de-DE"].translation.agentSwitcher = {
  ...(mutableResources["de-DE"].translation.agentSwitcher ?? {}),
  createAria: "Create new agent",
};

mutableResources["de-DE"].translation.chat.composer = {
  ...(mutableResources["de-DE"].translation.chat.composer ?? {}),
  placeholder: "Write a message...",
  send: "Send",
  sendHint: "Enter to send • Shift + Enter for a new line",
};

mutableResources["de-DE"].translation.chat.header = {
  ...(mutableResources["de-DE"].translation.chat.header ?? {}),
  viewDetails: "View details",
};

mutableResources["de-DE"].translation.chat.rail = {
  ...(mutableResources["de-DE"].translation.chat.rail ?? {}),
  clearSearch: "Clear search",
  close: "Close conversation list",
  empty: "No conversations yet",
  emptyHelper: "Start a new session to see it here.",
  newSession: "New session",
  noResults: "No results",
  openLabel: "Open conversation list",
  search: "Search",
  title: "Conversations",
  unavailable: "History unavailable",
};

mutableResources["de-DE"].translation.chat.reasoning = {
  ...(mutableResources["de-DE"].translation.chat.reasoning ?? {}),
  expandLabelDone: "Thought for {{duration}}",
  expandLabelDoneNoDuration: "Reasoning",
  expandLabelStreaming: "Thinking…",
};

mutableResources["de-DE"].translation.chat.thread = {
  ...(mutableResources["de-DE"].translation.chat.thread ?? {}),
  empty: "No messages yet.",
  errorGeneric: "Something went wrong. Please try again.",
  failed: "Failed to send",
  newMessages: "New messages",
  retry: "Retry",
  thinking: "Thinking…",
};

mutableResources["de-DE"].translation.chat.timestamp = {
  ...(mutableResources["de-DE"].translation.chat.timestamp ?? {}),
  lastActivity: "Last activity",
};

mutableResources["de-DE"].translation.chat.toolCall = {
  ...(mutableResources["de-DE"].translation.chat.toolCall ?? {}),
  completed: "Completed",
  cost: "cost",
  failed: "Failed",
  queued: "Queued",
  retrying: "Retrying",
  running: "Running",
  tools: "tools",
  viewArgs: "Arguments",
  viewExecution: "View execution",
};

mutableResources["de-DE"].translation.commandBar = {
  ...(mutableResources["de-DE"].translation.commandBar ?? {}),
  emptyState: "No matching commands or agents.",
  modalTitle: "Command bar",
  placeholder: "Search commands, agents, and actions…",
  shortcutHint: "⌘K",
};

mutableResources["de-DE"].translation.commandBar.agent = {
  ...(mutableResources["de-DE"].translation.commandBar.agent ?? {}),
  description: "Open agent detail",
};

mutableResources["de-DE"].translation.commandBar.groups = {
  ...(mutableResources["de-DE"].translation.commandBar.groups ?? {}),
  actions: "Actions",
  agents: "Agents",
  approvals: "Approvals",
  pages: "Pages",
  recents: "Recent",
  skills: "Skills",
  tools: "Tools",
};

mutableResources["de-DE"].translation.commandBar.recents = {
  ...(mutableResources["de-DE"].translation.commandBar.recents ?? {}),
  noQuery: "No recent query",
};

mutableResources["de-DE"].translation.common = {
  ...(mutableResources["de-DE"].translation.common ?? {}),
  actions: "Actions",
  attempts: "Attempts",
  back: "Back",
  cancel: "Cancel",
  clear: "Clear",
  close: "Close",
  code: "Code",
  completedAt: "Completed at",
  copy: "Copy",
  details: "Details",
  display: "Display",
  edit: "Edit",
  executions: "Executions",
  expand: "Expand",
  filters: "Filters",
  lines: "Lines",
  message: "Message",
  mode: "Mode",
  model: "Model",
  noAgent: "No agent",
  noHistory: "No history",
  off: "Off",
  on: "On",
  open: "Open",
  payload: "Payload",
  phase: "Phase",
  pod: "Pod",
  preview: "Preview",
  reconnect: "Reconnect",
  refresh: "Refresh",
  save: "Save",
  schedules: "Schedules",
  sessions: "Sessions",
  startedAt: "Started at",
  task: "Task",
  timing: "Timing",
  totalTime: "Total time",
  user: "User",
  visual: "Visual",
  workspaceDirectory: "Workspace directory",
};

mutableResources["de-DE"].translation.controlPlane.create = {
  ...(mutableResources["de-DE"].translation.controlPlane.create ?? {}),
  agentIdHint: "Lowercase, no spaces. Used as canonical identifier.",
  agentIdLabel: "Agent ID",
  agentIdPlaceholder: "e.g. sales-assistant",
  cancel: "Cancel",
  colorLabel: "Color",
  descriptionLabel: "Description",
  descriptionPlaceholder: "Optional short description",
  genericError: "Could not create the resource. Please try again.",
  nameLabel: "Name",
  parentWorkspace: "Parent workspace",
  squadNone: "No squad",
  squadOptional: "Squad (optional)",
  submit: "Create",
  subtitle: "Fill the fields below to publish.",
  typeLabel: "Type",
  workspaceChoose: "Choose a workspace",
  workspaceNone: "No workspace",
  workspaceOptional: "Workspace (optional)",
};

mutableResources["de-DE"].translation.controlPlane.create.name = {
  ...(mutableResources["de-DE"].translation.controlPlane.create.name ?? {}),
  agent: "Agent name",
  squad: "Squad name",
  workspace: "Workspace name",
};

mutableResources["de-DE"].translation.controlPlane.policy = {
  ...(mutableResources["de-DE"].translation.controlPlane.policy ?? {}),
  add: "Add",
  addPlaceholder: "Add new item…",
  empty: "No items yet.",
  remove: "Remove",
};

mutableResources["de-DE"].translation.controlPlane.prompt = {
  ...(mutableResources["de-DE"].translation.controlPlane.prompt ?? {}),
  edit: "Edit",
  placeholder: "Write the system prompt for this agent…",
  preview: "Preview",
};

mutableResources["de-DE"].translation.controlPlane.saveBar = {
  ...(mutableResources["de-DE"].translation.controlPlane.saveBar ?? {}),
  dirty: "Unsaved changes",
  dirtyMany: "{{count}} unsaved changes",
  discard: "Discard",
  save: "Save",
  saved: "Saved",
};

mutableResources["de-DE"].translation.costs.page = {
  ...(mutableResources["de-DE"].translation.costs.page ?? {}),
  allocationDominant: "Dominant:",
  allocationFooter: "{{label}} accounts for {{value}} of the current cut and leads the observed distribution.",
  emptyBreakdownShort: "Not enough data",
  executionsCount: "{{count}} executions",
  loadError: "Could not load costs.",
  noConversations: "No conversations in the current filter.",
  noDominantAllocation: "No dominant concentration",
  noDominantModel: "No dominant model",
  noDominantOrigin: "No dominant origin",
  noModel: "No model",
  noPeak: "No highlighted peak in the period",
  noRecentPreview: "No recent preview",
  queriesCount: "{{count}} queries",
  shareInPeriod: "Share in period",
  unavailable: "Costs unavailable",
};

mutableResources["de-DE"].translation.costs.page.allocationModes = {
  ...(mutableResources["de-DE"].translation.costs.page.allocationModes ?? {}),
  task: "By task",
};

mutableResources["de-DE"].translation.costs.page.breakdowns = {
  ...(mutableResources["de-DE"].translation.costs.page.breakdowns ?? {}),
  byAgentTitle: "Distribution by agent",
  byModelTitle: "Distribution by model",
  byTaskTitle: "Distribution by task type",
};

mutableResources["de-DE"].translation.costs.page.kpiContexts = {
  ...(mutableResources["de-DE"].translation.costs.page.kpiContexts ?? {}),
  noComparableBase: "No comparable baseline",
  previousBase: "Previous base {{value}}",
  resolvedConversations: "{{count}} resolved conversations",
  totalPeriod: "{{queries}} queries · {{executions}} executions",
};

mutableResources["de-DE"].translation.costs.page.timeChart = {
  ...(mutableResources["de-DE"].translation.costs.page.timeChart ?? {}),
  base: "Base:",
  buckets: "Buckets:",
  driver: "Driver · {{value}}",
  emptyShort: "Not enough data",
  modeLabel: "Mode",
  noBucket: "No bucket",
  noDriver: "No dominant driver",
  peak: "Peak:",
  variation: "Variation:",
};

mutableResources["de-DE"].translation.dashboard.checklist = {
  ...(mutableResources["de-DE"].translation.dashboard.checklist ?? {}),
  agent: "Create your first agent",
  dismiss: "Dismiss",
  provider: "Configure a provider",
  subtitle: "Finish the workspace setup to unlock automations.",
  telegram: "Connect Telegram",
  title: "Getting started",
};

mutableResources["de-DE"].translation.dlq.page = {
  ...(mutableResources["de-DE"].translation.dlq.page ?? {}),
  affectedAgents: "Affected agents",
};

mutableResources["de-DE"].translation.dlq.table = {
  ...(mutableResources["de-DE"].translation.dlq.table ?? {}),
  noAgent: "No agent linked",
};

mutableResources["de-DE"].translation.executions.page = {
  ...(mutableResources["de-DE"].translation.executions.page ?? {}),
  loadError: "Could not load execution details.",
};

mutableResources["de-DE"].translation.executions.page.metrics = {
  ...(mutableResources["de-DE"].translation.executions.page.metrics ?? {}),
  avgDurationHint: "Average run time across the current filter",
  costHint: "Total cost for the current cut",
  toolsHint: "Number of tool invocations observed",
  warningsHint: "Tasks that required retries or flagged warnings",
};

mutableResources["de-DE"].translation.memory.curation = {
  ...(mutableResources["de-DE"].translation.memory.curation ?? {}),
  selectedCount: "{{count}} items selected",
};

mutableResources["de-DE"].translation.memory.curation.detail = {
  ...(mutableResources["de-DE"].translation.memory.curation.detail ?? {}),
  memoriesConnected: "{{count}} connected memories",
};

mutableResources["de-DE"].translation.memory.curation.row = {
  ...(mutableResources["de-DE"].translation.memory.curation.row ?? {}),
  sessionCount: "{{count}} sessions",
};

mutableResources["de-DE"].translation.memory.inspector = {
  ...(mutableResources["de-DE"].translation.memory.inspector ?? {}),
  content: "Content",
  details: "Details",
  empty: "Select a point on the map",
  expiresAt: "Expires at",
  members: "Members",
  never: "Never",
  recenter: "Recenter",
  selectPointHint: "Click a memory on the map to inspect it.",
};

mutableResources["de-DE"].translation.memory.map = {
  ...(mutableResources["de-DE"].translation.memory.map ?? {}),
  canvasAriaLabel: "Memory map canvas",
  clusters: "Clusters",
  memoryCount: "{{count}} memories",
  reset: "Reset map",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
};

mutableResources["de-DE"].translation.memory.page = {
  ...(mutableResources["de-DE"].translation.memory.page ?? {}),
  noAgentsDescription: "Create or publish at least one agent before opening the map.",
  noAgentsTitle: "No agents available",
};

mutableResources["de-DE"].translation.overview.activity = {
  ...(mutableResources["de-DE"].translation.overview.activity ?? {}),
  deploy: "Deploy",
  events: "{{count}} events",
  latestExecutions: "Latest executions",
  noRecent: "No recent activity",
  retry: "Retry",
  showingRecent: "Showing the most recent events",
  taskCompleted: "Task completed",
  taskFailed: "Task failed",
  taskQueued: "Task queued",
  taskStarted: "Task started",
};

mutableResources["de-DE"].translation.runtime.overview.metrics = {
  ...(mutableResources["de-DE"].translation.runtime.overview.metrics ?? {}),
  attentionHint: "Executions requiring review or retries",
  executionsHint: "Live executions across visible agents",
  onlineAgents: "Agents online",
  onlineAgentsHint: "Agents with a healthy runtime heartbeat",
};

mutableResources["de-DE"].translation.schedules.page = {
  ...(mutableResources["de-DE"].translation.schedules.page ?? {}),
  unavailable: "Schedules unavailable",
  unavailableDescription: "Unable to load canonical schedules.",
  visibleAgents: "Visible agents",
};

mutableResources["de-DE"].translation.schedules.table = {
  ...(mutableResources["de-DE"].translation.schedules.table ?? {}),
  nextRun: "Next run",
};

mutableResources["de-DE"].translation.screenTime = {
  ...(mutableResources["de-DE"].translation.screenTime ?? {}),
  focusAgents: "Agents in focus",
};

mutableResources["de-DE"].translation.sessions.composer = {
  ...(mutableResources["de-DE"].translation.sessions.composer ?? {}),
  selectAgentToStart: "Select a specific agent here to start a chat.",
};

mutableResources["de-DE"].translation.sessions.context = {
  ...(mutableResources["de-DE"].translation.sessions.context ?? {}),
  summaryLabel: "Summary",
};

mutableResources["de-DE"].translation.sessions.context.artifacts = {
  ...(mutableResources["de-DE"].translation.sessions.context.artifacts ?? {}),
  executionFallback: "Execution artifact",
  label: "Artifacts",
  openExternal: "Open externally",
  previewUnavailable: "Preview unavailable",
};

mutableResources["de-DE"].translation.sessions.detail = {
  ...(mutableResources["de-DE"].translation.sessions.detail ?? {}),
  agent: "Agent",
  model: "Model",
};

mutableResources["de-DE"].translation.sessions.thread = {
  ...(mutableResources["de-DE"].translation.sessions.thread ?? {}),
  heroHelper: "Pick an agent in the composer and send the first message.",
  heroTitle: "Start a new conversation",
  newChatEyebrow: "New chat",
};

mutableResources["de-DE"].translation.settings.sections = {
  ...(mutableResources["de-DE"].translation.settings.sections ?? {}),
  navigation: "Navigation",
};

Object.assign(literalResources["en-US"] as Record<string, string>, generatedLiteralResources["en-US"]);
Object.assign(literalResources["pt-BR"] as Record<string, string>, generatedLiteralResources["pt-BR"]);
Object.assign(literalResources["es-ES"] as Record<string, string>, generatedLiteralResources["es-ES"]);
Object.assign(literalResources["fr-FR"] as Record<string, string>, generatedLiteralResources["fr-FR"]);
Object.assign(literalResources["de-DE"] as Record<string, string>, generatedLiteralResources["de-DE"]);

export type ResourceLanguages = keyof typeof resources;
