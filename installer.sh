#!/bin/bash
set -e

# --- Configuration ---
GITHUB_USER="HEXMOSTAFA"
REPO_NAME="hexbackup"
BRANCH="main"

# --- Variables ---
INSTALL_DIR="/opt/hexbackup"
PANEL_SCRIPT_NAME="marzban_panel.py"
BOT_SCRIPT_NAME="marzban_bot.py"
REQUIREMENTS_FILE="requirements.txt"
LAUNCHER_NAME="hexbackup-panel"

# --- Functions ---
print_color() {
    COLOR=$1
    TEXT=$2
    if [ -t 1 ]; then
        echo -e "\e[${COLOR}m${TEXT}\e[0m"
    else
        echo "${TEXT}"
    fi
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        print_color "1;31" "Error: This script must be run as root. Please use 'sudo'."
        exit 1
    fi
}

detect_package_manager() {
    if command -v apt-get &> /dev/null; then echo "apt-get";
    elif command -v yum &> /dev/null; then echo "yum";
    elif command -v dnf &> /dev/null; then echo "dnf";
    else
        print_color "1;31" "Unsupported OS. Please install Python 3, Pip, and Curl manually."
        exit 1
    fi
}

install_dependencies() {
    local pm=$(detect_package_manager)
    print_color "1;33" "▶ Installing system dependencies (python3, pip, curl) using ${pm}..."
    case "$pm" in
        "apt-get")
            apt-get update > /dev/null 2>&1
            apt-get install -y python3 python3-pip curl > /dev/null 2>&1
            ;;
        *) # For yum and dnf
            $pm install -y python3 python3-pip curl > /dev/null 2>&1
            ;;
    esac
    print_color "1;32" "✔ Dependencies installed successfully."
}

get_file_url() {
    echo "https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/${BRANCH}/$1"
}

# --- Main Script ---
check_root

print_color "1;34" "============================================"
print_color "1;32" "  HexBackup | Marzban Backup Tool Installer "
print_color "1;34" "============================================"
echo

install_dependencies
echo

print_color "1;33" "▶ Creating installation directory at ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"
print_color "1;32" "✔ Directory created."
echo

print_color "1;33" "▶ Downloading scripts from GitHub to ${INSTALL_DIR}..."
curl -sSL -o "${INSTALL_DIR}/${PANEL_SCRIPT_NAME}" "$(get_file_url ${PANEL_SCRIPT_NAME})"
curl -sSL -o "${INSTALL_DIR}/${BOT_SCRIPT_NAME}" "$(get_file_url ${BOT_SCRIPT_NAME})"
curl -sSL -o "${INSTALL_DIR}/${REQUIREMENTS_FILE}" "$(get_file_url ${REQUIREMENTS_FILE})"
chmod +x "${INSTALL_DIR}"/*.py
print_color "1;32" "✔ Scripts downloaded."
echo

print_color "1;33" "▶ Installing Python libraries from requirements.txt..."
python3 -m pip install --upgrade pip > /dev/null 2>&1
python3 -m pip install -r "${INSTALL_DIR}/${REQUIREMENTS_FILE}"
print_color "1;32" "✔ Python libraries installed."
echo

print_color "1;33" "▶ Creating launcher command '${LAUNCHER_NAME}'..."
ln -sf "${INSTALL_DIR}/${PANEL_SCRIPT_NAME}" "/usr/local/bin/${LAUNCHER_NAME}"
chmod +x "/usr/local/bin/${LAUNCHER_NAME}"
print_color "1;32" "✔ Launcher command created."
echo

print_color "1;34" "============================================"
print_color "1;32" "✅ Environment setup is complete!"
print_color "1;37" "To configure the application, run the panel using:"
print_color "1;36" "sudo ${LAUNCHER_NAME}"
print_color "1;34" "============================================"
