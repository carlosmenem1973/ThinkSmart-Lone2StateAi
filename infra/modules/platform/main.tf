data "aws_availability_zones" "available" { state = "available" }
data "aws_caller_identity" "current" {}
data "aws_ec2_managed_prefix_list" "cloudfront" { name = "com.amazonaws.global.cloudfront.origin-facing" }
locals {
  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)
  prefix = "${var.name}-${var.environment}"
  common_tags = merge(var.tags, { Project = var.name, Environment = var.environment, ManagedBy = "OpenTofu" })
  private_subnet_cidrs = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnet_cidrs  = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i + 8)]
}

resource "aws_vpc" "this" {
  cidr_block = var.vpc_cidr
  enable_dns_support = true
  enable_dns_hostnames = true
  tags = merge(local.common_tags, { Name = "${local.prefix}-vpc" })
}
resource "aws_internet_gateway" "this" { vpc_id = aws_vpc.this.id
  tags = local.common_tags }
resource "aws_subnet" "public" {
  count = var.az_count
  vpc_id = aws_vpc.this.id
  cidr_block = local.public_subnet_cidrs[count.index]
  availability_zone = local.azs[count.index]
  map_public_ip_on_launch = true
  tags = merge(local.common_tags, { Name = "${local.prefix}-public-${count.index + 1}", Tier = "public" })
}
resource "aws_subnet" "private" {
  count = var.az_count
  vpc_id = aws_vpc.this.id
  cidr_block = local.private_subnet_cidrs[count.index]
  availability_zone = local.azs[count.index]
  map_public_ip_on_launch = false
  tags = merge(local.common_tags, { Name = "${local.prefix}-private-${count.index + 1}", Tier = "private" })
}
resource "aws_eip" "nat" { count = var.single_nat_gateway ? 1 : var.az_count
  domain = "vpc"
  depends_on = [aws_internet_gateway.this]
  tags = local.common_tags }
resource "aws_nat_gateway" "this" {
  count = var.single_nat_gateway ? 1 : var.az_count
  allocation_id = aws_eip.nat[count.index].id
  subnet_id = aws_subnet.public[var.single_nat_gateway ? 0 : count.index].id
  depends_on = [aws_internet_gateway.this]
  tags = merge(local.common_tags, { Name = "${local.prefix}-nat-${count.index + 1}" })
}
resource "aws_route_table" "public" { vpc_id = aws_vpc.this.id
  tags = merge(local.common_tags, { Name = "${local.prefix}-public-rt" }) }
resource "aws_route" "public_internet" { route_table_id = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id = aws_internet_gateway.this.id }
resource "aws_route_table_association" "public" { count = var.az_count
  subnet_id = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id }
resource "aws_route_table" "private" { count = var.az_count
  vpc_id = aws_vpc.this.id
  tags = merge(local.common_tags, { Name = "${local.prefix}-private-rt-${count.index + 1}" }) }
resource "aws_route" "private_nat" {
  count = var.az_count
  route_table_id = aws_route_table.private[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id = aws_nat_gateway.this[var.single_nat_gateway ? 0 : count.index].id
}
resource "aws_route_table_association" "private" { count = var.az_count
  subnet_id = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id }

resource "aws_security_group" "alb" {
  name = "${local.prefix}-alb-sg"
  description = "Only CloudFront origin-facing network can reach the ALB"
  vpc_id = aws_vpc.this.id
  ingress {
    from_port = 80
    to_port = 80
    protocol = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }
  egress {
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.common_tags
}
resource "aws_security_group" "alb_tls" {
  name = "${local.prefix}-alb-tls-sg"
  description = "CloudFront HTTPS origin access"
  vpc_id = aws_vpc.this.id
  ingress {
    from_port = 443
    to_port = 443
    protocol = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }
  egress {
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.common_tags
}
resource "aws_security_group" "ecs" {
  name = "${local.prefix}-ecs-sg"
  description = "Only ALB can reach API tasks"
  vpc_id = aws_vpc.this.id
  ingress { from_port = 8000
  to_port = 8000
  protocol = "tcp"
  security_groups = [aws_security_group.alb.id, aws_security_group.alb_tls.id] }
  egress { from_port = 0
  to_port = 0
  protocol = "-1"
  cidr_blocks = ["0.0.0.0/0"] }
  tags = local.common_tags
}
resource "aws_security_group" "db" {
  name = "${local.prefix}-db-sg"
  description = "PostgreSQL only from ECS"
  vpc_id = aws_vpc.this.id
  ingress { from_port = 5432
  to_port = 5432
  protocol = "tcp"
  security_groups = [aws_security_group.ecs.id] }
  tags = local.common_tags
}
resource "aws_security_group" "redis" {
  name = "${local.prefix}-redis-sg"
  description = "Redis only from ECS"
  vpc_id = aws_vpc.this.id
  ingress { from_port = 6379
  to_port = 6379
  protocol = "tcp"
  security_groups = [aws_security_group.ecs.id] }
  tags = local.common_tags
}

resource "aws_iam_role" "gitlab_ci" {
  count = var.gitlab_oidc_provider_arn != "" && var.gitlab_subject != "" ? 1 : 0
  name = "${local.prefix}-gitlab-ci"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Federated = var.gitlab_oidc_provider_arn }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = { StringEquals = {
        "gitlab.com:aud" = "sts.amazonaws.com"
        "gitlab.com:sub" = var.gitlab_subject
      } }
    }]
  })
  tags = local.common_tags
}
resource "aws_iam_role_policy_attachment" "gitlab_poweruser" {
  count = var.gitlab_oidc_provider_arn != "" && var.gitlab_subject != "" ? 1 : 0
  role = aws_iam_role.gitlab_ci[0].name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}
