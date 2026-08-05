#!/bin/bash

# Stop on the first error. The blocks below used to be one long "&& \" chain, which meant
# that a failure in an early block silently skipped everything after it.
set -e

# setup DNS
# DNS inside of WSL2 is sometimes a problem
# In the beginning, /etc/resolv.conf is a symlink to /mnt/wsl/resolv.conf and name resolution works
# Problem: Sometimes, etc/resolv.conf is a symlink to ../run/systemd/resolve/stub-resolv.conf and it does not work
# Workaround 1: Configure a static /etc/resolv.conf with the DNS server of your choice
# Problem: Sometimes, etc/resolv.conf is removed again and recreated as a symlink to ../run/systemd/resolve/stub-resolv.conf
#echo "[network]" >> /etc/wsl.conf && \
#echo "generateResolvConf = false" >> /etc/wsl.conf && \
#rm /etc/resolv.conf && \
#echo "nameserver 1.1.1.1" > /etc/resolv.conf && \
# Workaround 2: Configure systemd-resolved with the DNS server of your choice
# Problem: Not tested yet
#echo "DNS=1.1.1.1" >> /etc/systemd/resolved.conf && \

# The demo user, not root. The Python that this script installs has to belong to the
# account that runs the later setup steps and the demos, and /root is not readable by it.
SETUP_USER="$(getent passwd 1000 | cut -d: -f1)"
echo "Setting up for user $SETUP_USER"

# update packages
apt update && \
apt -y upgrade

# install the Microsoft ODBC driver for SQL Server
# https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server
# This is the same package repository the sibling repository uses to install PowerShell.
# unixodbc-dev is needed in case pip has to build pyodbc from source instead of using a wheel.
apt-get install -y wget apt-transport-https software-properties-common && \
wget -q -O /tmp/packages-microsoft-prod.deb "https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/packages-microsoft-prod.deb" && \
dpkg -i /tmp/packages-microsoft-prod.deb && \
apt-get update && \
ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev

# install docker
# https://docs.docker.com/engine/install/ubuntu/
apt-get install -y ca-certificates curl gnupg2 lsb-release && \
mkdir -p /etc/apt/keyrings && \
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg && \
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list && \
apt update && \
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin && \
update-alternatives --set iptables /usr/sbin/iptables-legacy && \
service docker start
# As of April 2025, we need a restart so that docker can setup the network for the containers.
# But as we need a restart of the WSL2, we currently don't need this.
# service docker restart

# install 7zip
apt-get install -y p7zip-full

# install the build dependencies for pyenv
#Note, selecting 'libncurses-dev' instead of 'libncursesw5-dev'
#curl is already the newest version (8.5.0-2ubuntu10.9).
#git is already the newest version (1:2.43.0-1ubuntu7.3).
#git set to manually installed.
#xz-utils is already the newest version (5.6.1+really5.4.5-1ubuntu0.3).
#xz-utils set to manually installed.
apt-get install -y make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libncurses-dev tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev

# install pyenv and Python as the demo user
# pyenv compiles Python from source, so this step takes several minutes.
# The initialisation goes into ~/.profile and not only into ~/.bashrc, because ~/.bashrc
# returns immediately when it is not run interactively - which is exactly how the later
# setup steps are started. Without this, pyenv would not be on the PATH for any of them.
sudo -u "$SETUP_USER" -H bash <<'EOF'
set -e

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

if [ ! -d "$PYENV_ROOT" ]; then
    curl -fsSL https://pyenv.run | bash
fi

if ! grep -q PYENV_ROOT ~/.profile; then
    {
        echo ''
        echo 'export PYENV_ROOT="$HOME/.pyenv"'
        echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"'
        echo 'eval "$(pyenv init -)"'
    } >> ~/.profile
fi

eval "$(pyenv init -)"

pyenv install -s 3.14.6
pyenv global 3.14.6

python --version
EOF

# To pull and save the docker images:
# docker pull mcr.microsoft.com/mssql/server:2025-CU5-ubuntu-24.04
# docker save -o /mnt/c/tmp/DockerImages/SQLServer.tar mcr.microsoft.com/mssql/server:2025-CU5-ubuntu-24.04
# docker pull container-registry.oracle.com/database/express:21.3.0-xe
# docker save -o /mnt/c/tmp/DockerImages/Oracle.tar container-registry.oracle.com/database/express:21.3.0-xe

# Load docker images from files to save time and download data volume
if [ -f "/mnt/c/tmp/DockerImages/SQLServer.tar" ]; then
    if ! docker image inspect mcr.microsoft.com/mssql/server:2025-CU5-ubuntu-24.04 >/dev/null 2>&1; then
        echo "Loading docker image 2025-CU5-ubuntu-24.04 for SQL Server from file..."
        docker load -i /mnt/c/tmp/DockerImages/SQLServer.tar
        if ! docker image inspect mcr.microsoft.com/mssql/server:2025-CU5-ubuntu-24.04 >/dev/null 2>&1; then
            echo "Failed to load SQL Server image, exiting with error."
            exit 1
        fi
    else
        echo "SQL Server image already present, skipping load."
    fi
fi

if [ -f "/mnt/c/tmp/DockerImages/Oracle.tar" ]; then
    if ! docker image inspect container-registry.oracle.com/database/express:21.3.0-xe >/dev/null 2>&1; then
        echo "Loading docker image 21.3.0-xe for Oracle from file..."
        docker load -i /mnt/c/tmp/DockerImages/Oracle.tar
        if ! docker image inspect container-registry.oracle.com/database/express:21.3.0-xe >/dev/null 2>&1; then
            echo "Failed to load Oracle image, exiting with error."
            exit 1
        fi
    else
        echo "Oracle image already present, skipping load."
    fi
fi
