# AI Agents for AWS Terraform Generation

Plataforma de geração de Infrastructure as Code (Terraform) para AWS baseada em pipeline multi-agente.

A aplicação recebe um prompt em linguagem natural, transforma-o numa `spec.json` estruturada, gera artefactos Terraform (`main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`, `backend.tf`) e executa validações/políticas para entregar um resultado auditável (`summary.json` + relatórios).

Inclui um RAG local (baseado em ficheiros Markdown em `infra_agents/knowledge/`) para melhorar consistência técnica nos agentes de `Requisitos`, `Planeador` e `Gerador`.

O projeto suporta dois motores de orquestração:
- `classic`: fluxo determinístico implementado em Python puro
- `langgraph`: fluxo em grafo de estados com LangGraph/LangChain

Por defeito (`engine=auto`), usa `langgraph` quando a dependência está instalada; caso contrário usa `classic`.

## Objetivo

Este projeto implementa um MVP de orquestração por agentes para:
- converter prompt em `spec.json` estruturado
- gerar design e código Terraform AWS
- validar com ferramentas reais (quando disponíveis)
- aplicar políticas de segurança
- produzir resumo final do job e relatórios

## Arquitetura dos agentes

Ordem de execução no supervisor:
1. `Requisitos`
2. `Planeador de Arquitetura`
3. `Gerador Terraform`
4. `Validador/QA`
5. `Segurança/Políticas`
6. `Custos`

O supervisor faz loop controlado de correção (`max_iterations`) entre geração e validação.

## AWS Scope do scaffold

O scaffold está adaptado para AWS com:
- provider `hashicorp/aws` (`~> 5.0`)
- backend remoto `s3` + lock `dynamodb` (`backend.hcl.example`)
- verificação opcional de conta AWS (`expected_account_id`)
- VPC com subnets públicas/privadas e NAT
- IAM role mínima por runtime (`ecs`, `eks`, `ec2`)
- recursos de compute base:
  - `ecs`: cluster com Container Insights
  - `ec2`: launch template + autoscaling group (quando `autoscaling=true`)
  - `eks`: placeholder controlado para extensão na próxima iteração
- RDS com `manage_master_user_password = true` (sem password hardcoded)
- outputs principais de conta/região/rede/iam/database

## RAG local

- Fonte de conhecimento: `infra_agents/knowledge/*.md`
- Retriever lexical local: `infra_agents/rag.py`
- Agentes que usam RAG: `requirements`, `planner`, `generator`
- Transparência por job:
  - `reports/rag_requirements.md`
  - `reports/rag_planner.md`
  - `reports/rag_generator.md`
  - `summary.json` inclui `history` com `metadata.rag_sources`

## Estrutura

- `infra_agents/contracts.py`: contrato entre agentes e validação da spec
- `infra_agents/orchestrator.py`: facade de seleção de engine
- `infra_agents/orchestration/`: implementações `classic` e `langgraph`
- `infra_agents/agents/`: agentes (`requirements`, `planner`, `generator`, `validator`, `security`, `cost`)
- `infra_agents/tools/`: wrappers para filesystem e comandos CLI
- `infra_agents/knowledge/`: base local de referências/padrões
- `examples/prompt.txt`: prompt de exemplo
- `tests/`: testes unitários e de pipeline

## Pré-requisitos

- Python `>= 3.11`
- Terraform CLI (opcional mas recomendado)
- Ferramentas opcionais de validação/custo:
  - `tflint`
  - `checkov`
  - `tfsec`
  - `infracost`
- Dependências opcionais para engine LangGraph:
  - `langgraph`
  - `langchain-core`

Se as ferramentas não estiverem instaladas, o pipeline continua e regista `warning` no relatório.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Para ativar orquestração com LangGraph:

```bash
pip install -e .[langgraph]
```

## Execução via CLI

Com prompt em ficheiro:

```bash
python -m infra_agents.cli --prompt-file examples/prompt.txt
```

Com prompt inline:

```bash
python -m infra_agents.cli --prompt "AWS prod em eu-west-1 com ECS e RDS postgres"
```

Comandos via entrypoints:

```bash
infra-agents --prompt-file examples/prompt.txt
```

Parâmetros úteis:
- `--output-dir` (default: `jobs`)
- `--max-iterations` (default: `3`)
- `--execution-mode` (atual: apenas `plan-only`)
- `--engine` (`auto`, `classic`, `langgraph`)

## Execução via API

Iniciar API local:

```bash
python -m infra_agents.api
```

Criar job:

```bash
curl -X POST http://127.0.0.1:8080/jobs \
  -H 'content-type: application/json' \
  -d '{"prompt":"AWS prod eu-west-1 com ECS e RDS"}'
```

A resposta inclui `job_id`, `status`, `workspace`, `summary_file` e `engine`.

## Outputs do job

Cada execução cria `jobs/<job_id>/` com artefactos como:
- `spec.json`
- `design.md`
- `main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`, `versions.tf`
- `backend.tf`, `backend.hcl.example`, `terraform.tfvars`
- `reports/validation.json`
- `reports/security.json`
- `reports/cost.json`
- `summary.json`

## Guardrails implementados

- allowlist de provider: apenas `aws`
- backend remoto obrigatório com `s3`
- verificação de configuração de lock DynamoDB no backend example
- execução em `plan-only`
- deteção de padrões inseguros:
  - acesso público explícito
  - credenciais hardcoded
  - encriptação desativada
  - IMDSv2 opcional (bloqueado)

## Estados possíveis do job

- `validated`: validação concluída sem erros bloqueantes
- `blocked`: bloqueado por políticas de segurança (severity `critical`)
- `failed`: erros de validação após esgotar iterações
- `done`: finalizado sem necessidade de validação adicional

## Testes

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

## Limitações atuais (MVP)

- EKS ainda está como placeholder de integração
- `terraform plan` depende de ambiente com rede/credenciais/plugins
- não executa `terraform apply`
- não integra OPA/Conftest nem catálogo interno de módulos ainda
