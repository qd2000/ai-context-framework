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

function Install-CanonicalAcfCmd {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Package,
        [Parameter(Mandatory = $true)]
        [string]$ToolDirectory,
        [Parameter(Mandatory = $true)]
        [string]$BinDirectory
    )

    if ($env:OS -ne "Windows_NT" -or $Package -ne "ai-context-framework") {
        return $null
    }

    $scriptsDirectory = Join-Path (Join-Path $ToolDirectory $Package) "Scripts"
    $pythonCandidates = @(
        (Join-Path $scriptsDirectory "python.exe"),
        (Join-Path $scriptsDirectory "python"),
        (Join-Path $scriptsDirectory "python.cmd")
    )
    $pythonExecutable = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($pythonExecutable)) {
        throw "Unable to find the uv-tool Python runtime required for canonical acf.cmd."
    }

    $acfCmd = Join-Path $BinDirectory "acf.cmd"
    $acfExe = Join-Path $BinDirectory "acf.exe"
    $pythonForCmd = [System.IO.Path]::GetFullPath($pythonExecutable).Replace("%", "%%")
    $callPrefix = if ([System.IO.Path]::GetExtension($pythonExecutable) -ieq ".cmd") { "call " } else { "" }
    $cmdContent = (
        "@echo off`r`n" +
        "setlocal`r`n" +
        $callPrefix + '"' + $pythonForCmd + '" -m acf %*' + "`r`n" +
        "exit /b %ERRORLEVEL%`r`n"
    )
    $temporaryCmd = "$acfCmd.tmp-$([guid]::NewGuid().ToString('N'))"
    try {
        [System.IO.File]::WriteAllText(
            $temporaryCmd,
            $cmdContent,
            [System.Text.UTF8Encoding]::new($false)
        )
        Move-Item -LiteralPath $temporaryCmd -Destination $acfCmd -Force
    } finally {
        if (Test-Path -LiteralPath $temporaryCmd) {
            Remove-Item -LiteralPath $temporaryCmd -Force
        }
    }

    # uv emits acf.exe for the console-script entry point.  On Windows PATHEXT
    # normally prefers .EXE to .CMD, so leaving both files would bypass the
    # canonical shim.  Remove only ACF's same-directory launcher after the CMD
    # replacement is durable; the package environment itself stays untouched.
    if (Test-Path -LiteralPath $acfExe) {
        Remove-Item -LiteralPath $acfExe -Force
    }
    if (Test-Path -LiteralPath $acfExe) {
        throw "Canonical acf.cmd installation failed because acf.exe still exists: $acfExe"
    }
    if (-not (Test-Path -LiteralPath $acfCmd)) {
        throw "Canonical acf.cmd installation failed: $acfCmd"
    }

    $pathEntries = @($env:PATH -split [System.IO.Path]::PathSeparator)
    $binOnPath = $pathEntries | Where-Object {
        if ([string]::IsNullOrWhiteSpace($_)) { return $false }
        try {
            return [System.IO.Path]::GetFullPath($_).TrimEnd('\') -ieq [System.IO.Path]::GetFullPath($BinDirectory).TrimEnd('\')
        } catch {
            return $false
        }
    }
    if ($binOnPath) {
        $resolved = Get-Command acf -CommandType Application -All -ErrorAction Stop | Select-Object -First 1
        if (-not ([System.IO.Path]::GetFullPath($resolved.Source) -ieq [System.IO.Path]::GetFullPath($acfCmd))) {
            throw "Canonical Windows ACF resolution failed: Get-Command acf resolved to $($resolved.Source), expected $acfCmd"
        }
    }

    return $acfCmd
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found on PATH. Install uv first, then rerun this script."
}

$uvPaths = Get-UvToolPaths
Assert-UvToolNotInUse -Package $Package -ToolDirectory $uvPaths.ToolDirectory -BinDirectory $uvPaths.BinDirectory

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

$binDirectory = $uvPaths.BinDirectory
$acfCmd = Install-CanonicalAcfCmd -Package $Package -ToolDirectory $uvPaths.ToolDirectory -BinDirectory $binDirectory
$acfExecutable = if ($null -ne $acfCmd) { $acfCmd } else { Join-Path $binDirectory "acf" }

Write-Host "Installed $packageSpec."
Write-Host "uv tool bin directory: $binDirectory"
if (Test-Path -LiteralPath $acfExecutable) {
    & $acfExecutable --version
    if ($null -ne $acfCmd) {
        Write-Host "Canonical Windows ACF command: $acfCmd"
    }
} else {
    Write-Host "Restart the shell if 'acf' is not yet available on PATH."
}
