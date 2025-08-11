#!/usr/bin/env python3
# =================================================================
# HexBackup | Marzban Backup & Restore Panel - Finalized Version
# Creator: @HEXMOSTAFA
# Re-engineered & Optimized by AI Assistant
# Version: 8.0 (Stable Backup & Restore Logic)
# =================================================================

import os
import sys
import subprocess
import json
import shutil
import tarfile
from time import sleep
from datetime import datetime
import requests
from subprocess import Popen, PIPE
import tempfile
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, Optional
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.theme import Theme
except ImportError:
    print("FATAL ERROR: 'rich' library is not installed. Please run 'pip3 install rich'.")
    sys.exit(1)

# --- Global Configuration ---
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
FILES_TO_BACKUP = [Path("/var/lib/marzban"), Path("/opt/marzban")]
EXCLUDED_DATABASES = ['information_schema', 'mysql', 'performance_schema', 'sys']
CRON_JOB_IDENTIFIER = "# HEXMOSTAFA_MARZBAN_BACKUP_JOB"
MARZBAN_SERVICE_PATH = Path("/opt/marzban")
LOG_FILE = SCRIPT_DIR / "marzban_backup.log"
TG_BOT_FILE_NAME = "marzban_bot.py"
DOTENV_PATH = MARZBAN_SERVICE_PATH / ".env"

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5),
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
    """Displays the script header."""
    console.clear()
    header_text = Text("HexBackup | Marzban Backup & Restore Panel\nCreator: @HEXMOSTAFA | Version 8.0", justify="center", style="header")
    console.print(Panel(header_text, style="blue", border_style="info"))
    console.print()

def show_main_menu() -> str:
    """Displays the main menu and gets user choice."""
    console.print(Panel(
        "[menu]1[/menu]. [bold]Create Full Backup[/bold]\n"
        "[menu]2[/menu]. [bold]Restore from Backup[/bold]\n"
        "[menu]3[/menu]. [bold]Setup Telegram Bot[/bold]\n"
        "[menu]4[/menu]. [bold]Setup Auto Backup (Cronjob)[/bold]\n"
        "[menu]5[/menu]. [bold]Exit[/bold]",
        title="Main Menu", title_align="left", border_style="info"
    ))
    return Prompt.ask("[prompt]Enter your choice[/prompt]", choices=["1", "2", "3", "4", "5"], default="5")

def load_config_file() -> Optional[Dict[str, Any]]:
    """Loads configuration from config.json."""
    if not CONFIG_FILE.exists():
        return None
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        log_message("Invalid config file format. It will be recreated.", "danger")
        return None

def find_dotenv_password() -> Optional[str]:
    """Tries to find the database password from the .env file."""
    if not DOTENV_PATH.exists():
        return None
    try:
        with open(DOTENV_PATH, 'r') as f:
            for line in f:
                if line.strip().startswith('MYSQL_ROOT_PASSWORD='):
                    return line.strip().split('=', 1)[1]
                if line.strip().startswith('MARIADB_ROOT_PASSWORD='):
                    return line.strip().split('=', 1)[1]
        return None
    except Exception as e:
        log_message(f"Error reading .env file: {e}", "danger")
        return None

def get_config(ask_telegram: bool = False, ask_database: bool = False, ask_interval: bool = False) -> Dict[str, Any]:
    """Prompts for user input and saves the configuration."""
    config = load_config_file() or {"telegram": {}, "database": {}}
    
    if ask_telegram:
        console.print(Panel("Telegram Bot Credentials", style="info"))
        config["telegram"]['bot_token'] = Prompt.ask("[prompt]Enter your Telegram Bot Token[/prompt]", default=config.get("telegram", {}).get('bot_token'))
        config["telegram"]['admin_chat_id'] = Prompt.ask("[prompt]Enter your Admin Chat ID[/prompt]", default=config.get("telegram", {}).get('admin_chat_id'))

    if ask_database:
        if find_database_container():
            console.print(Panel("Database Credentials", style="info"))
            config.setdefault('database', {})
            
            found_password = find_dotenv_password()
            if found_password:
                console.print(f"[info]Password found in .env file: [bold]{found_password}[/bold][/info]")
                if Confirm.ask("[prompt]Do you want to use this password?[/prompt]", default=True):
                    config["database"]['user'] = Prompt.ask("[prompt]Enter the Database Username[/prompt]", default=config.get("database", {}).get('user', 'root'))
                    config["database"]['password'] = found_password
                else:
                    config["database"]['user'] = Prompt.ask("[prompt]Enter the Database Username[/prompt]", default=config.get("database", {}).get('user', 'root'))
                    config["database"]['password'] = Prompt.ask("[prompt]Enter the database password[/prompt]", password=True)
            else:
                log_message("Could not find password in .env file. Please enter manually.", "warning")
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
    """Logs a message to the console and log file."""
    if not sys.stdout.isatty():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    else:
        console.print(f"[{style}]{message}[/{style}]")
    logger.info(message)

