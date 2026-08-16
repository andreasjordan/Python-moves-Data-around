# Checks that this machine has what the setup needs, and changes nothing at all.
#
# The setup owns WSL2 and this repository working tree. It does not install anything on your
# machine and it does not change your machine's configuration - see "The setup owns WSL2, not your
# machine" in AGENTS.md. Everything below is therefore yours to install, and this script exists so
# that a missing piece is named in seconds rather than found after a quarter of an hour of Oracle
# starting up.
#
# It has no dependencies, deliberately. It runs before anything is guaranteed to be there, so it
# imports no module, calls no lib/ function and prints with Write-Host. It is the one PowerShell
# file in this repository besides 01_setup.ps1 and 07_check_ports.ps1, for the same reason as those
# two: Windows is what starts it.
#
# 01_setup.ps1 runs it first and stops when it reports anything. It is read-only, so like
# 07_check_ports.ps1 it is also safe to run on its own at any time.

[CmdletBinding()]
param ()

# Deliberately not $ErrorActionPreference = 'Stop'. The point of this script is to name every
# missing piece in one pass; stopping at the first one means installing them one per run.

# A finding is what is missing plus the command that fixes it. These helpers are local to the
# script and follow no contract from lib/ - that one is for Python.
$missing = [System.Collections.Generic.List[object]]::new()

function Add-Finding {
    param ([string]$What, [string]$Fix)
    $missing.Add([PSCustomObject]@{ What = $What ; Fix = $Fix })
}

function Write-Result {
    param ([string]$Name, [bool]$Ok, [string]$Detail)
    Write-Host ('  {0,-44} {1,-8} {2}' -f $Name, $(if ($Ok) { 'ok' } else { 'MISSING' }), $Detail)
}

Write-Host 'Checking this machine for what the setup needs'
Write-Host ''

# Python itself
# No minimum version is asserted. The repository has never named one, and inventing a floor here
# would be a rule nobody has decided - so the version is printed instead, which is enough to
# recognise a wrong interpreter. What is checked is that "python" answers at all: on Windows it is
# often the Microsoft Store stub, which is on the PATH and does nothing.
$pythonVersion = $null
if (Get-Command -Name python -ErrorAction SilentlyContinue) {
    $pythonVersion = (python --version 2>&1 | Out-String).Trim()
}
$pythonOk = $pythonVersion -match '^Python 3\.'
Write-Result -Name 'python on the PATH' -Ok $pythonOk -Detail $pythonVersion
if (-not $pythonOk) {
    Add-Finding -What 'no working "python" on the PATH - a Microsoft Store stub counts as missing' `
        -Fix 'install Python from https://www.python.org/downloads/ and tick "Add python.exe to PATH"'
}

# The packages
# requirements-windows.txt is the one list for this side, and it starts with "-r requirements.txt",
# so the include is followed rather than the shared list being read separately. Nothing else
# enumerates the packages and nothing here should start.
function Get-RequirementName {
    param ([string]$Path)

    foreach ($line in (Get-Content -Path $Path)) {
        $line = ($line -split '#')[0].Trim()
        if (-not $line) { continue }

        if ($line -match '^-r\s+(.+)$') {
            Get-RequirementName -Path (Join-Path (Split-Path -Path $Path) $Matches[1].Trim())
            continue
        }

        # "psycopg[binary]" is the package psycopg with an extra, and pip lists it under the bare
        # name. Version specifiers are stripped for the same reason, although nothing is pinned.
        ($line -split '[\[<>=!~;]')[0].Trim()
    }
}

if ($pythonOk) {
    # One pip call rather than one per package - "pip show" eight times is eight interpreter starts
    $installed = @{ }
    foreach ($package in (python -m pip list --format=json | ConvertFrom-Json)) {
        # PEP 503 normalisation, so that confluent-kafka and confluent_kafka are the same name
        $installed[($package.name -replace '[-_.]+', '-').ToLower()] = $package.version
    }

    $packagesMissing = @()
    foreach ($requirement in (Get-RequirementName -Path $PSScriptRoot/requirements-windows.txt)) {
        $key = ($requirement -replace '[-_.]+', '-').ToLower()
        $found = $installed.ContainsKey($key)
        Write-Result -Name "package $requirement" -Ok $found -Detail $installed[$key]
        if (-not $found) { $packagesMissing += $requirement }
    }

    if ($packagesMissing) {
        Add-Finding -What "Python packages not installed: $($packagesMissing -join ', ')" `
            -Fix 'python -m pip install -r requirements-windows.txt'
    }
}

