# AWS API

- **Integration key**: `aws_api`
- **Kind**: mcp
- **Tier**: recommended
- **Category**: cloud
- **Canonical source**: https://github.com/awslabs/mcp/tree/main/src/aws-api-mcp-server
- **Transport**: stdio
- **Install command**: `uvx awslabs.aws-api-mcp-server==1.3.33`

## Descrição

Servidor MCP oficial AWS Labs (Python via uvx) para execução real de operações AWS via API. Cobre S3, EC2, Lambda, IAM, CloudWatch, DynamoDB. Complementa aws_knowledge (read-only docs) com execução real. Default: always_ask em todas as tools — operador pode habilitar read_only_mode no grant.

## Connection profile

**Strategy**: `api_key`

### Campos principais

| Campo | Obrigatório | Tipo | Descrição |
|---|---|---|---|
| `AWS_ACCESS_KEY_ID` | sim | password | Access Key ID |
| `AWS_SECRET_ACCESS_KEY` | sim | password | Secret Access Key |
| `AWS_REGION` | sim | text | Default Region — Ex.: us-east-1, sa-east-1. |
| `AWS_SESSION_TOKEN` | não | password | Session Token (credenciais temporárias) |
| `AWS_PROFILE` | não | text | AWS Profile (~/.aws/credentials) |


## Runtime constraints

- `read_only_mode`
- `allow_private_network`

## Tools expostas

| Tool | Classificação | Descrição |
|---|---|---|
| `s3_list_buckets` | read | Listar buckets S3 |
| `s3_get_object` | read | Ler objeto S3 |
| `s3_put_object` | destructive | Upload de objeto S3 |
| `ec2_describe_instances` | read | Listar instâncias EC2 |
| `ec2_start_instances` | destructive | Iniciar instâncias EC2 |
| `ec2_stop_instances` | destructive | Parar instâncias EC2 |
| `lambda_list_functions` | read | Listar funções Lambda |
| `lambda_invoke` | write | Invocar função Lambda |
| `iam_list_users` | read | Listar usuários IAM |
| `cloudwatch_get_metric_data` | read | Consultar métricas CloudWatch |
| `dynamodb_query` | read | Query DynamoDB |
| `dynamodb_put_item` | destructive | Inserir item DynamoDB |

## Como o agente usa bem

<!-- MANUAL:BEGIN:mcp-aws_api-patterns -->
- (preencher com padrões recomendados)
<!-- MANUAL:END:mcp-aws_api-patterns -->

## Gotchas

<!-- MANUAL:BEGIN:mcp-aws_api-gotchas -->
- (preencher com cuidados específicos)
<!-- MANUAL:END:mcp-aws_api-gotchas -->