resource "aws_iam_role_policy" "gitlab_iam_limited" {
  count = var.gitlab_oidc_provider_arn != "" && var.gitlab_subject != "" ? 1 : 0
  name = "${local.prefix}-gitlab-iam-limited"
  role = aws_iam_role.gitlab_ci[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:UpdateAssumeRolePolicy", "iam:TagRole", "iam:UntagRole", "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:CreatePolicy", "iam:DeletePolicy", "iam:GetPolicy", "iam:GetPolicyVersion", "iam:CreatePolicyVersion", "iam:DeletePolicyVersion"], Resource = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.prefix}*", "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${local.prefix}*"] },
      { Effect = "Allow", Action = ["iam:List*", "iam:GetAccountSummary"], Resource = "*" },
      { Effect = "Allow", Action = ["iam:PassRole"], Resource = [aws_iam_role.execution.arn, aws_iam_role.task.arn], Condition = { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } } },
      { Effect = "Allow", Action = ["iam:CreateServiceLinkedRole"], Resource = "*", Condition = { StringEquals = { "iam:AWSServiceName" = ["ecs.amazonaws.com", "elasticloadbalancing.amazonaws.com", "rds.amazonaws.com", "elasticache.amazonaws.com"] } } }
    ]
  })
}

resource "aws_ecr_repository" "api" { name = "${local.prefix}/api"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
  tags = local.common_tags }
resource "aws_ecr_repository" "worker" { name = "${local.prefix}/worker"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
  tags = local.common_tags }
resource "aws_cloudwatch_log_group" "api" { name = "/ecs/${local.prefix}/api"
  retention_in_days = var.environment == "prod" ? 90 : 14
  tags = local.common_tags }
resource "aws_cloudwatch_log_group" "worker" { name = "/ecs/${local.prefix}/worker"
  retention_in_days = var.environment == "prod" ? 90 : 14
  tags = local.common_tags }
resource "aws_ecs_cluster" "this" { name = local.prefix
  setting { name = "containerInsights"
  value = "enabled" }
  tags = local.common_tags }
