# Local controlled cutover. No volume removal or data deletion. Fail closed.
param([string]$BackupName = 'standalone-migration-20261010')
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($BackupName -notmatch '^[a-zA-Z0-9-]+$') { throw 'Invalid backup directory name' }
$taskBackup = [IO.Path]::GetFullPath((Join-Path $taskRoot ('data/' + $BackupName)))
$taskDataRoot = [IO.Path]::GetFullPath((Join-Path $taskRoot 'data')) + [IO.Path]::DirectorySeparatorChar
if (-not $taskBackup.StartsWith($taskDataRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Backup path outside workspace data' }
if (Test-Path -LiteralPath $taskBackup) { throw 'Backup exists; do not rerun a cutover blindly' }
New-Item -ItemType Directory -Path $taskBackup | Out-Null

function Invoke-TaskDocker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw ('Docker command failed: ' + ($args[0..([Math]::Min(2, $args.Count - 1))] -join ' ')) }
}

Push-Location $taskRoot
try {
    Invoke-TaskDocker compose stop frontend backend worker
    Invoke-TaskDocker compose --env-file .env -f lms-simulator/docker-compose.yml stop lms-simulator
    # Fixed, inspected container names, explicit DB names, custom-format backups.
    Invoke-TaskDocker exec pacewise-pacewise-postgres-1 pg_dump -U pacewise -d pacewise -Fc -f /tmp/pacewise-before-standalone.dump
    Invoke-TaskDocker exec pacewise-lms-lms-postgres-1 pg_dump -U canvas -d canvas_development -Fc -f /tmp/source-before-standalone.dump
    Invoke-TaskDocker cp 'pacewise-pacewise-postgres-1:/tmp/pacewise-before-standalone.dump' (Join-Path $taskBackup 'pacewise-before.dump')
    Invoke-TaskDocker cp 'pacewise-lms-lms-postgres-1:/tmp/source-before-standalone.dump' (Join-Path $taskBackup 'source-before.dump')

    # The stopped source container remains readable through docker cp.
    $taskUploads = Join-Path $taskRoot 'data/course-source/uploads'
    $taskMocks = Join-Path $taskRoot 'data/course-source/mock-files'
    if ((Test-Path -LiteralPath $taskUploads) -and (Get-ChildItem -LiteralPath $taskUploads -Force | Select-Object -First 1)) { throw 'Destination uploads is not empty' }
    if ((Test-Path -LiteralPath $taskMocks) -and (Get-ChildItem -LiteralPath $taskMocks -Force | Select-Object -First 1)) { throw 'Destination mock files is not empty' }
    New-Item -ItemType Directory -Path $taskUploads -Force | Out-Null
    New-Item -ItemType Directory -Path $taskMocks -Force | Out-Null
    Invoke-TaskDocker cp 'pacewise-lms-lms-simulator-1:/app/uploads/.' $taskUploads
    Invoke-TaskDocker cp 'pacewise-lms-lms-simulator-1:/app/static/mock-files/.' $taskMocks

    $taskMigrationScript = Join-Path $taskRoot 'src/course_source/migration.py'
    Invoke-TaskDocker compose --env-file .env -f lms-simulator/docker-compose.yml run --rm --no-deps --entrypoint python `
        -v "${taskMigrationScript}:/tmp/migration.py:ro" -v "${taskBackup}:/backup" lms-simulator `
        /tmp/migration.py --export /backup/source.jsonl.gz --report /backup/source-inventory.json
    Invoke-TaskDocker compose run --rm --no-deps --user 0 -e PYTHONPATH=/home/appuser/.local/lib/python3.11/site-packages backend python -m src.course_source.migration `
        --export "/app/data/$BackupName/pacewise-before.jsonl.gz" --report "/app/data/$BackupName/pacewise-inventory-before.json"
    Invoke-TaskDocker compose run --rm --no-deps --user 0 -e PYTHONPATH=/home/appuser/.local/lib/python3.11/site-packages backend python -m src.course_source.migration `
        --import-snapshot "/app/data/$BackupName/source.jsonl.gz" --report "/app/data/$BackupName/import-verification.json"
    # Second import verifies idempotency and persisted transaction, not just memory.
    Invoke-TaskDocker compose run --rm --no-deps --user 0 -e PYTHONPATH=/home/appuser/.local/lib/python3.11/site-packages backend python -m src.course_source.migration `
        --import-snapshot "/app/data/$BackupName/source.jsonl.gz" --report "/app/data/$BackupName/import-retry-verification.json"
    Invoke-TaskDocker compose run --rm --no-deps --user 0 -e PYTHONPATH=/home/appuser/.local/lib/python3.11/site-packages backend python -m src.course_source.migration `
        --export "/app/data/$BackupName/pacewise-after.jsonl.gz" --report "/app/data/$BackupName/pacewise-inventory-after.json"
    $taskBefore = Get-Content -LiteralPath (Join-Path $taskBackup 'pacewise-inventory-before.json') -Raw | ConvertFrom-Json
    $taskAfter = Get-Content -LiteralPath (Join-Path $taskBackup 'pacewise-inventory-after.json') -Raw | ConvertFrom-Json
    if (($taskBefore.inventory | ConvertTo-Json -Depth 5 -Compress) -ne ($taskAfter.inventory | ConvertTo-Json -Depth 5 -Compress)) { throw 'PaceWise historical data changed during migration' }
    Invoke-TaskDocker compose up -d backend worker frontend
    Invoke-TaskDocker compose --env-file .env -f lms-simulator/docker-compose.yml stop lms-postgres
    Write-Output 'Cutover done: source verified, main history unchanged, both old services stopped. Run live smoke checks next.'
} finally { Pop-Location }
