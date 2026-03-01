region              = "eu-west-1"
aws_profile         = "devops"
expected_account_id = "123456789012"
env                 = "prod"
az_count            = 2
vpc_cidr            = "10.0.0.0/16"
public_subnets      = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnets     = ["10.0.11.0/24", "10.0.12.0/24"]

tags = {
  owner       = "platform-team"
  cost_center = "shared"
}

db_enabled           = true
db_engine            = "postgres"
db_multi_az          = true
db_backups           = true
db_instance_class    = "db.t3.micro"
db_allocated_storage = 20
compute_type         = "ecs"
autoscaling          = true
ec2_ami_id           = "ami-0c02fb55956c7d316"
ec2_instance_type    = "t3.micro"
log_kms_key_id       = ""
