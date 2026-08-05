$ErrorActionPreference = 'Stop'

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

# Run WSL2 to keep docker containers running
wsl --cd $PSScriptRoot --user root
