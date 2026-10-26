# Smoke test Fase 1 — ejecutar con el stack levantado.
# Uso: powershell -ExecutionPolicy Bypass -File .\scripts\smoke-test.ps1

$ErrorActionPreference = "Stop"
$Api = if ($env:API_BASE) { $env:API_BASE } else { "http://localhost:8001" }
$Sku = "SMOKE-" + (Get-Date -Format "yyyyMMddHHmmss")

function Write-Step($Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Assert-Equal($Expected, $Actual, $Label) {
    if ($Expected -ne $Actual) {
        throw "Fallo en '$Label': esperado=$Expected actual=$Actual"
    }
    Write-Host "OK  $Label = $Actual" -ForegroundColor Green
}

Write-Step "Health"
$health = Invoke-RestMethod -Uri "$Api/health"
Assert-Equal "ok" $health.status "status"
Assert-Equal "ok" $health.database "database"

Write-Step "Crear producto $Sku"
$productBody = @{
    sku = $Sku
    name = "Producto smoke test"
    description = "Creado por scripts/smoke-test.ps1"
    category = "Test"
    unit = "unit"
} | ConvertTo-Json

$product = Invoke-RestMethod -Method Post -Uri "$Api/products" -ContentType "application/json" -Body $productBody
Write-Host "Producto id=$($product.id)" -ForegroundColor Green

Write-Step "Inventario inicial en cero"
$stock = Invoke-RestMethod -Uri "$Api/inventory/$($product.id)"
Assert-Equal 0 $stock.quantity "quantity"
Assert-Equal 0 $stock.available_quantity "available_quantity"

Write-Step "Entrada de 10 unidades"
$receipt = @{
    product_id = $product.id
    type = "RECEIPT"
    quantity = 10
    reference = "SMOKE-IN"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$Api/inventory/movements" -ContentType "application/json" -Body $receipt | Out-Null

$stock = Invoke-RestMethod -Uri "$Api/inventory/$($product.id)"
Assert-Equal 10 $stock.quantity "quantity"
Assert-Equal 10 $stock.available_quantity "available_quantity"

Write-Step "Reserva de 3 unidades"
$reservation = @{
    product_id = $product.id
    type = "RESERVATION"
    quantity = 3
    reference = "SMOKE-RES"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$Api/inventory/movements" -ContentType "application/json" -Body $reservation | Out-Null

$stock = Invoke-RestMethod -Uri "$Api/inventory/$($product.id)"
Assert-Equal 3 $stock.reserved_quantity "reserved_quantity"
Assert-Equal 7 $stock.available_quantity "available_quantity"

Write-Step "Salida de 4 unidades"
$shipment = @{
    product_id = $product.id
    type = "SHIPMENT"
    quantity = 4
    reference = "SMOKE-OUT"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$Api/inventory/movements" -ContentType "application/json" -Body $shipment | Out-Null

$stock = Invoke-RestMethod -Uri "$Api/inventory/$($product.id)"
Assert-Equal 6 $stock.quantity "quantity"
Assert-Equal 3 $stock.available_quantity "available_quantity"

Write-Step "Salida inválida de 99 unidades (debe fallar)"
$invalid = @{
    product_id = $product.id
    type = "SHIPMENT"
    quantity = 99
    reference = "SMOKE-FAIL"
} | ConvertTo-Json

try {
    Invoke-RestMethod -Method Post -Uri "$Api/inventory/movements" -ContentType "application/json" -Body $invalid | Out-Null
    throw "La salida inválida fue aceptada"
} catch {
    Write-Host "OK  rechazada: $($_.Exception.Message)" -ForegroundColor Green
}

Write-Step "Historial"
$movements = Invoke-RestMethod -Uri "$Api/inventory/$($product.id)/movements"
Assert-Equal 3 $movements.Count "movimientos"

Write-Step "Eliminar producto de prueba"
Invoke-RestMethod -Method Delete -Uri "$Api/products/$($product.id)" | Out-Null
Write-Host "OK  producto eliminado" -ForegroundColor Green

Write-Host "`nSmoke test completado correctamente." -ForegroundColor Green
