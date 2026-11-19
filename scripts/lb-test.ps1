# Fase 5: balanceo entre las 3 replicas de WH-002 y caida de una replica
# Uso: powershell -ExecutionPolicy Bypass -File .\scripts\lb-test.ps1

$Compose = @("compose", "--env-file", ".env", "-f", "infrastructure/compose/compose.multi.yml")
$Lb = "http://localhost:8002"

function Get-Instance {
    $r = Invoke-WebRequest -Uri "$Lb/inventory/1" -TimeoutSec 3 -UseBasicParsing
    return $r.Headers["X-Instance-Id"]
}

Write-Host "`n==> 1. Repartiendo 9 requests" -ForegroundColor Cyan
foreach ($i in 1..9) {
    $inst = Get-Instance
    if (-not $inst) { Write-Host "ERROR: la respuesta no trae X-Instance-Id. Revisa que wh002-lb este corriendo" -ForegroundColor Red; exit 1 }
    Write-Host "request $i -> $inst"
}

Write-Host "`n==> 2. Apagando wh002-api-2 mientras llegan requests" -ForegroundColor Cyan
$ok = 0; $err = 0; $stopped = $false; $started = $false
$sw = [Diagnostics.Stopwatch]::StartNew()
while ($sw.Elapsed.TotalSeconds -lt 20) {
    $t = [int]$sw.Elapsed.TotalSeconds
    if ($t -ge 5 -and -not $stopped) {
        Start-Job { docker @using:Compose stop wh002-api-2 } | Out-Null
        Write-Host "  (segundo ${t}: apagando wh002-api-2)"; $stopped = $true
    }
    if ($t -ge 14 -and -not $started) {
        Start-Job { docker @using:Compose start wh002-api-2 } | Out-Null
        Write-Host "  (segundo ${t}: prendiendo wh002-api-2)"; $started = $true
    }
    try { Invoke-WebRequest -Uri "$Lb/inventory/1" -TimeoutSec 3 -UseBasicParsing | Out-Null; $ok++ } catch { $err++ }
    Start-Sleep -Milliseconds 100
}
Get-Job | Wait-Job | Remove-Job

Write-Host "requests OK: $ok"
Write-Host "requests con error: $err"

Write-Host "`n==> 3. Reparto despues de que wh002-api-2 volvio" -ForegroundColor Cyan
Start-Sleep -Seconds 5
1..6 | ForEach-Object { Write-Host "request $_ -> $(Get-Instance)" }

Write-Host ""
if ($err -eq 0) {
    Write-Host "OK: WH-002 siguio respondiendo con una replica apagada" -ForegroundColor Green
} else {
    Write-Host "Hubo $err errores de $($ok + $err) requests" -ForegroundColor Red
    exit 1
}
