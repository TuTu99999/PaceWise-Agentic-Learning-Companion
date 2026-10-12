# One-time namespace-only relocation. Original simulator stays parked for rollback.
# No data, configuration, or source files are deleted or overwritten.
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskSource = Join-Path $taskRoot 'lms-simulator/app'
$taskDestination = Join-Path $taskRoot 'src/course_source'
New-Item -ItemType Directory -Path $taskDestination -Force | Out-Null
$taskModules = @('models', 'dates', 'deadline_snapshot', 'learning_api', 'pacewise_contracts', 'integration_api', 'teacher_management', 'course_management', 'schedule_import', 'telemetry', 'demo_seed_policy')
foreach ($taskModule in $taskModules) {
    $taskTarget = Join-Path $taskDestination ($taskModule + '.py')
    if (Test-Path -LiteralPath $taskTarget) { throw "Refusing to overwrite: $taskTarget" }
    $taskText = [IO.File]::ReadAllText((Join-Path $taskSource ($taskModule + '.py')))
    $taskText = $taskText.Replace('from app.', 'from src.course_source.').Replace('from app import', 'from src.course_source import')
    [IO.File]::WriteAllText($taskTarget, $taskText, [Text.UTF8Encoding]::new($false))
}
Write-Output ('Relocated domain modules: ' + $taskModules.Count)
