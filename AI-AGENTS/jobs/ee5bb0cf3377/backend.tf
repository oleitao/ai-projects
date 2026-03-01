terraform {
  backend "s3" {}
}

# Exemplo de init remoto:
# terraform init -backend-config=backend.hcl.example
