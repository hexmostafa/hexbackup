#!/usr/bin/env python3
# =================================================================
# Marzban Complete Backup & Restore Panel
# Creator: @HEXMOSTAFA
# Version: 4.2.0 (Final Optimized Version)
#
# Features:
# - tar.gz streaming for efficient backups.
# - Fully automated non-interactive mode for bots/cron.
# - Immediate backup after setting up a cronjob.
# - Robust helper commands for bot integration.
# =================================================================

import os
import sys
import subprocess
import json
import shutil
import tarfile
from time import sleep, time
from datetime import datetime
import requests
from subprocess import Popen, PIPE
import tempfile
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, Optional

# --- بررسی نصب بودن کتابخانه‌های مورد نیاز ---
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.theme import Theme
except ImportError:
    print("FATAL ERROR: 'rich' library is not installed. Please run 'pip3 install rich' to continue.")
    sys.exit(1)

# --- تنظیمات سراسری ---
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
FILES_TO_BACKUP = ["/var/lib/marzban", "/opt/marzban"]
EXCLUDED_DATABASES = ['information_schema', 'mysql', 'performance_schema', 'sys']
EXCLUDED_DIRS_IN_VARLIB = ['mysql', 'logs']
CRON_JOB_IDENTIFIER = "# HEXMOSTAFA_MARZBAN_BACKUP_JOB"
MARZBAN_SERVICE_PATH = "/opt/marzban"
LOG_FILE = os.path.join(SCRIPT_DIR, "marzban_backup.log")

# --- راه‌اندازی سیستم لاگ‌گیری ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- راه‌اندازی کنسول Rich ---
custom_theme = Theme({
    "info": "cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "danger": "bold red",
    "header": "bold white on blue",
    "menu": "bold yellow",
    "prompt": "bold magenta"
})
console = Console(theme=custom_theme)

# =================================================================
# توابع کمکی (HELPER FUNCTIONS)
# =================================================================

def show_header():
    """نمایش هدر برنامه در حالت تعاملی."""
    console.clear()
    header_text = Text("Marzban Complete Backup & Restore Panel\nCreator: @HEXMOSTAFA | Version 4.2.0", justify="center", style="header")
    console.print(Panel(header_text, style="blue", border_style="info"))
    console.print()

def show_main_menu() -> str:
    """نمایش منوی اصلی و دریافت انتخاب کاربر."""
    console.print(Panel(
        "[menu]1[/menu]. [bold]Create Full Backup[/bold]\n"
        "[menu]2[/menu]. [bold]Restore from Backup[/bold]\n"
        "[menu]3[/menu]. [bold]Setup Telegram Bot[/bold]\n"
        "[menu]4[/menu]. [bold]Setup Auto Backup (Cronjob)[/bold]\n"
        "[menu]5[/menu]. [bold]Exit[/bold]",
        title="Main Menu",
        title_align="left",
        border_style="info"
    ))
    return Prompt.ask("[prompt]Enter your choice[/prompt]", choices=["1", "2", "3", "4", "5"], default="5")

def load_config_file() -> Optional[Dict[str, Any]]:
    """خواندن فایل تنظیمات بدون تعامل با کاربر."""
    if not os.path.exists(CONFIG_FILE):
        logger.error("config.json not found.")
        return None
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error("config.json is corrupted.")
        return None

def get_config(ask_telegram: bool = False, ask_database: bool = False, ask_interval: bool = False) -> Dict[str, Any]:
    """دریافت و ذخیره اطلاعات تنظیمات به صورت تعاملی."""
    config = load_config_file() or {"telegram": {}, "database": {}}
    # ... (منطق کامل این تابع برای دریافت اطلاعات از کاربر)
    # (این بخش برای اختصار حذف شده چون تغییری نکرده است)
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        if any([ask_telegram, ask_database, ask_interval]):
            console.print(f"[success]Settings saved to '{CONFIG_FILE}'[/success]")
    except Exception as e:
        console.print(f"[danger]Failed to save config file: {str(e)}[/danger]")
    return config


def log_message(message: str, style: str = "info"):
    """لاگ کردن پیام هم در کنسول و هم در فایل."""
    if not sys.stdout.isatty():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    else:
        console.print(f"[{style}]{message}[/{style}]")
    logger.info(message)

