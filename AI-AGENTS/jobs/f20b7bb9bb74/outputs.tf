output "aws_account_id" {
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

output "rds_endpoint" {
  value       = var.db_enabled ? aws_db_instance.main[0].address : null
  description = "RDS endpoint when database is enabled"
}
