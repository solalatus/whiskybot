########################################################
# 0. Locals
########################################################
locals {
  project      = "whiskybot"
  prefix       = "${local.project}-${terraform.workspace}"
  backend_port = 8080
  ui_port      = 3000
  cpu          = 512
  memory       = 1024
}

########################################################
# 1. VPC & Public Subnets
########################################################
resource "aws_vpc" "main" {
  cidr_block           = "10.10.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${local.prefix}-vpc"
  }
}

data "aws_availability_zones" "az" {
  state = "available"
}

resource "aws_subnet" "public" {
  for_each = {
    for idx, az in slice(data.aws_availability_zones.az.names, 0, 2) : idx => az
  }

  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 4, each.key)
  availability_zone       = each.value
  map_public_ip_on_launch = true

  tags = {
    Name = "${local.prefix}-subnet-${each.value}"
  }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${local.prefix}-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "${local.prefix}-rt"
  }
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

########################################################
# 2. Security Groups
########################################################
resource "aws_security_group" "alb" {
  name        = "${local.prefix}-alb-sg"
  description = "Allow HTTP and HTTPS from Internet"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "alb_internal" {
  name        = "${local.prefix}-alb-internal-sg"
  description = "Internal ALB for backend"
  vpc_id      = aws_vpc.main.id

  # egress only
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "tasks" {
  name        = "${local.prefix}-tasks-sg"
  description = "Allow ALBs to reach ECS tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Public ALB to UI"
    from_port       = local.ui_port
    to_port         = local.ui_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "Internal ALB to backend"
    from_port       = local.backend_port
    to_port         = local.backend_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_internal.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# break the cycle with a stand-alone rule
resource "aws_security_group_rule" "allow_tasks_to_internal_alb" {
  description                = "Allow Chainlit tasks to reach internal ALB listener"
  type                       = "ingress"
  from_port                  = 80
  to_port                    = 80
  protocol                   = "tcp"
  security_group_id          = aws_security_group.alb_internal.id
  source_security_group_id   = aws_security_group.tasks.id
}


########################################################
# 3. Public Application Load Balancer
########################################################
resource "aws_lb" "main" {
  name               = "${local.prefix}-alb"
  load_balancer_type = "application"
  subnets            = [for s in aws_subnet.public : s.id]
  security_groups    = [aws_security_group.alb.id]
}

########################################################
# 4. Internal Application Load Balancer
########################################################
resource "aws_lb" "internal" {
  name               = "${local.prefix}-alb-internal"
  internal           = true
  load_balancer_type = "application"
  subnets            = [for s in aws_subnet.public : s.id]
  security_groups    = [aws_security_group.alb_internal.id]
}

########################################################
# 5. Reference Existing Route53 Zone
########################################################
data "aws_route53_zone" "primary" {
  name         = var.domain_name
  private_zone = false
}

########################################################
# 6. ACM Certificate (DNS-validated)
########################################################
resource "aws_acm_certificate" "cert" {
  domain_name               = var.domain_name
  subject_alternative_names = ["www.${var.domain_name}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for o in aws_acm_certificate.cert.domain_validation_options : o.domain_name => o
  }

  zone_id = data.aws_route53_zone.primary.zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  ttl     = 300
  records = [each.value.resource_record_value]
}

resource "aws_acm_certificate_validation" "cert_validation" {
  certificate_arn         = aws_acm_certificate.cert.arn
  validation_record_fqdns = values(aws_route53_record.cert_validation)[*].fqdn
}

########################################################
# 7. Cognito User Pool + Client
########################################################
resource "aws_cognito_user_pool" "pool" {
  name = "${local.prefix}-pool"
}

resource "aws_cognito_user_pool_domain" "domain" {
  domain       = "${local.prefix}"
  user_pool_id = aws_cognito_user_pool.pool.id
}

resource "aws_cognito_user_pool_client" "client" {
  name                                 = "${local.prefix}-client"
  user_pool_id                         = aws_cognito_user_pool.pool.id
  generate_secret                      = true
  explicit_auth_flows                  = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  allowed_oauth_flows_user_pool_client = true
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = ["https://${var.domain_name}/oauth2/idpresponse"]
  logout_urls                          = ["https://${var.domain_name}/logout"]
}

########################################################
# 8. Public ALB Listeners & Rules
########################################################
resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      protocol    = "HTTPS"
      port        = "443"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = aws_acm_certificate_validation.cert_validation.certificate_arn

  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "Not Found"
      status_code  = "404"
    }
  }
}