def find_database_container() -> Optional[str]:
    """Finds the name of the MySQL or MariaDB container."""
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
    """Runs a docker compose command in the Marzban directory."""
    if not MARZBAN_SERVICE_PATH.is_dir():
        log_message("Marzban path not found. Is it installed?", "danger")
        return False
    command = f"cd {MARZBAN_SERVICE_PATH} && docker-compose {action}"
    try:
        log_message(f"Running command: {command}", "info")
        subprocess.run(command, shell=True, check=True, capture_output=True, text=True, executable='/bin/bash')
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Command failed: {e.stderr}", "danger")
        return False

# =================================================================
# CORE LOGIC: BACKUP, RESTORE, CRONJOB, BOT SETUP
# =================================================================

def run_full_backup(config: Dict[str, Any], is_cron: bool = False):
    """Performs a full backup of Marzban panel."""
    log_message("Starting full backup process...", "info")
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    backup_temp_dir = Path(tempfile.mkdtemp(prefix="hexbackup_"))
    final_archive_path = Path(f"/tmp/marzban_backup_{timestamp}.tar.gz")

    try:
        container_name = find_database_container()
        db_config = config.get('database', {})
        if container_name and db_config.get('user') and db_config.get('password'):
            log_message("Found database container. Backing up databases...", "info")
            db_backup_path = backup_temp_dir / "db_dumps"
            db_backup_path.mkdir(parents=True, exist_ok=True)
            try:
                list_dbs_cmd = f"docker exec -i {container_name} mysql -u {db_config['user']} -p'{db_config['password']}' -e 'SHOW DATABASES;'"
                result = subprocess.run(list_dbs_cmd, shell=True, check=True, capture_output=True, text=True)
                databases = [db for db in result.stdout.strip().split('\n') if db not in EXCLUDED_DATABASES and db != 'Database']
                for db in databases:
                    log_message(f"Dumping database: {db}", "info")
                    dump_cmd = f"docker exec -i {container_name} mysqldump -u{db_config['user']} -p'{db_config['password']}' --databases {db} > {str(db_backup_path / f'{db}.sql')}"
                    subprocess.run(dump_cmd, shell=True, check=True, executable='/bin/bash')
                log_message("Database backup complete.", "success")
            except subprocess.CalledProcessError as e:
                log_message(f"Database backup failed: {e.stderr}", "danger")
            except Exception as e:
                log_message(f"An unexpected error occurred during database backup: {e}", "danger")
        else:
            log_message("No database container found or credentials missing. Skipping database backup.", "warning")

        log_message("Backing up filesystem...", "info")
        fs_backup_path = backup_temp_dir / "filesystem"
        fs_backup_path.mkdir(parents=True, exist_ok=True)
        
        # This function now correctly ignores the `mysql` directory entirely from /var/lib/marzban
        def ignore_func(path, names):
            if Path(path) == Path("/var/lib/marzban"):
                return ["mysql"]
            # To handle other exclusions
            ignored = ["__pycache__", ".env.example", "*.sock*", "logs"]
            return [name for name in names if any(pattern in name for pattern in ignored)]

        for path in FILES_TO_BACKUP:
            if path.exists():
                # Correctly copies the content of each folder to a new path in temp directory
                shutil.copytree(path, fs_backup_path / path.name, ignore=ignore_func, dirs_exist_ok=True)
                log_message(f"Backed up: {path}", "info")
            else:
                log_message(f"Warning: Path not found - {path}", "warning")
        
        log_message("File backup complete.", "success")
        log_message("Compressing backup into .tar.gz file...", "info")
        
        with tarfile.open(final_archive_path, "w:gz") as tar:
            if (backup_temp_dir / "db_dumps").is_dir():
                tar.add(backup_temp_dir / "db_dumps", arcname="db_dumps")
            if (backup_temp_dir / "filesystem").is_dir():
                tar.add(backup_temp_dir / "filesystem", arcname="filesystem")
        
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
        if final_archive_path.exists() and not is_cron:
            pass # Keep the file for manual use

