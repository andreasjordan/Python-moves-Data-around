#!/bin/bash

set -e

# pyenv is initialised in ~/.profile by 02_wsl2_setup.sh, but this script may also be started
# without a login shell, so the PATH is set up here as well.
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

# The same two helpers as 02_wsl2_setup.sh, for the same reason. pip writes a "Collecting" and a
# "Downloading" line per package and a progress bar for each wheel - about sixty lines for this
# requirements file - and none of it is read unless something fails.
step() {
    echo ""
    echo "--> [$(date +%H:%M:%S)] $*"
}

# stdout goes to /dev/null and stderr does not, so a version conflict, a missing wheel or a build
# failure still explains itself and "set -e" still stops the script.
#
# The cost of this is the "Successfully installed ..." line, which was the only record of what the
# resolver actually picked. requirements.txt is deliberately unpinned, so that record was never
# reproducible anyway - and 00_check_host.ps1 prints the versions on the Windows side.
pip_install() {
    python -m pip install --quiet "$@" >/dev/null
}

echo "Installing Python packages for $(python --version)"

# This is the pyenv Python, not the system Python that Ubuntu marks as externally managed,
# so a plain pip install is all it takes.
step "Upgrading pip"
pip_install --upgrade pip

# requirements.txt and not a list here, because Windows installs the same packages from the same
# file - and the two lists used to be kept in step by hand, which failed twice.
step "Installing the packages from requirements.txt"
pip_install -r requirements.txt

echo ""
echo "Finished"
