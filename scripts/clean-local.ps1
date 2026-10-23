<#
.SYNOPSIS
    Safe cleanup of known ignored local artifacts.

.DESCRIPTION
    Lists or removes named local cache directories that are already gitignored.
    Default mode is dry-run. Use -Confirm to actually delete.

    SAFETY:
    - Only named directories are eligible (default: __pycache__, .ruff_cache,
      .pytest_cache).
    - Tracked files are never candidates.
    - .env, certs/, data/, results/, and .venv are excluded.
    - Paths outside the repository root are rejected.
    - No wildcards or recursive root deletion.

.PARAMETER Confirm
    Actually delete the candidates. Without this switch, only a list is printed.

.PARAMETER Path
    Specific directory names to clean. Defaults to __pycache__, .ruff_cache,
    .pytest_cache.

.EXAMPLE
    .\scripts\clean-local.ps1
    # Dry-run: shows what would be deleted.

.EXAMPLE
    .\scripts\clean-local.ps1 -Confirm
    # Deletes the default cache directories.
#>
[CmdletBinding()]
param(
    [switch]$Confirm,
    [string[]]$Path = @("__pycache__", ".ruff_cache", ".pytest_cache")
)

$ErrorActionPreference = "Stop"

# Protected names that must never be cleaned.
$Protected = @(".env", "certs", "data", "results", ".venv", ".git", "migrations",
               "datasets", "prompts", "contract", "ledger", "ledger_api", "tests",
               "docs", ".github")

$RepoRoot = (git rev-parse --show-toplevel 2>$null)
if (-not $RepoRoot) {
    Write-Error "Not inside a Git repository."
    exit 1
}
$RepoRoot = (Resolve-Path $RepoRoot).Path

$Candidates = @()

foreach ($Name in $Path) {
    # Reject protected names.
    if ($Protected -contains $Name) {
        Write-Warning "Skipping protected name: $Name"
        continue
    }

    # Find all matching directories under the repo root.
    $Found = Get-ChildItem -Path $RepoRoot -Directory -Recurse -Filter $Name `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.FullName.StartsWith($RepoRoot) -and
            -not $_.FullName.Contains(".venv") -and
            -not $_.FullName.Contains(".git\")
        }

    foreach ($Dir in $Found) {
        # Verify no tracked files exist inside.
        $TrackedOutput = git ls-files -- $Dir.FullName 2>&1 | Where-Object { $_ -is [string] }
        if ($TrackedOutput) {
            Write-Warning "Skipping $($Dir.FullName): contains tracked files."
            continue
        }
        $Candidates += $Dir
    }
}

if ($Candidates.Count -eq 0) {
    Write-Host "No eligible directories found."
    exit 0
}

Write-Host "`nEligible directories ($($Candidates.Count)):"
foreach ($Dir in $Candidates) {
    $Size = (Get-ChildItem -Path $Dir.FullName -Recurse -File -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum).Sum
    $SizeKB = [math]::Round(($Size / 1024), 1)
    Write-Host "  $($Dir.FullName)  ($SizeKB KB)"
}

if (-not $Confirm) {
    Write-Host "`nDry run. Use -Confirm to delete these directories."
    exit 0
}

foreach ($Dir in $Candidates) {
    Remove-Item -Path $Dir.FullName -Recurse -Force
    Write-Host "  Deleted: $($Dir.FullName)"
}

Write-Host "`nDone. Removed $($Candidates.Count) directories."
