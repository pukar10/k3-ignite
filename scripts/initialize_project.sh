#!/usr/bin/env bash
set -e

# ==== Paths ====
SCRIPTS_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
DEP_DIR=$(realpath "${SCRIPTS_DIR}/../dependencies")

# ==== Sshpass, install if not found ====
if command -v sshpass >/dev/null 2>&1; then
  echo "sshpass already installed."
fi
echo "sshpass not found; installing..."
if [[ "$OSTYPE" == "darwin"* ]]; then
  if command -v brew >/dev/null 2>&1; then
    # sshpass isn't in Homebrew core; this tap works.
    brew install hudochenkov/sshpass/sshpass
  else
    echo "❌ Homebrew not found. Install brew or install sshpass manually." >&2
    exit 1
  fi
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y && sudo apt-get install -y sshpass
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y sshpass
elif command -v yum >/dev/null 2>&1; then
  sudo yum install -y sshpass
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


# ==== Pyenv, setup venv or create ====
if [ ! -d .venv ]; then
  echo "Creating venv with Python 3.13.0..."
  pyenv local 3.13.0
  python -m venv .venv
fi
source .venv/bin/activate
echo "Using Python: $(python --version)"


# ==== Python Req ====
echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing Python dependencies..."
pip install -r "${DEP_DIR}/python_requirements.txt"

# ==== Ansible Req ===={
echo "Installing Ansible collections locally..."
export ANSIBLE_COLLECTIONS_PATHS="$(pwd)/.ansible/collections"
mkdir -p "$ANSIBLE_COLLECTIONS_PATHS"
ansible-galaxy collection install -r "${DEP_DIR}/ansible_requirements.yml"

echo "✅ Project initialized successfully."
