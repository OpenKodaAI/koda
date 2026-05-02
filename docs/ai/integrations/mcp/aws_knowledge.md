# AWS Knowledge

- **Integration key**: `aws_knowledge`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: cloud
- **Canonical source**: https://docs.aws.amazon.com/mcp/
- **Transport**: http_sse
- **Install command**: `npx -y mcp-remote@0.1.38 https://knowledge-mcp.global.api.aws`
- **Remote URL**: https://knowledge-mcp.global.api.aws

## Descrição

Servidor MCP oficial da AWS com acesso público (sem credenciais) à documentação, blogs, What's New e guias de Well-Architected. Para acesso a recursos AWS reais, use AWS API MCP ou IAM.

## Connection profile

**Strategy**: `none`

## Runtime constraints

Nenhuma restrição de runtime aplicável a esta integração.

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `search_documentation` | read | Buscar na documentação AWS |
| `read_documentation` | read | Ler página de documentação |
| `recommend` | read | Recomendar recursos AWS para um caso de uso |
| `search_whats_new` | read | Buscar anúncios What's New |
| `search_well_architected` | read | Buscar guias Well-Architected |
| `search_blogs` | read | Buscar blogs AWS |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-aws_knowledge-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-aws_knowledge-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-aws_knowledge-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-aws_knowledge-gotchas -->
