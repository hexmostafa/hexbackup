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
SERVICE_NAME="marzban_bot.service"
LAUNCHER_NAME="hexbackup-panel"

# --- Functions ---
print_color() {
    COLOR=$1
    TEXT=$2
    # Check if stdout is a terminal
    if [ -t 1 ]; then
        echo -e "\e[${COLOR}m${TEXT}\e[0m"
    else
        echo "${TEXT}"
    fi
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        print_color "1;31" "خطا: این اسکریپت باید با دسترسی root اجرا شود. لطفاً از 'sudo' استفاده کنید."
        exit 1
    fi
}

detect_package_manager() {
    if command -v apt-get &> /dev/null; then
        echo "apt-get"
    elif command -v yum &> /dev/null; then
        echo "yum"
    elif command -v dnf &> /dev/null; then
        echo "dnf"
    else
        print_color "1;31" "سیستم عامل شما پشتیبانی نمی‌شود. لطفاً Python 3 و Pip را به صورت دستی نصب کنید."
        exit 1
    fi
}

install_dependencies() {
    local pm=$(detect_package_manager)
    print_color "1;33" "▶ در حال نصب نیازمندی‌های سیستم (python3, pip, curl) با استفاده از ${pm}..."
    case "$pm" in
        "apt-get")
            apt-get update > /dev/null 2>&1
            apt-get install -y python3 python3-pip curl > /dev/null 2>&1
            ;;
        "yum")
            yum install -y python3 python3-pip curl > /dev/null 2>&1
            ;;
        "dnf")
            dnf install -y python3 python3-pip curl > /dev/null 2>&1
            ;;
    esac
    print_color "1;32" "✔ نیازمندی‌ها با موفقیت نصب شدند."
}

get_file_url() {
    echo "https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/${BRANCH}/$1"
}

# --- Main Script ---
check_root

print_color "1;34" "============================================"
print_color "1;32" "  HexBackup | نصاب ابزار پشتیبان‌گیری مرزبان  "
print_color "1;34" "============================================"
echo

install_dependencies
echo

print_color "1;33" "▶ در حال ایجاد دایرکتوری نصب در ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"
print_color "1;32" "✔ دایرکتوری ایجاد شد."
echo

print_color "1;33" "▶ در حال دانلود اسکریپت‌ها از گیت‌هاب..."
curl -sSL -o "${INSTALL_DIR}/${PANEL_SCRIPT_NAME}" "$(get_file_url ${PANEL_SCRIPT_NAME})"
curl -sSL -o "${INSTALL_DIR}/${BOT_SCRIPT_NAME}" "$(get_file_url ${BOT_SCRIPT_NAME})"
curl -sSL -o "${INSTALL_DIR}/${REQUIREMENTS_FILE}" "$(get_file_url ${REQUIREMENTS_FILE})"
chmod +x "${INSTALL_DIR}"/*.py
print_color "1;32" "✔ اسکریپت‌ها دانلود شدند."
echo

print_color "1;33" "▶ در حال نصب کتابخانه‌های پایتون از requirements.txt..."
# This is a more robust way to install pip packages on modern systems
python3 -m pip install --upgrade pip > /dev/null 2>&1
python3 -m pip install -r "${INSTALL_DIR}/${REQUIREMENTS_FILE}"
print_color "1;32" "✔ کتابخانه‌های پایتون نصب شدند."
echo

print_color "1;33" "▶ در حال ایجاد سرویس systemd برای ربات تلگرام..."
cat << EOF > "/etc/systemd/system/${SERVICE_NAME}"
[Unit]
Description=HexBackup Telegram Bot for Marzban
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
# The bot will only start if config.json exists
ExecStartPre=/bin/bash -c 'while [ ! -f ${INSTALL_DIR}/config.json ]; do sleep 2; done'
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/${BOT_SCRIPT_NAME}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
print_color "1;32" "✔ سرویس ربات ایجاد شد. (توجه: سرویس تا زمان کانفیگ اولیه اجرا نخواهد شد)"
echo

print_color "1;33" "▶ در حال ایجاد دستور اجرای پنل با نام '${LAUNCHER_NAME}'..."
ln -sf "${INSTALL_DIR}/${PANEL_SCRIPT_NAME}" "/usr/local/bin/${LAUNCHER_NAME}"
chmod +x "/usr/local/bin/${LAUNCHER_NAME}"
print_color "1;32" "✔ دستور اجرای پنل ایجاد شد."
echo

print_color "1;34" "============================================"
print_color "1;32" "✅ نصب با موفقیت انجام شد!"
print_color "1;37" "برای شروع و انجام تنظیمات اولیه، دستور زیر را اجرا کنید:"
print_color "1;36" "sudo ${LAUNCHER_NAME}"
print_color "1;34" "============================================"