resource "aws_iam_role" "execution" {
  name = "${local.prefix}-ecs-execution"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  tags = local.common_tags
}
resource "aws_iam_role_policy_attachment" "execution" { role = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" }
resource "aws_iam_role" "task" {
  name = "${local.prefix}-ecs-task"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  tags = local.common_tags
}
resource "aws_iam_policy" "task_bedrock" {
  name = "${local.prefix}-task-bedrock"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "InvokeEUNovaLiteInferenceProfile"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/eu.amazon.nova-lite-v1:0"
      },
      {
        Sid    = "InvokeEUNovaLiteDestinationModels"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:eu-west-1::foundation-model/amazon.nova-lite-v1:0",
          "arn:aws:bedrock:eu-west-3::foundation-model/amazon.nova-lite-v1:0",
          "arn:aws:bedrock:eu-central-1::foundation-model/amazon.nova-lite-v1:0",
          "arn:aws:bedrock:eu-north-1::foundation-model/amazon.nova-lite-v1:0"
        ]
        Condition = {
          StringEquals = {
            "bedrock:InferenceProfileArn" = "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/eu.amazon.nova-lite-v1:0"
          }
        }
      },
      {
        Sid      = "ReadEUInferenceProfile"
        Effect   = "Allow"
        Action   = ["bedrock:GetInferenceProfile"]
        Resource = "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/eu.amazon.nova-lite-v1:0"
      },
      {
        Sid      = "InvokeAgentCoreWebSearch"
        Effect   = "Allow"
        Action   = ["bedrock-agentcore:InvokeWebSearch"]
        Resource = "arn:aws:bedrock-agentcore:${var.aws_region}:aws:tool/web-search.v1"
      }
    ]
  })
  tags = local.common_tags
}
resource "aws_iam_role_policy_attachment" "task_bedrock" {
  role       = aws_iam_role.task.name
  policy_arn = aws_iam_policy.task_bedrock.arn
}
resource "aws_iam_policy" "task_secrets" {
  name = "${local.prefix}-task-secrets"
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [aws_secretsmanager_secret.app.arn] }, { Effect = "Allow", Action = ["kms:Decrypt"], Resource = ["*"] , Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${var.aws_region}.amazonaws.com" } } }] })
}
resource "aws_iam_role_policy_attachment" "task_secrets" { role = aws_iam_role.execution.name
  policy_arn = aws_iam_policy.task_secrets.arn }

resource "aws_secretsmanager_secret" "app" { name = "${local.prefix}/application"
  description = "Populate JSON keys after infrastructure deployment"
  recovery_window_in_days = var.environment == "prod" ? 30 : 7
  tags = local.common_tags }
resource "aws_secretsmanager_secret_version" "app_initial" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    DATABASE_URL = "postgresql+psycopg://REPLACE_ME"
    REDIS_URL = "rediss://REPLACE_ME:6379/0"
    SECRET_KEY = "REPLACE_ME"
    BOOTSTRAP_ADMIN_EMAIL = "REPLACE_ME"
    BOOTSTRAP_ADMIN_PASSWORD = "REPLACE_ME"
    MICROSOFT_CLIENT_ID = "REPLACE_ME"
    MICROSOFT_CLIENT_SECRET = "REPLACE_ME"
    MICROSOFT_TENANT_ID = "REPLACE_ME"
    MICROSOFT_REDIRECT_URI = "https://REPLACE_ME/api/v1/integrations/microsoft/callback"
  })
  lifecycle { ignore_changes = [secret_string] }
}
resource "aws_db_subnet_group" "this" { name = local.prefix
  subnet_ids = aws_subnet.private[*].id
  tags = local.common_tags }
resource "aws_db_instance" "this" {
  identifier = local.prefix
  engine = "postgres"
  engine_version = "16.4"
  instance_class = var.db_instance_class
  allocated_storage = var.environment == "prod" ? 100 : 30
  max_allocated_storage = var.environment == "prod" ? 300 : 80
  storage_type = "gp3"
  storage_encrypted = true
  db_name = "estateai"
  username = "estateadmin"
  manage_master_user_password = true
  multi_az = var.db_multi_az
  db_subnet_group_name = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible = false
  backup_retention_period = var.db_backup_days
  deletion_protection = var.environment == "prod"
  skip_final_snapshot = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${local.prefix}-final" : null
  auto_minor_version_upgrade = true
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  tags = local.common_tags
}
resource "aws_elasticache_subnet_group" "this" { name = local.prefix
  subnet_ids = aws_subnet.private[*].id }
resource "aws_elasticache_replication_group" "this" {
  replication_group_id = local.prefix
  description = "EstateAI ${var.environment} Redis"
  engine = "redis"
  engine_version = "7.0"
  node_type = var.redis_node_type
  num_cache_clusters = var.redis_num_cache_nodes
  port = 6379
  subnet_group_name = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  automatic_failover_enabled = var.redis_num_cache_nodes > 1
  multi_az_enabled = var.redis_num_cache_nodes > 1
  snapshot_retention_limit = var.environment == "prod" ? 7 : 1
  apply_immediately = var.environment != "prod"
  tags = local.common_tags
}

resource "aws_lb" "this" { name = substr(local.prefix, 0, 32)
  load_balancer_type = "application"
  internal = false
  subnets = aws_subnet.public[*].id
  security_groups = [aws_security_group.alb.id, aws_security_group.alb_tls.id]
  enable_deletion_protection = var.environment == "prod"
  tags = local.common_tags }
