# Design de Infraestrutura

## Contexto
- Cloud: aws
- Região: eu-west-1
- Ambiente: prod
- Conta AWS alvo: 123456789012

## Padrões
- Naming: `<env>-<service>-<resource>`
- Ambientes: `dev`, `staging`, `prod`
- Backend remoto: S3 + DynamoDB lock com config em `backend.hcl.example`
- Providers com versão fixa em `versions.tf`
- Execução por defeito: `plan-only`

## Módulos aprovados
- terraform-aws-modules/vpc/aws
- terraform-aws-modules/ecs/aws
- terraform-aws-modules/rds/aws

## Runtime de Compute
- Tipo selecionado: `ecs`
- IAM de runtime gerado com trust policy mínima por tipo (ecs/eks/ec2)

## Backend remoto AWS
- Bucket: `tfstate-prod-123456789012`
- Tabela lock: `tfstate-locks-prod`
- Prefixo de state: `infra-agents`

## Guardrails
- Apenas provider `aws`
- Bloquear recursos públicos inseguros
- Exigir encriptação e logging
- Exigir tags `owner` e `cost_center`
