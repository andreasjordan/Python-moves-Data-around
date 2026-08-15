$ErrorActionPreference = 'Stop'

# Install the Python packages on Windows
# Everything else in this script happens inside WSL2, but the notebooks run here, against the Windows
# Python - so this is the side that has to be able to reach the databases in the end.
# It is first because it is the only step that costs nothing when it fails: a missing "python" or a
# broken package is found in seconds, rather than after a quarter of an hour of Oracle starting up.
# requirements-windows.txt is requirements.txt plus "notebook", which is the only package that
# differs between the two sides - WSL2 never opens a notebook.
python -m pip install -r "$PSScriptRoot\requirements-windows.txt"
if ($LASTEXITCODE -ne 0) { throw 'failure installing the Python packages on Windows'}

# Setup WSL2 with the ODBC driver, docker and Python
wsl --cd $PSScriptRoot --user root ./02_wsl2_setup.sh
if ($LASTEXITCODE -ne 0) { throw 'failure in 02_wsl2_setup.sh'}

# Install the Python packages
wsl --cd $PSScriptRoot ./03_python_setup.sh
if ($LASTEXITCODE -ne 0) { throw 'failure in 03_python_setup.sh'}

# Shutdown needed by docker
wsl --shutdown

# Start docker containers
wsl --cd $PSScriptRoot --user root ./04_docker_compose.sh
if ($LASTEXITCODE -ne 0) { throw 'failure in 04_docker_compose.sh'}

# Create sample data
# "bash -l" is needed so that pyenv is on the PATH and "python" is the 3.14.6 from 02_wsl2_setup.sh
wsl --cd $PSScriptRoot bash -lc 'python ./05_sample_data_setup.py'
if ($LASTEXITCODE -ne 0) { throw 'failure in 05_sample_data_setup.py'}

# Test connections
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
$deadline = (Get-Date).AddMinutes(3)
foreach ($port in 1433, 1521, 5432, 27017, 19092) {
    while (-not (Test-Connection -TargetName 127.0.0.1 -TcpPort $port -Quiet)) {
        if ((Get-Date) -gt $deadline) {
            Write-Warning "no port forwarding on Windows for 127.0.0.1:$port"
            break
        }
        Start-Sleep -Seconds 5
    }
}

# Test connections from Windows
# The same script again, from the side that runs the demos - the notebooks only ever take this path.
#
# A failure here is remembered rather than thrown, so that the stop below still runs. Everything
# above this line has already been built, and there is no reason to leave the containers to be
# killed by the WSL2 idle timeout just because a connection test failed.
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
wsl --cd "$PSScriptRoot\docker" --user root docker compose stop
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'failure stopping the containers - they are still running and will be in the way of the sibling repository'
}

# The containers are down, so nothing needs WSL2 held open any more
Stop-Process -InputObject $keepWsl2Alive -ErrorAction Ignore

if ($windowsTestFailed) { throw 'failure in 06_test_connections.py on Windows'}
