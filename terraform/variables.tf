variable "aws_region" {
  default = "us-east-1"
}

variable "vpc_cidr" {
  default = "10.0.0.0/16"
}

variable "subnet_cidr" {
  default = "10.0.1.0/24"
}

variable "my_ip_cidr" {
  description = "IP para SSH, ej: 181.50.10.20/32"
  type        = string
}

variable "key_name" {
  description = "Key pair de AWS Academy"
  default     = "vockey"
}

variable "instance_profile" {
  description = "Instance profile predefinido del Learner Lab"
  default     = "LabInstanceProfile"
}

variable "repo_url" {
  default = "https://github.com/velasq967/Cloud_proyect.git"
}

variable "repo_branch" {
  default = "main"
}

variable "central_instance_type" {
  default = "t3.small"
}

# WH-002 tiene mas carga, por eso es mas grande
variable "warehouses" {
  type = list(object({
    id            = string
    name          = string
    instance_type = string
  }))
  default = [
    { id = "WH-001", name = "Bodega Norte", instance_type = "t3.small" },
    { id = "WH-002", name = "Bodega Centro", instance_type = "t3.medium" },
    { id = "WH-003", name = "Bodega Sur", instance_type = "t3.small" },
  ]
}

variable "rabbitmq_user" {
  default = "warehouse"
}

variable "rabbitmq_password" {
  description = "Password de RabbitMQ (va en terraform.tfvars)"
  type        = string
  sensitive   = true
}
