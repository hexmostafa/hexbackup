#!/usr/bin/env python3
# =================================================================
# Marzban Complete Backup & Restore Panel
# Creator: @HEXMOSTAFA
# Version: 4.1.0 (Optimized with tar.gz streaming)
#
# A single, robust script for both interactive management
# and automated/bot-driven backups & restores.
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
CONTAINER_NAME = "marzban-mysql-1"  # Default container name
FILES_TO_BACKUP = ["/var/lib/marzban", "/opt/marzban"]
EXCLUDED_DATABASES = ['information_schema', 'mysql', 'performance_schema', 'sys']
# Directories to exclude within /var/lib/marzban
EXCLUDED_DIRS_IN_VARLIB = ['mysql', 'logs']
CRON_JOB_IDENTIFIER = "# HEXMOSTAFA_MARZBAN_BACKUP_JOB"
MARZBAN_SERVICE_PATH = "/opt/marzban"
LOG_FILE = os.path.join(SCRIPT_DIR, "marzban_backup.log")

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
# HELPER FUNCTIONS
# =================================================================

def show_header():
    console.clear()
    header_text = Text("Marzban Complete Backup & Restore Panel\nCreator: @HEXMOSTAFA | Version 4.1.0 (tar.gz Edition)", justify="center", style="header")
    console.print(Panel(header_text, style="blue", border_style="info"))
    console.print()

def show_main_menu() -> str:
    """Displays the main menu with 5 options."""
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
    """Loads config from file without interaction."""
    if not os.path.exists(CONFIG_FILE):
        logger.error("config.json not found. Please run the script interactively first to create it.")
        return None
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error("config.json is corrupted.")
        return None

def get_config(ask_telegram: bool = False, ask_database: bool = False, ask_interval: bool = False) -> Dict[str, Any]:
    """
    A modular function to get specific parts of the configuration.
    It loads existing config, asks for new info, and saves it back.
    """
    config = load_config_file() or {"telegram": {}, "database": {}}

    if ask_telegram:
        console.print(Panel("Telegram Bot Credentials", style="info"))
        config["telegram"]['bot_token'] = Prompt.ask(
            "[prompt]Enter your Telegram Bot Token[/prompt]", default=config.get("telegram", {}).get('bot_token')
        )
        config["telegram"]['admin_chat_id'] = Prompt.ask(
            "[prompt]Enter your Admin Chat ID[/prompt]", default=config.get("telegram", {}).get('admin_chat_id')
        )

    if ask_database:
        if find_database_container():
            console.print(Panel("Database Credentials", style="info"))
            config.setdefault('database', {})
            config["database"]['user'] = Prompt.ask(
                "[prompt]Enter the Database Username[/prompt]", default=config.get("database", {}).get('user', 'root')
            )
            config["database"]['password'] = Prompt.ask("[prompt]Enter the database password[/prompt]", password=True)
        else:
            log_message("No database detected, skipping database credential setup.", "warning")
            config['database'] = {}
            
    if ask_interval:
        config.setdefault('telegram', {})
        config["telegram"]['backup_interval'] = Prompt.ask(
            "[prompt]Enter automatic backup interval in minutes (e.g., 60)[/prompt]",
            default=config.get("telegram", {}).get('backup_interval', '60')
        )
        
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        if any([ask_telegram, ask_database, ask_interval]):
            console.print(f"[success]Settings saved to '{CONFIG_FILE}'[/success]")
    except Exception as e:
        console.print(f"[danger]Failed to save config file: {str(e)}[/danger]")
        
    return config

