# Construye y publica las imágenes de la Fase 1 en Amazon ECR.
# Uso:
#   .\scripts\aws\build-push.ps1 -AccountId 123456789012 -Region us-east-1 -Tag 1.0.0

param(
    [Parameter(Mandatory = $true)][string]$AccountId,
    [string]$Region = "us-east-1",
    [string]$Tag = "1.0.0"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\..\.."
$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"

Write-Host "==> Login a ECR" -ForegroundColor Cyan
aws ecr get-login-password --region $Region |
    docker login --username AWS --password-stdin $Registry

Write-Host "==> Build API" -ForegroundColor Cyan
docker build --platform linux/amd64 -t "warehouse-api:$Tag" -f "$Root\services\warehouse-api\Dockerfile" $Root
docker tag "warehouse-api:$Tag" "$Registry/warehouse-api:$Tag"
docker push "$Registry/warehouse-api:$Tag"

Write-Host "==> Build Frontend" -ForegroundColor Cyan
docker build --platform linux/amd64 -t "warehouse-frontend:$Tag" -f "$Root\services\frontend\app\Dockerfile" $Root
docker tag "warehouse-frontend:$Tag" "$Registry/warehouse-frontend:$Tag"
docker push "$Registry/warehouse-frontend:$Tag"

Write-Host "`nImágenes publicadas:" -ForegroundColor Green
Write-Host "$Registry/warehouse-api:$Tag"
Write-Host "$Registry/warehouse-frontend:$Tag"
