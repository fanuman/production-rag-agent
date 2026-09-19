# infra/terraform/ecs.tf
data "aws_caller_identity" "current" {}

resource "aws_ecs_cluster" "main" {
  name = "production-rag-agent-tf-cluster"
}

resource "aws_cloudwatch_log_group" "app_logs" {
  name              = "/ecs/production-rag-agent-tf-task"
  retention_in_days = 3
}

resource "aws_security_group" "app_sg" {
  name   = "production-rag-agent-tf-sg"
  vpc_id = data.aws_vpc.default.id

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.my_ip]
  }

  ingress {
    from_port   = 8001
    to_port     = 8001
    protocol    = "tcp"
    cidr_blocks = [var.my_ip]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_task_definition" "app_task" {
  family                   = "production-rag-agent-tf-task"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.task_execution_role.arn
  task_role_arn             = aws_iam_role.task_role.arn

  container_definitions = jsonencode([
    {
      name      = "app"
      image     = "${data.aws_caller_identity.current.account_id}.dkr.ecr.eu-north-1.amazonaws.com/production-rag-agent:latest"
      essential = true
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment = [
        { name = "REDIS_HOST", value = "localhost" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app_logs.name
          "awslogs-region"        = "eu-north-1"
          "awslogs-stream-prefix" = "app"
        }
      }
    },
    {
      name      = "chroma"
      image     = "chromadb/chroma:latest"
      essential = true
      portMappings = [{ containerPort = 8001, protocol = "tcp" }]
      environment = [
        { name = "CHROMA_PORT", value = "8001" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app_logs.name
          "awslogs-region"        = "eu-north-1"
          "awslogs-stream-prefix" = "chroma"
        }
      }
    },
    {
      name      = "redis"
      image     = "redis/redis-stack-server:latest"
      essential = true
      portMappings = [{ containerPort = 6379, protocol = "tcp" }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app_logs.name
          "awslogs-region"        = "eu-north-1"
          "awslogs-stream-prefix" = "redis"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "app_service" {
  name            = "production-rag-agent-tf-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app_task.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.app_sg.id]
    assign_public_ip = true
  }
}