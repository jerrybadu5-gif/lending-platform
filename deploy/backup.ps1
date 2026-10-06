# Nightly backup of both Fineract databases (run from the deploy folder).
# Schedule with Windows Task Scheduler, e.g. daily 23:30:
#   powershell -ExecutionPolicy Bypass -File C:\path\to\deploy\backup.ps1
# Copy the backups folder off this machine (OneDrive, NAS, USB) — a backup on the same disk is not a backup.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
New-Item -ItemType Directory -Force -Path backups | Out-Null

foreach ($db in @("fineract_tenants", "fineract_default")) {
    docker compose exec -T postgresql sh -c "pg_dump -U `$POSTGRES_USER -Fc $db > /backups/$db-$stamp.dump"
    if ($LASTEXITCODE -ne 0) { throw "Backup of $db failed" }
}

# Keep 30 days
Get-ChildItem backups -Filter *.dump | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item
Write-Host "Backup complete: backups\*-$stamp.dump"

# Restore (into an EMPTY stack):
#   docker compose exec -T postgresql sh -c "pg_restore -U `$POSTGRES_USER -d fineract_default --clean --if-exists /backups/fineract_default-YYYYMMDD-HHMM.dump"