resource "aws_lb_target_group" "api" { name = substr("${local.prefix}-api", 0, 32)
  port = 8000
  protocol = "HTTP"
  vpc_id = aws_vpc.this.id
  target_type = "ip"
  health_check { path = "/health/live"
  matcher = "200"
  interval = 30
  healthy_threshold = 2
  unhealthy_threshold = 3 }
  tags = local.common_tags }
resource "aws_lb_listener" "http_forward" {
  count = var.certificate_arn == "" ? 1 : 0
  load_balancer_arn = aws_lb.this.arn
  port = 80
  protocol = "HTTP"
  default_action { type = "forward"
    target_group_arn = aws_lb_target_group.api.arn }
}
resource "aws_lb_listener" "http_redirect" {
  count = var.certificate_arn == "" ? 0 : 1
  load_balancer_arn = aws_lb.this.arn
  port = 80
  protocol = "HTTP"
  default_action {
    type = "redirect"
    redirect { port = "443"
    protocol = "HTTPS"
    status_code = "HTTP_301" }
  }
}
resource "aws_lb_listener" "https" {
  count = var.certificate_arn == "" ? 0 : 1
  load_balancer_arn = aws_lb.this.arn
  port = 443
  protocol = "HTTPS"
  certificate_arn = var.certificate_arn
  ssl_policy = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  default_action { type = "forward"
    target_group_arn = aws_lb_target_group.api.arn }
}
resource "aws_route53_record" "api_origin" {
  count = var.route53_zone_id != "" && var.api_origin_domain_name != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name = var.api_origin_domain_name
  type = "A"
  alias {
    name = aws_lb.this.dns_name
    zone_id = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}
resource "aws_ecs_task_definition" "api" {
  family = "${local.prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode = "awsvpc"
  cpu = var.api_cpu
  memory = var.api_memory
  execution_role_arn = aws_iam_role.execution.arn
  task_role_arn = aws_iam_role.task.arn
  container_definitions = jsonencode([{ name = "api", image = "${aws_ecr_repository.api.repository_url}:${var.api_image_tag}", essential = true, portMappings = [{ containerPort = 8000, protocol = "tcp" }], environment = [{ name = "APP_NAME", value = "ThinkSmart-Lone2StateAi" }, { name = "ENVIRONMENT", value = var.environment }, { name = "TIMEZONE", value = "Europe/Lisbon" }, { name = "BEDROCK_REGION", value = var.aws_region }, { name = "BEDROCK_MODEL_ID", value = "eu.amazon.nova-lite-v1:0" }, { name = "BEDROCK_WEB_SEARCH_ENABLED", value = "true" }, { name = "BEDROCK_WEB_SEARCH_ID", value = "web-search.v1" }, { name = "COOKIE_SECURE", value = "true" }, { name = "FRONTEND_ORIGIN", value = var.frontend_domain_name == "" ? "https://${aws_cloudfront_distribution.frontend.domain_name}" : "https://${var.frontend_domain_name}" }], secrets = [{ name = "DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:DATABASE_URL::" }, { name = "REDIS_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:REDIS_URL::" }, { name = "SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:SECRET_KEY::" }, { name = "BOOTSTRAP_ADMIN_EMAIL", valueFrom = "${aws_secretsmanager_secret.app.arn}:BOOTSTRAP_ADMIN_EMAIL::" }, { name = "BOOTSTRAP_ADMIN_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app.arn}:BOOTSTRAP_ADMIN_PASSWORD::" }, { name = "MICROSOFT_CLIENT_ID", valueFrom = "${aws_secretsmanager_secret.app.arn}:MICROSOFT_CLIENT_ID::" }, { name = "MICROSOFT_CLIENT_SECRET", valueFrom = "${aws_secretsmanager_secret.app.arn}:MICROSOFT_CLIENT_SECRET::" }, { name = "MICROSOFT_TENANT_ID", valueFrom = "${aws_secretsmanager_secret.app.arn}:MICROSOFT_TENANT_ID::" }, { name = "MICROSOFT_REDIRECT_URI", valueFrom = "${aws_secretsmanager_secret.app.arn}:MICROSOFT_REDIRECT_URI::" }, { name = "GOOGLE_MAPS_API_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:GOOGLE_MAPS_API_KEY::" }], logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.api.name, "awslogs-region" = var.aws_region, "awslogs-stream-prefix" = "api" } } }])
  depends_on = [aws_iam_role_policy_attachment.execution, aws_iam_role_policy_attachment.task_secrets, aws_iam_role_policy_attachment.task_bedrock]
}
resource "aws_ecs_task_definition" "worker" {
  family = "${local.prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode = "awsvpc"
  cpu = var.worker_cpu
  memory = var.worker_memory
  execution_role_arn = aws_iam_role.execution.arn
  task_role_arn = aws_iam_role.task.arn
  container_definitions = jsonencode([{ name = "worker", image = "${aws_ecr_repository.worker.repository_url}:${var.api_image_tag}", essential = true, command = ["sh", "-c", "until alembic current 2>/dev/null | grep -q '(head)'; do sleep 3; done; exec celery -A app.workers.celery_app.celery worker --beat --loglevel=INFO"], environment = [{ name = "ENVIRONMENT", value = var.environment }, { name = "TIMEZONE", value = "Europe/Lisbon" }, { name = "BEDROCK_REGION", value = var.aws_region }, { name = "BEDROCK_MODEL_ID", value = "eu.amazon.nova-lite-v1:0" }, { name = "BEDROCK_WEB_SEARCH_ENABLED", value = "true" }, { name = "BEDROCK_WEB_SEARCH_ID", value = "web-search.v1" }], secrets = [{ name = "DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:DATABASE_URL::" }, { name = "REDIS_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:REDIS_URL::" }, { name = "SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:SECRET_KEY::" }], logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.worker.name, "awslogs-region" = var.aws_region, "awslogs-stream-prefix" = "worker" } } }])
  depends_on = [aws_iam_role_policy_attachment.execution, aws_iam_role_policy_attachment.task_secrets, aws_iam_role_policy_attachment.task_bedrock]
}
resource "aws_ecs_service" "api" {
  name = "api"
  cluster = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count = var.api_desired_count
  launch_type = "FARGATE"
  platform_version = "LATEST"
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent = 200
  enable_execute_command = false
  network_configuration { subnets = aws_subnet.private[*].id
  security_groups = [aws_security_group.ecs.id]
  assign_public_ip = false }
  load_balancer { target_group_arn = aws_lb_target_group.api.arn
  container_name = "api"
  container_port = 8000 }
  depends_on = [aws_lb_listener.http_forward, aws_lb_listener.http_redirect, aws_lb_listener.https, aws_secretsmanager_secret_version.app_initial]
  
  tags = local.common_tags
}
resource "aws_ecs_service" "worker" {
  name = "worker"
  cluster = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count = var.worker_desired_count
  launch_type = "FARGATE"
  platform_version = "LATEST"
  network_configuration { subnets = aws_subnet.private[*].id
  security_groups = [aws_security_group.ecs.id]
  assign_public_ip = false }
  
  tags = local.common_tags
}
resource "aws_sns_topic" "alerts" {
  name = "${local.prefix}-alerts"
  tags = local.common_tags
}
resource "aws_cloudwatch_metric_alarm" "api_cpu" {
  alarm_name = "${local.prefix}-api-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods = 2
  metric_name = "CPUUtilization"
  namespace = "AWS/ECS"
  period = 300
  statistic = "Average"
  threshold = 80
  dimensions = { ClusterName = aws_ecs_cluster.this.name, ServiceName = aws_ecs_service.api.name }
  alarm_actions = [aws_sns_topic.alerts.arn]
  treat_missing_data = "notBreaching"
  tags = local.common_tags
}
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name = "${local.prefix}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods = 2
  metric_name = "CPUUtilization"
  namespace = "AWS/RDS"
  period = 300
  statistic = "Average"
  threshold = 80
  dimensions = { DBInstanceIdentifier = aws_db_instance.this.identifier }
  alarm_actions = [aws_sns_topic.alerts.arn]
  treat_missing_data = "notBreaching"
  tags = local.common_tags
}
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name = "${local.prefix}-alb-5xx"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = 1
  metric_name = "HTTPCode_ELB_5XX_Count"
  namespace = "AWS/ApplicationELB"
  period = 300
  statistic = "Sum"
  threshold = 5
  dimensions = { LoadBalancer = aws_lb.this.arn_suffix }
  alarm_actions = [aws_sns_topic.alerts.arn]
  treat_missing_data = "notBreaching"
  tags = local.common_tags
}

