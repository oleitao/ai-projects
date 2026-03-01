locals {
  service_name         = "app"
  name_prefix          = "${var.env}-${local.service_name}"
  compute_principal    = var.compute_type == "ecs" ? "ecs-tasks.amazonaws.com" : (var.compute_type == "eks" ? "eks.amazonaws.com" : "ec2.amazonaws.com")
  db_log_exports       = var.db_engine == "postgres" ? ["postgresql", "upgrade"] : ["error", "general", "slowquery"]
  allow_public_subnets = false
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

check "aws_account_match" {
  assert {
    condition     = var.expected_account_id == "" || data.aws_caller_identity.current.account_id == var.expected_account_id
    error_message = "Connected AWS account does not match expected_account_id"
  }
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name                    = "${local.name_prefix}-vpc"
  cidr                    = var.vpc_cidr
  azs                     = slice(data.aws_availability_zones.available.names, 0, var.az_count)
  public_subnets          = var.public_subnets
  private_subnets         = var.private_subnets
  map_public_ip_on_launch = local.allow_public_subnets
  enable_dns_hostnames    = true
  enable_dns_support      = true
  enable_nat_gateway      = true
  single_nat_gateway      = var.env != "prod"
  one_nat_gateway_per_az  = var.env == "prod"

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/${var.env}/app"
  retention_in_days = 30
  kms_key_id        = var.log_kms_key_id != "" ? var.log_kms_key_id : null
  tags              = var.tags
}

resource "aws_security_group" "app" {
  name_prefix = "${local.name_prefix}-sg"
  description = "Restrictive SG for app workloads"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "HTTPS from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

data "aws_iam_policy_document" "compute_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = [local.compute_principal]
    }
  }
}

resource "aws_iam_role" "compute" {
  name_prefix        = "${local.name_prefix}-compute-"
  assume_role_policy = data.aws_iam_policy_document.compute_assume_role.json
  tags               = var.tags
}

data "aws_iam_policy_document" "compute_runtime" {
  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["*"]
  }

  statement {
    sid = "ECRRead"
    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchCheckLayerAvailability",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "compute_runtime" {
  name_prefix = "${local.name_prefix}-runtime-"
  policy      = data.aws_iam_policy_document.compute_runtime.json
  tags        = var.tags
}

resource "aws_iam_role_policy_attachment" "compute_runtime" {
  role       = aws_iam_role.compute.name
  policy_arn = aws_iam_policy.compute_runtime.arn
}

resource "aws_iam_role_policy_attachment" "ec2_ssm" {
  count      = var.compute_type == "ec2" ? 1 : 0
  role       = aws_iam_role.compute.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2" {
  count       = var.compute_type == "ec2" ? 1 : 0
  name_prefix = "${local.name_prefix}-profile-"
  role        = aws_iam_role.compute.name
}

resource "aws_launch_template" "ec2" {
  count = var.compute_type == "ec2" ? 1 : 0

  name_prefix   = "${local.name_prefix}-lt-"
  image_id      = var.ec2_ami_id
  instance_type = var.ec2_instance_type

  iam_instance_profile {
    name = aws_iam_instance_profile.ec2[0].name
  }

  vpc_security_group_ids = [aws_security_group.app.id]

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  tag_specifications {
    resource_type = "instance"
    tags          = var.tags
  }
}

resource "aws_autoscaling_group" "ec2" {
  count = var.compute_type == "ec2" && var.autoscaling ? 1 : 0

  name_prefix         = "${local.name_prefix}-asg-"
  min_size            = 1
  max_size            = 2
  desired_capacity    = 1
  vpc_zone_identifier = module.vpc.private_subnets

  launch_template {
    id      = aws_launch_template.ec2[0].id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "${local.name_prefix}-ec2"
    propagate_at_launch = true
  }
}

resource "aws_ecs_cluster" "main" {
  count = var.compute_type == "ecs" ? 1 : 0
  name  = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = var.tags
}

resource "terraform_data" "eks_cluster_placeholder" {
  count = var.compute_type == "eks" ? 1 : 0
  input = {
    message = "EKS module integration planned for next iteration"
  }
}

resource "aws_db_subnet_group" "main" {
  count      = var.db_enabled ? 1 : 0
  name       = "${local.name_prefix}-db-subnets"
  subnet_ids = module.vpc.private_subnets
  tags       = var.tags
}

resource "aws_db_instance" "main" {
  count                           = var.db_enabled ? 1 : 0
  identifier                      = "${local.name_prefix}-db"
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
  skip_final_snapshot             = var.env != "prod"
  backup_retention_period         = var.db_backups ? 7 : 0
  enabled_cloudwatch_logs_exports = local.db_log_exports
  performance_insights_enabled    = true
  deletion_protection             = var.env == "prod"
  tags                            = var.tags
}

resource "terraform_data" "compute_metadata" {
  input = {
    compute_type      = var.compute_type
    autoscaling       = var.autoscaling
    caller_account_id = data.aws_caller_identity.current.account_id
    region            = data.aws_region.current.name
  }
}
