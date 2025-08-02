#!/usr/bin/env python3
# =================================================================
# Marzban Complete Backup & Restore Panel
# Creator: @HEXMOSTAFA
# Version: 4.2 (Robust filesystem backup logic + Optimizations)
#
# A single, robust script for both interactive management
# and automated/bot-driven backups & restores.
# =================================================================

import os
import sys
import subprocess
import json
import shutil
from time import sleep, time
from datetime import datetime
import requests
from subprocess import Popen, PIPE
import tempfile
import zipfile
import logging
from logging.handlers import RotatingFileHandler
import traceback

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
# Paths to back up. This structure is critical for the new backup logic.
FILES_TO_BACKUP = ["/var/lib/marzban", "/opt/marzban"] 
EXCLUDED_DATABASES = ['information_schema', 'mysql', 'performance_schema', 'sys']
CRON_JOB_IDENTIFIER = "# HEXMOSTAFA_MARZBAN_BACKUP_JOB"
MARZBAN_SERVICE_PATH = "/opt/marzban"
LOG_FILE = os.path.join(SCRIPT_DIR, "marzban_backup.log")

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] - %(message)s',
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler(sys.stdout)
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
console = Console(theme=custom_theme, log_path=False)

# =================================================================
# HELPER FUNCTIONS
# =================================================================

def show_header():
    console.clear()
    header_text = Text("Marzban Complete Backup & Restore Panel\nCreator: @HEXMOSTAFA | Version 4.2", justify="center", style="header")
    console.print(Panel(header_text, style="blue", border_style="info"))
    console.print()

def show_main_menu():
    """Displays the main menu."""
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

def load_config_file():
    """Loads config from file without interaction."""
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Config file at '{CONFIG_FILE}' is unreadable or corrupted: {e}")
        return None

def get_config(ask_telegram=False, ask_database=False, ask_interval=False):
    """Modular function to get specific parts of the configuration and save it securely."""
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
            config['database'] = config.get('database', {})
            config["database"]['user'] = Prompt.ask(
                "[prompt]Enter the Database Username[/prompt]", default=config.get("database", {}).get('user', 'root')
            )
            config["database"]['password'] = Prompt.ask("[prompt]Enter the database password[/prompt]", password=True)
        else:
            log_message("No database container detected. Skipping database credential setup.", "warning")
            config['database'] = {}
            
    if ask_interval:
        config['telegram'] = config.get('telegram', {})
        config["telegram"]['backup_interval'] = Prompt.ask(
            "[prompt]Enter automatic backup interval in minutes (e.g., 60)[/prompt]",
            default=str(config.get("telegram", {}).get('backup_interval', '60'))
        )
        
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        # Set secure permissions for the config file
        os.chmod(CONFIG_FILE, 0o600)
        if any([ask_telegram, ask_database, ask_interval]):
             console.print(f"[success]Settings saved to '{CONFIG_FILE}'. Permissions set to 600 for security.[/success]")
    except Exception as e:
        console.print(f"[danger]Failed to save config file: {str(e)}[/danger]")
        
    return config

def setup_bot_flow():
    """A dedicated flow for setting up the Telegram Bot and its systemd service."""
    show_header()
    console.print(Panel("Telegram Bot Setup", style="info"))
    console.print("This will configure your bot and create a background service to run it permanently.")

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

        log_message("Reloading systemd daemon...", "info")
        subprocess.run(['systemctl', 'daemon-reload'], check=True)

        with console.status("[bold green]Activating Telegram bot service...[/bold green]"):
            log_message("Enabling and starting the bot service...", "info")
            subprocess.run(['systemctl', 'enable', '--now', 'marzban_bot.service'], check=True, capture_output=True, text=True)

        sleep(3)
        result = subprocess.run(['systemctl', 'is-active', 'marzban_bot.service'], capture_output=True, text=True)

        if result.stdout.strip() == "active":
            console.print("[bold green]✅ Telegram bot service is now running successfully.[/bold green]")
            log_message("Systemd service for the bot verified as active.", "success")
        else:
            console.print("[bold red]❌ Bot service failed to start. Check logs for details.[/bold red]")
            status_result = subprocess.run(['systemctl', 'status', 'marzban_bot.service'], capture_output=True, text=True)
            console.print(Panel(status_result.stderr or status_result.stdout, title="[danger]Systemctl Status[/danger]"))
            log_message(f"Service failed to activate. Status: {result.stdout.strip()}", "danger")

    except PermissionError:
        console.print(f"[danger]Error: Permission denied. Could not write to {service_file_path}. Please run as root ('sudo').[/danger]")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]❌ Failed to execute a system command: {e.stderr.strip()}[/bold red]")
        log_message(f"Failed to manage systemd service: {e.stderr.strip()}", "danger")
    except Exception as e:
        console.print(f"[bold red]❌ An unexpected error occurred: {e}[/bold red]")
        log_message(f"An unexpected error occurred during bot setup: {e}", "danger", exc_info=True)

