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

#creacion vpc
resource "aws_vpc" "main_vpc" {
  cidr_block = var.vpc_cidr 

  tags = {
    Name = "warehouse-vpc"
  }
}

#subnet
resource "aws_subnet" "main_subnet" {
  vpc_id                  = aws_vpc.main_vpc.id
  cidr_block              = var.subnet_cidr
  map_public_ip_on_launch = true # Asigna IP pública automáticamente

  tags = {
    Name = "warehouse-subnet"
  }
}

#bodega 1 instancia
resource "aws_instance" "wh_001" {
  ami           = var.ami_id
  instance_type = var.instance_type
  subnet_id     = aws_subnet.main_subnet.id

  tags = {
    Name = "WH-001"
  }
}

#bodega 2 instancia
resource "aws_instance" "wh_002" {
  ami           = var.ami_id
  instance_type = var.instance_type
  subnet_id     = aws_subnet.main_subnet.id

  tags = {
    Name = "WH-002"
  }
}

#instancia central
resource "aws_instance" "central" {
  ami           = var.ami_id
  instance_type = var.instance_type
  subnet_id     = aws_subnet.main_subnet.id

  tags = {
    Name = "CENTRAL"
  }
}