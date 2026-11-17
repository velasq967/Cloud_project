output "vpc_id" {
  value = aws_vpc.main_vpc.id
}

output "subnet_id" {
  value = aws_subnet.main_subnet.id
}

output "ip_wh_001" {
  value = aws_instance.wh_001.public_ip
}

output "ip_wh_002" {
  value = aws_instance.wh_002.public_ip
}

output "ip_central" {
  value = aws_instance.central.public_ip
}