def log_message(message, style="info", **kwargs):
    """Log a message to console and file."""
    console.print(f"[{style}]{message}[/{style}]", **kwargs)
    logger.info(message)

def find_database_container():
    """Finds the MySQL/MariaDB container for Marzban."""
    log_message("Searching for Marzban database container...", "info")
    try:
        result = subprocess.run(
            "docker ps --format '{{.Names}} {{.Image}}' | grep -iE 'mysql|mariadb'",
            shell=True, check=True, capture_output=True, text=True
        )
        # Prefer a container with 'marzban' in its name
        for line in result.stdout.strip().split('\n'):
            if 'marzban' in line.lower():
                container_name = line.split()[0]
                log_message(f"Detected Marzban-specific database container: {container_name}", "success")
                return container_name
        # Fallback to the first found container if no specific one is found
        first_container = result.stdout.strip().split('\n')[0].split()[0]
        log_message(f"Found a generic database container: {first_container}. Using it as fallback.", "warning")
        return first_container
    except (subprocess.CalledProcessError, IndexError):
        log_message("No active MySQL/MariaDB database container found.", "warning")
        return None

def run_marzban_command(action):
    """Runs a docker compose command for Marzban (up, down, etc.)."""
    if not os.path.isdir(MARZBAN_SERVICE_PATH):
        log_message(f"Marzban directory '{MARZBAN_SERVICE_PATH}' not found. Cannot manage services.", "danger")
        return False
    command = f"cd {MARZBAN_SERVICE_PATH} && docker compose {action}"
    try:
        subprocess.run(command, shell=True, check=True, capture_output=True, text=True, executable='/bin/bash')
        logger.info(f"Successfully executed 'docker compose {action}' in {MARZBAN_SERVICE_PATH}")
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Failed to run 'docker compose {action}': {e.stderr.strip()}", "danger")
        return False

# =================================================================
# CORE LOGIC: BACKUP, RESTORE, CRONJOB
# =================================================================

