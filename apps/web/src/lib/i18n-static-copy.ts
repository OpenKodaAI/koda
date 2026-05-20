export const staticCopyResources = {
  "en-US": {
    controlPlane: {
      agentEditor: {
        steps: {
          identidade: {
            label: "Identity",
            title: "Agent foundation",
            description: "Define the name, visual appearance and connect communication channels such as Telegram.",
            summary: "Who the agent is and how it connects.",
          },
          comportamento: {
            label: "Behavior",
            title: "Personality, instructions and limits",
            description: "Configure mission, operating instructions, response format and security guardrails in objective sections.",
            summary: "Personality, instructions, limits and autonomy.",
          },
          recursos: {
            label: "Capabilities",
            title: "Model and voice",
            description: "Choose the reasoning provider and model, define budget and configure voice capabilities.",
            summary: "Provider, model, budget and voice.",
          },
          skills: {
            label: "Skills",
            title: "Specialized skills",
            description: "Configure the skills policy and create custom skills with individual activation control.",
            summary: "Skills policy and custom skills.",
          },
          conhecimento: {
            label: "Knowledge",
            title: "Memory and grounding",
            description: "Configure persistent memory, RAG, and review approved knowledge candidates and runbooks.",
            summary: "Memory, RAG and knowledge governance.",
          },
          integracoes: {
            label: "Integrations",
            title: "Agent integrations",
            description: "Connect and control which core integrations and MCP servers this agent can access.",
            summary: "Core integrations and MCPs.",
          },
          segredos: {
            label: "Secrets & Variables",
            title: "Secrets and variables",
            description: "Grant access to global secrets and shared variables, and manage local agent variables.",
            summary: "Secret grants and env vars.",
          },
          publicacao: {
            label: "Publishing",
            title: "Save and publish",
            description: "Review pending changes and publish the agent with one click.",
            summary: "Summary, save and publish.",
          },
        },
      },
      agentLifecycle: {
        draftPendingPublish: {
          label: "Unpublished changes",
          description: "There are editor changes that have not been published yet. Save and publish to apply them to runtime.",
        },
        draftUnsaved: {
          label: "Unpublished draft",
          description: "Initial configuration is in progress. Publish for the first time to make the agent operable.",
        },
        neverConfigured: {
          label: "Never published",
          description: "The agent was created but does not have a published version yet. Configure and publish it to activate.",
        },
        awaitingActivation: {
          label: "Published, awaiting activation",
          description: "The version is published but runtime has not started yet. Click Activate to put the agent to work.",
        },
        updatePending: {
          label: "Update pending",
          description: "Runtime is running v{{applied}}, but v{{desired}} has already been published and is waiting to be applied.",
        },
        publishedActive: {
          label: "Active",
          description: "Runtime is running v{{applied}} normally. Messages are processed.",
        },
        publishedPaused: {
          label: "Published · Paused",
          description: "Version v{{applied}} is published but runtime is paused. Messages are not processed.",
        },
        unknown: {
          label: "Status: {{status}}",
          labelFallback: "Unknown state",
          description: "State not covered by the publishing wizard. Check control-plane logs if it persists.",
        },
      },
      instructionBlocks: {
        instructions: {
          label: "Instructions",
          description: "How the agent should process requests, when to escalate, and success criteria.",
        },
        systemPrompt: {
          label: "System Prompt",
          description: "Core directive passed to the LLM before any message.",
        },
        rules: {
          label: "Rules",
          description: "Inviolable rules, security guardrails and limits.",
        },
        identity: {
          label: "Identity",
          description: "Name, professional role and basic agent context.",
        },
        soul: {
          label: "Soul",
          description: "Personality, tone and values for the agent in free prose.",
        },
      },
      mcpToolPolicy: {
        options: {
          auto: { label: "Automatic", description: "Automatic classification" },
          alwaysAllow: { label: "Always allow", description: "Run without approval" },
          alwaysAsk: { label: "Always ask", description: "Requires approval" },
          blocked: { label: "Blocked", description: "Never run" },
        },
      },
      skillCategories: {
        general: "General",
        engineering: "Engineering",
        design: "Design",
        analysis: "Analysis",
        operations: "Operations",
        research: "Research",
        cloud: "Cloud",
      },
      intelligence: {
        memoryProfiles: {
          conservative: "Conservative",
          balanced: "Balanced",
          strongLearning: "Strong learning",
        },
        knowledgeProfiles: {
          curatedOnly: "Curated only",
          curatedWorkspace: "Curated + workspace",
          curatedWorkspacePatterns: "Curated + workspace + patterns",
        },
        embeddingModelDescription: "The model used to index memories, the knowledge base and semantic cache. No model is installed by default: download on demand only if needed.",
      },
    },
    downloads: {
      canceling: "Cancelling download...",
      cancelingAction: "Cancelling",
      cancelingAria: "Cancelling download",
      completedBeforeCancel: "Download completed before cancellation.",
      failed: "Download failed",
      canceled: "Download cancelled.",
      cancelFailed: "Failed to cancel download",
      startFailed: "Failed to start download",
      resuming: "Resuming download...",
      serverUnresponsive: "No response from the server — check the connection",
      reconnecting: "Unstable connection — trying to reconnect",
      cancelAction: "Cancel",
      cancelAria: "Cancel download",
    },
  },
  "pt-BR": {
    controlPlane: {
      agentEditor: {
        steps: {
          identidade: {
            label: "Identidade",
            title: "Fundação do agente",
            description: "Defina nome, aparência visual e conecte canais de comunicação como Telegram.",
            summary: "Quem é o agente e como ele se conecta.",
          },
          comportamento: {
            label: "Comportamento",
            title: "Personalidade, instruções e limites",
            description: "Configure missão, instruções de operação, formato de resposta e guardrails de segurança em seções objetivas.",
            summary: "Personalidade, instruções, limites e autonomia.",
          },
          recursos: {
            label: "Recursos",
            title: "Modelo e voz",
            description: "Escolha o provider e modelo de raciocínio, defina orçamento e configure capacidades de voz.",
            summary: "Provider, modelo, orçamento e voz.",
          },
          skills: {
            label: "Skills",
            title: "Skills especializadas",
            description: "Configure a política de skills, crie skills customizadas com controle individual de ativação.",
            summary: "Política de skills e skills customizadas.",
          },
          conhecimento: {
            label: "Conhecimento",
            title: "Memória e grounding",
            description: "Configure memória persistente, RAG e revise candidatos de conhecimento e runbooks aprovados.",
            summary: "Memória, RAG e governança de conhecimento.",
          },
          integracoes: {
            label: "Integrações",
            title: "Integrações do agente",
            description: "Conecte e controle quais integrações core e servidores MCP este agente pode acessar.",
            summary: "Integrações core e MCPs.",
          },
          segredos: {
            label: "Segredos & Variáveis",
            title: "Segredos e variáveis",
            description: "Conceda acesso a segredos globais e variáveis compartilhadas, e gerencie variáveis locais do agente.",
            summary: "Grants de secrets e env vars.",
          },
          publicacao: {
            label: "Publicação",
            title: "Salvar e publicar",
            description: "Revise as alterações pendentes e publique o agente com um único clique.",
            summary: "Resumo, salvar e publicar.",
          },
        },
      },
      agentLifecycle: {
        draftPendingPublish: {
          label: "Alterações não publicadas",
          description: "Há mudanças no editor que ainda não foram publicadas. Salve e publique para aplicá-las ao runtime.",
        },
        draftUnsaved: {
          label: "Rascunho não publicado",
          description: "Configuração inicial em andamento. Publique pela primeira vez para tornar o agente operável.",
        },
        neverConfigured: {
          label: "Nunca publicado",
          description: "O agente foi criado mas ainda não tem nenhuma versão publicada. Configure e publique para ativar.",
        },
        awaitingActivation: {
          label: "Publicado, aguardando ativação",
          description: "Versão publicada mas o runtime ainda não foi inicializado. Clique em Ativar para colocar o agente para rodar.",
        },
        updatePending: {
          label: "Atualização pendente",
          description: "Runtime rodando a v{{applied}}, mas a v{{desired}} já foi publicada e aguarda aplicação.",
        },
        publishedActive: {
          label: "Ativo",
          description: "Runtime rodando v{{applied}} normalmente. Mensagens são processadas.",
        },
        publishedPaused: {
          label: "Publicado · Pausado",
          description: "Versão v{{applied}} publicada mas o runtime está pausado. Mensagens não são processadas.",
        },
        unknown: {
          label: "Status: {{status}}",
          labelFallback: "Estado desconhecido",
          description: "Estado não previsto pelo wizard de publicação. Consulte os logs do control-plane se persistir.",
        },
      },
      instructionBlocks: {
        instructions: {
          label: "Instruções",
          description: "Como o agente deve processar solicitações, quando escalar, critérios de sucesso.",
        },
        systemPrompt: {
          label: "System Prompt",
          description: "Diretriz central passada ao LLM antes de qualquer mensagem.",
        },
        rules: {
          label: "Regras",
          description: "Regras invioláveis, guardrails de segurança e limites.",
        },
        identity: {
          label: "Identidade",
          description: "Nome, papel profissional e contexto básico do agente.",
        },
        soul: {
          label: "Soul",
          description: "Personalidade, tom e valores do agente em prosa livre.",
        },
      },
      mcpToolPolicy: {
        options: {
          auto: { label: "Automático", description: "Classificação automática" },
          alwaysAllow: { label: "Sempre permitir", description: "Executar sem aprovação" },
          alwaysAsk: { label: "Sempre perguntar", description: "Requer aprovação" },
          blocked: { label: "Bloqueado", description: "Nunca executar" },
        },
      },
      skillCategories: {
        general: "Geral",
        engineering: "Engenharia",
        design: "Design",
        analysis: "Análise",
        operations: "Operações",
        research: "Pesquisa",
        cloud: "Cloud",
      },
      intelligence: {
        memoryProfiles: {
          conservative: "Conservador",
          balanced: "Equilibrado",
          strongLearning: "Aprendizado forte",
        },
        knowledgeProfiles: {
          curatedOnly: "Curado apenas",
          curatedWorkspace: "Curado + workspace",
          curatedWorkspacePatterns: "Curado + workspace + padrões",
        },
        embeddingModelDescription: "O modelo usado para indexar memórias, knowledge base e cache semântico. Nenhum modelo vem instalado: baixe sob demanda apenas se precisar.",
      },
    },
    downloads: {
      canceling: "Cancelando download...",
      cancelingAction: "Cancelando",
      cancelingAria: "Cancelando download",
      completedBeforeCancel: "Download concluído antes do cancelamento.",
      failed: "Falha no download",
      canceled: "Download cancelado.",
      cancelFailed: "Falha ao cancelar o download",
      startFailed: "Falha ao iniciar o download",
      resuming: "Retomando download...",
      serverUnresponsive: "Sem resposta do servidor — verifique a conexão",
      reconnecting: "Conexão instável — tentando reconectar",
      cancelAction: "Cancelar",
      cancelAria: "Cancelar download",
    },
  },
  "es-ES": {
    controlPlane: {
      agentEditor: {
        steps: {
          identidade: {
            label: "Identidad",
            title: "Base del agente",
            description: "Define el nombre, la apariencia visual y conecta canales de comunicación como Telegram.",
            summary: "Quién es el agente y cómo se conecta.",
          },
          comportamento: {
            label: "Comportamiento",
            title: "Personalidad, instrucciones y límites",
            description: "Configura misión, instrucciones operativas, formato de respuesta y guardrails de seguridad en secciones objetivas.",
            summary: "Personalidad, instrucciones, límites y autonomía.",
          },
          recursos: {
            label: "Recursos",
            title: "Modelo y voz",
            description: "Elige el proveedor y modelo de razonamiento, define presupuesto y configura capacidades de voz.",
            summary: "Proveedor, modelo, presupuesto y voz.",
          },
          skills: {
            label: "Skills",
            title: "Skills especializadas",
            description: "Configura la política de skills y crea skills personalizadas con control individual de activación.",
            summary: "Política de skills y skills personalizadas.",
          },
          conhecimento: {
            label: "Conocimiento",
            title: "Memoria y grounding",
            description: "Configura memoria persistente, RAG y revisa candidatos de conocimiento y runbooks aprobados.",
            summary: "Memoria, RAG y gobernanza del conocimiento.",
          },
          integracoes: {
            label: "Integraciones",
            title: "Integraciones del agente",
            description: "Conecta y controla qué integraciones core y servidores MCP puede acceder este agente.",
            summary: "Integraciones core y MCPs.",
          },
          segredos: {
            label: "Secretos y variables",
            title: "Secretos y variables",
            description: "Concede acceso a secretos globales y variables compartidas, y gestiona variables locales del agente.",
            summary: "Grants de secrets y env vars.",
          },
          publicacao: {
            label: "Publicación",
            title: "Guardar y publicar",
            description: "Revisa los cambios pendientes y publica el agente con un solo clic.",
            summary: "Resumen, guardar y publicar.",
          },
        },
      },
      agentLifecycle: {
        draftPendingPublish: {
          label: "Cambios no publicados",
          description: "Hay cambios en el editor que aún no se han publicado. Guarda y publica para aplicarlos al runtime.",
        },
        draftUnsaved: {
          label: "Borrador no publicado",
          description: "La configuración inicial está en curso. Publica por primera vez para que el agente sea operativo.",
        },
        neverConfigured: {
          label: "Nunca publicado",
          description: "El agente fue creado pero todavía no tiene una versión publicada. Configúralo y publícalo para activarlo.",
        },
        awaitingActivation: {
          label: "Publicado, esperando activación",
          description: "La versión está publicada, pero el runtime aún no se ha iniciado. Haz clic en Activar para poner el agente en marcha.",
        },
        updatePending: {
          label: "Actualización pendiente",
          description: "El runtime ejecuta v{{applied}}, pero v{{desired}} ya fue publicada y espera aplicación.",
        },
        publishedActive: {
          label: "Activo",
          description: "El runtime ejecuta v{{applied}} normalmente. Los mensajes se procesan.",
        },
        publishedPaused: {
          label: "Publicado · Pausado",
          description: "La versión v{{applied}} está publicada, pero el runtime está pausado. Los mensajes no se procesan.",
        },
        unknown: {
          label: "Estado: {{status}}",
          labelFallback: "Estado desconocido",
          description: "Estado no previsto por el asistente de publicación. Consulta los logs del control-plane si persiste.",
        },
      },
      instructionBlocks: {
        instructions: {
          label: "Instrucciones",
          description: "Cómo debe procesar solicitudes el agente, cuándo escalar y criterios de éxito.",
        },
        systemPrompt: {
          label: "System Prompt",
          description: "Directriz central enviada al LLM antes de cualquier mensaje.",
        },
        rules: {
          label: "Reglas",
          description: "Reglas inviolables, guardrails de seguridad y límites.",
        },
        identity: {
          label: "Identidad",
          description: "Nombre, rol profesional y contexto básico del agente.",
        },
        soul: {
          label: "Soul",
          description: "Personalidad, tono y valores del agente en prosa libre.",
        },
      },
      mcpToolPolicy: {
        options: {
          auto: { label: "Automático", description: "Clasificación automática" },
          alwaysAllow: { label: "Permitir siempre", description: "Ejecutar sin aprobación" },
          alwaysAsk: { label: "Preguntar siempre", description: "Requiere aprobación" },
          blocked: { label: "Bloqueado", description: "Nunca ejecutar" },
        },
      },
      skillCategories: {
        general: "General",
        engineering: "Ingeniería",
        design: "Diseño",
        analysis: "Análisis",
        operations: "Operaciones",
        research: "Investigación",
        cloud: "Cloud",
      },
      intelligence: {
        memoryProfiles: {
          conservative: "Conservador",
          balanced: "Equilibrado",
          strongLearning: "Aprendizaje fuerte",
        },
        knowledgeProfiles: {
          curatedOnly: "Solo curado",
          curatedWorkspace: "Curado + workspace",
          curatedWorkspacePatterns: "Curado + workspace + patrones",
        },
        embeddingModelDescription: "El modelo usado para indexar memorias, la knowledge base y la caché semántica. Ningún modelo viene instalado: descárgalo bajo demanda solo si lo necesitas.",
      },
    },
    downloads: {
      canceling: "Cancelando descarga...",
      cancelingAction: "Cancelando",
      cancelingAria: "Cancelando descarga",
      completedBeforeCancel: "La descarga terminó antes de la cancelación.",
      failed: "Error en la descarga",
      canceled: "Descarga cancelada.",
      cancelFailed: "No se pudo cancelar la descarga",
      startFailed: "No se pudo iniciar la descarga",
      resuming: "Reanudando descarga...",
      serverUnresponsive: "Sin respuesta del servidor — verifica la conexión",
      reconnecting: "Conexión inestable — intentando reconectar",
      cancelAction: "Cancelar",
      cancelAria: "Cancelar descarga",
    },
  },
  "fr-FR": {
    controlPlane: {
      agentEditor: {
        steps: {
          identidade: {
            label: "Identité",
            title: "Fondation de l'agent",
            description: "Définissez le nom, l'apparence visuelle et connectez des canaux de communication comme Telegram.",
            summary: "Qui est l'agent et comment il se connecte.",
          },
          comportamento: {
            label: "Comportement",
            title: "Personnalité, instructions et limites",
            description: "Configurez la mission, les instructions d'exploitation, le format de réponse et les guardrails de sécurité dans des sections objectives.",
            summary: "Personnalité, instructions, limites et autonomie.",
          },
          recursos: {
            label: "Ressources",
            title: "Modèle et voix",
            description: "Choisissez le fournisseur et le modèle de raisonnement, définissez le budget et configurez les capacités vocales.",
            summary: "Fournisseur, modèle, budget et voix.",
          },
          skills: {
            label: "Skills",
            title: "Skills spécialisées",
            description: "Configurez la politique de skills et créez des skills personnalisées avec contrôle individuel de l'activation.",
            summary: "Politique de skills et skills personnalisées.",
          },
          conhecimento: {
            label: "Connaissance",
            title: "Mémoire et grounding",
            description: "Configurez la mémoire persistante, le RAG, et révisez les candidats de connaissance et runbooks approuvés.",
            summary: "Mémoire, RAG et gouvernance de la connaissance.",
          },
          integracoes: {
            label: "Intégrations",
            title: "Intégrations de l'agent",
            description: "Connectez et contrôlez les intégrations core et serveurs MCP auxquels cet agent peut accéder.",
            summary: "Intégrations core et MCP.",
          },
          segredos: {
            label: "Secrets et variables",
            title: "Secrets et variables",
            description: "Accordez l'accès aux secrets globaux et aux variables partagées, et gérez les variables locales de l'agent.",
            summary: "Grants de secrets et env vars.",
          },
          publicacao: {
            label: "Publication",
            title: "Enregistrer et publier",
            description: "Vérifiez les changements en attente et publiez l'agent en un clic.",
            summary: "Résumé, enregistrer et publier.",
          },
        },
      },
      agentLifecycle: {
        draftPendingPublish: {
          label: "Changements non publiés",
          description: "Des changements dans l'éditeur n'ont pas encore été publiés. Enregistrez et publiez pour les appliquer au runtime.",
        },
        draftUnsaved: {
          label: "Brouillon non publié",
          description: "La configuration initiale est en cours. Publiez une première fois pour rendre l'agent opérationnel.",
        },
        neverConfigured: {
          label: "Jamais publié",
          description: "L'agent a été créé mais n'a encore aucune version publiée. Configurez-le et publiez-le pour l'activer.",
        },
        awaitingActivation: {
          label: "Publié, en attente d'activation",
          description: "La version est publiée, mais le runtime n'a pas encore démarré. Cliquez sur Activer pour lancer l'agent.",
        },
        updatePending: {
          label: "Mise à jour en attente",
          description: "Le runtime exécute v{{applied}}, mais v{{desired}} a déjà été publiée et attend son application.",
        },
        publishedActive: {
          label: "Actif",
          description: "Le runtime exécute v{{applied}} normalement. Les messages sont traités.",
        },
        publishedPaused: {
          label: "Publié · En pause",
          description: "La version v{{applied}} est publiée, mais le runtime est en pause. Les messages ne sont pas traités.",
        },
        unknown: {
          label: "Statut : {{status}}",
          labelFallback: "État inconnu",
          description: "État non prévu par l'assistant de publication. Consultez les logs du control-plane si cela persiste.",
        },
      },
      instructionBlocks: {
        instructions: {
          label: "Instructions",
          description: "Comment l'agent doit traiter les demandes, quand escalader et les critères de réussite.",
        },
        systemPrompt: {
          label: "System Prompt",
          description: "Directive centrale transmise au LLM avant tout message.",
        },
        rules: {
          label: "Règles",
          description: "Règles inviolables, guardrails de sécurité et limites.",
        },
        identity: {
          label: "Identité",
          description: "Nom, rôle professionnel et contexte de base de l'agent.",
        },
        soul: {
          label: "Soul",
          description: "Personnalité, ton et valeurs de l'agent en prose libre.",
        },
      },
      mcpToolPolicy: {
        options: {
          auto: { label: "Automatique", description: "Classification automatique" },
          alwaysAllow: { label: "Toujours autoriser", description: "Exécuter sans approbation" },
          alwaysAsk: { label: "Toujours demander", description: "Nécessite une approbation" },
          blocked: { label: "Bloqué", description: "Ne jamais exécuter" },
        },
      },
      skillCategories: {
        general: "Général",
        engineering: "Ingénierie",
        design: "Design",
        analysis: "Analyse",
        operations: "Opérations",
        research: "Recherche",
        cloud: "Cloud",
      },
      intelligence: {
        memoryProfiles: {
          conservative: "Conservateur",
          balanced: "Équilibré",
          strongLearning: "Apprentissage fort",
        },
        knowledgeProfiles: {
          curatedOnly: "Curé uniquement",
          curatedWorkspace: "Curé + workspace",
          curatedWorkspacePatterns: "Curé + workspace + modèles",
        },
        embeddingModelDescription: "Le modèle utilisé pour indexer les mémoires, la knowledge base et le cache sémantique. Aucun modèle n'est installé par défaut : téléchargez à la demande uniquement si nécessaire.",
      },
    },
    downloads: {
      canceling: "Annulation du téléchargement...",
      cancelingAction: "Annulation",
      cancelingAria: "Annulation du téléchargement",
      completedBeforeCancel: "Le téléchargement s'est terminé avant l'annulation.",
      failed: "Échec du téléchargement",
      canceled: "Téléchargement annulé.",
      cancelFailed: "Impossible d'annuler le téléchargement",
      startFailed: "Impossible de démarrer le téléchargement",
      resuming: "Reprise du téléchargement...",
      serverUnresponsive: "Aucune réponse du serveur — vérifiez la connexion",
      reconnecting: "Connexion instable — tentative de reconnexion",
      cancelAction: "Annuler",
      cancelAria: "Annuler le téléchargement",
    },
  },
  "de-DE": {
    controlPlane: {
      agentEditor: {
        steps: {
          identidade: {
            label: "Identität",
            title: "Agent-Grundlage",
            description: "Definieren Sie Namen und visuelles Erscheinungsbild und verbinden Sie Kommunikationskanäle wie Telegram.",
            summary: "Wer der Agent ist und wie er sich verbindet.",
          },
          comportamento: {
            label: "Verhalten",
            title: "Persönlichkeit, Anweisungen und Grenzen",
            description: "Konfigurieren Sie Mission, Betriebsanweisungen, Antwortformat und Sicherheits-Guardrails in klaren Abschnitten.",
            summary: "Persönlichkeit, Anweisungen, Grenzen und Autonomie.",
          },
          recursos: {
            label: "Ressourcen",
            title: "Modell und Stimme",
            description: "Wählen Sie Anbieter und Reasoning-Modell, legen Sie Budget fest und konfigurieren Sie Sprachfunktionen.",
            summary: "Anbieter, Modell, Budget und Stimme.",
          },
          skills: {
            label: "Skills",
            title: "Spezialisierte Skills",
            description: "Konfigurieren Sie die Skill-Richtlinie und erstellen Sie benutzerdefinierte Skills mit individueller Aktivierungssteuerung.",
            summary: "Skill-Richtlinie und benutzerdefinierte Skills.",
          },
          conhecimento: {
            label: "Wissen",
            title: "Speicher und Grounding",
            description: "Konfigurieren Sie persistenten Speicher, RAG, und prüfen Sie genehmigte Wissenskandidaten und Runbooks.",
            summary: "Speicher, RAG und Wissens-Governance.",
          },
          integracoes: {
            label: "Integrationen",
            title: "Agent-Integrationen",
            description: "Verbinden und steuern Sie, auf welche Core-Integrationen und MCP-Server dieser Agent zugreifen kann.",
            summary: "Core-Integrationen und MCPs.",
          },
          segredos: {
            label: "Secrets & Variablen",
            title: "Secrets und Variablen",
            description: "Gewähren Sie Zugriff auf globale Secrets und gemeinsame Variablen und verwalten Sie lokale Agent-Variablen.",
            summary: "Secret-Grants und Env Vars.",
          },
          publicacao: {
            label: "Veröffentlichung",
            title: "Speichern und veröffentlichen",
            description: "Prüfen Sie ausstehende Änderungen und veröffentlichen Sie den Agenten mit einem Klick.",
            summary: "Zusammenfassung, speichern und veröffentlichen.",
          },
        },
      },
      agentLifecycle: {
        draftPendingPublish: {
          label: "Unveröffentlichte Änderungen",
          description: "Im Editor gibt es Änderungen, die noch nicht veröffentlicht wurden. Speichern und veröffentlichen Sie sie, um sie auf den Runtime anzuwenden.",
        },
        draftUnsaved: {
          label: "Unveröffentlichter Entwurf",
          description: "Die Erstkonfiguration läuft. Veröffentlichen Sie erstmals, damit der Agent betriebsbereit wird.",
        },
        neverConfigured: {
          label: "Nie veröffentlicht",
          description: "Der Agent wurde erstellt, hat aber noch keine veröffentlichte Version. Konfigurieren und veröffentlichen Sie ihn zum Aktivieren.",
        },
        awaitingActivation: {
          label: "Veröffentlicht, wartet auf Aktivierung",
          description: "Die Version ist veröffentlicht, aber der Runtime wurde noch nicht gestartet. Klicken Sie auf Aktivieren, um den Agenten zu starten.",
        },
        updatePending: {
          label: "Update ausstehend",
          description: "Der Runtime läuft mit v{{applied}}, aber v{{desired}} wurde bereits veröffentlicht und wartet auf Anwendung.",
        },
        publishedActive: {
          label: "Aktiv",
          description: "Der Runtime läuft normal mit v{{applied}}. Nachrichten werden verarbeitet.",
        },
        publishedPaused: {
          label: "Veröffentlicht · Pausiert",
          description: "Version v{{applied}} ist veröffentlicht, aber der Runtime ist pausiert. Nachrichten werden nicht verarbeitet.",
        },
        unknown: {
          label: "Status: {{status}}",
          labelFallback: "Unbekannter Zustand",
          description: "Zustand nicht vom Veröffentlichungsassistenten abgedeckt. Prüfen Sie die Control-Plane-Logs, falls dies anhält.",
        },
      },
      instructionBlocks: {
        instructions: {
          label: "Anweisungen",
          description: "Wie der Agent Anfragen verarbeiten soll, wann er eskaliert und welche Erfolgskriterien gelten.",
        },
        systemPrompt: {
          label: "System Prompt",
          description: "Zentrale Direktive, die vor jeder Nachricht an das LLM übergeben wird.",
        },
        rules: {
          label: "Regeln",
          description: "Unverletzliche Regeln, Sicherheits-Guardrails und Grenzen.",
        },
        identity: {
          label: "Identität",
          description: "Name, berufliche Rolle und grundlegender Agent-Kontext.",
        },
        soul: {
          label: "Soul",
          description: "Persönlichkeit, Ton und Werte des Agenten als freie Prosa.",
        },
      },
      mcpToolPolicy: {
        options: {
          auto: { label: "Automatisch", description: "Automatische Klassifizierung" },
          alwaysAllow: { label: "Immer erlauben", description: "Ohne Genehmigung ausführen" },
          alwaysAsk: { label: "Immer fragen", description: "Erfordert Genehmigung" },
          blocked: { label: "Blockiert", description: "Nie ausführen" },
        },
      },
      skillCategories: {
        general: "Allgemein",
        engineering: "Engineering",
        design: "Design",
        analysis: "Analyse",
        operations: "Betrieb",
        research: "Recherche",
        cloud: "Cloud",
      },
      intelligence: {
        memoryProfiles: {
          conservative: "Konservativ",
          balanced: "Ausgewogen",
          strongLearning: "Starkes Lernen",
        },
        knowledgeProfiles: {
          curatedOnly: "Nur kuratiert",
          curatedWorkspace: "Kuratiert + Workspace",
          curatedWorkspacePatterns: "Kuratiert + Workspace + Muster",
        },
        embeddingModelDescription: "Das Modell zum Indizieren von Erinnerungen, Knowledge Base und semantischem Cache. Standardmäßig ist kein Modell installiert: Laden Sie es nur bei Bedarf herunter.",
      },
    },
    downloads: {
      canceling: "Download wird abgebrochen...",
      cancelingAction: "Wird abgebrochen",
      cancelingAria: "Download wird abgebrochen",
      completedBeforeCancel: "Der Download wurde vor dem Abbruch abgeschlossen.",
      failed: "Download fehlgeschlagen",
      canceled: "Download abgebrochen.",
      cancelFailed: "Download konnte nicht abgebrochen werden",
      startFailed: "Download konnte nicht gestartet werden",
      resuming: "Download wird fortgesetzt...",
      serverUnresponsive: "Keine Antwort vom Server — prüfen Sie die Verbindung",
      reconnecting: "Instabile Verbindung — erneuter Verbindungsversuch",
      cancelAction: "Abbrechen",
      cancelAria: "Download abbrechen",
    },
  },
} as const;
