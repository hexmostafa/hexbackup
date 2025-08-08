#!/usr/bin/env python3
# =================================================================
# Marzban Complete Backup & Restore Panel
# Creator: @HEXMOSTAFA
# Version: 4.4 (Database Connection Fix)
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

# --- Third-party Library Check ---
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.theme import Theme
except ImportError:
    print("FATAL ERROR: 'rich' library is not installed. Please run 'pip3 install rich' to continue.")
    sys.exit(1)

# --- Global Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
FILES_TO_BACKUP = ["/var/lib/marzban", "/opt/marzban"]
EXCLUDED_DATABASES = ['information_schema', 'mysql', 'performance_schema', 'sys']
EXCLUDED_DIRS_IN_VARLIB = ['mysql', 'logs'] 
CRON_JOB_IDENTIFIER = "# HEXMOSTAFA_MARZBAN_BACKUP_JOB"
MARZBAN_SERVICE_PATH = "/opt/marzban"
LOG_FILE = os.path.join(SCRIPT_DIR, "marzban_backup.log")
DB_BACKUP_DIR_NAME = "db_dumps"

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Rich Console Setup ---
custom_theme = Theme({
    "info": "cyan", "success": "bold green", "warning": "bold yellow",
    "danger": "bold red", "header": "bold white on blue", "menu": "bold yellow", "prompt": "bold magenta"
})
console = Console(theme=custom_theme)

# =================================================================
# HELPER FUNCTIONS
# =================================================================

def show_header():
    console.clear()
    header_text = Text("Marzban Complete Backup & Restore Panel\nCreator: @HEXMOSTAFA | Version 4.4", justify="center", style="header")
    console.print(Panel(header_text, style="blue", border_style="info"))
    console.print()

def show_main_menu() -> str:
    console.print(Panel(
        "[menu]1[/menu]. [bold]Create Full Backup[/bold]\n"
        "[menu]2[/menu]. [bold]Restore from Backup[/bold]\n"
        "[menu]3[/menu]. [bold]Setup Automated Backups (Cronjob)[/bold]\n"
        "[menu]4[/menu]. [bold]Exit[/bold]",
        title="Main Menu", title_align="left", border_style="info"
    ))
    return Prompt.ask("[prompt]Enter your choice[/prompt]", choices=["1", "2", "3", "4"], default="4")

def load_config_file() -> Optional[Dict[str, Any]]:
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        log_message("Invalid config file format. It will be recreated.", "danger")
        return None

def get_config(ask_telegram: bool = False, ask_database: bool = False, ask_interval: bool = False) -> Dict[str, Any]:
    config = load_config_file() or {"telegram": {}, "database": {}}
    
    if ask_telegram:
        console.print(Panel("Telegram Bot Credentials", style="info"))
        config["telegram"]['bot_token'] = Prompt.ask("[prompt]Enter your Telegram Bot Token[/prompt]", default=config.get("telegram", {}).get('bot_token'))
        config["telegram"]['admin_chat_id'] = Prompt.ask("[prompt]Enter your Admin Chat ID[/prompt]", default=config.get("telegram", {}).get('admin_chat_id'))
    if ask_database:
        if find_database_container():
            console.print(Panel("Database Credentials", style="info"))
            config.setdefault('database', {})
            config["database"]['user'] = Prompt.ask("[prompt]Enter the Database Username[/prompt]", default=config.get("database", {}).get('user', 'root'))
            config["database"]['password'] = Prompt.ask("[prompt]Enter the database password[/prompt]", password=True)
        else:
            log_message("No MySQL/MariaDB container found. Assuming SQLite. Skipping database credentials.", "warning")
            
    if ask_interval:
        config.setdefault('telegram', {})
        config["telegram"]['backup_interval'] = Prompt.ask("[prompt]Enter auto backup interval in minutes[/prompt]", default=config.get("telegram", {}).get('backup_interval', '60'))
    
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        if any([ask_telegram, ask_database, ask_interval]):
            console.print(f"[success]Settings saved to '{CONFIG_FILE}'[/success]")
    except Exception as e:
        console.print(f"[danger]Failed to save config file: {str(e)}[/danger]")
    return config

