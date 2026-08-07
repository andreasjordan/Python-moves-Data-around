#!/bin/bash

set -e

# pyenv is initialised in ~/.profile by 02_wsl2_setup.sh, but this script may also be started
# without a login shell, so the PATH is set up here as well.
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

echo "Installing Python packages for $(python --version)"

# This is the pyenv Python, not the system Python that Ubuntu marks as externally managed,
# so a plain pip install is all it takes.
#
# requirements.txt and not a list here, because Windows installs the same packages from the same
# file - and the two lists used to be kept in step by hand, which failed twice.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "Finished"