resource "aws_lb_listener_rule" "ui" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 100

  action {
    order = 1
    type  = "authenticate-cognito"

    authenticate_cognito {
      user_pool_arn              = aws_cognito_user_pool.pool.arn
      user_pool_client_id        = aws_cognito_user_pool_client.client.id
      user_pool_domain           = aws_cognito_user_pool_domain.domain.domain
      on_unauthenticated_request = "authenticate"
    }
  }

  action {
    order            = 2
    type             = "forward"
    target_group_arn = aws_lb_target_group.ui.arn
  }

  condition {
    path_pattern {
      values = ["/*"]
    }
  }
}

########################################################
# 9. Internal ALB Listener (backend only)
########################################################
resource "aws_lb_listener" "internal_http" {
  load_balancer_arn = aws_lb.internal.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

########################################################
# 10. Target Groups
########################################################
resource "aws_lb_target_group" "backend" {
  name        = "${local.prefix}-backend"
  port        = local.backend_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path    = "/healthz"
    matcher = "200"
  }
}

resource "aws_lb_target_group" "ui" {
  name        = "${local.prefix}-ui"
  port        = local.ui_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path    = "/"
    matcher = "200-404"
  }
}

########################################################
# 11. IAM Role for ECS Tasks
########################################################
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "exec" {
  name               = "${local.prefix}-task-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "exec_attach" {
  role       = aws_iam_role.exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

########################################################
# 12. ECS Cluster, Logs, ECR, Task Definitions & Services
########################################################
resource "aws_ecs_cluster" "main" {
  name = "${local.prefix}-cluster"
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.prefix}-backend"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "ui" {
  name              = "/ecs/${local.prefix}-ui"
  retention_in_days = 14
}

resource "aws_ecr_repository" "backend" {
  name         = "${local.prefix}-backend"
  force_delete = true
}

resource "aws_ecr_repository" "ui" {
  name         = "${local.prefix}-ui"
  force_delete = true
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.prefix}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = local.cpu
  memory                   = local.memory
  execution_role_arn       = aws_iam_role.exec.arn

  container_definitions = jsonencode([
    {
      name         = "backend"
      image        = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
      essential    = true
      portMappings = [
        {
          containerPort = local.backend_port
          hostPort      = local.backend_port
          protocol      = "tcp"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options   = {
          awslogs-group         = aws_cloudwatch_log_group.backend.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "backend"
        }
      }
      environment = [
        {
          name  = "PORT"
          value = tostring(local.backend_port)
        }
      ]
    }
  ])
}

resource "aws_ecs_task_definition" "ui" {
  family                   = "${local.prefix}-ui"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = local.cpu
  memory                   = local.memory
  execution_role_arn       = aws_iam_role.exec.arn

  container_definitions = jsonencode([
    {
      name         = "chainlit"
      image        = "${aws_ecr_repository.ui.repository_url}:${var.image_tag}"
      essential    = true
      portMappings = [
        {
          containerPort = local.ui_port
          hostPort      = local.ui_port
          protocol      = "tcp"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options   = {
          awslogs-group         = aws_cloudwatch_log_group.ui.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ui"
        }
      }
      environment = [
        {
          name  = "CHAINLIT_PORT"
          value = tostring(local.ui_port)
        },
        {
          name  = "LANGSERVE_URL"
          value = "http://${aws_lb.internal.dns_name}/chat"
        }
      ]
    }
  ])
}

resource "aws_ecs_service" "backend" {
  name            = "${local.prefix}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  force_new_deployment = true

  network_configuration {
    subnets          = [for s in aws_subnet.public : s.id]
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = local.backend_port
  }

  lifecycle { ignore_changes = [desired_count] }
  depends_on = [aws_lb_listener.internal_http]
}

resource "aws_ecs_service" "ui" {
  name            = "${local.prefix}-ui"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.ui.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  force_new_deployment = true

  network_configuration {
    subnets          = [for s in aws_subnet.public : s.id]
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.ui.arn
    container_name   = "chainlit"
    container_port   = local.ui_port
  }

  lifecycle { ignore_changes = [desired_count] }
  depends_on = [aws_lb_listener_rule.ui]
}

########################################################
# 13. Route 53 Alias A Records (apex + www to public ALB)
########################################################
resource "aws_route53_record" "apex" {
  zone_id = data.aws_route53_zone.primary.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "www" {
  zone_id = data.aws_route53_zone.primary.zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

########################################################
# 14. Outputs
########################################################
output "app_url" {
  description = "Your public HTTPS endpoint"
  value       = "https://${var.domain_name}"
}