def run_full_backup(config, is_cron=False):
    """
    Creates a full backup of databases and files using a robust, non-duplicating method.
    """
    log_message("Starting full backup process...", "info")
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    backup_temp_dir = tempfile.mkdtemp(prefix="marzban_backup_")
    # We create the zip file in a known location like /tmp
    zip_base_name = os.path.join("/tmp", f"marzban_full_backup_{timestamp}")
    zip_filename = f"{zip_base_name}.zip"

    try:
        # --- Database Backup ---
        container_name = find_database_container()
        if container_name and config.get('database', {}).get('user'):
            log_message("Backing up MySQL databases...", "info")
            db_user = config['database']['user']
            db_pass = config['database']['password']
            
            db_staging_dir = os.path.join(backup_temp_dir, "database")
            os.makedirs(db_staging_dir, exist_ok=True)

            list_dbs_cmd = f"docker exec -e MYSQL_PWD='{db_pass}' {container_name} mysql -u {db_user} -N -e 'SHOW DATABASES;'"
            process = subprocess.run(list_dbs_cmd, shell=True, check=True, capture_output=True, text=True)
            databases = [db for db in process.stdout.strip().split('\n') if db not in EXCLUDED_DATABASES]
            
            for db_name in databases:
                sql_path = os.path.join(db_staging_dir, f"{db_name}.sql")
                dump_cmd = (f"docker exec -e MYSQL_PWD='{db_pass}' {container_name} "
                            f"mysqldump -u {db_user} --databases {db_name} > {sql_path}")
                subprocess.run(dump_cmd, shell=True, check=True, capture_output=True)
            log_message(f"Successfully backed up databases: {', '.join(databases)}", "success")
        else:
            log_message("No configured database found. Skipping MySQL backup.", "warning")

        # --- Filesystem Backup (ROBUST, NON-DUPLICATING LOGIC) ---
        log_message("Backing up Marzban configuration files...", "info")
        fs_staging_dir = os.path.join(backup_temp_dir, "filesystem")
        os.makedirs(fs_staging_dir)

        def ignore_patterns(path, names):
            ignored = set()
            # This logic specifically targets the mysql/logs inside /var/lib/marzban
            if '/var/lib/marzban' in path and os.path.basename(path) == 'marzban':
                for name in names:
                    if name in ['mysql', 'logs']:
                        ignored.add(name)
            return ignored

        for source_path in FILES_TO_BACKUP:
            if not os.path.exists(source_path):
                log_message(f"Source path '{source_path}' does not exist. Skipping.", "warning")
                continue
            
            # Destination path inside the staging 'filesystem' directory
            # This maintains the absolute path structure, e.g., /.../filesystem/var/lib/marzban
            destination_path = os.path.join(fs_staging_dir, source_path.lstrip('/'))
            
            log_message(f"Copying '{source_path}' to staging area...", "info")
            if os.path.isdir(source_path):
                # copytree requires the destination to NOT exist.
                # This is the key to preventing duplication.
                shutil.copytree(source_path, destination_path, ignore=ignore_patterns, symlinks=True)
            elif os.path.isfile(source_path):
                os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                shutil.copy2(source_path, destination_path)
        
        log_message("File backup stage complete.", "success")

        # --- Compression and Upload ---
        log_message("Compressing backup into a zip file...", "info")
        shutil.make_archive(zip_base_name, 'zip', root_dir=backup_temp_dir)
        log_message(f"Compression complete. File created at: {zip_filename}", "success")

        log_message("Uploading backup to Telegram...", "info")
        tg_config = config['telegram']
        url = f"https://api.telegram.org/bot{tg_config['bot_token']}/sendDocument"
        caption = f"✅ Marzban Backup ({'Auto' if is_cron else 'Manual'})\n📅 {timestamp}"
        with open(zip_filename, 'rb') as f:
            response = requests.post(
                url,
                data={'chat_id': tg_config['admin_chat_id'], 'caption': caption},
                files={'document': f},
                timeout=300
            )
        response.raise_for_status() # Raise an exception for HTTP errors
        log_message("Backup successfully sent to Telegram!", "success")

    except Exception as e:
        log_message(f"A critical error occurred during backup: {str(e)}", "danger")
        logger.error("Backup failed", exc_info=True)
        # Re-raise to be caught by higher-level handlers if necessary
        raise
    finally:
        log_message("Cleaning up temporary files...", "info")
        shutil.rmtree(backup_temp_dir, ignore_errors=True)
        if os.path.exists(zip_filename):
            os.remove(zip_filename)
            
