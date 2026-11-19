# Apaga WH-002 y revisa que WH-001 y WH-003 sigan funcionando
# Uso: powershell -ExecutionPolicy Bypass -File .\scripts\fault-test-wh002.ps1

$Compose = @("compose", "--env-file", ".env", "-f", "infrastructure/compose/compose.multi.yml")
$Api = @{ "WH-001" = "http://localhost:8001"; "WH-002" = "http://localhost:8002"; "WH-003" = "http://localhost:8003" }
$failures = 0

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

function Test-Health($wh) {
    try {
        $r = Invoke-WebRequest -Uri "$($Api[$wh])/health" -TimeoutSec 3 -UseBasicParsing
        Write-Host ("{0,-7} /health -> {1}" -f $wh, $r.StatusCode)
        return $r.StatusCode -eq 200
    } catch {
        Write-Host ("{0,-7} /health -> FALLA ({1})" -f $wh, $_.Exception.Message)
        return $false
    }
}

function Test-Movement($wh) {
    $body = @{ product_id = 1; type = "RECEIPT"; quantity = 1; reference = "fault-test" } | ConvertTo-Json
    try {
        $r = Invoke-WebRequest -Uri "$($Api[$wh])/inventory/movements" -Method Post -Body $body `
            -ContentType "application/json" -Headers @{ "X-Correlation-ID" = "fault-test-$wh" } `
            -TimeoutSec 3 -UseBasicParsing
        Write-Host ("{0,-7} POST /inventory/movements -> {1}" -f $wh, $r.StatusCode)
        return $true
    } catch {
        Write-Host ("{0,-7} POST /inventory/movements -> FALLA ({1})" -f $wh, $_.Exception.Message)
        return $false
    }
}

Step "1. Estado inicial"
"WH-001", "WH-002", "WH-003" | ForEach-Object { [void](Test-Health $_) }

Step "2. Apagando WH-002 (api + db)"
docker @Compose stop wh002-api wh002-db | Out-Null
Start-Sleep -Seconds 2

Step "3. WH-002 caida, probando WH-001 y WH-003"
if (Test-Health "WH-002") { Write-Host "ERROR: WH-002 deberia estar caida"; $failures++ }
foreach ($wh in "WH-001", "WH-003") {
    if (-not (Test-Health $wh)) { $failures++ }
    if (-not (Test-Movement $wh)) { $failures++ }
}

Step "4. Levantando WH-002 otra vez"
docker @Compose start wh002-db wh002-api | Out-Null
for ($i = 0; $i -lt 30; $i++) {
    try { Invoke-WebRequest -Uri "$($Api['WH-002'])/health" -TimeoutSec 2 -UseBasicParsing | Out-Null; break } catch { Start-Sleep -Seconds 2 }
}
if (-not (Test-Health "WH-002")) { $failures++ }

Write-Host ""
if ($failures -eq 0) {
    Write-Host "OK: WH-001 y WH-003 siguieron funcionando con WH-002 caida" -ForegroundColor Green
} else {
    Write-Host "FALLARON $failures pruebas" -ForegroundColor Red
    exit 1
}
