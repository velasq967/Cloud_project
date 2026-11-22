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

locals {
  warehouses = {
    for wh in var.warehouses : wh.id => wh
  }
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
    description = "Central API (Fase 7)"
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

  user_data = templatefile("${path.module}/user_data/central.sh.tftpl", {
    repo_url     = var.repo_url
    repo_branch  = var.repo_branch
    rabbit_user  = var.rabbitmq_user
    rabbit_pass  = var.rabbitmq_password
  })

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

  user_data = templatefile("${path.module}/user_data/warehouse.sh.tftpl", {
    repo_url       = var.repo_url
    repo_branch    = var.repo_branch
    warehouse_id   = each.value.id
    warehouse_name = each.value.name
    rabbit_host    = aws_instance.central.private_ip
    rabbit_user    = var.rabbitmq_user
    rabbit_pass    = var.rabbitmq_password
  })

  root_block_device {
    volume_size = 20
  }

  tags = { Name = each.value.id, Role = "warehouse" }
}

resource "aws_s3_bucket" "warehouse_platform" {
  bucket = "warehouse-bucket-para-registros-diarios-22112026"

  tags = {
    Name  = "Warehouse Platform Storage"
    Phase = "8-S3-Batch"
  }
}