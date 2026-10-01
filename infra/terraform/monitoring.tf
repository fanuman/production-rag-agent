# infra/terraform/monitoring.tf

resource "aws_sns_topic" "alerts" {
  name = "production-rag-agent-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Closes the Day 34 gap: secrets.py logs a warning on Secrets Manager
# fallback, but nothing alerted on it. This turns that log line into a
# real metric, then alarms on it.
resource "aws_cloudwatch_log_metric_filter" "secret_fallback" {
  name           = "secret-fallback-warning"
  log_group_name = aws_cloudwatch_log_group.app_logs.name
  pattern        = "\"Could not load secret from Secrets Manager\""

  metric_transformation {
    name          = "SecretFallbackCount"
    namespace     = "ProductionRagAgent"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "secret_fallback_alarm" {
  alarm_name          = "production-rag-agent-secret-fallback"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods   = 1
  metric_name         = "SecretFallbackCount"
  namespace           = "ProductionRagAgent"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Fires when the app falls back from Secrets Manager to a local env value - the OpenAI key may be stale, missing, or Secrets Manager is unreachable."
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "production-rag-agent-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods   = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.app_service.name
  }
  alarm_description  = "ECS service CPU utilization above 80% for 2 consecutive minutes"
  alarm_actions      = [aws_sns_topic.alerts.arn]
  treat_missing_data = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "high_memory" {
  alarm_name          = "production-rag-agent-high-memory"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods   = 2
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.app_service.name
  }
  alarm_description  = "ECS service memory utilization above 80% for 2 consecutive minutes"
  alarm_actions      = [aws_sns_topic.alerts.arn]
  treat_missing_data = "notBreaching"
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "production-rag-agent"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "ECS CPU & Memory Utilization"
          region = "eu-north-1"
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.app_service.name],
            [".", "MemoryUtilization", ".", ".", ".", "."]
          ]
          period = 60
          stat   = "Average"
          view   = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Secrets Manager Fallback Count"
          region  = "eu-north-1"
          metrics = [["ProductionRagAgent", "SecretFallbackCount"]]
          period  = 60
          stat    = "Sum"
          view    = "timeSeries"
        }
      }
    ]
  })
}