def setup_bot_flow():
    """A dedicated flow for setting up the Telegram Bot."""
    show_header()
    console.print(Panel("Telegram Bot Setup", style="info"))
    console.print("This process will configure your bot and create a background service to run it permanently.")
    get_config(ask_telegram=True, ask_database=True)
    log_message("Configuration information saved successfully.", "success")
    console.print()

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        bot_script_path = os.path.join(script_dir, "marzban_bot.py")
        python_executable = sys.executable
        service_file_path = "/etc/systemd/system/marzban_bot.service"
        log_message(f"Creating systemd service file at {service_file_path}...", "info")

        service_content = f"""[Unit]
Description=HexBackup Telegram Bot for Marzban
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={script_dir}
ExecStart={python_executable} {bot_script_path}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
        with open(service_file_path, "w") as f:
            f.write(service_content)

        log_message("Service file created. Reloading systemd daemon...", "info")
        subprocess.run(['systemctl', 'daemon-reload'], check=True)

        with console.status("[bold green]Activating Telegram bot service...[/bold green]"):
            subprocess.run(['systemctl', 'enable', '--now', 'marzban_bot.service'], check=True, capture_output=True, text=True)
            sleep(3)

        result = subprocess.run(['systemctl', 'is-active', 'marzban_bot.service'], capture_output=True, text=True)
        if result.stdout.strip() == "active":
            console.print("[bold green]✅ Telegram bot service is now running successfully.[/bold green]")
        else:
            console.print("[bold red]❌ The bot service failed to start. Check logs.[/bold red]")
            status_result = subprocess.run(['systemctl', 'status', 'marzban_bot.service'], capture_output=True, text=True)
            console.print(Panel(status_result.stderr or status_result.stdout, title="[danger]Systemctl Status Output[/danger]"))

    except PermissionError:
        console.print(f"[danger]Error: Permission denied. Could not write to {service_file_path}. Please run with 'sudo'.[/danger]")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]❌ Failed to execute a system command: {e.stderr.strip()}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]❌ An unexpected error occurred: {e}[/bold red]")


def log_message(message: str, style: str = "info"):
    """Log a message to console and file."""
    if not sys.stdout.isatty():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    else:
        console.print(f"[{style}]{message}[/{style}]")
    logger.info(message)


def find_database_container() -> Optional[str]:
    """Find the MySQL/MariaDB container for Marzban. Returns name or None."""
    log_message("Searching for a Marzban-related database container...", "info")
    try:
        cmd = "docker ps --format '{{.Names}} {{.Image}}' | grep -E 'mysql|mariadb'"
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            if 'marzban' in line.lower():
                container_name = line.split()[0]
                log_message(f"Detected database container: {container_name}", "success")
                return container_name
        return None
    except subprocess.CalledProcessError:
        log_message("No active Marzban database container found.", "warning")
        return None

def run_marzban_command(action: str) -> bool:
    """Run a docker compose command for Marzban."""
    if not os.path.isdir(MARZBAN_SERVICE_PATH):
        log_message(f"Marzban path '{MARZBAN_SERVICE_PATH}' not found.", "danger")
        return False
    command = f"cd {MARZBAN_SERVICE_PATH} && docker compose {action}"
    try:
        subprocess.run(command, shell=True, check=True, capture_output=True, text=True, executable='/bin/bash')
        logger.info(f"Successfully executed 'docker compose {action}'")
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Failed to run 'docker compose {action}': {e.stderr.strip()}", "danger")
        return False

# =================================================================
# CORE LOGIC: BACKUP, RESTORE, CRONJOB
# =================================================================

def run_full_backup(config: Dict[str, Any], is_cron: bool = False):
    """
    Creates a full backup using tar.gz and streams data directly to the archive
    to optimize disk I/O and space usage.
    """
    log_message(f"Starting full backup process (v4.1.0)...", "info")
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    # Create a temporary file for the archive
    archive_file = tempfile.NamedTemporaryFile(delete=False, prefix="marzban_backup_", suffix=".tar.gz")
    archive_filename = archive_file.name
    archive_file.close() # Close it so tarfile can open it properly

    try:
        with tarfile.open(archive_filename, "w:gz") as tar:
            # --- Conditional Database Backup ---
            container_name = find_database_container()
            if container_name and config.get('database'):
                log_message("Backing up databases...", "info")
                db_user = config['database']['user']
                db_pass = config['database']['password']
                list_dbs_cmd = f"docker exec -e MYSQL_PWD='{db_pass}' {container_name} mysql -u {db_user} -e 'SHOW DATABASES;'"
                process = subprocess.run(list_dbs_cmd, shell=True, check=True, capture_output=True, text=True)
                databases = [db for db in process.stdout.strip().split('\n')[1:] if db not in EXCLUDED_DATABASES]
                
                # Create a temporary dir for SQL dumps
                with tempfile.TemporaryDirectory() as db_temp_dir:
                    for db_name in databases:
                        sql_path = os.path.join(db_temp_dir, f"{db_name}.sql")
                        dump_cmd = f"docker exec -e MYSQL_PWD='{db_pass}' {container_name} mysqldump -u {db_user} --databases {db_name} > {sql_path}"
                        subprocess.run(dump_cmd, shell=True, check=True)
                        # Add the SQL file to the tar archive under 'database/' directory
                        tar.add(sql_path, arcname=f"database/{db_name}.sql")
                    log_message(f"Successfully backed up databases: {', '.join(databases)}", "success")
            else:
                log_message("No database container found or configured. Skipping database backup.", "warning")

            # --- Optimized Filesystem Backup ---
            log_message("Backing up configuration files...", "info")

            def exclude_filter(tarinfo: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
                """Filter function for tarfile to exclude specific directories."""
                # Check if the file is inside /var/lib/marzban and in the excluded list
                path_parts = tarinfo.name.split(os.sep)
                if 'var' in path_parts and 'lib' in path_parts and 'marzban' in path_parts:
                    for part in path_parts:
                        if part in EXCLUDED_DIRS_IN_VARLIB:
                            log_message(f"Excluding from backup: {tarinfo.name}", "info")
                            return None
                return tarinfo

            for path in FILES_TO_BACKUP:
                if os.path.exists(path):
                    log_message(f"Adding '{path}' to archive...", "info")
                    # arcname removes the leading '/' to make it a relative path inside the archive
                    tar.add(path, arcname=path.lstrip('/'), filter=exclude_filter)
                else:
                    log_message(f"Path '{path}' does not exist. Skipping.", "warning")

            log_message("File backup complete.", "success")

        log_message(f"Compression complete. File: {archive_filename}", "success")

        # --- Upload to Telegram ---
        log_message("Uploading to Telegram...", "info")
        tg_config = config['telegram']
        url = f"https://api.telegram.org/bot{tg_config['bot_token']}/sendDocument"
        caption = f"✅ Marzban Backup ({'Auto' if is_cron else 'Manual'})\n📅 {timestamp}"
        try:
            with open(archive_filename, 'rb') as f:
                response = requests.post(
                    url,
                    data={'chat_id': tg_config['admin_chat_id'], 'caption': caption},
                    files={'document': f},
                    timeout=300
                )
                response.raise_for_status()
            log_message("Backup successfully sent to Telegram!", "success")
        except requests.exceptions.RequestException as e:
            log_message(f"Network error while sending to Telegram: {str(e)}", "danger")
            raise

    except Exception as e:
        log_message(f"A critical error occurred during backup: {str(e)}", "danger")
        logger.error("Backup failed", exc_info=True)
        raise
    finally:
        log_message("Cleaning up temporary files...", "info")
        if os.path.exists(archive_filename):
            os.remove(archive_filename)

def download_from_telegram(tg_config: Dict[str, str], timeout: int = 120) -> Optional[str]:
    """Waits for and downloads a .tar.gz backup file from the Telegram bot."""
    bot_token, chat_id = tg_config['bot_token'], tg_config['admin_chat_id']
    log_message(f"Please send the .tar.gz backup file to your bot now. Waiting for {timeout} seconds...", "info")
    offset = 0
    try:
        # Get the latest update_id to start from
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset=-1"
        response = requests.get(url, timeout=10).json()
        if response.get('ok') and response.get('result'):
            offset = response['result'][0]['update_id'] + 1
    except requests.RequestException:
        pass
    
    start_time = time()
    while time() - start_time < timeout:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=10"
            updates = requests.get(url, timeout=15).json()
            if updates['ok'] and updates['result']:
                for update in updates['result']:
                    offset = update['update_id'] + 1
                    msg = update.get('message', {})
                    if str(msg.get('chat', {}).get('id')) == str(chat_id) and 'document' in msg:
                        doc = msg['document']
                        if doc['file_name'].endswith('.tar.gz'):
                            log_message(f"Backup file '{doc['file_name']}' received.", "success")
                            file_id = doc['file_id']
                            with console.status("[info]Downloading file...", spinner="earth"):
                                file_info_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
                                file_info = requests.get(file_info_url, timeout=10).json()
                                if not file_info.get('ok'):
                                    raise Exception(f"Failed to get file info: {file_info.get('description')}")
                                
                                file_path_on_tg = file_info['result']['file_path']
                                download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path_on_tg}"
                                temp_archive = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz", prefix="tg_backup_")
                                
                                with requests.get(download_url, stream=True, timeout=300) as r:
                                    r.raise_for_status()
                                    shutil.copyfileobj(r.raw, temp_archive)
                                temp_archive.close()
                                log_message(f"File downloaded to: {temp_archive.name}", "success")
                                return temp_archive.name
            sleep(3)
        except requests.RequestException as e:
            log_message(f"Network error: {str(e)}. Retrying...", "warning")
            sleep(5)
            
    log_message("Timeout! No backup file was received.", "danger")
    return None


def run_restore_process(archive_path: str, config: Dict[str, Any]) -> bool:
    """The core, non-interactive restore logic."""
    if not tarfile.is_tarfile(archive_path):
        log_message("The provided file is not a valid .tar.gz archive.", "danger")
        return False
        
    with tempfile.TemporaryDirectory(prefix="marzban_restore_") as temp_dir:
        try:
            log_message(f"Starting restore from: {archive_path}", "info")
            with tarfile.open(archive_path, 'r:gz') as tar:
                # Check for key directories before extracting
                if not any(f.name.startswith('filesystem/') for f in tar.getmembers()):
                    raise Exception("Invalid backup structure: 'filesystem/' directory not found.")
                tar.extractall(path=temp_dir)
            log_message("Backup file is valid and unzipped.", "success")

            with console.status("[info]Stopping all Marzban services...[/info]"):
                if not run_marzban_command("down"): raise Exception("Could not stop Marzban services.")
            log_message("All Marzban services stopped.", "success")

            # Restore filesystem
            fs_restore_path = os.path.join(temp_dir, "filesystem")
            if os.path.isdir(fs_restore_path):
                log_message("Restoring all files (configs, SQLite DB)...", "info")
                # Using copytree with dirs_exist_ok to overwrite everything
                shutil.copytree(fs_restore_path, "/", dirs_exist_ok=True)
                log_message("All files restored successfully.", "success")

            # Restore MySQL database if it exists in the backup
            db_restore_path = os.path.join(temp_dir, "database")
            if os.path.isdir(db_restore_path) and os.listdir(db_restore_path):
                log_message("✅ MySQL backup data found. Proceeding with MySQL restore.", "success")
                if not config.get('database') or not config['database'].get('password'):
                    raise Exception("Backup contains MySQL data, but no DB credentials in config.json.")
                
                log_message("Clearing old MySQL data directory...", "info")
                mysql_data_dir = "/var/lib/marzban/mysql"
                if os.path.exists(mysql_data_dir): shutil.rmtree(mysql_data_dir)
                os.makedirs(mysql_data_dir, exist_ok=True)
                
                with console.status("[info]Starting services to initialize MySQL...[/info]"):
                    if not run_marzban_command("up -d"): raise Exception("Could not start Marzban services.")
                log_message("Waiting 30 seconds for MySQL to stabilize...", "info")
                sleep(30)
                
                container_name = find_database_container()
                if not container_name: raise Exception("Could not find MySQL container after restart.")
                
                for sql_file in os.listdir(db_restore_path):
                    if sql_file.endswith(".sql"):
                        db_name = os.path.splitext(sql_file)[0]
                        sql_file_path = os.path.join(db_restore_path, sql_file)
                        log_message(f"Importing data into '{db_name}' MySQL database...", "info")
                        restore_cmd = (f"cat {sql_file_path} | docker exec -i -e MYSQL_PWD='{config['database']['password']}' "
                                       f"{container_name} mysql -u {config['database']['user']} {db_name}")
                        subprocess.run(restore_cmd, shell=True, check=True)
                        log_message(f"MySQL database '{db_name}' restored successfully.", "success")
            else:
                log_message("ℹ️ No MySQL backup data found. Skipping MySQL restore steps.", "info")

            log_message("Performing final restart to apply all changes...", "info")
            run_marzban_command("down")
            if run_marzban_command("up -d"):
                log_message("Marzban services restarted successfully.", "success")
            else:
                log_message("Failed to restart Marzban services. Please check manually.", "warning")

            console.print(Panel("[bold green]✅ Restore process completed successfully![/bold green]"))
            return True
        except Exception as e:
            log_message(f"A critical error occurred during restore: {str(e)}", "danger")
            logger.error(f"Restore failed: {str(e)}", exc_info=True)
            log_message("Attempting to bring Marzban service back up as a safety measure...", "info")
            run_marzban_command("up -d")
            return False

def restore_flow():
    """Interactive restore flow from the CLI menu."""
    show_header()
    console.print(Panel(
        "[bold]This is a highly destructive operation.[/bold]\nIt will [danger]STOP[/danger] services, "
        "[danger]DELETE[/danger] databases and MySQL data, and [danger]OVERWRITE[/danger] all Marzban data.",
        title="[warning]CRITICAL WARNING[/warning]", border_style="danger"
    ))
    if not Confirm.ask("[danger]Do you understand the risks and wish to continue?[/danger]"):
        log_message("Restore operation cancelled.", "info"); return
        
    config = get_config(ask_database=True) # Ask for DB credentials as they are needed for restore
    archive_path = None
    
    console.print(Panel(
        "[menu]1[/menu]. Use a local backup file\n[menu]2[/menu]. Download from Telegram bot",
        title="Select Restore Source", border_style="info"
    ))
    choice = Prompt.ask("[prompt]Choose your method[/prompt]", choices=["1", "2"], default="1")
    
    if choice == "1":
        archive_path = Prompt.ask("[prompt]Enter the full path to your .tar.gz backup file[/prompt]")
        if not os.path.exists(archive_path):
            log_message(f"File not found: '{archive_path}'. Aborting.", "danger"); return
    elif choice == "2":
        archive_path = download_from_telegram(config['telegram'])
        if not archive_path:
            log_message("Could not get backup from Telegram. Aborting.", "danger"); return
    
    if archive_path:
        run_restore_process(archive_path, config)
    
    if choice == "2" and archive_path and os.path.exists(archive_path):
        os.remove(archive_path)

def setup_cronjob_flow(interactive: bool = True):
    """Setup or update cronjob."""
    if interactive:
        show_header()
        console.print(Panel("Automatic Backup Setup (Cronjob)", style="info"))

    config = load_config_file()
    if not config or not config.get("telegram", {}).get('bot_token'):
        log_message("Telegram Bot is not configured. Please run 'Setup Telegram Bot' first.", "danger")
        return
    
    if interactive: config = get_config(ask_interval=True, ask_database=True)
    interval = config.get("telegram", {}).get('backup_interval')
    if not interval:
        log_message("Backup interval is not set. Please set it up from the menu first.", "danger")
        return

    python_executable = sys.executable
    script_path = os.path.abspath(__file__)
    cron_command = f"*/{interval} * * * * {python_executable} {script_path} run-backup"
    
    if interactive:
        console.print(Panel(f"The following command will be added to crontab:\n\n[info]{cron_command}[/info]", title="Cronjob Command"))
        if not Confirm.ask("[prompt]Do you authorize this action?[/prompt]"):
            log_message("Automatic setup cancelled.", "info"); return
            
    try:
        current_crontab = subprocess.run(['crontab', '-l'], capture_output=True, text=True).stdout
        new_lines = [line for line in current_crontab.splitlines() if CRON_JOB_IDENTIFIER not in line]
        new_lines.append(f"{cron_command} {CRON_JOB_IDENTIFIER}")
        
        p = Popen(['crontab', '-'], stdin=PIPE)
        p.communicate(input="\n".join(new_lines).encode() + b"\n")
        
        if p.returncode == 0:
            log_message("✅ Crontab updated successfully!", "success")
        else:
            raise Exception("The 'crontab' command failed.")
    except Exception as e:
        log_message(f"A critical error occurred while updating crontab: {str(e)}", "danger")

def main():
    """Main function to dispatch tasks based on arguments or run interactively."""
    # --- NON-INTERACTIVE MODE (for Bot and Cron) ---
    if len(sys.argv) > 1:
        command = sys.argv[1]
        logger.info(f"Running in Non-Interactive Mode, command: {command}")
        
        config = load_config_file()
        if not config:
            print("❌ Error: config.json not found or corrupted.")
            sys.exit(1)

        if command in ['run-backup', 'do-backup']:
            try:
                run_full_backup(config, is_cron=(command == 'run-backup'))
                sys.exit(0)
            except Exception:
                sys.exit(1)
        
        elif command == 'do-restore':
            if len(sys.argv) < 3:
                print("❌ Error: Restore command called without a file path.")
                sys.exit(1)
            archive_path = sys.argv[2]
            if not os.path.exists(archive_path):
                print(f"❌ Error: Restore file not found: {archive_path}")
                sys.exit(1)
            
            if run_restore_process(archive_path, config):
                sys.exit(0)
            else:
                sys.exit(1)
        
        else:
            print(f"❌ Error: Unknown non-interactive command '{command}'")
            sys.exit(1)

    # --- INTERACTIVE MODE (for human users) ---
    if os.geteuid() != 0:
        log_message("This script requires root privileges. Please run it with 'sudo'.", "danger")
        sys.exit(1)
        
    while True:
        show_header()
        choice = show_main_menu()
        if choice == "1":
            config = get_config(ask_telegram=True, ask_database=True)
            try:
                run_full_backup(config)
            except Exception:
                log_message("Backup process failed. Check logs for details.", "danger")
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
