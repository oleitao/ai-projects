### naming-and-tagging.md
# Naming e Tagging
## Naming
Formato recomendado: `<env>-<service>-<resource>`
## Tags obrigatórias
- owner
- cost_center

### modules.md
# Módulos AWS Aprovados
## Rede e base
- terraform-aws-modules/vpc/aws
## Compute
- terraform-aws-modules/ecs/aws
- terraform-aws-modules/eks/aws
- terraform-aws-modules/autoscaling/aws
## Dados

### providers.md
# AWS Provider Allowlist
- aws (hashicorp/aws) versão `~> 5.0`
Regras:
- Qualquer provider fora desta lista deve ser bloqueado.
- Backend remoto obrigatório em S3 com lock por DynamoDB.
