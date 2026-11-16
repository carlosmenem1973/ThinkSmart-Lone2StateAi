variable "name" { type = string }
variable "environment" { type = string }
variable "aws_region" { type = string }
variable "vpc_cidr" { type = string }
variable "az_count" { type = number
  default = 2 }
variable "single_nat_gateway" { type = bool
  default = true }
variable "api_image_tag" { type = string
  default = "bootstrap" }
variable "api_cpu" { type = number
  default = 512 }
variable "api_memory" { type = number
  default = 1024 }
variable "worker_cpu" { type = number
  default = 512 }
variable "worker_memory" { type = number
  default = 1024 }
variable "api_desired_count" { type = number
  default = 1 }
variable "worker_desired_count" { type = number
  default = 1 }
variable "db_instance_class" { type = string }
variable "db_multi_az" { type = bool
  default = false }
variable "db_backup_days" { type = number
  default = 7 }
variable "redis_node_type" { type = string }
variable "redis_num_cache_nodes" { type = number
  default = 1 }
variable "frontend_domain_name" { type = string
  default = "" }
variable "tags" { type = map(string)
  default = {} }
variable "gitlab_oidc_provider_arn" { type = string
  default = "" }
variable "gitlab_subject" { type = string
  default = "" }

variable "certificate_arn" {
  type = string
  default = ""
  validation {
    condition = var.certificate_arn == "" || var.api_origin_domain_name != ""
    error_message = "api_origin_domain_name must be set when certificate_arn is configured."
  }
}
variable "api_origin_domain_name" { type = string
  default = "" }
variable "route53_zone_id" { type = string
  default = "" }
