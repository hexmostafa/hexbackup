#!/bin/bash
set -e

# --- Configuration ---
# !!! IMPORTANT: Change this to your GitHub username !!!
GITHUB_USER="HEXMOSTAFA"
REPO_NAME="hexbackup"
BRANCH="main"

# --- Variables ---
INSTALL_DIR="/opt/hexbackup"
PANEL_SCRIPT_NAME="marzban_panel.py"
BOT_SCRIPT_NAME="marzban_bot.py"
REQUIREMENTS_FILE="requirements.txt"
SERVICE_NAME="marzban_bot.service"
LAUNCHER_NAME="hexbackup-panel"
VENV_DIR="venv"

# --- Functions ---
print_color() {
    COLOR=$1
    TEXT=$2
    echo -e "\e[${COLOR}m${TEXT}\e[0m"
}

get_file_url() {
    echo "https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/${BRANCH}/$1"
}

# --- Main Script ---
if [ "$(id -u)" -ne 0 ]; then
    print_color "1;31" "Error: This script must be run as root. Please use 'sudo' or run as the root user."
    exit 1
fi

print_color "1;34" "============================================"
print_color "1;32" " HexBackup | Marzban Backup Tool Installer  "
print_color "1;34" "============================================"
echo

print_color "1;33" "▶ Installing dependencies (python3, pip, curl, venv)..."
apt-get update > /dev/null 2>&1
apt-get install -y python3 python3-pip python3-venv curl > /dev/null 2>&1
print_color "1;32" "✔ Dependencies installed."
echo

print_color "1;33" "▶ Creating installation directory ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"
print_color "1;32" "✔ Directory created."
echo

print_color "1;33" "▶ Downloading scripts from GitHub..."
curl -sSL -o "${INSTALL_DIR}/${PANEL_SCRIPT_NAME}" "$(get_file_url ${PANEL_SCRIPT_NAME})"
curl -sSL -o "${INSTALL_DIR}/${BOT_SCRIPT_NAME}" "$(get_file_url ${BOT_SCRIPT_NAME})"
curl -sSL -o "${INSTALL_DIR}/${REQUIREMENTS_FILE}" "$(get_file_url ${REQUIREMENTS_FILE})"
chmod +x "${INSTALL_DIR}"/*.py
print_color "1;32" "✔ Scripts downloaded."
echo

# --- CHANGE: Installing libraries in a virtual environment ---
print_color "1;33" "▶ Setting up Python virtual environment..."
python3 -m venv "${INSTALL_DIR}/${VENV_DIR}"
# Activate the virtual environment. Note: `source` is for interactive shells, but this works in a script.
source "${INSTALL_DIR}/${VENV_DIR}/bin/activate"

print_color "1;33" "▶ Installing Python libraries from requirements.txt..."
pip install -r "${INSTALL_DIR}/${REQUIREMENTS_FILE}"
# Deactivate the virtual environment after installation
deactivate
print_color "1;32" "✔ Python libraries installed in virtual environment."
echo

# --- Creating systemd service (updated ExecStart to use venv) ---
print_color "1;33" "▶ Creating systemd service for the Telegram bot..."
cat << EOF > "/etc/systemd/system/${SERVICE_NAME}"
[Unit]
Description=HexBackup Telegram Bot
After=network.target

[Service]
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/${VENV_DIR}/bin/python3 ${INSTALL_DIR}/${BOT_SCRIPT_NAME}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
print_color "1;32" "✔ Bot service created."
echo

# --- Creating launcher command (updated to use venv) ---
print_color "1;33" "▶ Creating launcher command '${LAUNCHER_NAME}'..."
cat << EOF > "/usr/local/bin/${LAUNCHER_NAME}"
#!/bin/bash
# Use the python executable from the virtual environment
"${INSTALL_DIR}/${VENV_DIR}/bin/python3" "${INSTALL_DIR}/${PANEL_SCRIPT_NAME}" "\$@"
EOF
chmod +x "/usr/local/bin/${LAUNCHER_NAME}"
print_color "1;32" "✔ Launcher created."
echo

print_color "1;34" "============================================"
print_color "1;32" "✅ Installation Complete!"
print_color "1;37" "Run the panel to start configuration:"
print_color "1;36" "sudo ${LAUNCHER_NAME}"
print_color "1;34" "============================================"