def _restore_database_from_dump(container_name: str, db_config: Dict[str, str], db_dump_path: Path) -> bool:
    """Restores databases from SQL dump files."""
    try:
        sql_files = [f for f in db_dump_path.iterdir() if f.suffix == '.sql']
        if not sql_files:
            log_message("No database dumps found to restore.", "warning")
            return True
        log_message("Restoring the following databases: " + ", ".join([f.stem for f in sql_files]), "info")
        if not Confirm.ask("[danger]This will drop and recreate your existing databases. Continue?[/danger]"):
            log_message("Database restore cancelled by user.", "warning")
            return False

        for sql_file in sql_files:
            db = sql_file.stem
            log_message(f"Dropping and recreating database: {db}", "info")
            drop_cmd = f"docker exec -i {container_name} mysql -u{db_config['user']} -p'{db_config['password']}' -e 'DROP DATABASE IF EXISTS `{db}`; CREATE DATABASE `{db}`;'"
            subprocess.run(drop_cmd, shell=True, check=True, executable='/bin/bash')
            log_message(f"Importing data into database: {db}", "info")
            import_cmd = f"docker exec -i {container_name} mysql -u{db_config['user']} -p'{db_config['password']}' {db} < {str(sql_file)}"
            subprocess.run(import_cmd, shell=True, check=True, executable='/bin/bash')
        log_message("✅ Database restore completed successfully.", "success")
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Database restore failed. Error: {e.stderr}", "danger")
        return False
    except Exception as e:
        log_message(f"An unexpected error occurred during database restore: {e}", "danger")
        return False

def _perform_restore(archive_path: Path, config: Dict[str, Any]):
    """Main logic for the restore process."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        with console.status("[info]Stopping all Marzban services...[/info]", spinner="dots"):
            if not run_marzban_command("down"):
                raise Exception("Could not stop Marzban services.")
        log_message("All Marzban services stopped.", "success")
        
        log_message(f"Extracting backup file '{archive_path}'...", "info")
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=temp_dir)
        log_message("Extraction completed successfully.", "success")
        
        log_message("Restoring Marzban configuration files...", "info")
        db_dump_path = temp_dir / "db_dumps"
        fs_restore_path = temp_dir / "filesystem"

        if fs_restore_path.exists():
            for path in FILES_TO_BACKUP:
                source_path = fs_restore_path / path.name
                if source_path.exists():
                    if path.exists():
                        log_message(f"Removing existing directory: {path}", "warning")
                        shutil.rmtree(path)
                    log_message(f"Copying files from {source_path} to {path}", "info")
                    shutil.copytree(source_path, path)
            log_message("Filesystem restore completed successfully.", "success")
        else:
            log_message("Filesystem data not found in backup. Skipping filesystem restore.", "warning")

        container_name = find_database_container()
        if container_name:
            if db_dump_path.is_dir():
                if not _restore_database_from_dump(container_name, config['database'], db_dump_path):
                    log_message("Database restore failed. Aborting.", "danger")
                    return
            else:
                log_message("No database dumps found in backup. Skipping database restore.", "warning")
        else:
            log_message("No database container found. Skipping database restore.", "warning")

    except Exception as e:
        log_message(f"A critical error occurred during restore: {e}", "danger")
    finally:
        log_message("Cleaning up temporary files...", "info")
        shutil.rmtree(temp_dir, ignore_errors=True)
        log_message("Starting Marzban services...", "info")
        run_marzban_command("up -d")
        console.print(Panel("[bold green]✅ Restore process finished. Please check your Marzban panel.[/bold green]"))

def restore_flow():
    """Interactive flow for restoring a backup."""
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
    archive_path_str = Prompt.ask("[prompt]Enter the full path to your .tar.gz backup file[/prompt]")
    archive_path = Path(archive_path_str)
    if not archive_path.exists():
        log_message(f"Error: The file '{archive_path}' was not found. Aborting.", "danger")
        return
    _perform_restore(archive_path, config)

def setup_bot_flow():
    """Interactive flow for setting up the Telegram bot."""
    show_header()
    console.print(Panel("Telegram Bot Setup", style="info"))
    config = get_config(ask_telegram=True)
    if not config.get('telegram', {}).get('bot_token'):
        log_message("Bot token is required to set up the bot.", "danger")
        return
    
    bot_script_path = SCRIPT_DIR / TG_BOT_FILE_NAME
    if not bot_script_path.exists():
        log_message(f"Bot script '{TG_BOT_FILE_NAME}' not found. Please ensure the installation script has run successfully.", "danger")
        return
    
    try:
        log_message("Checking and installing required Python libraries...", "info")
        venv_pip = SCRIPT_DIR / 'venv' / 'bin' / 'pip'
        subprocess.check_call([str(venv_pip), "install", "pyTelegramBotAPI"])
        log_message("Libraries installed successfully. Continuing setup...", "success")

        service_file_path = Path("/etc/systemd/system/marzban_bot.service")
        service_content = f"""[Unit]
