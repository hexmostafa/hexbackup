#!/usr/bin/env python3
# =================================================================
# HexBackup | Marzban Backup & Restore Panel - Finalized Version
# Creator: @HEXMOSTAFA
# Re-engineered & Optimized by AI Assistant
# Version: 15.2 (Immediate Backup on Cron Setup)
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
PATHS_TO_BACKUP = {
    "var_lib_marzban": Path("/var/lib/marzban"),
    "opt_marzban": Path("/opt/marzban")
}
DB_SERVICE_NAME = "mysql"
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
        logging.StreamHandler(sys.stdout)
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
    header_text = Text("HexBackup | Marzban Backup & Restore Panel\nCreator: @HEXMOSTAFA | Version 15.2", justify="center", style="header")
    console.print(Panel(header_text, style="blue", border_style="info"))
    console.print()

def show_main_menu() -> str:
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
    if not CONFIG_FILE.exists():
        return None
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        log_message("Invalid config file format. It will be recreated.", "danger")
        return None

def save_config_file(config: Dict[str, Any]):
    """Saves the provided config dictionary to the config file."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        log_message(f"Failed to save config file: {e}", "danger")

def find_dotenv_password() -> Optional[str]:
    if not DOTENV_PATH.exists():
        return None
    try:
        with open(DOTENV_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith(('MYSQL_ROOT_PASSWORD=', 'MARIADB_ROOT_PASSWORD=')):
                    return line.strip().split('=', 1)[1].strip()
            return None
    except Exception as e:
        log_message(f"Error reading .env file: {e}", "danger")
        return None

def find_database_container() -> Optional[str]:
    try:
        cmd = "docker ps -a --format '{{.Names}} {{.Image}}' | grep -E 'mysql|mariadb'"
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            if 'marzban' in line.lower():
                return line.split()[0]
        lines = result.stdout.strip().split('\n')
        if lines and lines[0]:
            return lines[0].split()[0]
        return None
    except subprocess.CalledProcessError:
        return None

def get_config(ask_telegram: bool = False, ask_database: bool = False, ask_interval: bool = False) -> Dict[str, Any]:
    config = load_config_file() or {"telegram": {}, "database": {}}
    if ask_telegram:
        console.print(Panel("Telegram Bot Credentials", style="info"))
        config["telegram"]['bot_token'] = Prompt.ask("[prompt]Enter your Telegram Bot Token[/prompt]", default=config.get("telegram", {}).get('bot_token'))
        config["telegram"]['admin_chat_id'] = Prompt.ask("[prompt]Enter your Admin Chat ID[/prompt]", default=config.get("telegram", {}).get('admin_chat_id'))
    if ask_database:
        console.print(Panel("Database Credentials", style="info"))
        config.setdefault('database', {})
        found_password = find_dotenv_password()
        if found_password:
            console.print(f"[info]Password found in .env file: [bold]...hidden...[/bold][/info]")
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
    if ask_interval:
        config.setdefault('telegram', {})
        config["telegram"]['backup_interval'] = Prompt.ask("[prompt]Enter auto backup interval in minutes[/prompt]", default=str(config.get("telegram", {}).get('backup_interval', '60')))

    save_config_file(config)
    if any([ask_telegram, ask_database, ask_interval]):
        console.print(f"[success]Settings saved to '{CONFIG_FILE}'[/success]")
    return config

def log_message(message: str, style: str = "info"):
    level = logging.INFO
    if style == "danger": level = logging.ERROR
    elif style == "warning": level = logging.WARNING
    logger.log(level, message)
    if sys.stdout.isatty():
        console.print(f"[{style}]{message}[/{style}]")
    else:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def run_marzban_command(action: str) -> bool:
    if not MARZBAN_SERVICE_PATH.is_dir():
        log_message("Marzban path not found. Is it installed?", "danger")
        return False
    command = f"cd {MARZBAN_SERVICE_PATH} && docker compose {action}"
    try:
        log_message(f"Running command: docker compose {action}", "info")
        subprocess.run(command, shell=True, check=True, capture_output=True, text=True, executable='/bin/bash')
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Command with 'docker compose' failed: {e.stderr}", "warning")
    command = f"cd {MARZBAN_SERVICE_PATH} && docker-compose {action}"
    try:
        log_message(f"Attempting command with 'docker-compose': docker-compose {action}", "info")
        subprocess.run(command, shell=True, check=True, capture_output=True, text=True, executable='/bin/bash')
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        stderr = getattr(e, 'stderr', str(e))
        log_message(f"Command with 'docker-compose' failed: {stderr}", "danger")
        return False
    return False

# =================================================================
# CORE LOGIC
# =================================================================

def run_full_backup(config: Dict[str, Any], is_cron: bool = False):
    log_message("Starting full backup process...", "info")
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    backup_temp_dir = Path(tempfile.mkdtemp(prefix="hexbackup_"))
    final_archive_path = Path(f"/root/marzban_backup_{timestamp}.tar.gz")
    final_archive_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        container_name = find_database_container()
        db_config = config.get('database', {})
        if container_name and db_config.get('user') and db_config.get('password'):
            log_message(f"Found database container '{container_name}'. Backing up databases...", "info")
            db_backup_path = backup_temp_dir / "db_dumps"
            db_backup_path.mkdir()
            try:
                list_dbs_cmd = f"docker exec -i {container_name} mysql -u{db_config['user']} -p'{db_config['password']}' -e 'SHOW DATABASES;'"
                result = subprocess.run(list_dbs_cmd, shell=True, check=True, capture_output=True, text=True)
                databases = [db for db in result.stdout.strip().split('\n') if db not in EXCLUDED_DATABASES and db != 'Database']
                for db in databases:
                    log_message(f"Dumping database: {db}", "info")
                    dump_cmd = f"docker exec -i {container_name} mysqldump -u{db_config['user']} -p'{db_config['password']}' --databases {db} > {str(db_backup_path / f'{db}.sql')}"
                    subprocess.run(dump_cmd, shell=True, check=True, executable='/bin/bash')
                log_message("Database backup complete.", "success")
            except subprocess.CalledProcessError as e:
                log_message(f"An unexpected error occurred during database backup: {e.stderr}", "danger")
                log_message("Hint: Is the database container running and password correct?", "warning")
        else:
            log_message("No database container found or credentials missing in config.json. Skipping database backup.", "warning")
        
        log_message("Backing up filesystem...", "info")
        fs_backup_path = backup_temp_dir / "filesystem"
        fs_backup_path.mkdir()
        for unique_name, path in PATHS_TO_BACKUP.items():
            if path.exists():
                log_message(f"Copying '{path}' to backup as '{unique_name}'", "info")
                destination = fs_backup_path / unique_name
                ignore_func = shutil.ignore_patterns('mysql', 'logs', '*.sock', '*.sock.lock')
                shutil.copytree(path, destination, dirs_exist_ok=True, ignore=ignore_func, symlinks=False)
            else:
                log_message(f"Warning: Path not found, skipping - {path}", "warning")
        
        log_message("File backup complete.", "success")
        log_message(f"Compressing backup into '{final_archive_path}'...", "info")
        with tarfile.open(final_archive_path, "w:gz") as tar:
            tar.add(str(backup_temp_dir), arcname=".")
        log_message(f"Backup created successfully: {final_archive_path}", "success")
        
        tg_config = config.get('telegram', {})
        if tg_config.get('bot_token') and tg_config.get('admin_chat_id'):
            log_message("Sending backup to Telegram...", "info")
            url = f"https://api.telegram.org/bot{tg_config['bot_token']}/sendDocument"
            caption = f"✅ Marzban Backup ({'Auto' if is_cron else 'Manual'})\n📅 {timestamp}"
            with open(final_archive_path, 'rb') as f:
                requests.post(url, data={'chat_id': tg_config['admin_chat_id'], 'caption': caption}, files={'document': f}, timeout=300).raise_for_status()
            log_message("Backup sent to Telegram!", "success")
    except Exception as e:
        log_message(f"A critical error occurred during backup: {e}", "danger")
        logger.exception("Backup process failed")
    finally:
        log_message("Cleaning up temporary files...", "info")
        shutil.rmtree(backup_temp_dir, ignore_errors=True)
        if is_cron and final_archive_path.exists():
            os.remove(final_archive_path)
            log_message("Removed local cron backup file.", "info")

def _perform_restore(archive_path: Path, config: Dict[str, Any]):
    temp_dir = Path(tempfile.mkdtemp(prefix="restore_"))
    try:
        log_message("Verifying and extracting backup file...", "info")
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=temp_dir)
        log_message("Backup extracted successfully.", "success")
        
        with console.status("[info]Stopping all Marzban services...[/info]", spinner="dots"):
            if not run_marzban_command("down"): raise Exception("Could not stop Marzban services.")
        log_message("All Marzban services stopped.", "success")
        
        fs_restore_path = temp_dir / "filesystem"
        if fs_restore_path.exists():
            log_message("Restoring configuration files...", "info")
            if (fs_restore_path / "opt_marzban").exists():
                shutil.copytree(fs_restore_path / "opt_marzban", MARZBAN_SERVICE_PATH, dirs_exist_ok=True)
                log_message(f"Restored '{MARZBAN_SERVICE_PATH}'.", "success")
            if (fs_restore_path / "var_lib_marzban").exists():
                shutil.copytree(fs_restore_path / "var_lib_marzban", Path("/var/lib/marzban"), dirs_exist_ok=True)
                log_message(f"Restored '/var/lib/marzban'.", "success")
        
        log_message("Reading database password from restored .env file...", "info")
        new_password = find_dotenv_password()
        if new_password:
            log_message("Password successfully read from backup. Updating current session.", "success")
            config['database']['password'] = new_password
            save_config_file(config)
            log_message("config.json has been updated with the correct password.", "success")
        else:
            log_message("Could not find password in restored .env file. Using password from config.json.", "warning")
            
        mysql_data_dir = Path("/var/lib/marzban/mysql")
        log_message(f"Clearing MySQL data directory ({mysql_data_dir}) for clean initialization...", "info")
        if mysql_data_dir.exists(): shutil.rmtree(mysql_data_dir)
        mysql_data_dir.mkdir(parents=True, exist_ok=True)
        
        with console.status("[info]Starting all Marzban services to initialize DB...[/info]", spinner="dots"):
            if not run_marzban_command("up -d"): raise Exception("Could not start Marzban services.")
        log_message("All Marzban services started.", "success")
        log_message("Waiting for MySQL service to stabilize (30 seconds)...", "info")
        sleep(30)
        
        db_restore_path = temp_dir / "db_dumps"
        sql_files = list(db_restore_path.glob("*.sql"))
        sql_file_to_restore = db_restore_path / "marzban.sql"
        if not sql_file_to_restore.exists() and sql_files:
            sql_file_to_restore = sql_files[0]

        if sql_file_to_restore.exists():
            container_name = find_database_container()
            db_user = config['database']['user']
            db_pass = config['database']['password']
            if not container_name: raise Exception("Could not find database container after restart.")
            
            db_name_to_restore = sql_file_to_restore.stem
            log_message(f"Importing data into database '{db_name_to_restore}'...", "info")
            restore_cmd = f"cat {sql_file_to_restore} | docker exec -i {container_name} mysql -u{db_user} -p'{db_pass}' {db_name_to_restore}"
            
            result = subprocess.run(restore_cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                log_message("Database imported successfully.", "success")
            else:
                raise Exception(f"Database import failed: {result.stderr}")
        else:
            log_message("No .sql file found in backup. Skipping database data import.", "warning")

        console.print(Panel("[bold green]✅ Restore process finished. Please check your Marzban panel.[/bold green]"))

    except Exception as e:
        log_message(f"A critical error occurred during restore: {e}", "danger")
        logger.exception("Restore process failed")
        log_message("Attempting to bring Marzban service back up as a safety measure...", "info")
        run_marzban_command("up -d")
    finally:
        log_message("Cleaning up temporary files...", "info")
        shutil.rmtree(temp_dir, ignore_errors=True)

def restore_flow():
    show_header()
    console.print(Panel("[bold]This is a destructive operation that will overwrite all Marzban data.", title="[warning]CRITICAL WARNING[/warning]", border_style="danger"))
    if not Confirm.ask("[danger]Do you understand the risks and wish to continue?[/danger]"):
        log_message("Restore cancelled by user.", "warning")
        return
    config = get_config(ask_database=True)
    if not config.get('database', {}).get('password'):
        log_message("Initial database credentials are required. Aborting.", "danger")
        return
    archive_path_str = Prompt.ask("[prompt]Enter the full path to your .tar.gz backup file[/prompt]")
    archive_path = Path(archive_path_str.strip())
    if not archive_path.is_file():
        log_message(f"Error: The file '{archive_path}' was not found. Aborting.", "danger")
        return
    _perform_restore(archive_path, config)

def setup_bot_flow():
    show_header()
    console.print(Panel("Telegram Bot Setup", style="info"))
    console.print("[info]For the bot to function correctly, it needs access to both Telegram and Database credentials.[/info]")
    
    config = get_config(ask_telegram=True, ask_database=True)
    
    if not all([config.get('telegram', {}).get('bot_token'), config.get('telegram', {}).get('admin_chat_id'), config.get('database', {}).get('password')]):
        log_message("Bot token, Admin Chat ID, and Database password are all required. Setup aborted.", "danger")
        return
        
    bot_script_path = SCRIPT_DIR / TG_BOT_FILE_NAME
    if not bot_script_path.exists():
        log_message(f"Bot script '{TG_BOT_FILE_NAME}' not found.", "danger")
        return
        
    try:
        log_message("Installing required Python libraries for the bot...", "info")
        venv_pip = SCRIPT_DIR / 'venv' / 'bin' / 'pip'
        pip_executable = str(venv_pip) if venv_pip.exists() else 'pip3'
        subprocess.check_call([pip_executable, "install", "--upgrade", "pyTelegramBotAPI", "aiohttp", "aiofiles"])
        
        service_file_path = Path("/etc/systemd/system/marzban_bot.service")
        venv_python = SCRIPT_DIR / 'venv' / 'bin' / 'python3'
        python_executable = str(venv_python) if venv_python.exists() else sys.executable

        service_content = f"""[Unit]