def find_database_container() -> Optional[str]:
    """پیدا کردن کانتینر دیتابیس مربوط به مرزبان."""
    try:
        cmd = "docker ps --format '{{.Names}} {{.Image}}' | grep -E 'mysql|mariadb'"
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            if 'marzban' in line.lower():
                return line.split()[0]
        return None
    except subprocess.CalledProcessError:
        return None

def run_marzban_command(action: str) -> bool:
    """اجرای دستورات docker compose برای مرزبان."""
    if not os.path.isdir(MARZBAN_SERVICE_PATH):
        log_message(f"Marzban path '{MARZBAN_SERVICE_PATH}' not found.", "danger")
        return False
    command = f"cd {MARZBAN_SERVICE_PATH} && docker compose {action}"
    try:
        subprocess.run(command, shell=True, check=True, capture_output=True, text=True, executable='/bin/bash')
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Failed to run 'docker compose {action}': {e.stderr.strip()}", "danger")
        return False

# =================================================================
# منطق اصلی: بکاپ، ریستور، کرون‌جاب
# =================================================================

def run_full_backup(config: Dict[str, Any], is_cron: bool = False):
    """
    ایجاد بکاپ کامل با فرمت tar.gz و ارسال به تلگرام.
    این تابع داده‌ها را مستقیماً به آرشیو اضافه می‌کند تا بهینه باشد.
    """
    log_message("Starting full backup process...", "info")
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    
    with tempfile.NamedTemporaryFile(delete=False, prefix="marzban_backup_", suffix=".tar.gz") as archive_file:
        archive_filename = archive_file.name

    try:
        with tarfile.open(archive_filename, "w:gz") as tar:
            # --- بکاپ دیتابیس (در صورت وجود) ---
            container_name = find_database_container()
            if container_name and config.get('database'):
                log_message("Backing up databases...", "info")
                db_user = config['database']['user']
                db_pass = config['database']['password']
                list_dbs_cmd = f"docker exec -e MYSQL_PWD='{db_pass}' {container_name} mysql -u {db_user} -e 'SHOW DATABASES;'"
                process = subprocess.run(list_dbs_cmd, shell=True, check=True, capture_output=True, text=True)
                databases = [db for db in process.stdout.strip().split('\n')[1:] if db not in EXCLUDED_DATABASES]
                
                with tempfile.TemporaryDirectory() as db_temp_dir:
                    for db_name in databases:
                        sql_path = os.path.join(db_temp_dir, f"{db_name}.sql")
                        dump_cmd = f"docker exec -e MYSQL_PWD='{db_pass}' {container_name} mysqldump -u {db_user} --databases {db_name} > {sql_path}"
                        subprocess.run(dump_cmd, shell=True, check=True)
                        tar.add(sql_path, arcname=f"database/{db_name}.sql")
                    log_message(f"Successfully backed up databases: {', '.join(databases)}", "success")

            # --- بکاپ فایل‌های سیستمی ---
            log_message("Backing up configuration files...", "info")
            def exclude_filter(tarinfo: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
                """فیلتر برای حذف پوشه‌های مشخص از آرشیو."""
                path_parts = tarinfo.name.split(os.sep)
                if 'var' in path_parts and 'lib' in path_parts and 'marzban' in path_parts:
                    for part in path_parts:
                        if part in EXCLUDED_DIRS_IN_VARLIB:
                            return None
                return tarinfo

            for path in FILES_TO_BACKUP:
                if os.path.exists(path):
                    tar.add(path, arcname=path.lstrip('/'), filter=exclude_filter)

        log_message(f"Compression complete. File: {archive_filename}", "success")
        
        # --- آپلود در تلگرام ---
        tg_config = config.get('telegram', {})
        if not tg_config.get('bot_token'):
            log_message("Telegram not configured. Skipping upload.", "warning")
            return

        url = f"https://api.telegram.org/bot{tg_config['bot_token']}/sendDocument"
        caption = f"✅ Marzban Backup ({'Auto' if is_cron else 'Manual'})\n📅 {timestamp}"
        with open(archive_filename, 'rb') as f:
            requests.post(url, data={'chat_id': tg_config['admin_chat_id'], 'caption': caption}, files={'document': f}, timeout=300).raise_for_status()
        log_message("Backup successfully sent to Telegram!", "success")

    except Exception as e:
        log_message(f"A critical error occurred during backup: {str(e)}", "danger")
        logger.error("Backup failed", exc_info=True)
        raise
    finally:
        if os.path.exists(archive_filename):
            os.remove(archive_filename)

def run_restore_process(archive_path: str, config: Dict[str, Any]) -> bool:
    """منطق اصلی و غیرتعاملی برای ریستور کردن بکاپ."""
    # (این تابع برای اختصار حذف شده چون تغییری نکرده است)
    pass

def setup_cronjob_flow(interactive: bool = True) -> bool:
    """تنظیم کرون‌جاب. در حالت غیرتعاملی سوالی نمی‌پرسد و یک بکاپ اولیه می‌گیرد."""
    if interactive:
        show_header()
        console.print(Panel("Automatic Backup Setup (Cronjob)", style="info"))

    config = load_config_file()
    if not config or not config.get("telegram", {}).get('bot_token'):
        log_message("Telegram Bot is not configured.", "danger")
        return False
    
    if interactive:
        config = get_config(ask_interval=True, ask_database=True)
    
    interval = config.get("telegram", {}).get('backup_interval')
    if not interval or not interval.isdigit() or int(interval) <= 0:
        log_message("Backup interval is not set or invalid.", "danger")
        return False

    python_executable = sys.executable
    script_path = os.path.abspath(__file__)
    cron_command = f"*/{interval} * * * * {python_executable} {script_path} run-backup"
    
    if interactive:
        console.print(Panel(f"The command to be added to crontab:\n\n[info]{cron_command}[/info]", title="Cronjob Command"))
        if not Confirm.ask("[prompt]Do you authorize this action?[/prompt]"):
            return False
            
    try:
        current_crontab = subprocess.run(['crontab', '-l'], capture_output=True, text=True, check=False).stdout
        new_lines = [line for line in current_crontab.splitlines() if CRON_JOB_IDENTIFIER not in line]
        new_lines.append(f"{cron_command} {CRON_JOB_IDENTIFIER}")
        
        p = Popen(['crontab', '-'], stdin=PIPE)
        p.communicate(input=("\n".join(new_lines) + "\n").encode())
        
        if p.returncode != 0:
            raise Exception("The 'crontab' command failed.")

        log_message("✅ Crontab updated successfully!", "success")
        
        if not interactive:
            log_message("Cronjob set. Performing an initial backup as confirmation...", "info")
            try:
                run_full_backup(config, is_cron=True)
                log_message("Initial backup completed successfully.", "success")
            except Exception as e:
                log_message(f"Initial backup failed, but cronjob is set. Error: {e}", "warning")
        
        return True
    except Exception as e:
        log_message(f"A critical error occurred while updating crontab: {str(e)}", "danger")
        return False

def main():
    """تابع اصلی برای مدیریت دستورات تعاملی و غیرتعاملی."""
    # --- حالت غیرتعاملی (برای ربات و کرون‌جاب) ---
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'get-db-type':
            db_type = "SQLite" # Default
            if find_database_container():
                db_type = "MySQL"
            print(json.dumps({"database_type": db_type}))
            sys.exit(0)

        logger.info(f"Running in Non-Interactive Mode, command: {command}")
        
        config = load_config_file()
        if not config:
            sys.exit(1)

        if command in ['run-backup', 'do-backup']:
            try:
                run_full_backup(config, is_cron=(command == 'run-backup'))
                sys.exit(0)
            except Exception:
                sys.exit(1)
        
        elif command == 'do-restore':
            # ...
            sys.exit(1)

        elif command == 'do-auto-backup-setup':
            if setup_cronjob_flow(interactive=False):
                sys.exit(0)
            else:
                sys.exit(1)
        
        else:
            sys.exit(1)

    # --- حالت تعاملی (برای کاربر) ---
    if os.geteuid() != 0:
        log_message("This script requires root privileges. Please run it with 'sudo'.", "danger")
        sys.exit(1)
        
    while True:
        show_header()
        choice = show_main_menu()
        if choice == "1":
            config = get_config(ask_telegram=True, ask_database=True)
            try: run_full_backup(config)
            except Exception: log_message("Backup failed.", "danger")
        elif choice == "2":
            # restore_flow()
            pass
        elif choice == "3":
            # setup_bot_flow()
            pass
        elif choice == "4":
        
            setup_cronjob_flow()
        elif choice == "5":
            break
        Prompt.ask("\n[prompt]Press Enter to return to the main menu...[/prompt]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_message("\nApplication exited by user.", "warning")
        sys.exit(0)
    except Exception as e:
        log_message(f"An unexpected fatal error occurred: {str(e)}", "danger")
        logger.critical("Unexpected fatal error", exc_info=True)
        sys.exit(1)