def download_from_telegram(tg_config, timeout=120):
    bot_token, chat_id = tg_config['bot_token'], tg_config['admin_chat_id']
    log_message(f"Please send the .zip backup file to your bot now. Waiting for {timeout} seconds...", "info")
    offset = 0
    try:
        # Get the latest update_id to start polling from there
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset=-1"
        response = requests.get(url, timeout=10).json()
        if response.get('ok') and response.get('result'):
            offset = response['result'][0]['update_id'] + 1
    except requests.RequestException:
        pass # Ignore if we can't get the initial offset

    start_time = time()
    while time() - start_time < timeout:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=10"
            updates = requests.get(url, timeout=15).json()
            if updates.get('ok') and updates.get('result'):
                for update in updates['result']:
                    offset = update['update_id'] + 1
                    if 'message' in update and 'document' in update['message'] and str(update['message']['chat']['id']) == str(chat_id):
                        doc = update['message']['document']
                        if doc.get('file_name', '').endswith('.zip'):
                            log_message(f"Backup file '{doc['file_name']}' received.", "success")
                            file_id = doc['file_id']
                            with console.status("[info]Downloading file from Telegram...", spinner="earth"):
                                file_info_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
                                file_info = requests.get(file_info_url, timeout=10).json()
                                if not file_info.get('ok'):
                                    raise Exception(f"Failed to get file info: {file_info.get('description')}")
                                
                                download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_info['result']['file_path']}"
                                temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", prefix="tg_backup_")
                                
                                with requests.get(download_url, stream=True, timeout=300) as r:
                                    r.raise_for_status()
                                    shutil.copyfileobj(r.raw, temp_zip)
                                temp_zip.close() # Close file handle to ensure it's written
                                log_message(f"File downloaded to: {temp_zip.name}", "success")
                                return temp_zip.name
            sleep(2) # Short sleep between polls
        except requests.RequestException as e:
            log_message(f"Network error while polling Telegram: {e}. Retrying...", "warning")
            sleep(5)

    log_message("Timeout! No backup file was received from Telegram.", "danger")
    return None

def run_restore_process(zip_path, config):
    """The core, non-interactive restore logic."""
    with tempfile.TemporaryDirectory(prefix="marzban_restore_") as temp_dir:
        try:
            log_message(f"Starting restore from: {os.path.basename(zip_path)}", "info")
            log_message("Verifying backup file structure...", "info")
            with zipfile.ZipFile(zip_path, 'r') as zf:
                if not any(f.startswith('filesystem/') for f in zf.namelist()):
                    raise ValueError("Invalid backup: 'filesystem/' directory not found inside zip.")
                zf.extractall(temp_dir)
            log_message("Backup file is valid and extracted.", "success")

            with console.status("[info]Stopping Marzban services...[/info]", spinner="dots"):
                if not run_marzban_command("down"):
                    raise RuntimeError("Could not stop Marzban services. Restore cannot continue.")
            log_message("Marzban services stopped.", "success")

            fs_restore_path = os.path.join(temp_dir, "filesystem")
            log_message("Restoring files and directories...", "info")
            # Using copytree to restore, which handles permissions and directories correctly.
            # We restore to the root directory '/'.
            shutil.copytree(fs_restore_path, "/", dirs_exist_ok=True)
            log_message("Filesystem restore complete.", "success")

            db_restore_path = os.path.join(temp_dir, "database")
            if os.path.isdir(db_restore_path) and os.listdir(db_restore_path):
                log_message("MySQL backup data found. Proceeding with MySQL restore.", "success")
                if not config.get('database'):
                    raise ValueError("Backup contains MySQL data, but DB credentials are not configured.")
                
                log_message("Clearing old MySQL data volume...", "info")
                mysql_data_dir = "/var/lib/marzban/mysql"
                if os.path.exists(mysql_data_dir): shutil.rmtree(mysql_data_dir)
                os.makedirs(mysql_data_dir, exist_ok=True)
                
                with console.status("[info]Starting services to initialize MySQL...[/info]"):
                    if not run_marzban_command("up -d"):
                        raise RuntimeError("Could not start Marzban services for MySQL initialization.")
                
                log_message("Waiting 30 seconds for MySQL to stabilize...", "info")
                sleep(30)
                
                container_name = find_database_container()
                if not container_name:
                    raise RuntimeError("Could not find MySQL container after restart.")

                log_message("Importing data into MySQL databases...", "info")
                for sql_file in os.listdir(db_restore_path):
                    if sql_file.endswith('.sql'):
                        db_name = os.path.splitext(sql_file)[0]
                        sql_file_path = os.path.join(db_restore_path, sql_file)
                        restore_cmd = (f"cat {sql_file_path} | docker exec -i -e MYSQL_PWD='{config['database']['password']}' "
                                       f"{container_name} mysql -u {config['database']['user']}")
                        subprocess.run(restore_cmd, shell=True, check=True, capture_output=True)
                        log_message(f"Successfully restored database '{db_name}'.", "success")
            else:
                log_message("No MySQL data found in backup. Skipping MySQL restore.", "info")

            log_message("Performing final restart to apply all changes...", "info")
            run_marzban_command("down") # Ensure clean state before final start
            if run_marzban_command("up -d"):
                log_message("Marzban services restarted successfully.", "success")
            else:
                log_message("Failed to restart Marzban services. Please check manually.", "warning")

            console.print(Panel("[bold green]✅ Restore process completed successfully![/bold green]"))
            return True

        except Exception as e:
            log_message(f"A critical error occurred during restore: {str(e)}", "danger", extra={'markup': True})
            logger.error(f"Restore failed: {str(e)}", exc_info=True)
            log_message("Attempting to bring Marzban service back up as a safety measure...", "info")
            run_marzban_command("up -d")
            return False