Description=HexBackup Telegram Bot for Marzban
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory={SCRIPT_DIR}
ExecStart={str(SCRIPT_DIR / 'venv' / 'bin' / 'python3')} {str(bot_script_path)}
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
"""
        with open(service_file_path, "w") as f:
            f.write(service_content)

        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        with console.status("[bold green]Activating Telegram bot service...[/bold green]"):
            subprocess.run(['systemctl', 'enable', '--now', 'marzban_bot.service'], check=True, capture_output=True, text=True)
        sleep(3)
        result = subprocess.run(['systemctl', 'is-active', 'marzban_bot.service'], capture_output=True, text=True)
        if result.stdout.strip() == "active":
            console.print("[bold green]✅ Telegram bot service is running successfully.[/bold green]")
        else:
            console.print("[bold red]❌ The bot service failed to start. Check logs with 'sudo journalctl -u marzban_bot.service'.[/bold red]")
    except subprocess.CalledProcessError as e:
        log_message(f"Failed to install required Python libraries or start service: {e}", "danger")
    except Exception as e:
        console.print(f"[bold red]❌ An unexpected error occurred: {e}[/bold red]")

def setup_cronjob_flow(interactive: bool = True) -> bool:
    """Interactive or automatic flow for setting up the cronjob."""
    if interactive:
        show_header()
        console.print(Panel("Automatic Backup Setup (Cronjob)", style="info"))
    config = load_config_file()
    if not config or not config.get("telegram", {}).get('bot_token'):
        log_message("Telegram Bot is not configured. Please set up the bot first.", "danger")
        return False
    if interactive:
        config = get_config(ask_interval=True, ask_database=True)
    interval = config.get("telegram", {}).get('backup_interval')
    if not interval or not str(interval).isdigit() or int(interval) <= 0:
        log_message("Invalid backup interval. Please provide a positive number.", "danger")
        return False
    
    python_executable = SCRIPT_DIR / 'venv' / 'bin' / 'python3'
    script_path = SCRIPT_DIR / Path(__file__).name
    cron_command = f"*/{interval} * * * * {str(python_executable)} {str(script_path)} run-backup > /dev/null 2>&1"
    
    if interactive:
        if not Confirm.ask(f"Add this to crontab?\n[info]{cron_command}[/info]"):
            log_message("Crontab setup cancelled by user.", "warning")
            return False
    try:
        current_crontab = subprocess.run(['crontab', '-l'], capture_output=True, text=True, check=False).stdout
        new_lines = [line for line in current_crontab.splitlines() if CRON_JOB_IDENTIFIER not in line]
        new_lines.append(f"{cron_command} {CRON_JOB_IDENTIFIER}")
        
        p = Popen(['crontab', '-'], stdin=PIPE)
        p.communicate(input=("\n".join(new_lines) + "\n").encode())
        if p.returncode != 0: raise Exception("Crontab command failed.")
        
        log_message("✅ Crontab updated successfully!", "success")
        if not interactive:
            log_message("Performing initial backup...", "info")
            run_full_backup(config, is_cron=True)
        return True
    except Exception as e:
        log_message(f"Error updating crontab: {str(e)}", "danger")
        return False

def main():
    """Main function to handle script execution."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        config = load_config_file()
        if not config: sys.exit(1)
        if command == 'run-backup':
            try: run_full_backup(config, is_cron=True)
            except Exception: sys.exit(1)
        elif command == 'do-restore':
            if len(sys.argv) > 2:
                archive_path = Path(sys.argv[2])
                try: _perform_restore(archive_path, config)
                except Exception: sys.exit(1)
            else:
                log_message("Error: Restore command requires a file path.", "danger")
                sys.exit(1)
        elif command == 'do-auto-backup-setup':
            sys.exit(0 if setup_cronjob_flow(interactive=False) else 1)
        sys.exit(0)

    if os.geteuid() != 0:
        log_message("This script requires root privileges. Please run with 'sudo'.", "danger")
        sys.exit(1)
    
    while True:
        show_header()
        choice = show_main_menu()
        if choice == "1":
            config = get_config(ask_telegram=True, ask_database=True)
            try: run_full_backup(config)
            except Exception: log_message("Backup failed.", "danger")
        elif choice == "2":
            restore_flow()
        elif choice == "3":
            setup_bot_flow()
        elif choice == "4":
            setup_cronjob_flow()
        elif choice == "5":
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
