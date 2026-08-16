$ErrorActionPreference = 'Stop'

# Every step announces itself before it runs, says roughly how long it takes, and is closed off
# with what it actually took.
#
# Two stretches of this script are quiet for minutes - 04_docker_compose.sh while Oracle starts,
# and the port wait near the end - and a quiet stretch with no output is indistinguishable from a
# script that has hung. Saying what is happening and roughly how long it takes is the whole fix.
#
# The measured "took" line exists because the estimates have been wrong: Oracle's first start was
# written down as a quarter of an hour for a long time and is about two minutes. A run now says so
# itself rather than leaving it to be guessed at.
#
# The clock is local time, while the container logs are UTC. That difference is what makes a
# failure here and the container log behind it look unrelated at a glance.
#
# This helper follows no contract from lib/, which is for Python.
$script:stepStarted = $null

function Write-Step {
    param ([string]$Message, [string]$Duration)

    # Floor, not [int]: casting a double to [int] rounds, so 59 seconds would print as "1:59"
    if ($script:stepStarted) {
        $took = (Get-Date) - $script:stepStarted
        Write-Host ('    took {0:0}:{1:00}' -f [math]::Floor($took.TotalMinutes), $took.Seconds) -ForegroundColor DarkGray
    }

    $script:stepStarted = Get-Date
    Write-Host ''
    Write-Host ('==> [{0:HH:mm:ss}] {1}' -f $script:stepStarted, $Message) -ForegroundColor Cyan
    if ($Duration) { Write-Host "    $Duration" -ForegroundColor DarkGray }
}

$runStarted = Get-Date

# Check this machine
# The setup owns WSL2 and this repository, and nothing else - so the things it will not install are
# checked first and named all at once. This step replaces the "pip install" that used to run here:
# the notebooks run on the Windows Python, so that side does have to be right, but making it right
# is yours. It is still the only step that costs nothing when it fails.
Write-Step -Message 'Checking this machine for what the setup needs' -Duration 'a few seconds, plus a WSL2 boot'
& $PSScriptRoot/00_check_host.ps1
if ($LASTEXITCODE -ne 0) { throw 'this machine is missing something the setup needs - see above' }

# Setup WSL2 with the ODBC driver, docker and Python
Write-Step -Message 'Installing the ODBC driver, docker, 7-Zip and Python inside WSL2' -Duration 'several minutes - pyenv compiles Python from source'
wsl --cd $PSScriptRoot --user root ./02_wsl2_setup.sh
if ($LASTEXITCODE -ne 0) { throw 'failure in 02_wsl2_setup.sh'}

# Install the Python packages inside WSL2
Write-Step -Message 'Installing the Python packages inside WSL2' -Duration 'a minute or two'
wsl --cd $PSScriptRoot ./03_python_setup.sh
if ($LASTEXITCODE -ne 0) { throw 'failure in 03_python_setup.sh'}

# Shutdown needed by docker
Write-Step -Message 'Shutting WSL2 down, which docker needs'
wsl --shutdown

# Start docker containers
Write-Step -Message 'Starting the containers and waiting for the demo databases' -Duration 'about two minutes once the images are there, four on a run that pulls them - the 15 minute timeout in 04 is a margin, not an expectation'
wsl --cd $PSScriptRoot --user root ./04_docker_compose.sh
if ($LASTEXITCODE -ne 0) { throw 'failure in 04_docker_compose.sh'}

# Create sample data
# "bash -l" is needed so that pyenv is on the PATH and "python" is the 3.14.6 from 02_wsl2_setup.sh
Write-Step -Message 'Creating and downloading the sample data' -Duration 'seconds when it is already there, a few minutes on a fresh clone'
wsl --cd $PSScriptRoot bash -lc 'python ./05_sample_data_setup.py'
if ($LASTEXITCODE -ne 0) { throw 'failure in 05_sample_data_setup.py'}

# Test connections
Write-Step -Message 'Testing every connection from inside WSL2'
wsl --cd $PSScriptRoot bash -lc 'python ./06_test_connections.py'
if ($LASTEXITCODE -ne 0) { throw 'failure in 06_test_connections.py'}

