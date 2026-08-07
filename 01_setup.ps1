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
# A failure here must not throw. Everything above this line has already been built, and Oracle alone
# is a quarter of an hour of it - but the last line of this script is what keeps the containers
# running, so a throw here would take all of it down. The failure is remembered instead, the shell
# below still opens, and the script fails once it returns.
python "$PSScriptRoot\06_test_connections.py"
$windowsTestFailed = $LASTEXITCODE -ne 0
if ($windowsTestFailed) {
    Write-Warning 'failure in 06_test_connections.py on Windows - the containers are left running so you can look into it'
}

# Run WSL2 to keep docker containers running
wsl --cd $PSScriptRoot --user root

if ($windowsTestFailed) { throw 'failure in 06_test_connections.py on Windows'}
