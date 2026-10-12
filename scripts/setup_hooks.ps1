# Install git pre-push hook for AI log submission (Windows PowerShell).
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1

$ErrorActionPreference = 'Stop'

$HookFile = '.git/hooks/pre-push'

# Git on Windows runs hooks via Git Bash, so the hook body must be bash.
$HookBody = @'
#!/usr/bin/env bash
# Pre-push: recover missed IDE prompts, then submit AI logs.
bash scripts/_pyrun.sh scripts/log_antigravity.py --auto || true
bash scripts/_pyrun.sh scripts/sync_codex_log.py || true
bash scripts/_pyrun.sh scripts/submit_log.py || true
exit 0
'@

# Git executes hooks through its POSIX compatibility layer. The shebang must
# be the very first bytes in the file, so write UTF-8 without BOM and use LF
# line endings even when this installer runs in Windows PowerShell 5.1.
$HookBody = $HookBody.Replace("`r`n", "`n")
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) $HookFile),
    $HookBody,
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "[ai-log] Git pre-push hook installed."

if (-not (Test-Path .ai-log)) { New-Item -ItemType Directory -Path .ai-log | Out-Null }
if (-not (Test-Path .ai-log/.gitkeep)) { New-Item -ItemType File -Path .ai-log/.gitkeep | Out-Null }

Write-Host "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
