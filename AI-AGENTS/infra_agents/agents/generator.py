from __future__ import annotations

import json
from pathlib import Path

from infra_agents.agents.base import BaseAgent
from infra_agents.contracts import AgentResult
from infra_agents.llm import AgentLLM, LLMRequest
from infra_agents.rag import LocalKnowledgeBase
from infra_agents.tools.filesystem import write_text


class TerraformGeneratorAgent(BaseAgent):
    name = "Gerador Terraform"

    def __init__(
        self,
        llm: AgentLLM,
        knowledge_base: LocalKnowledgeBase | None = None,
    ):
        self.knowledge_base = knowledge_base or LocalKnowledgeBase()
        self.llm = llm

    def run(self, state):  # type: ignore[override]
        if state.spec is None:
            raise ValueError("Spec em falta para o agente gerador")

        root = Path(state.workspace)
        spec = state.spec.to_dict()
        rag_hits = self.knowledge_base.retrieve(
            query=(
                f"generator terraform aws modules provider backend iam {spec['compute']['type']} "
                f"{spec['region']} {spec['env']}"
            ),
            top_k=3,
        )
        rag_sources = [hit.source for hit in rag_hits]
        rag_context = self.knowledge_base.render_context(rag_hits)
        tfvars_overrides: dict[str, str | int | float] = {}
        llm_payload = self.llm.generate_structured(
            LLMRequest(
                task="generator_overrides_v1",
                prompt=self._build_generator_llm_prompt(spec),
                context=self._build_generator_llm_context(spec, rag_context),
                schema_name="GeneratorOverrides",
            )
        )
        maybe_overrides = llm_payload.get("tfvars_overrides", {})
        if isinstance(maybe_overrides, dict):
            tfvars_overrides = self._sanitize_tfvars_overrides(maybe_overrides, spec)

        artifacts = [
            write_text(root / "versions.tf", self._versions_tf(rag_sources)),
            write_text(root / "providers.tf", self._providers_tf()),
            write_text(root / "backend.tf", self._backend_tf()),
            write_text(root / "backend.hcl.example", self._backend_hcl_example(spec)),
            write_text(root / "variables.tf", self._variables_tf()),
            write_text(root / "outputs.tf", self._outputs_tf()),
            write_text(root / "main.tf", self._main_tf(spec, rag_sources)),
            write_text(root / "terraform.tfvars", self._tfvars(spec, tfvars_overrides)),
        ]
        if rag_context:
            artifacts.append(write_text(root / "reports" / "rag_generator.md", rag_context + "\n"))

        return AgentResult(
            agent=self.name,
            artifacts=artifacts,
            findings=[],
            next_action="validate",
            metadata={"rag_sources": rag_sources, "llm_used": True, "tfvars_overrides": tfvars_overrides},
        )

    def _versions_tf(self, rag_sources: list[str]) -> str:
        rag_comment = ", ".join(rag_sources) if rag_sources else "none"
        return f"# RAG sources: {rag_comment}\n" + """terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
"""

    def _providers_tf(self) -> str:
        return """provider "aws" {
  region  = var.region
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = var.tags
  }
}
"""

    def _backend_tf(self) -> str:
        return """terraform {
  backend "s3" {}
}

# Exemplo de init remoto:
# terraform init -backend-config=backend.hcl.example
"""

    def _backend_hcl_example(self, spec: dict) -> str:
        aws = spec["aws"]
        return f"""bucket         = "{aws['backend_bucket']}"
key            = "{aws['backend_key_prefix']}/{spec['env']}/terraform.tfstate"
region         = "{spec['region']}"
dynamodb_table = "{aws['backend_dynamodb_table']}"
encrypt        = true
"""

    def _variables_tf(self) -> str:
        return """variable "region" {
  description = "AWS region"
  type        = string
}

variable "aws_profile" {
  description = "AWS profile name (optional)"
  type        = string
  default     = ""
}

variable "expected_account_id" {
  description = "Optional safety check for target AWS account"
  type        = string
  default     = ""
}

variable "env" {
  description = "Environment name"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env must be dev, staging, or prod"
  }
}

variable "az_count" {
  description = "How many AZs to use"
  type        = number
  default     = 2
}

variable "vpc_cidr" {
  description = "CIDR for VPC"
  type        = string
}

variable "public_subnets" {
  description = "Public subnet CIDRs"
  type        = list(string)
}

variable "private_subnets" {
  description = "Private subnet CIDRs"
  type        = list(string)
}

variable "tags" {
  description = "Mandatory tags"
  type        = map(string)

  validation {
    condition     = contains(keys(var.tags), "owner") && contains(keys(var.tags), "cost_center")
    error_message = "tags must include owner and cost_center"
  }
}

variable "db_enabled" {
  description = "Create RDS instance"
  type        = bool
  default     = true
}

variable "db_engine" {
  description = "Database engine"
  type        = string
  default     = "postgres"

  validation {
    condition     = contains(["postgres", "mysql"], var.db_engine)
    error_message = "db_engine must be postgres or mysql"
  }
}

variable "db_multi_az" {
  description = "Enable Multi-AZ RDS"
  type        = bool
  default     = true
}

variable "db_backups" {
  description = "Enable RDS backups"
  type        = bool
  default     = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Allocated storage for RDS"
  type        = number
  default     = 20
}

variable "compute_type" {
  description = "Compute runtime (ecs|eks|ec2)"
  type        = string

  validation {
    condition     = contains(["ecs", "eks", "ec2"], var.compute_type)
    error_message = "compute_type must be ecs, eks, or ec2"
  }
}

variable "autoscaling" {
  description = "Enable autoscaling"
  type        = bool
}

variable "ec2_ami_id" {
  description = "AMI id used when compute_type is ec2"
  type        = string
  default     = "ami-0c02fb55956c7d316"
}

variable "ec2_instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "log_kms_key_id" {
  description = "Optional KMS key for CloudWatch log encryption"
  type        = string
  default     = ""
}
"""

    def _main_tf(self, spec: dict, rag_sources: list[str]) -> str:
        public_access = str(spec["security"]["public_access"]).lower()
        rag_comment = ", ".join(rag_sources) if rag_sources else "none"
        return f"""# RAG sources: {rag_comment}
locals {{
  service_name          = "app"
  name_prefix           = "${{var.env}}-${{local.service_name}}"
  app_kms_key_arn       = var.log_kms_key_id != "" ? var.log_kms_key_id : aws_kms_key.app[0].arn
  container_image       = "${{data.aws_caller_identity.current.account_id}}.dkr.ecr.${{data.aws_region.current.name}}.amazonaws.com/${{local.service_name}}:latest"
  compute_principal     = var.compute_type == "ecs" ? "ecs-tasks.amazonaws.com" : (var.compute_type == "eks" ? "eks.amazonaws.com" : "ec2.amazonaws.com")
  db_log_exports        = var.db_engine == "postgres" ? ["postgresql", "upgrade"] : ["error", "general", "slowquery"]
  allow_public_subnets  = {public_access}
}}

data "aws_caller_identity" "current" {{}}

data "aws_region" "current" {{}}

data "aws_availability_zones" "available" {{
  state = "available"
}}

data "aws_prefix_list" "s3" {{
  name = "com.amazonaws.${{data.aws_region.current.name}}.s3"
}}

check "aws_account_match" {{
  assert {{
    condition     = var.expected_account_id == "" || data.aws_caller_identity.current.account_id == var.expected_account_id
    error_message = "Connected AWS account does not match expected_account_id"
  }}
}}

resource "aws_kms_key" "app" {{
  count = var.log_kms_key_id == "" ? 1 : 0

  description             = "KMS key for app logs and database insights"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = var.tags
}}

resource "aws_kms_alias" "app" {{
  count = var.log_kms_key_id == "" ? 1 : 0

  name          = "alias/${{local.name_prefix}}-app"
  target_key_id = aws_kms_key.app[0].key_id
}}

module "vpc" {{
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-vpc.git?ref=7c1f791efd61f326ed6102d564d1a65d1eceedf0"

  name                                   = "${{local.name_prefix}}-vpc"
  cidr                                   = var.vpc_cidr
  azs                                    = slice(data.aws_availability_zones.available.names, 0, var.az_count)
  public_subnets                         = var.public_subnets
  private_subnets                        = var.private_subnets
  enable_flow_log                        = true
  flow_log_destination_type              = "cloud-watch-logs"
  create_flow_log_cloudwatch_iam_role    = true
  create_flow_log_cloudwatch_log_group   = true
  flow_log_cloudwatch_log_group_retention_in_days = 365
  flow_log_cloudwatch_log_group_kms_key_id        = local.app_kms_key_arn
  map_public_ip_on_launch = local.allow_public_subnets
  enable_dns_hostnames    = true
  enable_dns_support      = true
  enable_nat_gateway      = true
  single_nat_gateway      = var.env != "prod"
  one_nat_gateway_per_az = var.env == "prod"

  tags = var.tags
}}

resource "aws_cloudwatch_log_group" "app" {{
  name              = "/${{var.env}}/app"
  retention_in_days = 365
  kms_key_id        = local.app_kms_key_arn
  tags              = var.tags
}}

resource "aws_security_group" "app" {{
  name_prefix = "${{local.name_prefix}}-sg"
  description = "Restrictive SG for app workloads"
  vpc_id      = module.vpc.vpc_id

  ingress {{
    description = "HTTPS from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }}

  egress {{
    description = "HTTPS to internal endpoints inside the VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }}

  egress {{
    description     = "HTTPS to S3 through the managed prefix list"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = [data.aws_prefix_list.s3.id]
  }}

  tags = var.tags
}}

data "aws_iam_policy_document" "compute_assume_role" {{
  statement {{
    actions = ["sts:AssumeRole"]

    principals {{
      type        = "Service"
      identifiers = [local.compute_principal]
    }}
  }}
}}

resource "aws_iam_role" "compute" {{
  name_prefix        = "${{local.name_prefix}}-compute-"
  assume_role_policy = data.aws_iam_policy_document.compute_assume_role.json
  tags               = var.tags
}}

data "aws_iam_policy_document" "compute_runtime" {{
  count = var.compute_type == "ecs" ? 0 : 1

  statement {{
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      aws_cloudwatch_log_group.app.arn,
      "${{aws_cloudwatch_log_group.app.arn}}:*",
    ]
  }}

  statement {{
    sid = "ECRRead"
    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchCheckLayerAvailability",
    ]
    resources = ["*"]
  }}
}}

resource "aws_iam_policy" "compute_runtime" {{
  count = var.compute_type == "ecs" ? 0 : 1

  name_prefix = "${{local.name_prefix}}-runtime-"
  policy      = data.aws_iam_policy_document.compute_runtime[0].json
  tags        = var.tags
}}

resource "aws_iam_role_policy_attachment" "compute_runtime" {{
  count = var.compute_type == "ecs" ? 0 : 1

  role       = aws_iam_role.compute.name
  policy_arn = aws_iam_policy.compute_runtime[0].arn
}}

resource "aws_iam_role" "ecs_execution" {{
  count = var.compute_type == "ecs" ? 1 : 0

  name_prefix        = "${{local.name_prefix}}-exec-"
  assume_role_policy = data.aws_iam_policy_document.compute_assume_role.json
  tags               = var.tags
}}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {{
  count      = var.compute_type == "ecs" ? 1 : 0
  role       = aws_iam_role.ecs_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}}

resource "aws_iam_role_policy_attachment" "ec2_ssm" {{
  count      = var.compute_type == "ec2" ? 1 : 0
  role       = aws_iam_role.compute.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}}

resource "aws_iam_instance_profile" "ec2" {{
  count = var.compute_type == "ec2" ? 1 : 0
  name_prefix = "${{local.name_prefix}}-profile-"
  role  = aws_iam_role.compute.name
}}

resource "aws_launch_template" "ec2" {{
  count = var.compute_type == "ec2" ? 1 : 0

  name_prefix   = "${{local.name_prefix}}-lt-"
  image_id      = var.ec2_ami_id
  instance_type = var.ec2_instance_type

  iam_instance_profile {{
    name = aws_iam_instance_profile.ec2[0].name
  }}

  vpc_security_group_ids = [aws_security_group.app.id]

  metadata_options {{
    http_endpoint = "enabled"
    http_tokens   = "required"
  }}

  tag_specifications {{
    resource_type = "instance"
    tags          = var.tags
  }}
}}

resource "aws_autoscaling_group" "ec2" {{
  count = var.compute_type == "ec2" && var.autoscaling ? 1 : 0

  name_prefix         = "${{local.name_prefix}}-asg-"
  min_size            = 1
  max_size            = 2
  desired_capacity    = 1
  vpc_zone_identifier = module.vpc.private_subnets

  launch_template {{
    id      = aws_launch_template.ec2[0].id
    version = "$Latest"
  }}

  tag {{
    key                 = "Name"
    value               = "${{local.name_prefix}}-ec2"
    propagate_at_launch = true
  }}
}}

resource "aws_ecs_cluster" "main" {{
  count = var.compute_type == "ecs" ? 1 : 0
  name  = "${{local.name_prefix}}-cluster"

  setting {{
    name  = "containerInsights"
    value = "enabled"
  }}

  tags = var.tags
}}

resource "aws_ecs_task_definition" "app" {{
  count = var.compute_type == "ecs" ? 1 : 0

  family                   = "${{local.name_prefix}}-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.autoscaling ? "512" : "256"
  memory                   = var.autoscaling ? "1024" : "512"
  execution_role_arn       = aws_iam_role.ecs_execution[0].arn
  task_role_arn            = aws_iam_role.compute.arn

  container_definitions = jsonencode([
    {{
      name                   = local.service_name
      image                  = local.container_image
      essential              = true
      readonlyRootFilesystem = true
      portMappings = [
        {{
          containerPort = 80
          hostPort      = 80
          protocol      = "tcp"
        }}
      ]
      logConfiguration = {{
        logDriver = "awslogs"
        options = {{
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = local.service_name
        }}
      }}
    }}
  ])

  tags = var.tags
}}

resource "aws_ecs_service" "app" {{
  count = var.compute_type == "ecs" ? 1 : 0

  name                   = "${{local.name_prefix}}-svc"
  cluster                = aws_ecs_cluster.main[0].id
  task_definition        = aws_ecs_task_definition.app[0].arn
  desired_count          = var.autoscaling ? 2 : 1
  launch_type            = "FARGATE"
  enable_execute_command = true

  network_configuration {{
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }}

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  depends_on = [
    aws_iam_role_policy_attachment.ecs_execution_managed,
  ]

  tags = var.tags
}}

resource "terraform_data" "eks_cluster_placeholder" {{
  count = var.compute_type == "eks" ? 1 : 0
  input = {{
    message = "EKS module integration planned for next iteration"
  }}
}}

resource "aws_db_subnet_group" "main" {{
  count      = var.db_enabled ? 1 : 0
  name       = "${{local.name_prefix}}-db-subnets"
  subnet_ids = module.vpc.private_subnets
  tags       = var.tags
}}

data "aws_iam_policy_document" "rds_monitoring_assume_role" {{
  statement {{
    actions = ["sts:AssumeRole"]

    principals {{
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }}
  }}
}}

resource "aws_iam_role" "rds_monitoring" {{
  count = var.db_enabled ? 1 : 0

  name_prefix        = "${{local.name_prefix}}-rds-monitor-"
  assume_role_policy = data.aws_iam_policy_document.rds_monitoring_assume_role.json
  tags               = var.tags
}}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {{
  count = var.db_enabled ? 1 : 0

  role       = aws_iam_role.rds_monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}}

resource "aws_db_instance" "main" {{
  count                           = var.db_enabled ? 1 : 0
  identifier                      = "${{local.name_prefix}}-db"
  allocated_storage               = var.db_allocated_storage
  engine                          = var.db_engine
  instance_class                  = var.db_instance_class
  username                        = "appadmin"
  manage_master_user_password     = true
  db_subnet_group_name            = aws_db_subnet_group.main[0].name
  vpc_security_group_ids          = [aws_security_group.app.id]
  publicly_accessible             = false
  multi_az                        = var.db_multi_az
  storage_encrypted               = true
  iam_database_authentication_enabled = true
  auto_minor_version_upgrade      = true
  monitoring_interval             = 60
  monitoring_role_arn             = aws_iam_role.rds_monitoring[0].arn
  performance_insights_kms_key_id = local.app_kms_key_arn
  skip_final_snapshot             = var.env != "prod"
  backup_retention_period         = var.db_backups ? 7 : 0
  enabled_cloudwatch_logs_exports = local.db_log_exports
  performance_insights_enabled = true
  deletion_protection          = var.env == "prod"
  tags                         = var.tags
}}

resource "terraform_data" "compute_metadata" {{
  input = {{
    compute_type      = var.compute_type
    autoscaling       = var.autoscaling
    caller_account_id = data.aws_caller_identity.current.account_id
    region            = data.aws_region.current.name
  }}
}}
"""

    def _outputs_tf(self) -> str:
        return """output "aws_account_id" {
  value       = data.aws_caller_identity.current.account_id
  description = "AWS account id in use"
}

output "aws_region" {
  value       = data.aws_region.current.name
  description = "AWS region in use"
}

output "vpc_id" {
  value       = module.vpc.vpc_id
  description = "VPC identifier"
}

output "private_subnets" {
  value       = module.vpc.private_subnets
  description = "Private subnet IDs"
}

output "security_group_id" {
  value       = aws_security_group.app.id
  description = "App security group"
}

output "compute_iam_role_arn" {
  value       = aws_iam_role.compute.arn
  description = "IAM role for selected compute runtime"
}

output "ecs_cluster_name" {
  value       = var.compute_type == "ecs" ? aws_ecs_cluster.main[0].name : null
  description = "ECS cluster name when compute_type=ecs"
}

output "ecs_service_name" {
  value       = var.compute_type == "ecs" ? aws_ecs_service.app[0].name : null
  description = "ECS service name when compute_type=ecs"
}

output "rds_endpoint" {
  value       = var.db_enabled ? aws_db_instance.main[0].address : null
  description = "RDS endpoint when database is enabled"
}
"""

    def _tfvars(self, spec: dict, tfvars_overrides: dict[str, str | int | float]) -> str:
        tags = spec["tags"]
        tags_hcl = "\n".join(f'  {k} = "{v}"' for k, v in tags.items())

        network = spec["network"]
        data = spec["data"]
        compute = spec["compute"]
        aws = spec["aws"]
        db_instance_class = str(tfvars_overrides.get("db_instance_class", "db.t3.micro"))
        db_allocated_storage = int(tfvars_overrides.get("db_allocated_storage", 20))
        ec2_instance_type = str(tfvars_overrides.get("ec2_instance_type", "t3.micro"))

        return f"""region              = "{spec['region']}"
aws_profile         = "{aws['profile']}"
expected_account_id = "{aws['account_id']}"
env                 = "{spec['env']}"
az_count            = 2
vpc_cidr            = "{network['vpc_cidr']}"
public_subnets      = ["{network['public_subnets'][0]}", "{network['public_subnets'][1]}"]
private_subnets     = ["{network['private_subnets'][0]}", "{network['private_subnets'][1]}"]

tags = {{
{tags_hcl}
}}

db_enabled        = {str(data['rds']).lower()}
db_engine         = "{data['engine']}"
db_multi_az       = {str(data['multi_az']).lower()}
db_backups        = {str(data['backups']).lower()}
db_instance_class = "{db_instance_class}"
db_allocated_storage = {db_allocated_storage}
compute_type      = "{compute['type']}"
autoscaling       = {str(compute['autoscaling']).lower()}
ec2_ami_id        = "ami-0c02fb55956c7d316"
ec2_instance_type = "{ec2_instance_type}"
log_kms_key_id    = ""
"""

    def _sanitize_tfvars_overrides(self, payload: dict, spec: dict) -> dict[str, str | int | float]:
        allowed_keys = {"db_instance_class", "db_allocated_storage", "ec2_instance_type"}
        sanitized: dict[str, str | int | float] = {}
        for key, value in payload.items():
            if key not in allowed_keys:
                continue
            if key == "ec2_instance_type" and spec["compute"]["type"] != "ec2":
                continue
            if key in {"db_instance_class", "db_allocated_storage"} and not spec["data"]["rds"]:
                continue
            if key == "db_allocated_storage":
                try:
                    numeric = int(value)
                except (ValueError, TypeError):
                    continue
                sanitized[key] = max(20, min(numeric, self._max_db_allocated_storage(spec)))
                continue
            if isinstance(value, str) and value:
                sanitized[key] = value
        return sanitized

    def _build_generator_llm_prompt(self, spec: dict) -> str:
        defaults = self._default_tfvars_inputs()
        prompt_payload = {
            "goal": "Recommend only safe tfvars overrides that improve sizing for this workload.",
            "spec": {
                "region": spec["region"],
                "env": spec["env"],
                "compute": spec["compute"],
                "data": spec["data"],
                "security": spec["security"],
            },
            "current_defaults": defaults,
            "allowed_override_keys": list(defaults.keys()),
            "rules": [
                "Return only tfvars_overrides.",
                "If no clear improvement exists, return an empty object for tfvars_overrides.",
                "Do not change compute_type, env, region, network, backend, tags, engine, or security.",
                "Only use ec2_instance_type when compute.type is ec2.",
                "Only use db_instance_class and db_allocated_storage when data.rds is true.",
                "Prefer conservative production-ready sizing changes over aggressive cost increases.",
            ],
        }
        return json.dumps(prompt_payload, ensure_ascii=False, indent=2)

    def _build_generator_llm_context(self, spec: dict, rag_context: str) -> str:
        allowed_values = {
            "db_instance_class": ["db.t3.micro", "db.t3.small", "db.t3.medium"],
            "db_allocated_storage": {"min": 20, "max": self._max_db_allocated_storage(spec)},
            "ec2_instance_type": ["t3.micro", "t3.small", "t3.medium", "t3.large"],
        }
        guidance = {
            "workload_hints": [
                f"env={spec['env']}",
                f"compute_type={spec['compute']['type']}",
                f"autoscaling={spec['compute']['autoscaling']}",
                f"db_enabled={spec['data']['rds']}",
                f"db_engine={spec['data']['engine']}",
                f"db_multi_az={spec['data']['multi_az']}",
                f"db_backups={spec['data']['backups']}",
            ],
            "allowed_values": allowed_values,
            "decision_policy": [
                "For ECS or EKS workloads, usually leave ec2_instance_type unchanged.",
                "For small production PostgreSQL with Multi-AZ, db.t3.small may be acceptable if a change is needed.",
                f"For this workload, do not exceed {self._max_db_allocated_storage(spec)} GiB for db_allocated_storage.",
                "Avoid overrides that are unrelated to the selected runtime.",
            ],
        }
        parts = [
            json.dumps(guidance, ensure_ascii=False, indent=2),
        ]
        if rag_context:
            parts.extend(["", "RAG context:", rag_context])
        return "\n".join(parts)

    def _default_tfvars_inputs(self) -> dict[str, str | int]:
        return {
            "db_instance_class": "db.t3.micro",
            "db_allocated_storage": 20,
            "ec2_instance_type": "t3.micro",
        }

    def _max_db_allocated_storage(self, spec: dict) -> int:
        sizing = str(spec["compute"].get("sizing", "small")).lower()
        if sizing == "small":
            return 100 if spec["env"] == "prod" else 50
        if sizing == "medium":
            return 250
        return 500
