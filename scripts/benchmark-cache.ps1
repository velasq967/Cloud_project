# Mide latencia de GET /inventory/{id} para comparar con/sin Redis.
# Uso:
#   .\scripts\benchmark-cache.ps1 -Requests 200 -ProductId 1
#   .\scripts\benchmark-cache.ps1 -Requests 200 -OutFile docs\evidencias\fase-02\cache-on.csv

param(
    [string]$Api = "http://localhost:8001",
    [int]$ProductId = 1,
    [int]$Requests = 200,
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"
$times = [System.Collections.Generic.List[double]]::new()
$sources = @{}

# Calentamiento: la primera lectura puede ser miss.
Invoke-RestMethod -Uri "$Api/inventory/$ProductId" | Out-Null

for ($i = 0; $i -lt $Requests; $i++) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $response = Invoke-RestMethod -Uri "$Api/inventory/$ProductId"
    $sw.Stop()
    $times.Add($sw.Elapsed.TotalMilliseconds)
    if ($response.source) {
        $sources[$response.source] = 1 + ($sources[$response.source] -as [int])
    }
}

$sorted = $times | Sort-Object
$avg = ($times | Measure-Object -Average).Average
$p50 = $sorted[[int]($Requests * 0.50)]
$p95 = $sorted[[int][Math]::Min($Requests - 1, $Requests * 0.95)]
$p99 = $sorted[[int][Math]::Min($Requests - 1, $Requests * 0.99)]

Write-Host "Requests: $Requests"
Write-Host ("Avg: {0:N2} ms" -f $avg)
Write-Host ("P50: {0:N2} ms" -f $p50)
Write-Host ("P95: {0:N2} ms" -f $p95)
Write-Host ("P99: {0:N2} ms" -f $p99)
Write-Host ("Sources: {0}" -f (($sources.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ", "))

if ($OutFile) {
    $rows = for ($i = 0; $i -lt $Requests; $i++) {
        [PSCustomObject]@{
            request = $i + 1
            elapsed_ms = [Math]::Round($times[$i], 3)
        }
    }
    $rows | Export-Csv -Path $OutFile -NoTypeInformation -Encoding UTF8
    Write-Host "Resultados: $OutFile"
}
