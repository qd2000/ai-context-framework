[CmdletBinding()]
param(
    [string]$Package = "ai-context-framework",
    [string]$Index = "",
    [switch]$Reinstall
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

function Get-UvToolPaths {
    $toolDirectory = (& uv tool dir).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($toolDirectory)) {
        throw "Unable to determine uv tool directory."
    }

    $binDirectory = (& uv tool dir --bin).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($binDirectory)) {
        throw "Unable to determine uv tool executable directory."
    }

    return @{
        ToolDirectory = $toolDirectory
        BinDirectory = $binDirectory
    }
}

function Assert-UvToolNotInUse {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Package,
        [Parameter(Mandatory = $true)]
        [string]$ToolDirectory,
        [Parameter(Mandatory = $true)]
        [string]$BinDirectory
    )

    if ($env:OS -ne "Windows_NT") {
        return
    }

    $packageDirectory = Join-Path $ToolDirectory $Package
    $packagePrefix = $null
    if (Test-Path -LiteralPath $packageDirectory) {
        $packagePrefix = [System.IO.Path]::GetFullPath($packageDirectory).TrimEnd('\') + '\'
    }

    $acfLauncher = $null
    if ($Package -eq "ai-context-framework") {
        $acfLauncher = [System.IO.Path]::GetFullPath((Join-Path $BinDirectory "acf.exe"))
    }

    $blockingProcesses = @()
    foreach ($process in (Get-CimInstance Win32_Process -ErrorAction Stop)) {
        if ([string]::IsNullOrWhiteSpace($process.ExecutablePath)) {
            continue
        }
        try {
            $executablePath = [System.IO.Path]::GetFullPath($process.ExecutablePath)
        } catch {
            continue
        }

        $insidePackage = $false
        if ($null -ne $packagePrefix) {
            $insidePackage = $executablePath.StartsWith(
                $packagePrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        }
        $isLauncher = (
            $null -ne $acfLauncher -and
            $executablePath.Equals($acfLauncher, [System.StringComparison]::OrdinalIgnoreCase)
        )
        if ($insidePackage -or $isLauncher) {
            $blockingProcesses += "pid=$($process.ProcessId) exe=$executablePath"
        }
    }

    if ($blockingProcesses.Count -gt 0) {
        throw (
            "Refusing to mutate the global uv tool while ACF tool processes are still running. " +
            "Wait for the owning task/process to finish, then retry. Blocking process(es): " +
            ($blockingProcesses -join "; ")
        )
    }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found on PATH. Install uv first, then rerun this script."
}

$uvPaths = Get-UvToolPaths
Assert-UvToolNotInUse -Package $Package -ToolDirectory $uvPaths.ToolDirectory -BinDirectory $uvPaths.BinDirectory

# Use an unpinned install request with --upgrade rather than `uv tool upgrade`.
# A tool originally installed from an exact version receipt can otherwise remain
# pinned to that version.  --force also lets this supported update path repair a
# partially missing tool environment after a prior interrupted mutation.
$upgradeArguments = @("tool", "install", "--force", "--upgrade")
if (-not [string]::IsNullOrWhiteSpace($Index)) {
    $upgradeArguments += @("--index", $Index)
}
if ($Reinstall) {
    $upgradeArguments += "--reinstall"
}
$upgradeArguments += $Package

Invoke-Uv $upgradeArguments
Invoke-Uv @("tool", "update-shell")

$binDirectory = $uvPaths.BinDirectory

$acfExecutable = Join-Path $binDirectory "acf.exe"
if (-not (Test-Path -LiteralPath $acfExecutable)) {
    $acfExecutable = Join-Path $binDirectory "acf"
}

Write-Host "Upgraded $Package."
if (Test-Path -LiteralPath $acfExecutable) {
    & $acfExecutable --version
} else {
    Write-Host "Restart the shell if 'acf' is not yet available on PATH."
}
