#!/bin/bash

# =================================================================
# HexBackup | Marzban Backup Tool Installer/Uninstaller
# Creator: @HEXMOSTAFA
# Version: 2.2.0 (Stable & Robust)
# =================================================================

set -e

INSTALL_DIR="/opt/hexbackup"
VENV_DIR="venv"
LAUNCHER_NAME="hexbackup-panel"
SERVICE_NAME="marzban_bot.service"
GITHUB_USER="HEXMOSTAFA"
REPO_NAME="hexbackup"
BRANCH="main"

C_RESET='\e[0m'
C_RED='\e[1;31m'
C_GREEN='\e[1;32m'
C_YELLOW='\e[1;33m'
C_BLUE='\e[1;34m'
C_CYAN='\e[1;36m'
C_WHITE='\e[1;37m'

print_msg() {
    local color=$1
    local text=$2
    if [ -t 1 ]; then
        echo -e "${color}${text}${C_RESET}"
    else
        echo "${text}"
    fi
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        print_msg "$C_RED" "❌ Error: This script must be run as root. Please use 'sudo'."
        exit 1
    fi
}

detect_package_manager() {
    if command -v apt-get &>/dev/null; then echo "apt";
    elif command -v dnf &>/dev/null; then echo "dnf";
    elif command -v yum &>/dev/null; then echo "yum";
    elif command -v pacman &>/dev/null; then echo "pacman";
    elif command -v zypper &>/dev/null; then echo "zypper";
    else
        print_msg "$C_RED" "❌ Unsupported OS."
        exit 1
    fi
}

install_dependencies() {
    local pm
    pm=$(detect_package_manager)
    print_msg "$C_YELLOW" "▶ Installing system dependencies..."
    
    local debian_pkgs="python3 python3-pip python3-venv curl build-essential python3-dev"
    local rhel_pkgs="python3 python3-pip python3-virtualenv curl python3-devel gcc make"
    local arch_pkgs="python python-pip python-virtualenv curl base-devel"
    local suse_pkgs="python3 python3-pip python3-virtualenv curl patterns-devel-base-devel_basis"

    case "$pm" in
        "apt") sudo apt-get update -qq && sudo apt-get install -y $debian_pkgs >/dev/null ;;
        "dnf") sudo dnf install -y $rhel_pkgs >/dev/null ;;
        "yum") sudo yum install -y $rhel_pkgs >/dev/null ;;
        "pacman") sudo pacman -Syu --noconfirm $arch_pkgs >/dev/null ;;
        "zypper") sudo zypper install -y $suse_pkgs >/dev/null ;;
    esac

    if ! command -v python3 &>/dev/null || ! command -v pip3 &>/dev/null; then
        print_msg "$C_RED" "❌ Dependency installation failed."
        exit 1
    fi

    print_msg "$C_GREEN" "✔ System dependencies installed."
}

uninstall() {
    print_msg "$C_YELLOW" "▶ Starting uninstallation..."
    if systemctl list-units --full -all | grep -q "${SERVICE_NAME}"; then
        print_msg "$C_YELLOW" "  - Stopping systemd service..."
        systemctl stop "$SERVICE_NAME" || true
        systemctl disable "$SERVICE_NAME" || true
        rm -f "/etc/systemd/system/${SERVICE_NAME}"
        systemctl daemon-reload
        print_msg "$C_GREEN" "  ✔ Service removed."
    fi
    if [ -f "/usr/local/bin/${LAUNCHER_NAME}" ]; then
        print_msg "$C_YELLOW" "  - Removing launcher command..."
        rm -f "/usr/local/bin/${LAUNCHER_NAME}"
        print_msg "$C_GREEN" "  ✔ Launcher removed."
    fi
    if [ -d "$INSTALL_DIR" ]; then
        print_msg "$C_YELLOW" "  - Removing installation directory..."
        rm -rf "$INSTALL_DIR"
        print_msg "$C_GREEN" "  ✔ Directory removed."
    fi
    print_msg "$C_GREEN" "✅ Uninstallation complete!"
}

install() {
    print_msg "$C_BLUE" "============================================"
    print_msg "$C_GREEN" "  HexBackup | Marzban Backup Tool Installer "
    print_msg "$C_BLUE" "============================================"
    echo
    if [ -d "$INSTALL_DIR" ] || [ -f "/usr/local/bin/${LAUNCHER_NAME}" ]; then
        print_msg "$C_YELLOW" "ℹ Previous installation detected. Running uninstaller first..."
        uninstall
        echo
    fi
    install_dependencies
    echo
    print_msg "$C_YELLOW" "▶ Creating installation directory at ${INSTALL_DIR}..."
    mkdir -p "$INSTALL_DIR"
    print_msg "$C_GREEN" "✔ Directory created."
    echo
    print_msg "$C_YELLOW" "▶ Downloading scripts and requirements from GitHub..."
    
    local files_to_download=("marzban_panel.py" "marzban_bot.py" "requirements.txt")
    for file in "${files_to_download[@]}"; do
        print_msg "$C_CYAN" "  - Downloading ${file}..."
        curl -sSL -o "${INSTALL_DIR}/${file}" "https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/${BRANCH}/${file}"
        if [ ! -s "${INSTALL_DIR}/${file}" ]; then
            print_msg "$C_RED" "❌ Failed to download ${file}."
            exit 1
        fi
    done

    chmod +x "${INSTALL_DIR}"/*.py
    print_msg "$C_GREEN" "✔ Scripts downloaded successfully."
    echo
    print_msg "$C_YELLOW" "▶ Setting up Python virtual environment..."
    python3 -m venv "${INSTALL_DIR}/${VENV_DIR}"
    if ! "${INSTALL_DIR}/${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/${REQUIREMENTS_FILE}"; then
        print_msg "$C_RED" "❌ Failed to install Python libraries."
        exit 1
    fi
    print_msg "$C_GREEN" "✔ Python libraries installed."
    echo
    print_msg "$C_YELLOW" "▶ Creating launcher command '${LAUNCHER_NAME}'..."
    cat << EOF > "/usr/local/bin/${LAUNCHER_NAME}"
#!/bin/bash
exec "${INSTALL_DIR}/${VENV_DIR}/bin/python3" "${INSTALL_DIR}/marzban_panel.py" "\$@"
EOF
    chmod +x "/usr/local/bin/${LAUNCHER_NAME}"
    print_msg "$C_GREEN" "✔ Launcher command created."
    echo
    print_msg "$C_BLUE" "============================================"
    print_msg "$C_GREEN" "✅ Installation is complete!"
    print_msg "$C_WHITE" "To start the configuration panel, just run:"
    print_msg "$C_CYAN" "    sudo ${LAUNCHER_NAME}"
    print_msg "$C_WHITE" "To uninstall the tool later, run:"
    print_msg "$C_CYAN" "    sudo /path/to/this/script.sh uninstall"
    print_msg "$C_BLUE" "============================================"
}

main() {
    check_root
    case "$1" in
        "uninstall")
            uninstall
            ;;
        *)
            install
            ;;
    esac
}

main "$@"