# Hold WSL2 open for the Windows half of this script
# Everything from here on runs on Windows, so no "wsl" process is alive - and WSL2 terminates the
# distribution a few seconds after its last process exits, taking every container with it. That is
# the same reason start_demo.ps1 ends in a "wsl" shell.
#
# Measured in the sibling repository before it had this: the last WSL2 step finished at 20:56:01, and
# at 20:56:16 every container logged a shutdown - postgres "received fast shutdown request", mongo a
# SignalHandler. The connection test two seconds later then failed against a database that no longer
# existed, with a socket error that reads exactly like a missing port forward. It is not one, and the
# two are indistinguishable from the driver's message alone - check the container log, whose
# timestamps are UTC while these are local.
$keepWsl2Alive = Start-Process -FilePath wsl -ArgumentList 'sleep', '900' -PassThru -NoNewWindow

# Wait for the port forwarding on the Windows side
# The step above reaches the containers over the WSL2 loopback. Windows reaches them through
# wslrelay, which publishes each container port here a moment after docker binds it inside WSL2 -
# and on a clean install, 1521 has been seen to arrive minutes after the other four, while Oracle
# itself was running and answering inside WSL2 the whole time. Connecting is cheap and silent, so
# wait for the forward rather than letting that race decide whether the setup succeeded.
Write-Step -Message 'Waiting for the Windows port forwarding' -Duration 'instant when the forwards are up, minutes on a cold install'
$deadline = (Get-Date).AddMinutes(3)
foreach ($port in 1433, 1521, 5432, 27017, 19092) {
    # Named one at a time, because this wait used to be completely silent and a port that lags the
    # others by minutes then looks exactly like a hung script
    Write-Host -NoNewline "    127.0.0.1:$port ... "
    while (-not (Test-Connection -TargetName 127.0.0.1 -TcpPort $port -Quiet)) {
        if ((Get-Date) -gt $deadline) {
            Write-Host 'not forwarded'
            Write-Warning "no port forwarding on Windows for 127.0.0.1:$port"
            break
        }
        Start-Sleep -Seconds 5
    }
    if ((Get-Date) -le $deadline) { Write-Host 'ok' }
}

# Test connections from Windows
# The same script again, from the side that runs the demos - the notebooks only ever take this path.
#
# A failure here is remembered rather than thrown, so that the stop below still runs. Everything
# above this line has already been built, and there is no reason to leave the containers to be
# killed by the WSL2 idle timeout just because a connection test failed.
Write-Step -Message 'Testing every connection from Windows, which is where the notebooks run'
python "$PSScriptRoot\06_test_connections.py"
$windowsTestFailed = $LASTEXITCODE -ne 0
if ($windowsTestFailed) {
    Write-Warning 'failure in 06_test_connections.py on Windows - run start_demo.ps1 and then 07_check_ports.ps1 to look into it'
}

# Stop the containers again
# This script sets the machine up, it does not start a demo. The volumes exist now - Oracle's first
# start is most of the time this script takes - so from here on, starting the containers is a minute
# rather than a quarter of an hour. start_demo.ps1 is what you run when you want to demo.
#
# Stopping here is what lets this script be run for both repositories one after the other: the
# sibling's setup would otherwise find these containers holding every port it wants.
#
# And it is a stop, not an exit: without it the containers are not left running, they are killed
# when WSL2 idles out, and SQL Server and Oracle do crash recovery on the next start.
Write-Step -Message 'Stopping the containers again - the setup builds, start_demo.ps1 runs' -Duration 'about a minute'
wsl --cd "$PSScriptRoot\docker" --user root docker compose stop
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'failure stopping the containers - they are still running and will be in the way of the sibling repository'
}

# The containers are down, so nothing needs WSL2 held open any more
Stop-Process -InputObject $keepWsl2Alive -ErrorAction Ignore

if ($windowsTestFailed) { throw 'failure in 06_test_connections.py on Windows'}

# The total, so that "the whole run takes about half an hour" in README.md stays a measurement
# rather than a memory
$total = (Get-Date) - $runStarted
Write-Step -Message ('Finished in {0:0}:{1:00}. Run start_demo.ps1 when you want to demo.' -f [math]::Floor($total.TotalMinutes), $total.Seconds)
