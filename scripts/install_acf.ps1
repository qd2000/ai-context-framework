[CmdletBinding()]
param(
    [string]$Package = "ai-context-framework",
    [string]$Version = "",
    [string]$Index = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Uv {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & uv @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "uv command failed with exit code ${LASTEXITCODE}: uv $($Arguments -join ' ')"
    }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found on PATH. Install uv first, then rerun this script."
}

$packageSpec = $Package
if (-not [string]::IsNullOrWhiteSpace($Version)) {
    $packageSpec = "$Package==$Version"
}

$installArguments = @("tool", "install")
if (-not [string]::IsNullOrWhiteSpace($Index)) {
    $installArguments += @("--index", $Index)
}
$installArguments += $packageSpec

Invoke-Uv $installArguments
Invoke-Uv @("tool", "update-shell")

$binDirectory = (& uv tool dir --bin).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($binDirectory)) {
    throw "Unable to determine uv tool executable directory."
}

$acfExecutable = Join-Path $binDirectory "acf.exe"
if (-not (Test-Path -LiteralPath $acfExecutable)) {
    $acfExecutable = Join-Path $binDirectory "acf"
}

Write-Host "Installed $packageSpec."
Write-Host "uv tool bin directory: $binDirectory"
if (Test-Path -LiteralPath $acfExecutable) {
    & $acfExecutable --version
} else {
    Write-Host "Restart the shell if 'acf' is not yet available on PATH."
}
