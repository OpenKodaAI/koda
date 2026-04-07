/* ------------------------------------------------------------------ */
/*  Extended integration catalog – data layer                          */
/* ------------------------------------------------------------------ */

export type IntegrationCategory = "development" | "productivity" | "data" | "cloud";

export type IntegrationCapability = {
  id: string;
  label: string;
  description: string;
  icon: string; // Lucide icon key
};

export type IntegrationCatalogEntry = {
  key: string;
  toggleKey: string;
  label: string;
  tagline: string;
  description: string;
  category: IntegrationCategory;
  hasCredentials: boolean;
  logoKey: string;
  gradientFrom: string;
  gradientTo: string;
  promptExample: string;
  capabilities: IntegrationCapability[];
  metadata: {
    developer: string;
    type: string;
    documentationUrl?: string;
  };
};

export const CATEGORY_LABELS: Record<IntegrationCategory, string> = {
  development: "Desenvolvimento",
  productivity: "Produtividade",
  data: "Dados",
  cloud: "Cloud",
};

export const INTEGRATION_CATALOG: IntegrationCatalogEntry[] = [
  {
    key: "browser",
    toggleKey: "browser_enabled",
    label: "Browser",
    tagline: "Navegação governada e automação de páginas",
    description:
      "Ative o browser gerenciado do Koda para navegar, extrair conteúdo, clicar, preencher formulários e coletar evidências com rastreabilidade e governança por domínio.",
    category: "productivity",
    hasCredentials: false,
    logoKey: "browser",
    gradientFrom: "#7C9CFF",
    gradientTo: "#3656D4",
    promptExample: "Abra o dashboard e capture um screenshot do estado atual da página",
    capabilities: [
      {
        id: "browser-navigate",
        label: "Navegação",
        description: "Abrir páginas e seguir fluxos com sessões escopadas por tarefa",
        icon: "Search",
      },
      {
        id: "browser-read",
        label: "Leitura da página",
        description: "Captura de texto, elementos e evidências visuais",
        icon: "FileText",
      },
      {
        id: "browser-actions",
        label: "Automação guiada",
        description: "Cliques, preenchimento e submissões com grants por ação",
        icon: "Workflow",
      },
    ],
    metadata: {
      developer: "Koda",
      type: "Runtime",
    },
  },
  {
    key: "jira",
    toggleKey: "jira_enabled",
    label: "Jira",
    tagline: "Busca e operações governadas de issues",
    description:
      "Use o Jira para buscar, criar e atualizar issues diretamente pela conversa. " +
      "O agente aplica governança automática de segurança, garantindo que apenas operações " +
      "permitidas sejam executadas dentro dos limites configurados.",
    category: "productivity",
    hasCredentials: true,
    logoKey: "jira",
    gradientFrom: "#2684FF",
    gradientTo: "#0052CC",
    promptExample: "Busque os tickets abertos do sprint atual no projeto PLAT",
    capabilities: [
      {
        id: "jira-search",
        label: "Buscar Issues",
        description: "Consultas JQL governadas com filtros de segurança",
        icon: "Search",
      },
      {
        id: "jira-create",
        label: "Criar Issues",
        description: "Criação de tickets com campos obrigatórios validados",
        icon: "Plus",
      },
      {
        id: "jira-update",
        label: "Atualizar Issues",
        description: "Transições de status, comentários e edição de campos",
        icon: "Pencil",
      },
      {
        id: "jira-boards",
        label: "Boards & Sprints",
        description: "Visualização de quadros, sprints e backlogs",
        icon: "LayoutDashboard",
      },
    ],
    metadata: {
      developer: "Atlassian",
      type: "API",
      documentationUrl: "https://developer.atlassian.com/cloud/jira/platform/rest/v3/",
    },
  },
  {
    key: "confluence",
    toggleKey: "confluence_enabled",
    label: "Confluence",
    tagline: "Leitura governada de páginas e espaços",
    description:
      "Acesse páginas e espaços do Confluence para pesquisa e referência contextual. " +
      "O acesso é governado com filtros de segurança para garantir que apenas conteúdo " +
      "autorizado seja lido pelo agente.",
    category: "productivity",
    hasCredentials: true,
    logoKey: "confluence",
    gradientFrom: "#1868DB",
    gradientTo: "#0747A6",
    promptExample: "Encontre a documentação de arquitetura no espaço ENG",
    capabilities: [
      {
        id: "confluence-search",
        label: "Buscar Páginas",
        description: "Pesquisa CQL em espaços e páginas com governança",
        icon: "Search",
      },
      {
        id: "confluence-read",
        label: "Leitura de Conteúdo",
        description: "Acesso governado ao corpo de páginas e anexos",
        icon: "FileText",
      },
      {
        id: "confluence-spaces",
        label: "Navegação de Espaços",
        description: "Listagem e exploração de espaços disponíveis",
        icon: "FolderOpen",
      },
    ],
    metadata: {
      developer: "Atlassian",
      type: "API",
      documentationUrl: "https://developer.atlassian.com/cloud/confluence/rest/v2/",
    },
  },
  {
    key: "gws",
    toggleKey: "gws_enabled",
    label: "Google Workspace",
    tagline: "Operações via credencial de serviço",
    description:
      "Integre com Gmail, Google Calendar, Drive e Sheets através de uma credencial " +
      "de serviço. Permite ao agente executar operações governadas nos serviços do " +
      "Google Workspace com controle granular de permissões.",
    category: "productivity",
    hasCredentials: true,
    logoKey: "google",
    gradientFrom: "#4285F4",
    gradientTo: "#34A853",
    promptExample: "Liste os próximos eventos do meu calendário para esta semana",
    capabilities: [
      {
        id: "gws-gmail",
        label: "Gmail",
        description: "Leitura e envio de e-mails governados",
        icon: "Mail",
      },
      {
        id: "gws-calendar",
        label: "Google Calendar",
        description: "Consulta e criação de eventos",
        icon: "Calendar",
      },
      {
        id: "gws-drive",
        label: "Google Drive",
        description: "Navegação e leitura de arquivos",
        icon: "HardDrive",
      },
      {
        id: "gws-sheets",
        label: "Google Sheets",
        description: "Leitura e edição de planilhas",
        icon: "Table",
      },
    ],
    metadata: {
      developer: "Google",
      type: "Serviço",
      documentationUrl: "https://developers.google.com/workspace",
    },
  },
  {
    key: "aws",
    toggleKey: "aws_enabled",
    label: "AWS",
    tagline: "Operações cloud com perfis e região",
    description:
      "Execute operações governadas nos serviços AWS usando perfis configurados. " +
      "Suporta múltiplos perfis (dev/prod) com região configurável para operações " +
      "seguras e auditáveis na infraestrutura cloud.",
    category: "cloud",
    hasCredentials: true,
    logoKey: "aws",
    gradientFrom: "#FF9900",
    gradientTo: "#232F3E",
    promptExample: "Liste as instâncias EC2 ativas na região us-east-1",
    capabilities: [
      {
        id: "aws-ec2",
        label: "EC2 & Compute",
        description: "Gerenciamento de instâncias e recursos de computação",
        icon: "Server",
      },
      {
        id: "aws-s3",
        label: "S3 & Storage",
        description: "Operações em buckets e objetos",
        icon: "HardDrive",
      },
      {
        id: "aws-logs",
        label: "CloudWatch Logs",
        description: "Consulta e análise de logs",
        icon: "ScrollText",
      },
      {
        id: "aws-profiles",
        label: "Perfis Multi-Ambiente",
        description: "Suporte a perfis dev e prod isolados",
        icon: "Shield",
      },
    ],
    metadata: {
      developer: "Amazon",
      type: "CLI",
      documentationUrl: "https://docs.aws.amazon.com/",
    },
  },
  {
    key: "gh",
    toggleKey: "gh_enabled",
    label: "GitHub",
    tagline: "CLI para repos, PRs e issues",
    description:
      "Use o GitHub CLI para inspecionar repositórios, revisar pull requests, " +
      "triagem de issues e depurar falhas de CI. Funciona com a autenticação " +
      "do CLI local sem credenciais adicionais.",
    category: "development",
    hasCredentials: true,
    logoKey: "github",
    gradientFrom: "#6e5494",
    gradientTo: "#24292e",
    promptExample: "Revise o PR #142 e sugira melhorias no código",
    capabilities: [
      {
        id: "gh-repos",
        label: "Repositórios",
        description: "Inspeção de repos, branches e commits",
        icon: "GitBranch",
      },
      {
        id: "gh-prs",
        label: "Pull Requests",
        description: "Revisão, comentários e merge de PRs",
        icon: "GitPullRequest",
      },
      {
        id: "gh-issues",
        label: "Issues",
        description: "Triagem, criação e atualização de issues",
        icon: "CircleDot",
      },
      {
        id: "gh-actions",
        label: "GitHub Actions",
        description: "Inspeção de workflows e depuração de falhas",
        icon: "Play",
      },
    ],
    metadata: {
      developer: "GitHub",
      type: "CLI",
      documentationUrl: "https://cli.github.com/manual/",
    },
  },
  {
    key: "glab",
    toggleKey: "glab_enabled",
    label: "GitLab",
    tagline: "CLI para repos, MRs e pipelines",
    description:
      "Use o GitLab CLI para gerenciar repositórios, merge requests e pipelines " +
      "de CI/CD. Funciona com a autenticação do CLI local sem credenciais adicionais.",
    category: "development",
    hasCredentials: true,
    logoKey: "gitlab",
    gradientFrom: "#FC6D26",
    gradientTo: "#292961",
    promptExample: "Verifique o status do pipeline da branch main",
    capabilities: [
      {
        id: "glab-repos",
        label: "Projetos",
        description: "Inspeção de projetos, branches e commits",
        icon: "GitBranch",
      },
      {
        id: "glab-mrs",
        label: "Merge Requests",
        description: "Revisão, comentários e merge de MRs",
        icon: "GitMerge",
      },
      {
        id: "glab-pipelines",
        label: "Pipelines CI/CD",
        description: "Monitoramento e depuração de pipelines",
        icon: "Workflow",
      },
    ],
    metadata: {
      developer: "GitLab",
      type: "CLI",
      documentationUrl: "https://gitlab.com/gitlab-org/cli",
    },
  },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

export type IntegrationStatus = "disabled" | "pending" | "connected";

/**
 * Derive connection status from draft state for a given integration entry.
 */
export function getIntegrationStatus(
  entry: IntegrationCatalogEntry,
  integrations: Record<string, boolean>,
  connection?: {
    connection_status?: string;
    last_error?: string;
    fields?: Array<{ required?: boolean; value?: string; value_present?: boolean }>;
  } | null,
): IntegrationStatus {
  const connectionStatus = connection?.connection_status;
  if (connectionStatus === "verified") return "connected";
  if (connectionStatus === "configured" || connectionStatus === "degraded" || connectionStatus === "auth_expired") {
    return "pending";
  }
  if (connectionStatus === "error" || connection?.last_error) return "pending";
  const enabled = Boolean(integrations[entry.toggleKey]);
  if (!enabled) return "disabled";

  const fields = connection?.fields || [];
  if (entry.hasCredentials && fields.length > 0) {
    const missingRequired = fields.filter(
      (f) => f.required && !(f.value || f.value_present),
    );
    return missingRequired.length === 0 ? "connected" : "pending";
  }
  return "connected";
}

export function getIntegrationByKey(key: string): IntegrationCatalogEntry | undefined {
  return INTEGRATION_CATALOG.find((e) => e.key === key);
}

export function getCategories(): IntegrationCategory[] {
  const seen = new Set<IntegrationCategory>();
  for (const entry of INTEGRATION_CATALOG) {
    seen.add(entry.category);
  }
  return Array.from(seen);
}

export function getIntegrationsByCategory(
  category: IntegrationCategory | "all",
): IntegrationCatalogEntry[] {
  if (category === "all") return INTEGRATION_CATALOG;
  return INTEGRATION_CATALOG.filter((e) => e.category === category);
}
