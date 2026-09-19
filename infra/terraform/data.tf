# data.tf - reference existing resources, don't recreate them
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_secretsmanager_secret" "openai_key" {
  name = "production-rag-agent/openai-api-key"
}