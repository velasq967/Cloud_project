output "vpc_id" {
  value = aws_vpc.main_vpc.id
}

output "subnet_id" {
  value = aws_subnet.main_subnet.id
}

output "central_public_ip" {
  value = aws_instance.central.public_ip
}

output "central_private_ip" {
  value = aws_instance.central.private_ip
}

output "rabbitmq_management_url" {
  value = "http://${aws_instance.central.public_ip}:15672"
}

output "s3_bucket" {
  value       = aws_s3_bucket.warehouse_platform.bucket
  description = "Bucket donde el batch sube los reportes y que dispara la Lambda."
}

output "lambda_function_name" {
  value = aws_lambda_function.report_processor.function_name
}

output "warehouses" {
  description = "IP y URLs de cada bodega"
  value = {
    for id, inst in aws_instance.warehouse : id => {
      public_ip = inst.public_ip
      frontend  = "http://${inst.public_ip}"
      api_docs  = "http://${inst.public_ip}:8000/docs"
    }
  }
}
