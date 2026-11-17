variable "aws_region" {
  default = "us-east-1"
}

variable "vpc_cidr" {
  default = "10.0.0.0/16"
}

variable "subnet_cidr" {
  default = "10.0.1.0/24"
}

variable "ami_id" {
  default = "ami-0c7217cdde317cfec" # Ubuntu 22.04 LTS en us-east-1
}

variable "instance_type" {
  default = "t3.micro"
}