variable "aws_region" { type = string
  default = "eu-west-1" }
variable "gitlab_oidc_provider_arn" { type = string
  default = "" }
variable "gitlab_subject" { type = string
  default = "" }
variable "api_image_tag" { type = string
  default = "bootstrap" }
variable "api_desired_count" { type = number
  default = 0 }
variable "worker_desired_count" { type = number
  default = 0 }
variable "beat_desired_count" { type = number
  default = 0
  validation {
    condition = var.beat_desired_count == 0 || var.beat_desired_count == 1
    error_message = "Beat desired count must be 0 during bootstrap or 1 when active."
  }
}

variable "certificate_arn" { type = string
  default = "" }
variable "api_origin_domain_name" { type = string
  default = "" }
variable "route53_zone_id" { type = string
  default = "" }