# The SQL Server ODBC driver
# pip cannot install this one, which is exactly why it is worth checking: it is a manual step in
# README.md and the only way to discover it was missing used to be a failing connection. The name
# is the one hard-coded in lib/connect_sql_instance.py and it has to match exactly.
#
# Read from the registry rather than with Get-OdbcDriver, because this script imports nothing.
$driverName = 'ODBC Driver 18 for SQL Server'
$driverKey = 'HKLM:\SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers'
$driverOk = (Test-Path -Path $driverKey) -and
    ((Get-ItemProperty -Path $driverKey).PSObject.Properties.Name -contains $driverName)
Write-Result -Name $driverName -Ok $driverOk -Detail ''
if (-not $driverOk) {
    Add-Finding -What "the $driverName is not installed, and pip cannot install it" `
        -Fix 'https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server'
}

# WSL2
# Starting the default distribution is the check, rather than parsing "wsl --list --verbose" -
# that output is UTF-16LE on Windows and reading it is a well known trap. Asking Linux a question
# and reading its answer avoids the encoding question entirely, and it proves the thing that
# actually matters: that there is a default distribution and that it starts.
#
# It costs the few seconds of a cold WSL2 boot, which is why it says so first.
if (-not (Get-Command -Name wsl -ErrorAction SilentlyContinue)) {
    Write-Result -Name 'WSL2' -Ok $false -Detail 'no wsl command'
    Add-Finding -What 'WSL2 is not installed' `
        -Fix 'wsl --install -d Ubuntu-24.04   (in an elevated prompt, then reboot)'
} else {
    Write-Host '  starting the default WSL2 distribution to check it ...'
    $kernel = wsl -e uname -r 2>$null

    if ($LASTEXITCODE -ne 0 -or -not $kernel) {
        Write-Result -Name 'a default WSL2 distribution' -Ok $false -Detail 'none that starts'
        Add-Finding -What 'WSL2 has no default distribution, or it does not start' `
            -Fix 'wsl --install -d Ubuntu-24.04   (in an elevated prompt, then reboot)'
    } else {
        # A WSL2 kernel names itself; a WSL1 one does not, and docker needs WSL2.
        $isWsl2 = $kernel -match 'WSL2'
        Write-Result -Name 'the distribution is WSL2' -Ok $isWsl2 -Detail $kernel
        if (-not $isWsl2) {
            Add-Finding -What "the default distribution runs on $kernel, which is not WSL2, and docker needs WSL2" `
                -Fix 'wsl --set-version <distribution> 2'
        }

        # 02_wsl2_setup.sh installs everything with apt and reads lsb_release, so a distribution
        # that is not Debian-based fails there in a way that says nothing about the cause.
        $null = wsl -e sh -c 'command -v apt-get' 2>$null
        $isApt = $LASTEXITCODE -eq 0
        Write-Result -Name 'the distribution has apt-get' -Ok $isApt -Detail ''
        if (-not $isApt) {
            Add-Finding -What 'the default distribution has no apt-get, and 02_wsl2_setup.sh installs everything with apt' `
                -Fix 'wsl --install -d Ubuntu-24.04   and make it the default with: wsl --set-default Ubuntu-24.04'
        }
    }
}

Write-Host ''

if (-not $missing.Count) {
    Write-Host 'This machine has everything the setup needs.'
    exit 0
}

Write-Host 'This machine is missing something the setup needs:'
Write-Host ''
foreach ($finding in $missing) {
    Write-Host "  * $($finding.What)"
    Write-Host "      $($finding.Fix)"
    Write-Host ''
}
Write-Host 'Install those yourself and run 01_setup.ps1 again. Nothing here has been changed.'
exit 1
