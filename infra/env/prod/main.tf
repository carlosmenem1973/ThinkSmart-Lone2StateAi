module "platform" {
  providers = { aws = aws, aws.use1 = aws.use1 }
  source = "../../modules/platform"
  name = "thinksmart-lone2stateai"
  environment = "prod"
  aws_region = var.aws_region
  vpc_cidr = "10.50.0.0/16"
  az_count = 2
  single_nat_gateway = false
  api_image_tag = var.api_image_tag
  api_cpu = 1024
  api_memory = 2048
  worker_cpu = 1024
  worker_memory = 2048
  api_desired_count = var.api_desired_count
  worker_desired_count = var.worker_desired_count
  beat_desired_count = var.beat_desired_count
  db_instance_class = "db.t4g.medium"
  db_multi_az = true
  db_backup_days = 14
  redis_node_type = "cache.t4g.small"
  redis_num_cache_nodes = 2
  gitlab_oidc_provider_arn = var.gitlab_oidc_provider_arn
  gitlab_subject = var.gitlab_subject
  certificate_arn = var.certificate_arn
  api_origin_domain_name = var.api_origin_domain_name
  route53_zone_id = var.route53_zone_id
  tags = { CostCentre = "estateai-prod" }
}
