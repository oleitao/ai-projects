### providers.md
- Backend remoto obrigatório em S3 com lock por DynamoDB.
# AWS Provider Allowlist
- aws (hashicorp/aws) versão `~> 5.0`
Regras:
- Qualquer provider fora desta lista deve ser bloqueado.

### modules.md
# Módulos AWS Aprovados
O gerador deve usar estes módulos/padrões como primeira opção e evitar recursos ad-hoc quando existir módulo aprovado.
## Rede e base
- terraform-aws-modules/vpc/aws
## Compute
- terraform-aws-modules/ecs/aws
- terraform-aws-modules/eks/aws
- terraform-aws-modules/autoscaling/aws