def log_message(message: str, style: str = "info"):
    if not sys.stdout.isatty():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    else:
        console.print(f"[{style}]{message}[/{style}]")
    logger.info(message)

def find_database_container() -> Optional[str]:
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
    if not os.path.isdir(MARZBAN_SERVICE_PATH):
        log_message("Marzban path not found. Is it installed?", "danger")
        return False
    command = f"cd {MARZBAN_SERVICE_PATH} && docker compose {action}"
    try:
        log_message(f"Running command: {command}", "info")
        subprocess.run(command, shell=True, check=True, capture_output=True, text=True, executable='/bin/bash')
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Command failed: {e.stderr}", "danger")
        return False
        
def download_from_telegram(tg_config: Dict[str, str], timeout: int = 120) -> Optional[str]:
    """Downloads a backup file from Telegram."""
    bot_token, chat_id = tg_config['bot_token'], tg_config['admin_chat_id']
    log_message(f"Please send the .tar.gz backup file to your bot now. Waiting for {timeout} seconds...", "info")
    start_time = time()
    offset = 0
    try:
        updates = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates?limit=1&timeout=5", timeout=10).json()
        if updates['ok'] and updates['result']:
            offset = updates['result'][0]['update_id'] + 1
    except requests.RequestException:
        pass

    while time() - start_time < timeout:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=10"
            updates = requests.get(url, timeout=15).json()
            if updates['ok'] and updates['result']:
                for update in updates['result']:
                    offset = update['update_id'] + 1
                    if 'message' in update and 'document' in update['message'] and str(update['message']['chat']['id']) == str(chat_id):
                        doc = update['message']['document']
                        if doc['file_name'].endswith('.tar.gz'):
                            log_message(f"Backup file '{doc['file_name']}' received.", "success")
                            file_id = doc['file_id']
                            with console.status("[info]Downloading file...", spinner="earth"):
                                file_info_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
                                file_info = requests.get(file_info_url, timeout=10).json()
                                if not file_info.get('ok'):
                                    log_message("Failed to get file info from Telegram.", "danger")
                                    return None
                                file_path_on_tg = file_info['result']['file_path']
                                download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path_on_tg}"
                                
                                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz", prefix="tg_backup_")
                                with requests.get(download_url, stream=True, timeout=300) as r:
                                    r.raise_for_status()
                                    shutil.copyfileobj(r.raw, temp_file)
                                temp_file.close()
                                log_message(f"File downloaded to: {temp_file.name}", "success")
                                return temp_file.name
            sleep(3)
        except requests.RequestException as e:
            log_message(f"Network error: {str(e)}. Retrying...", "warning")
            sleep(5)
    
    log_message("Timeout! No backup file was received.", "danger")
    return None

# =================================================================
# CORE LOGIC: BACKUP, RESTORE, CRONJOB
# =================================================================

