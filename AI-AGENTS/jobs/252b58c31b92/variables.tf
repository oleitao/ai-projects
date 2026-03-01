variable "region" {
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