def restore_flow():
    """Interactive restore flow for the CLI menu."""
    show_header()
    console.print(Panel(
        "[bold]This is a highly destructive operation.[/bold]\nIt will [danger]STOP[/danger] services, "
        "and [danger]OVERWRITE[/danger] all current Marzban data with the backup contents.",
        title="[warning]CRITICAL WARNING[/warning]", border_style="danger"
    ))
    if not Confirm.ask("[prompt]Do you understand the risks and wish to continue?[/prompt]", default=False):
        log_message("Restore operation cancelled by user.", "info"); return
    
    config = get_config()
    if not config:
        log_message("Configuration file is missing or invalid. Please run Setup first.", "danger"); return
        
    zip_path = None
    
    console.print(Panel(
        "[menu]1[/menu]. Use a local backup file\n[menu]2[/menu]. Download from Telegram bot",
        title="Select Restore Source", border_style="info"
    ))
    choice = Prompt.ask("[prompt]Choose your method[/prompt]", choices=["1", "2"], default="1")
    
    if choice == "1":
        zip_path = Prompt.ask("[prompt]Enter the full path to your .zip backup file[/prompt]")
        if not os.path.exists(zip_path):
            log_message(f"File not found: '{zip_path}'. Aborting.", "danger"); return
    elif choice == "2":
        if not config.get('telegram', {}).get('bot_token'):
            log_message("Telegram is not configured. Please use Option 3 in the main menu first.", "danger"); return
        zip_path = download_from_telegram(config['telegram'])
        if not zip_path:
            log_message("Could not get backup from Telegram. Aborting.", "danger"); return
    
    if zip_path and run_restore_process(zip_path, config):
        # If restore was successful and from telegram, clean up the downloaded file
        if choice == "2" and os.path.exists(zip_path):
            os.remove(zip_path)
            log_message(f"Cleaned up temporary download: {os.path.basename(zip_path)}", "info")