def run_full_backup(config: Dict[str, Any], is_cron: bool = False):
    """Create a full backup of Marzban databases and files in .tar.gz format."""
    log_message("Starting full backup process...", "info")
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    
    backup_temp_dir = tempfile.mkdtemp(prefix="marzban_backup_")
    
    final_archive_path = f"/tmp/marzban_backup_{timestamp}.tar.gz"

    try:
        container_name = find_database_container()
        db_config = config.get('database', {})
        if container_name and db_config.get('user') and db_config.get('password'):
            log_message("Found database container. Backing up databases...", "info")
            try:
                db_backup_path = os.path.join(backup_temp_dir, DB_BACKUP_DIR_NAME)
                os.makedirs(db_backup_path)
                
                # Command to list all databases
                #  --- اصلاحیه: استفاده از نام کانتینر به جای localhost ---
                list_dbs_cmd = f"docker exec -i {container_name} mysql -u {db_config['user']} -p'{db_config['password']}' -e 'SHOW DATABASES;'"
                result = subprocess.run(list_dbs_cmd, shell=True, check=True, capture_output=True, text=True)
                databases = [db for db in result.stdout.strip().split('\n') if db not in EXCLUDED_DATABASES and db != 'Database']
                
                for db in databases:
                    log_message(f"Dumping database: {db}", "info")
                    #  --- اصلاحیه: استفاده از نام کانتینر به جای localhost ---
                    dump_cmd = f"docker exec -i {container_name} mysqldump -u{db_config['user']} -p'{db_config['password']}' --databases {db} > {os.path.join(db_backup_path, f'{db}.sql')}"
                    subprocess.run(dump_cmd, shell=True, check=True, executable='/bin/bash')
                log_message("Database backup complete.", "success")
            except subprocess.CalledProcessError as e:
                log_message(f"Database backup failed: {e.stderr}", "danger")
            except Exception as e:
                log_message(f"An unexpected error occurred during database backup: {e}", "danger")

        log_message("Backing up filesystem...", "info")
        
        fs_backup_path = os.path.join(backup_temp_dir, "filesystem")
        os.makedirs(fs_backup_path)

        def ignore_func(path, names):
            ignored_names = []
            if 'var' in path and 'lib' in path and 'marzban' in path:
                ignored_names.extend(EXCLUDED_DIRS_IN_VARLIB)
            
            ignored_names.extend(['__pycache__', '.env.example', '*.sock*'])
            
            return set(ignored_names).intersection(names)

        for path in FILES_TO_BACKUP:
            if os.path.exists(path):
                dest_path = os.path.join(fs_backup_path, os.path.relpath(path, '/'))
                if os.path.isdir(path):
                    shutil.copytree(path, dest_path, ignore=ignore_func, dirs_exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(path, dest_path)
                log_message(f"Backed up: {path}", "info")
        
        log_message("File backup complete.", "success")
        
        log_message("Compressing backup into .tar.gz file...", "info")
        with tarfile.open(final_archive_path, "w:gz") as tar:
            tar.add(backup_temp_dir, arcname=os.path.basename(backup_temp_dir))
        
        log_message(f"Backup created successfully: {final_archive_path}", "success")
        
        tg_config = config.get('telegram', {})
        if tg_config.get('bot_token') and tg_config.get('admin_chat_id'):
            log_message("Sending backup to Telegram...", "info")
            url = f"https://api.telegram.org/bot{tg_config['bot_token']}/sendDocument"
            caption = f"✅ Marzban Backup ({'Auto' if is_cron else 'Manual'})\n📅 {timestamp}"
            
            file_size = os.path.getsize(final_archive_path)
            if file_size > 50 * 1024 * 1024:
                 log_message("Warning: Backup file is larger than 50MB. It may fail to send to Telegram.", "warning")
            
            with open(final_archive_path, 'rb') as f:
                requests.post(url, data={'chat_id': tg_config['admin_chat_id'], 'caption': caption}, files={'document': f}, timeout=300).raise_for_status()
            log_message("Backup sent to Telegram!", "success")
        else:
            log_message("Telegram bot is not configured. Skipping upload.", "warning")

    except requests.exceptions.RequestException as e:
        log_message(f"Telegram upload failed: {e}", "danger")
    except Exception as e:
        log_message(f"A critical error occurred during backup: {e}", "danger")
    finally:
        log_message("Cleaning up temporary files...", "info")
        shutil.rmtree(backup_temp_dir, ignore_errors=True)
        if os.path.exists(final_archive_path):
            os.remove(final_archive_path)

def _restore_database_from_dump(container_name: str, db_config: Dict[str, str], db_dump_path: str) -> bool:
    """Handles the database restoration from a temporary directory."""
    try:
        sql_files = [f for f in os.listdir(db_dump_path) if f.endswith('.sql')]
        if not sql_files:
            log_message("No database dumps found to restore.", "warning")
            return True
            
        log_message("Restoring the following databases: " + ", ".join([f.replace('.sql', '') for f in sql_files]), "info")
        if not Confirm.ask("[danger]This will drop and recreate your existing databases. Continue?[/danger]"):
            log_message("Database restore cancelled by user.", "warning")
            return False

        for sql_file in sql_files:
            db = sql_file.replace('.sql', '')
            
            log_message(f"Dropping and recreating database: {db}", "info")
            # --- اصلاحیه: استفاده از نام کانتینر به جای localhost ---
            drop_cmd = f"docker exec -i {container_name} mysql -u{db_config['user']} -p'{db_config['password']}' -e 'DROP DATABASE IF EXISTS `{db}`; CREATE DATABASE `{db}`;'"
            subprocess.run(drop_cmd, shell=True, check=True, executable='/bin/bash')
            
            log_message(f"Importing data into database: {db}", "info")
            # --- اصلاحیه: استفاده از نام کانتینر به جای localhost ---
            import_cmd = f"docker exec -i {container_name} mysql -u{db_config['user']} -p'{db_config['password']}' {db} < {os.path.join(db_dump_path, sql_file)}"
            subprocess.run(import_cmd, shell=True, check=True, executable='/bin/bash')
        
        log_message("✅ Database restore completed successfully.", "success")
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Database restore failed. Error: {e.stderr}", "danger")
        return False
    except Exception as e:
        log_message(f"An unexpected error occurred during database restore: {e}", "danger")
        return False

def restore_flow():
    """Restores Marzban from a backup file."""
    show_header()
    console.print(Panel(
        "[bold]This is a destructive operation that will overwrite all Marzban data and databases.[/bold]\n"
        "It's highly recommended to have a separate backup before proceeding.",
        title="[warning]CRITICAL WARNING[/warning]", border_style="danger"
    ))
    
    if not Confirm.ask("[danger]Do you understand the risks and wish to continue?[/danger]"):
        log_message("Restore cancelled by user.", "warning")
        return
    
    config = get_config(ask_database=True)
    if not config.get('database'):
        log_message("Database credentials not provided. Cannot proceed with restore.", "danger")
        return
        
    archive_path = None
    console.print(Panel(
        "[menu]1[/menu]. Use a local backup file\n[menu]2[/menu]. Download backup from Telegram bot",
        title="Select Restore Source", border_style="info"
    ))
    choice = Prompt.ask("[prompt]Choose your method[/prompt]", choices=["1", "2"], default="1")
    
    if choice == "1":
        archive_path = Prompt.ask("[prompt]Enter the full path to your .tar.gz backup file[/prompt]")
        if not os.path.exists(archive_path):
            log_message(f"Error: The file '{archive_path}' was not found. Aborting.", "danger")
            return
    elif choice == "2":
        archive_path = download_from_telegram(config['telegram'])
        if not archive_path:
            log_message("Could not get backup from Telegram. Aborting.", "danger")
            return
    
    temp_dir = tempfile.TemporaryDirectory()
    try:
        with console.status("[info]Stopping all Marzban services...[/info]", spinner="dots"):
            if not run_marzban_command("down"):
                raise Exception("Could not stop Marzban services.")
        log_message("All Marzban services stopped.", "success")
        
        log_message(f"Extracting backup file '{archive_path}'...", "info")
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=temp_dir.name)
        log_message("Extraction completed successfully.", "success")
        
        extracted_dir = os.path.join(temp_dir.name, os.listdir(temp_dir.name)[0])
        
        log_message("Restoring Marzban configuration files...", "info")
        for path in FILES_TO_BACKUP:
            source_path = os.path.join(extracted_dir, os.path.relpath(path, '/'))
            if os.path.exists(source_path):
                if os.path.exists(path):
                    log_message(f"Removing existing directory: {path}", "warning")
                    shutil.rmtree(path)
                log_message(f"Copying files from {source_path} to {path}", "info")
                shutil.copytree(source_path, path)
        log_message("Filesystem restore completed successfully.", "success")

        container_name = find_database_container()
        if container_name:
            db_dump_path = os.path.join(extracted_dir, DB_BACKUP_DIR_NAME)
            if os.path.isdir(db_dump_path):
                if not _restore_database_from_dump(container_name, config['database'], db_dump_path):
                    log_message("Database restore failed. Aborting.", "danger")
                    return
            else:
                log_message("No database dumps found in backup. Skipping database restore.", "warning")

    except Exception as e:
        log_message(f"A critical error occurred during restore: {e}", "danger")
    finally:
        log_message("Cleaning up temporary files...", "info")
        temp_dir.cleanup()
        if archive_path and os.path.exists(archive_path) and choice == "2":
            os.remove(archive_path)
            
        log_message("Starting Marzban services...", "info")
        run_marzban_command("up -d")
        
        console.print(Panel("[bold green]✅ Restore process finished. Please check your Marzban panel.[/bold green]"))

