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
        print_color "1;31" "Unsupported OS. Please install required packages manually."
        exit 1
    fi
}

install_dependencies() {
    local pm=$(detect_package_manager)
    print_color "1;33" "▶ Installing system dependencies..."
    
    # Packages for Debian/Ubuntu based systems
    local debian_pkgs="python3 python3-pip curl build-essential python3-dev"
    # Packages for RHEL/CentOS/Fedora based systems
    local rhel_pkgs="python3 python3-pip curl python3-devel gcc make"

    case "$pm" in
        "apt-get")
            apt-get update > /dev/null 2>&1
            apt-get install -y $debian_pkgs > /dev/null 2>&1
            ;;
        "yum")
            yum install -y $rhel_pkgs > /dev/null 2>&1
            ;;
        "dnf")
            dnf install -y $rhel_pkgs > /dev/null 2>&1
            ;;
    esac
    print_color "1;32" "✔ Dependencies installed successfully."
}

# --- Main Script ---
check_root

print_color "1;34" "============================================"
print_color "1;32" "  HexBackup | Marzban Backup Tool Installer "
print_color "1;34" "============================================"
echo

# STEP 1: Install all required system packages, including build tools
install_dependencies
echo

# STEP 2: Create installation directory
print_color "1;33" "▶ Creating installation directory at ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"
print_color "1;32" "✔ Directory created."
echo

# STEP 3: Download the latest scripts
print_color "1;33" "▶ Downloading scripts from GitHub to ${INSTALL_DIR}..."
curl -sSL -o "${INSTALL_DIR}/${PANEL_SCRIPT_NAME}" "https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/${BRANCH}/${PANEL_SCRIPT_NAME}"
curl -sSL -o "${INSTALL_DIR}/${BOT_SCRIPT_NAME}" "https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/${BRANCH}/${BOT_SCRIPT_NAME}"
curl -sSL -o "${INSTALL_DIR}/${REQUIREMENTS_FILE}" "https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/${BRANCH}/${REQUIREMENTS_FILE}"
chmod +x "${INSTALL_DIR}"/*.py
print_color "1;32" "✔ Scripts downloaded."
echo

# STEP 4: Install Python libraries with flags for compatibility
print_color "1;33" "▶ Installing Python libraries from requirements.txt..."
python3 -m pip install -r "${INSTALL_DIR}/${REQUIREMENTS_FILE}" --break-system-packages --ignore-installed
print_color "1;32" "✔ Python libraries installed successfully."
echo

# STEP 5: Create the launcher command
print_color "1;33" "▶ Creating launcher command '${LAUNCHER_NAME}'..."
ln -sf "${INSTALL_DIR}/${PANEL_SCRIPT_NAME}" "/usr/local/bin/${LAUNCHER_NAME}"
chmod +x "/usr/local/bin/${LAUNCHER_NAME}"
print_color "1;32" "✔ Launcher command created."
echo

print_color "1;34" "============================================"
print_color "1;32" "✅ Installation is complete!"
print_color "1;37" "To start the configuration panel, run:"
print_color "1;36" "sudo ${LAUNCHER_NAME}"
print_color "1;34" "============================================"