def setup_cronjob_flow(interactive=True):
    """Setup or update the automatic backup cronjob."""
    if interactive:
        show_header()
        console.print(Panel("Automatic Backup Setup (Cronjob)", style="info"))

    config = load_config_file()
    if not config or not config.get("telegram", {}).get('bot_token'):
        log_message("Telegram Bot is not configured. Please run 'Setup Telegram Bot' first.", "danger")
        return False

    if interactive:
        config = get_config(ask_interval=True)
        
    interval = config.get("telegram", {}).get('backup_interval', '60')
    if not interval or not str(interval).isdigit():
        log_message(f"Invalid backup interval: '{interval}'. Please set a valid number of minutes.", "danger")
        return False

    log_message("Performing an initial backup as a connectivity test...", "info")
    try:
        run_full_backup(config, is_cron=True)
        log_message("Initial backup test was successful!", "success")
    except Exception as e:
        log_message(f"Initial backup test failed: {e}", "danger")
        if interactive and not Confirm.ask("[prompt]The test failed. Do you want to set up the cronjob anyway?[/prompt]", default=False):
            return False
        elif not interactive:
            return False

    python_executable = sys.executable
    script_path = os.path.abspath(__file__)
    # Redirect stdout and stderr to the log file to capture cron output
    log_file_path = os.path.abspath(LOG_FILE)
    cron_command = f"*/{interval} * * * * {python_executable} {script_path} run-backup >> {log_file_path} 2>&1"
    
    if interactive:
        console.print(Panel(f"The following command will be added to the system crontab:\n\n[info]{cron_command}[/info]", title="Cronjob Command"))
        if not Confirm.ask("[prompt]Do you authorize this action?[/prompt]"):
            log_message("Cronjob setup cancelled by user.", "info")
            return False
            
    log_message("Attempting to modify system crontab...", "info")
    try:
        p_read = subprocess.run(['crontab', '-l'], capture_output=True, text=True, check=False)
        current_crontab = p_read.stdout
        
        # Filter out any old versions of this specific job
        new_lines = [line for line in current_crontab.strip().split('\n') if CRON_JOB_IDENTIFIER not in line and line.strip()]
        new_lines.append(f"{cron_command} {CRON_JOB_IDENTIFIER}")
        new_crontab_content = "\n".join(new_lines) + "\n"

        p_write = Popen(['crontab', '-'], stdin=PIPE, stdout=PIPE, stderr=PIPE)
        stdout, stderr = p_write.communicate(input=new_crontab_content.encode())
        
        if p_write.returncode == 0:
            log_message("✅ Crontab updated successfully!", "success")
            return True
        else:
            raise Exception(f"crontab command failed. Stderr: {stderr.decode().strip()}")

    except Exception as e:
        log_message(f"A critical error occurred while updating crontab: {e}", "danger")
        return False

def main():
    """Main function to dispatch tasks based on CLI arguments or run interactively."""
    # --- NON-INTERACTIVE MODE (for Bot and Cron) ---
    if len(sys.argv) > 1:
        command = sys.argv[1]
        logger.info(f"Running in Non-Interactive Mode, command: {command}")
        
        config = load_config_file()
        if not config and command not in ['get-db-type']:
            logger.error("Error: config.json not found or invalid. Please run script interactively to create it.")
            sys.exit(1)
        
        try:
            if command in ['run-backup', 'do-backup']:
                run_full_backup(config, is_cron=(command == 'run-backup'))
            elif command == 'do-restore':
                if len(sys.argv) < 3:
                    logger.error("Error: Restore command called without a file path.")
                    sys.exit(1)
                run_restore_process(sys.argv[2], config)
            elif command == 'do-auto-backup-setup':
                if not setup_cronjob_flow(interactive=False): sys.exit(1)
            else:
                logger.error(f"Error: Unknown non-interactive command '{command}'")
                sys.exit(1)
            sys.exit(0)
        except Exception as e:
            logger.error(f"Non-interactive command '{command}' failed: {e}", exc_info=True)
            sys.exit(1)

    # --- INTERACTIVE MODE (for human users) ---
    if os.geteuid() != 0:
        console.print("[danger]This script requires root privileges. Please run it with 'sudo'.[/danger]")
        sys.exit(1)
        
    while True:
        show_header()
        choice = show_main_menu()
        if choice == "1":
            config = get_config(ask_database=True)
            if not config.get('telegram', {}).get('bot_token'):
                log_message("Telegram details not found, running setup...", "info")
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
t            setup_cronjob_flow()
        elif choice == "5":
            log_message("Goodbye!", "info")
            break
        
        Prompt.ask("\n[prompt]Press Enter to return to the main menu...[/prompt]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\nApplication exited by user (KeyboardInterrupt).")
        print("\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        logger.error("An unexpected fatal error occurred in the main execution block.", exc_info=True)
        console.print(f"\n[danger]An unexpected fatal error occurred: {e}[/danger]")
        console.print_exception(show_locals=True)
        sys.exit(1)
