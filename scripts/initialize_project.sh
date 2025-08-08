#!/usr/bin/env bash
set -e

# ==== Paths ====
SCRIPTS_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
DEP_DIR=$(realpath "${SCRIPTS_DIR}/../dependencies")

# ==== sshpass: install only if missing ====
if command -v sshpass >/dev/null 2>&1; then
  echo "sshpass already installed."
else
  echo "Installing sshpass..."
  if [[ "$OSTYPE" == "darwin"* ]]; then
    if command -v brew >/dev/null 2>&1; then
      # sshpass isn't in Homebrew core; this tap works.
      brew list sshpass >/dev/null 2>&1 || brew install hudochenkov/sshpass/sshpass
    else
      echo "❌ Homebrew not found. Install brew or install sshpass manually." >&2
      exit 1
    fi
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y && sudo apt-get install -y sshpass
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf -y install sshpass
  elif command -v yum >/dev/null 2>&1; then
    sudo yum -y install sshpass
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper -n install sshpass
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm sshpass
  elif command -v apk >/dev/null 2>&1; then
    sudo apk add --no-cache sshpass
  else
    echo "❌ Unsupported system. Please install sshpass manually." >&2
    exit 1
  fi
fi


# ==== Pyenv, setup venv or create ====
if [[ "$(python --version 2>&1)" != Python\ 3.13.* ]]; then
  pyenv local 3.13.0
  echo "Running pyenv local 3.13.0"
fi

# ==== Python Req ====
echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing Python dependencies..."
python -m pip install -r "${DEP_DIR}/python_requirements.txt"

# ==== Ansible Req ===={
echo "Installing Ansible collections locally..."
export ANSIBLE_COLLECTIONS_PATHS="$(pwd)/.ansible/collections"
mkdir -p "$ANSIBLE_COLLECTIONS_PATHS"
ansible-galaxy collection install -r "${DEP_DIR}/ansible_requirements.yml"

echo "✅ Project initialized successfully."