resource "aws_s3_bucket" "frontend" { bucket = "${local.prefix}-${data.aws_caller_identity.current.account_id}-frontend"
  force_destroy = var.environment != "prod"
  tags = local.common_tags }
resource "aws_s3_bucket_public_access_block" "frontend" { bucket = aws_s3_bucket.frontend.id
  block_public_acls = true
  block_public_policy = true
  ignore_public_acls = true
  restrict_public_buckets = true }
resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" { bucket = aws_s3_bucket.frontend.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } } }
resource "aws_cloudfront_origin_access_control" "frontend" { name = "${local.prefix}-oac"
  description = "Private S3 origin"
  origin_access_control_origin_type = "s3"
  signing_behavior = "always"
  signing_protocol = "sigv4" }
resource "aws_wafv2_web_acl" "cloudfront" {
  provider = aws.use1
  name = "${local.prefix}-cloudfront-waf"
  description = "AWS managed baseline protections for EstateAI CloudFront"
  scope = "CLOUDFRONT"
  default_action { allow {} }
  rule {
    name = "RateLimitPerIp"
    priority = 1
    action { block {} }
    statement { rate_based_statement { limit = 1500
      aggregate_key_type = "IP" } }
    visibility_config { cloudwatch_metrics_enabled = true
      metric_name = "${local.prefix}-rate-limit"
      sampled_requests_enabled = true }
  }
  rule {
    name = "AWSManagedCommonRuleSet"
    priority = 10
    override_action { none {} }
    statement { managed_rule_group_statement { name = "AWSManagedRulesCommonRuleSet"
      vendor_name = "AWS" } }
    visibility_config { cloudwatch_metrics_enabled = true
      metric_name = "${local.prefix}-common"
      sampled_requests_enabled = true }
  }
  rule {
    name = "AWSManagedKnownBadInputs"
    priority = 20
    override_action { none {} }
    statement { managed_rule_group_statement { name = "AWSManagedRulesKnownBadInputsRuleSet"
      vendor_name = "AWS" } }
    visibility_config { cloudwatch_metrics_enabled = true
      metric_name = "${local.prefix}-bad-inputs"
      sampled_requests_enabled = true }
  }
  rule {
    name = "AWSManagedIpReputation"
    priority = 30
    override_action { none {} }
    statement { managed_rule_group_statement { name = "AWSManagedRulesAmazonIpReputationList"
      vendor_name = "AWS" } }
    visibility_config { cloudwatch_metrics_enabled = true
      metric_name = "${local.prefix}-ip-reputation"
      sampled_requests_enabled = true }
  }
  visibility_config { cloudwatch_metrics_enabled = true
      metric_name = "${local.prefix}-waf"
      sampled_requests_enabled = true }
  tags = local.common_tags
}