Description=HexBackup Telegram Bot for Marzban
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory={SCRIPT_DIR}
ExecStart={python_executable} {str(bot_script_path)}
Restart=always
[Install]
WantedBy=multi-user.target
"""
        with open(service_file_path, "w", encoding='utf-8') as f:
            f.write(service_content)
            
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        with console.status("[bold green]Activating Telegram bot service...[/bold green]"):
            subprocess.run(['systemctl', 'enable', '--now', 'marzban_bot.service'], check=True)
        sleep(3)
        
        result = subprocess.run(['systemctl', 'is-active', 'marzban_bot.service'], capture_output=True, text=True)
        if result.stdout.strip() == "active":
            console.print("[bold green]✅ Telegram bot service is running successfully.[/bold green]")
        else:
            console.print("[bold red]❌ The bot service failed to start. Check logs with 'journalctl -u marzban_bot'.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]❌ An unexpected error occurred: {e}[/bold red]")

def setup_cronjob_flow(interactive: bool = True):
    """Setup or update cronjob. Can be called interactively or by the bot."""
    if interactive:
        show_header()
        console.print(Panel("Automatic Backup Setup (Cronjob)", style="info"))

    config = load_config_file()
    if not all([config, config.get("telegram", {}).get('bot_token'), config.get("database", {}).get('password')]):
        log_message("Bot and Database are not fully configured. Please run 'Setup Telegram Bot' (Option 3) first.", "danger")
        return

    if interactive:
        config = get_config(ask_interval=True)

    interval = config.get("telegram", {}).get('backup_interval')
    if not interval or not str(interval).isdigit() or int(interval) <= 0:
        log_message("Invalid or missing backup interval in config.json. Cannot set up cronjob.", "danger")
        return

    venv_python = SCRIPT_DIR / 'venv' / 'bin' / 'python3'
    python_executable = str(venv_python) if venv_python.exists() else sys.executable
    script_path = Path(__file__).resolve()
    cron_command = f"*/{interval} * * * * {python_executable} {str(script_path)} run-backup > /dev/null 2>&1"
    
    if interactive:
        if not Confirm.ask(f"Add this to crontab?\n[info]{cron_command}[/info]"):
            log_message("Crontab setup cancelled.", "warning")
            return

    try:
        current_crontab = subprocess.run(['crontab', '-l'], capture_output=True, text=True, check=False).stdout
        new_lines = [line for line in current_crontab.splitlines() if CRON_JOB_IDENTIFIER not in line]
        
        if config.get("telegram", {}).get('backup_interval'):
            new_lines.append(f"{cron_command} {CRON_JOB_IDENTIFIER}")

        p = Popen(['crontab', '-'], stdin=PIPE)
        p.communicate(input=("\n".join(new_lines) + "\n").encode())
        if p.returncode != 0: raise Exception("Crontab command failed.")
        
        log_message("✅ Crontab updated successfully!", "success")
        print("Crontab updated successfully!")

        # <<< CHANGE START: Perform an initial backup after setting up the cron job >>>
        if interactive or not sys.stdout.isatty(): # Run if interactive or called by bot
            log_message("Performing an initial backup to test the new schedule...", "info")
            print("Performing an initial backup to test the new schedule...")
            run_full_backup(config, is_cron=False)
            log_message("Initial backup completed successfully.", "success")
        # <<< CHANGE END >>>

    except Exception as e:
        log_message(f"Error updating crontab: {str(e)}", "danger")

def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]
        config = load_config_file()
        if not config:
            log_message("Configuration file not found. Cannot run non-interactively.", "danger")
            sys.exit(1)
        if command == 'run-backup':
            run_full_backup(config, is_cron=True)
        elif command == 'do-restore':
            if len(sys.argv) > 2:
                archive_path = Path(sys.argv[2])
                if archive_path.is_file(): _perform_restore(archive_path, config)
                else: log_message(f"Backup file not found: {archive_path}", "danger"); sys.exit(1)
            else:
                log_message("Error: Restore command requires a file path argument.", "danger"); sys.exit(1)
        elif command == 'do-auto-backup-setup':
             setup_cronjob_flow(interactive=False)
        sys.exit(0)

    if os.geteuid() != 0:
        log_message("This script requires root privileges. Please run with 'sudo'.", "danger")
        sys.exit(1)
    
    while True:
        try:
            show_header()
            choice = show_main_menu()
            if choice == "1":
                config = get_config(ask_telegram=True, ask_database=True)
                run_full_backup(config)
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
        except (EOFError, TypeError) as e:
            log_message(f"A recoverable error occurred: {e}. Please try again.", "warning")
            Prompt.ask("\n[prompt]Press Enter to continue...[/prompt]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        log_message("Application exited by user.", "warning")
        sys.exit(0)
    except Exception as e:
        log_message(f"An unexpected fatal error occurred: {str(e)}", "danger")
        logger.critical("Unexpected fatal error", exc_info=True)
        sys.exit(1)
