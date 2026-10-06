# Nightly backup of both Fineract databases and the uploaded KYC documents (run from the deploy folder).
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

# Uploaded documents (ID scans, payslips) live in a Docker volume, not the database.
docker run --rm -v lending_fineract_content:/data:ro -v "${PWD}\backups:/backups" alpine `
    tar czf "/backups/documents-$stamp.tgz" -C /data .
if ($LASTEXITCODE -ne 0) { throw "Backup of uploaded documents failed" }

# Keep 30 days
Get-ChildItem backups -Include *.dump, *.tgz -Recurse | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item
Write-Host "Backup complete: backups\*-$stamp.*"

# Restore (into an EMPTY stack):
#   docker compose exec -T postgresql sh -c "pg_restore -U `$POSTGRES_USER -d fineract_default --clean --if-exists /backups/fineract_default-YYYYMMDD-HHMM.dump"
#   docker run --rm -v lending_fineract_content:/data -v "${PWD}\backups:/backups" alpine tar xzf /backups/documents-YYYYMMDD-HHMM.tgz -C /data
