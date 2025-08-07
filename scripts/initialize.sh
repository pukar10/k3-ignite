#!/usr/bin/env bash
set -e

# Activate venv or create it if it doesn't exist
if [ ! -d .venv ]; then
  echo "Creating venv with Python 3.13.0..."
  pyenv local 3.13.0
  python -m venv .venv
fi

source .venv/bin/activate
echo "Using Python: $(python --version)"

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing Python dependencies..."
pip install -r ../dependencies/python-requirements.txt

echo "Installing Ansible collections locally..."
export ANSIBLE_COLLECTIONS_PATHS="$(pwd)/.ansible/collections"
mkdir -p "$ANSIBLE_COLLECTIONS_PATHS"
ansible-galaxy collection install -r ../dependencies/ansible-requirements.yml --force

echo "✅ Project initialized successfully."