resource "aws_cloudfront_function" "spa_rewrite" {
  name = "${local.prefix}-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Route client-side application paths to index.html without rewriting API paths"
  publish = true
  code = <<-JS
    function handler(event) {
      var request = event.request
      
      var uri = request.uri
      
      if (uri.indexOf('/api/') === 0) return request
      
      if (uri.indexOf('.') === -1) request.uri = '/index.html'
      
      return request
      
    }
  JS
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled = true
  web_acl_id = aws_wafv2_web_acl.cloudfront.arn
  default_root_object = "index.html"
  price_class = "PriceClass_100"
  origin {
    domain_name = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id = "frontend-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }
  origin {
    domain_name = var.api_origin_domain_name != "" ? var.api_origin_domain_name : aws_lb.this.dns_name
    origin_id = "api-alb"
    custom_origin_config {
      http_port = 80
      https_port = 443
      origin_protocol_policy = var.certificate_arn == "" ? "http-only" : "https-only"
      origin_ssl_protocols = ["TLSv1.2"]
    }
  }
  ordered_cache_behavior {
    path_pattern = "/api/*"
    target_origin_id = "api-alb"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods = ["GET", "HEAD", "OPTIONS"]
    compress = true
    cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
  }
  default_cache_behavior {
    target_origin_id = "frontend-s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods = ["GET", "HEAD", "OPTIONS"]
    cached_methods = ["GET", "HEAD"]
    compress = true
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
    function_association {
      event_type = "viewer-request"
      function_arn = aws_cloudfront_function.spa_rewrite.arn
    }
  }

  restrictions { geo_restriction { restriction_type = "none" } }
  viewer_certificate { cloudfront_default_certificate = true }
  tags = local.common_tags
}
resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Sid = "AllowCloudFrontRead", Effect = "Allow", Principal = { Service = "cloudfront.amazonaws.com" }, Action = "s3:GetObject", Resource = "${aws_s3_bucket.frontend.arn}/*", Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn } } }] })
}
