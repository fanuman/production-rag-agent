# variables.tf
variable "my_ip" {
  description = "Your current public IP, in CIDR form, for security group access"
  type        = string
}

variable "alert_email" {
  description = "Email address for CloudWatch alarm notifications via SNS"
  type        = string
}