def setup_cronjob_flow():
    """Setup or update cronjob for automated backups."""
    show_header()
    console.print(Panel("Setup/Update Automatic Backups", style="info"))
    config = get_config(ask_telegram=True, ask_database=True, ask_interval=True)
    
    interval = config.get("telegram", {}).get('backup_interval')
    if not interval or not interval.isdigit() or int(interval) <= 0:
        log_message("Invalid backup interval. Aborting.", "danger")
        return
        
    python_executable = sys.executable
    script_path = os.path.abspath(__file__)
    cron_command = f"*/{interval} * * * * {python_executable} {script_path} run-backup > /dev/null 2>&1"
    
    if not Confirm.ask(f"Add this to crontab?\n[info]{cron_command}[/info]"):
        log_message("Automatic setup cancelled.", "info")
        return False
        
    try:
        current_crontab = subprocess.run(['crontab', '-l'], capture_output=True, text=True, check=False).stdout
        new_lines = [line for line in current_crontab.splitlines() if CRON_JOB_IDENTIFIER not in line.strip()]
        new_lines.append(f"{cron_command} {CRON_JOB_IDENTIFIER}")
        
        p = Popen(['crontab', '-'], stdin=PIPE)
        p.communicate(input=("\n".join(new_lines) + "\n").encode())
        
        if p.returncode != 0: raise Exception("Crontab command failed.")
        
        log_message("✅ Crontab updated successfully!", "success")
        log_message("Performing an initial backup to test the configuration...", "info")
        run_full_backup(config, is_cron=True)
        return True
    except Exception as e:
        log_message(f"Error updating crontab: {str(e)}", "danger")
        return False

def main():
    """Main function to dispatch tasks or run interactively."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        logger.info(f"Running in Non-Interactive Mode, command: {command}")
        config = load_config_file()
        if not config: 
            log_message("Config file not found or invalid. Cannot run non-interactive commands.", "danger")
            sys.exit(1)
        if command == 'run-backup':
            try: run_full_backup(config, is_cron=True)
            except Exception: sys.exit(1)
        elif command == 'do-auto-backup-setup':
            sys.exit(0 if setup_cronjob_flow() else 1)
        sys.exit(0)

    if os.geteuid() != 0:
        log_message("This script requires root privileges. Please run with 'sudo'.", "danger")
        sys.exit(1)
        
    while True:
        show_header()
        choice = show_main_menu()
        
        if choice == "1":
            config = get_config(ask_telegram=True, ask_database=True)
            try:
                run_full_backup(config)
            except Exception:
                log_message("Backup failed.", "danger")
        elif choice == "2":
            restore_flow()
        elif choice == "3":
            setup_cronjob_flow()
        elif choice == "4":
            log_message("Goodbye!", "info")
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
