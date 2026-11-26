terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# una EC2 por bodega + una central con rabbitmq

data "aws_caller_identity" "current" {}

locals {
  warehouses = {
    for wh in var.warehouses : wh.id => wh
  }

  # IP privadas fijas: la central necesita las URL de las bodegas y las bodegas
  # la IP de RabbitMQ. Fijarlas evita un ciclo entre las dos instancias.
  # AWS reserva las primeras 4 IP de la subred; se usa .10 para la central y .11+ para bodegas.
  central_private_ip = cidrhost(var.subnet_cidr, 10)
  warehouse_private_ips = {
    for i, wh in var.warehouses : wh.id => cidrhost(var.subnet_cidr, 11 + i)
  }
  warehouse_urls = join(",", [
    for wh in var.warehouses : "${wh.id}=http://${local.warehouse_private_ips[wh.id]}:8000"
  ])

  # Bucket unico por cuenta. Se puede sobreescribir con s3_bucket_name.
  s3_bucket_name = var.s3_bucket_name != "" ? var.s3_bucket_name : "warehouse-platform-${data.aws_caller_identity.current.account_id}"
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

# red

resource "aws_vpc" "main_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "warehouse-vpc" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main_vpc.id
  tags   = { Name = "warehouse-igw" }
}

resource "aws_subnet" "main_subnet" {
  vpc_id                  = aws_vpc.main_vpc.id
  cidr_block              = var.subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = { Name = "warehouse-subnet" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = { Name = "warehouse-public-rt" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.main_subnet.id
  route_table_id = aws_route_table.public.id
}

# security groups

resource "aws_security_group" "warehouse" {
  name        = "warehouse-node-sg"
  description = "Nodos de bodega: frontend y API publicos, SSH desde mi IP"
  vpc_id      = aws_vpc.main_vpc.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  ingress {
    description = "Frontend"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "API (Swagger y pruebas de carga)"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "warehouse-node-sg" }
}

resource "aws_security_group" "central" {
  name        = "warehouse-central-sg"
  description = "Central: RabbitMQ solo desde las bodegas, management desde mi IP"
  vpc_id      = aws_vpc.main_vpc.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  ingress {
    description     = "AMQP desde las bodegas"
    from_port       = 5672
    to_port         = 5672
    protocol        = "tcp"
    security_groups = [aws_security_group.warehouse.id]
  }

  ingress {
    description = "RabbitMQ management"
    from_port   = 15672
    to_port     = 15672
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  ingress {
    description = "Central API y Swagger (/docs)"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "warehouse-central-sg" }
}

# instancias

resource "aws_instance" "central" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.central_instance_type
  subnet_id              = aws_subnet.main_subnet.id
  vpc_security_group_ids = [aws_security_group.central.id]
  key_name               = var.key_name
  iam_instance_profile   = var.instance_profile
  private_ip             = local.central_private_ip

  user_data = templatefile("${path.module}/user_data/central.sh.tftpl", {
    repo_url       = var.repo_url
    repo_branch    = var.repo_branch
    rabbit_user    = var.rabbitmq_user
    rabbit_pass    = var.rabbitmq_password
    warehouse_urls = local.warehouse_urls
  })
  # user_data solo corre en el primer arranque: si cambia, se recrea la instancia
  user_data_replace_on_change = true

  root_block_device {
    volume_size = 20
  }

  tags = { Name = "CENTRAL", Role = "central" }
}

resource "aws_instance" "warehouse" {
  for_each = local.warehouses

  ami                    = data.aws_ami.ubuntu.id
  instance_type          = each.value.instance_type
  subnet_id              = aws_subnet.main_subnet.id
  vpc_security_group_ids = [aws_security_group.warehouse.id]
  key_name               = var.key_name
  iam_instance_profile   = var.instance_profile
  private_ip             = local.warehouse_private_ips[each.key]

  user_data = templatefile("${path.module}/user_data/warehouse.sh.tftpl", {
    repo_url       = var.repo_url
    repo_branch    = var.repo_branch
    warehouse_id   = each.value.id
    warehouse_name = each.value.name
    rabbit_host    = local.central_private_ip
    rabbit_user    = var.rabbitmq_user
    rabbit_pass    = var.rabbitmq_password
  })

  root_block_device {
    volume_size = 20
  }

  tags = { Name = each.value.id, Role = "warehouse" }
}

#s3 bucket

resource "terraform_data" "s3_bucket" {
  input = {
    bucket = local.s3_bucket_name
    region = var.aws_region
  }

  provisioner "local-exec" {
    command = "aws s3api create-bucket --bucket ${self.input.bucket} --region ${self.input.region}"
  }

  provisioner "local-exec" {
    when       = destroy
    command    = "aws s3 rb s3://${self.input.bucket} --force --region ${self.input.region}"
    on_failure = continue
  }
}

resource "terraform_data" "s3_bucket_ensure" {
  triggers_replace = timestamp()

  provisioner "local-exec" {
    command = "aws s3api create-bucket --bucket ${local.s3_bucket_name} --region ${var.aws_region}"
  }

  depends_on = [terraform_data.s3_bucket]
}

#lambda

#aqui volvemos el handler.py (de services/lambda) en un .zip
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../services/lambda/handler.py"
  output_path = "${path.module}/lambda_payload.zip"
}

resource "aws_lambda_function" "report_processor" {
  function_name    = "warehouse-report-processor"
  role             = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.lambda_role_name}"
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 30

  tags = {
    Name  = "Warehouse Report Processor"
    Phase = "9-Lambda"
  }
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.report_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = "arn:aws:s3:::${local.s3_bucket_name}"

  depends_on = [terraform_data.s3_bucket]
}

# 5. Conectar el disparador (Trigger) del bucket solo para la carpeta reports/
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = local.s3_bucket_name

  lambda_function {
    lambda_function_arn = aws_lambda_function.report_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "reports/"
    filter_suffix       = ".json"
  }

  depends_on = [terraform_data.s3_bucket_ensure, aws_lambda_permission.allow_s3]
}