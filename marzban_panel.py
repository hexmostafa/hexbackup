#!/usr/bin/env python3 
#================================================================= 
# Marzban Complete Backup & Restore Panel 
# Creator: @HEXMOSTAFA 
# Version: 4.0 (Unified & Bot-Compatible) 
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
# کد اصلاح‌شده (صحیح) 
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__)) 
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json") 
CONTAINER_NAME = "marzban-mysql-1"  # Default container name 
FILES_TO_BACKUP = ["/var/lib/marzban", "/opt/marzban"] 
EXCLUDED_DATABASES = ['information_schema', 'mysql', 'performance_schema', 'sys'] 
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
    header_text = Text("Marzban Complete Backup & Restore Panel\nCreator: @HEXMOSTAFA | Version 4.0", justify="center", style="header") 
    console.print(Panel(header_text, style="blue", border_style="info")) 
    console.print() 

def show_main_menu(): 
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

def load_config_file(): 
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

def get_config(ask_telegram=False, ask_database=False, ask_interval=False): 
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
            # Ensure the 'database' key exists 
            if 'database' not in config: 
                config['database'] = {} 
            config["database"]['user'] = Prompt.ask( 
                "[prompt]Enter the Database Username[/prompt]", default=config.get("database", {}).get('user', 'root') 
            ) 
            config["database"]['password'] = Prompt.ask("[prompt]Enter the database password[/prompt]", password=True) 
        else: 
            log_message("No database detected, skipping database credential setup.", "warning") 
            config['database'] = {} 
             
    if ask_interval: 
        # Ensure the 'telegram' key exists 
        if 'telegram' not in config: 
            config['telegram'] = {} 
        config["telegram"]['backup_interval'] = Prompt.ask( 
            "[prompt]Enter automatic backup interval in minutes (e.g., 60)[/prompt]", 
            default=config.get("telegram", {}).get('backup_interval', '60') 
        ) 
         
    # Save the updated configuration 
    try: 
        with open(CONFIG_FILE, 'w') as f: 
            json.dump(config, f, indent=4) 
        if any([ask_telegram, ask_database, ask_interval]): 
             console.print(f"[success]Settings saved to '{CONFIG_FILE}'[/success]") 
    except Exception as e: 
        console.print(f"[danger]Failed to save config file: {str(e)}[/danger]") 
         
    return config 

import os 
import sys 
import subprocess 
from time import sleep 
from rich.panel import Panel 

# Make sure these are defined at the top of your marzban_panel.py file 
# from rich.console import Console 
# console = Console() 

def setup_bot_flow(): 
    """ 
    A dedicated flow for setting up the Telegram Bot. 
    1. Gets credentials from the user. 
    2. Dynamically creates the systemd service file. 
    3. Enables and starts the service. 
    4. Verifies that the service is running correctly. 
    """ 
    show_header() 
    console.print(Panel("Telegram Bot Setup", style="info")) 
    console.print("This process will configure your bot and create a background service to run it permanently.") 

    # Step 1: Get credentials and save config.json 
    get_config(ask_telegram=True, ask_database=True) 
    log_message("Configuration information saved successfully.", "success") 
    console.print() 

    # Step 2: Create and enable the systemd service file dynamically 
    try: 
        # Define paths 
        script_dir = os.path.dirname(os.path.abspath(__file__)) 
        bot_script_path = os.path.join(script_dir, "marzban_bot.py") 
        python_executable = sys.executable  # Gets the full path to the current python interpreter 
        service_file_path = "/etc/systemd/system/marzban_bot.service" 

        log_message(f"Creating systemd service file at {service_file_path}...", "info") 

        # Define the content of the service file 
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
        # Write the service file (requires root) 
        with open(service_file_path, "w") as f: 
            f.write(service_content) 

        log_message("Service file created. Reloading systemd daemon...", "info") 
        subprocess.run(['systemctl', 'daemon-reload'], check=True) 

        # Step 3: Enable and start the service 
        with console.status("[bold green]Activating Telegram bot service...[/bold green]"): 
            log_message("Enabling and starting the bot service now...", "info") 
            subprocess.run(['systemctl', 'enable', '--now', 'marzban_bot.service'], check=True, capture_output=True, text=True) 

        # Step 4: Verify that the service is running 
        sleep(3)  # Give the bot a few seconds to start and potentially fail 
        result = subprocess.run(['systemctl', 'is-active', 'marzban_bot.service'], capture_output=True, text=True) 

        if result.stdout.strip() == "active": 
            console.print("[bold green]✅ Telegram bot service is now running successfully in the background.[/bold green]") 
            log_message("Systemd service for the bot was verified as active.", "success") 
        else: 
            console.print("[bold red]❌ The bot service failed to stay running. Please check the logs.[/bold red]") 
            status_result = subprocess.run(['systemctl', 'status', 'marzban_bot.service'], capture_output=True, text=True) 
            console.print(Panel(status_result.stderr or status_result.stdout, title="[danger]Systemctl Status Output[/danger]")) 
            log_message(f"Service failed to stay active. Status: {result.stdout.strip()}", "danger") 

    except PermissionError: 
        console.print(f"[danger]Error: Permission denied. Could not write to {service_file_path}. Please run the panel with 'sudo'.[/danger]") 
    except subprocess.CalledProcessError as e: 
        error_details = e.stderr.strip() 
        console.print(f"[bold red]❌ Failed to execute a system command: {error_details}[/bold red]") 
        log_message(f"Failed to manage systemd service: {error_details}", "danger") 
    except Exception as e: 
        console.print(f"[bold red]❌ An unexpected error occurred: {e}[/bold red]") 
        log_message(f"An unexpected error occurred during bot setup: {e}", "danger", exc_info=True) 
         

def log_message(message, style="info"): 
    """Log a message to console and file with proper rich formatting.""" 
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S') 
    if not sys.stdout.isatty(): 
        print(f"[{timestamp}] {message}") 
    else: 
        try: 
            console.print(f"[{style}]{message}[/{style}]") 
        except Exception as e: 
            print(f"[{timestamp}] [ERROR] Invalid rich style formatting: {str(e)}") 
            print(f"[{timestamp}] {message}") 
    logger.info(message) 

def find_database_container(): 
    """Find the MySQL/MariaDB container for Marzban. Returns name or None.""" 
    log_message("Searching for a Marzban-related database container...", "info") 
    try: 
        # This command looks for running containers with mysql or mariadb in their image name 
        result = subprocess.run( 
            "docker ps --format '{{.Names}} {{.Image}}' | grep -E 'mysql|mariadb'", 
            shell=True, check=True, capture_output=True, text=True 
        ) 
        containers = result.stdout.strip().split('\n') 
        for container in containers: 
            # We assume the marzban db container has 'marzban' in its name 
            if 'marzban' in container.lower(): 
                container_name = container.split()[0] 
                log_message(f"Detected database container: {container_name}", "success") 
                return container_name 
         
        log_message("No active Marzban database container found.", "warning") 
        return None 
    except subprocess.CalledProcessError: 
        # This block runs if the grep command finds nothing and returns an error 
        log_message("No active database container found.", "warning") 
        return None 

def check_container_running(container_name): 
    """Check if a Docker container is running.""" 
    try: 
        result = subprocess.run( 
            f"docker inspect --format='{{.State.Running}}' {container_name}", 
            shell=True, check=True, capture_output=True, text=True 
        ) 
        if result.stdout.strip() == "true": 
            logger.info(f"Container '{container_name}' is running.") 
            return True 
        else: 
            logger.warning(f"Container '{container_name}' is not running.") 
            return False 
    except subprocess.CalledProcessError: 
        logger.error(f"Failed to check container status for '{container_name}'. It might not exist.") 
        return False 

def start_database_container(container_name): 
    """Start the database container if it's not running.""" 
    if not check_container_running(container_name): 
        log_message(f"Attempting to start container '{container_name}'...", "info") 
        try: 
            subprocess.run(f"docker start {container_name}", shell=True, check=True, capture_output=True) 
            log_message(f"Container '{container_name}' started successfully.", "success") 
            return True 
        except subprocess.CalledProcessError as e: 
            log_message(f"Failed to start container '{container_name}': {e.stderr}", "danger") 
            return False 
    return True 

def test_database_connection(container_name, db_user, db_pass): 
    """Test database connection.""" 
    log_message("Testing database connection...", "info") 
    try: 
        subprocess.run( 
            f"docker exec -e MYSQL_PWD='{db_pass}' {container_name} mysql -u {db_user} -h 127.0.0.1 -e 'SELECT 1;'", 
            shell=True, check=True, capture_output=True, text=True 
        ) 
        log_message("Database connection test successful.", "success") 
        return True 
    except subprocess.CalledProcessError as e: 
        log_message( 
            f"Database connection test failed: {e.stderr}\nPlease check credentials and service status.", "danger" 
        ) 
        return False 

def run_marzban_command(action): 
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
        log_message(f"Failed to run 'docker compose {action}': {e.stderr}", "danger") 
        return False 

def run_marzban_restart(): 
    """Run marzban restart command.""" 
    try: 
        subprocess.run( 
            "marzban restart", 
            shell=True, check=True, capture_output=True, text=True, executable='/bin/bash' 
        ) 
        log_message("Marzban restart command executed successfully.", "success") 
        return True 
    except subprocess.CalledProcessError as e: 
        log_message(f"Failed to run 'marzban restart': {e.stderr}", "danger") 
        return False 

# ================================================================= 
# CORE LOGIC: BACKUP, RESTORE, CRONJOB 
# ================================================================= 

def run_full_backup(config, is_cron=False): 
    """ 
    Create a full backup, excluding specified directories like mysql and logs. 
    """ 
    log_message("Starting full backup process...", "info") 
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S') 
    backup_temp_dir = tempfile.mkdtemp(prefix="marzban_backup_") 
    zip_filename = f"/tmp/marzban_full_backup_{timestamp}.zip" 

    try: 
        # --- Conditional Database Backup --- 
        container_name = find_database_container() 
        if container_name and config.get('database'): 
            log_message("Backing up databases...", "info") 
            # ... (بخش بکاپ دیتابیس بدون تغییر باقی می‌ماند) ... 
            db_user = config['database']['user'] 
            db_pass = config['database']['password'] 
            list_dbs_cmd = f"docker exec -e MYSQL_PWD='{db_pass}' {container_name} mysql -u {db_user} -e 'SHOW DATABASES;'" 
            process = subprocess.run(list_dbs_cmd, shell=True, check=True, capture_output=True, text=True) 
            databases = [db for db in process.stdout.strip().split('\n')[1:] if db not in EXCLUDED_DATABASES] 
            db_zip_path = os.path.join(backup_temp_dir, "database") 
            os.makedirs(db_zip_path, exist_ok=True) 
            for db_name in databases: 
                sql_path = os.path.join(db_zip_path, f"{db_name}.sql") 
                dump_cmd = f"docker exec -e MYSQL_PWD='{db_pass}' {container_name} mysqldump -u {db_user} --databases {db_name} > {sql_path}" 
                subprocess.run(dump_cmd, shell=True, check=True) 
            log_message("Database backup complete.", "success") 
        else: 
            log_message("No database container found or configured. Skipping database backup.", "warning") 

        # --- Filesystem Backup with Exclusions --- 
        log_message("Backing up configuration files (excluding mysql data and logs)...", "info") 
         
        # Define a function that tells shutil which directories to ignore 
        def ignore_specific_dirs(directory, contents): 
            # We check if the current directory is /var/lib/marzban 
            if os.path.basename(directory) == 'marzban' and 'lib' in directory: 
                return ['mysql', 'logs'] # Ignore these two directories if found 
            return [] # Otherwise, ignore nothing 

        fs_zip_path = os.path.join(backup_temp_dir, "filesystem") 
        os.makedirs(fs_zip_path, exist_ok=True) 
         
        for file_path in FILES_TO_BACKUP: 
            if os.path.exists(file_path): 
                dest_path = os.path.join(fs_zip_path, file_path.lstrip('/')) 
                if os.path.isdir(file_path): 
                    # Use the ignore function here 
                    shutil.copytree(file_path, dest_path, dirs_exist_ok=True, ignore=ignore_specific_dirs) 
                else: 
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True) 
                    shutil.copy2(file_path, dest_path) 
                logger.info(f"Backed up contents of: {file_path}") 
            else: 
                log_message(f"Path '{file_path}' does not exist. Skipping.", "warning") 
        log_message("File backup complete.", "success") 

        # --- Compression and Upload (remains the same) --- 
        log_message("Compressing backup file...", "info") 
        shutil.make_archive(zip_filename.replace('.zip', ''), 'zip', backup_temp_dir) 
        log_message(f"Compression complete. File: {zip_filename}", "success") 

        log_message("Uploading to Telegram...", "info") 
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
        if response.status_code == 200: 
            log_message("Backup successfully sent to Telegram!", "success") 
        else: 
            raise Exception(f"Telegram upload failed. Status: {response.status_code}, Response: {response.text}") 

    except Exception as e: 
        log_message(f"A critical error occurred during backup: {str(e)}", "danger") 
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
                    if 'message' in update and 'document' in update['message'] and str(update['message']['chat']['id']) == str(chat_id): 
                        doc = update['message']['document'] 
                        if doc['file_name'].endswith('.zip'): 
                            log_message(f"Backup file '{doc['file_name']}' received.", "success") 
                            file_id = doc['file_id'] 
                            with console.status("[info]Downloading file...", spinner="earth"): 
                                file_info_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}" 
                                file_info = requests.get(file_info_url, timeout=10).json() 
                                if not file_info.get('ok'): 
                                    raise Exception(f"Failed to get file info: {file_info}") 
                                file_path_on_tg = file_info['result']['file_path'] 
                                download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path_on_tg}" 
                                temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", prefix="tg_backup_") 
                                with requests.get(download_url, stream=True, timeout=300) as r: 
                                    r.raise_for_status() 
                                    shutil.copyfileobj(r.raw, temp_zip) 
                                temp_zip.close() 
                                log_message(f"File downloaded to: {temp_zip.name}", "success") 
                                return temp_zip.name 
            sleep(3) 
        except requests.RequestException as e: 
            log_message(f"Network error: {str(e)}. Retrying...", "warning") 
            sleep(5) 
    log_message("Timeout! No backup file was received.", "danger") 
    return None 

def run_restore_process(zip_path, config): 
    """ 
    The core, non-interactive restore logic with corrected timing and restart sequence. 
    """ 
    with tempfile.TemporaryDirectory(prefix="marzban_restore_") as temp_dir: 
        try: 
            log_message(f"Starting restore from: {zip_path}", "info") 
            log_message("Verifying backup file structure...", "info") 
            with zipfile.ZipFile(zip_path, 'r') as zf: 
                if not any(f.startswith('filesystem/') for f in zf.namelist()): 
                    raise Exception("Invalid backup structure: 'filesystem' directory not found.") 
                zf.extractall(temp_dir) 
            log_message("Backup file is valid and unzipped.", "success") 

            sqlite_db_path = os.path.join(temp_dir, "filesystem/var/lib/marzban/db.sqlite3") 
            if os.path.exists(sqlite_db_path): 
                log_message("✅ SQLite database file (db.sqlite3) found in backup.", "success") 
            else: 
                log_message("ℹ️ No SQLite database found in backup.", "info") 

            with console.status("[info]Stopping all Marzban services...[/info]"): 
                if not run_marzban_command("down"): raise Exception("Could not stop Marzban services.") 
            log_message("All Marzban services stopped.", "success") 

            fs_restore_path = os.path.join(temp_dir, "filesystem") 
            if os.path.isdir(fs_restore_path): 
                log_message("Restoring all files (including configs and SQLite DB)...", "info") 
                shutil.copytree(fs_restore_path, "/", dirs_exist_ok=True) 
                log_message("All files restored successfully.", "success") 

            db_restore_path = os.path.join(temp_dir, "database") 
            if os.path.isdir(db_restore_path) and os.listdir(db_restore_path): 
                log_message("✅ MySQL backup data found. Proceeding with MySQL restore.", "success") 
                if not config.get('database'): 
                    raise Exception("Backup contains MySQL data, but no DB credentials in config.json.") 
                 
                log_message("Clearing MySQL data directory...", "info") 
                mysql_data_dir = "/var/lib/marzban/mysql" 
                if os.path.exists(mysql_data_dir): shutil.rmtree(mysql_data_dir) 
                os.makedirs(mysql_data_dir, exist_ok=True) 
                 
                with console.status("[info]Starting services to initialize MySQL...[/info]"): 
                    if not run_marzban_command("up -d"): raise Exception("Could not start Marzban services.") 
                log_message("Services started for MySQL initialization.", "success") 

                # --- CHANGE 1: Wait time reduced to 10 seconds --- 
                log_message("Waiting for MySQL service to stabilize (30 seconds)...", "info") 
                sleep(30) 
                 
                container_name = find_database_container() 
                if not container_name: 
                     raise Exception("Could not find MySQL container after restart.") 
                 
                if not test_database_connection(container_name, config['database']['user'], config['database']['password']): 
                    raise Exception("Cannot connect to the new MySQL database. Check logs.") 

                sql_file_path = os.path.join(db_restore_path, 'marzban.sql') 
                if os.path.exists(sql_file_path): 
                    log_message("Importing data into 'marzban' MySQL database...", "info") 
                    restore_cmd = (f"cat {sql_file_path} | docker exec -i -e MYSQL_PWD='{config['database']['password']}' " 
                                   f"{container_name} mysql -u {config['database']['user']} marzban") 
                    subprocess.run(restore_cmd, shell=True, check=True) 
                    log_message("MySQL database 'marzban' restored successfully.", "success") 
            else: 
                log_message("ℹ️ No MySQL backup data found. Skipping MySQL restore steps.", "info") 

            # --- CHANGE 2: Final restart logic replaced for reliability --- 
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
    """Interactive restore flow for the CLI menu.""" 
    show_header() 
    console.print(Panel( 
        "[bold]This is a highly destructive operation.[/bold]\nIt will [danger]STOP[/danger] services, " 
        "[danger]DELETE[/danger] databases and MySQL data, and [danger]OVERWRITE[/danger] all Marzban data.", 
        title="[warning]CRITICAL WARNING[/warning]", border_style="danger" 
    )) 
    if not Confirm.ask("[danger]Do you understand the risks and wish to continue?[/danger]"): 
        log_message("Restore operation cancelled.", "info"); return 
     
    config = get_config() 
    zip_path = None 
     
    console.print(Panel( 
        "[menu]1[/menu]. Use a local backup file\n[menu]2[/menu]. Send backup file to Telegram bot", 
        title="Select Restore Source", border_style="info" 
    )) 
    choice = Prompt.ask("[prompt]Choose your method[/prompt]", choices=["1", "2"], default="1") 
     
    if choice == "1": 
        zip_path = Prompt.ask("[prompt]Enter the full path to your .zip backup file[/prompt]") 
        if not os.path.exists(zip_path): 
            log_message(f"File not found: '{zip_path}'. Aborting.", "danger"); return 
    elif choice == "2": 
        zip_path = download_from_telegram(config['telegram']) 
        if not zip_path: 
            log_message("Could not get backup from Telegram. Aborting.", "danger"); return 
     
    run_restore_process(zip_path, config) 
     
    if choice == "2" and zip_path and os.path.exists(zip_path): 
        os.remove(zip_path) 

def setup_cronjob_flow(interactive=True): 
    """Setup or update cronjob, skipping confirmation in non-interactive mode.""" 
    if interactive: 
        show_header() 
        console.print(Panel("Automatic Backup Setup (Cronjob)", style="info")) 

    config = load_config_file() 
    if not config or not config.get("telegram", {}).get('bot_token'): 
        log_message("Telegram Bot is not configured. Please run 'Setup Telegram Bot' from the main menu first.", "danger") 
        return False 

    if interactive: 
        config = get_config(ask_interval=True) 
         
    interval = config.get("telegram", {}).get('backup_interval') 
    if not interval: 
        log_message("Backup interval is not set. Please run this setup interactively from the panel menu first.", "danger") 
        return False 

    log_message("Performing an initial backup as a test...", "info") 
    try: 
        run_full_backup(config) 
        log_message("Initial backup test successful!", "success") 
    except Exception as e: 
        log_message(f"Initial backup test failed: {str(e)}", "danger") 
        if interactive: 
            if not Confirm.ask("[prompt]The test failed, but you can still try to set up the cronjob. Continue?[/prompt]", default=False): 
                return False 
        else: 
            return False 

    python_executable = sys.executable 
    script_path = os.path.abspath(__file__) 
    cron_command = f"*/{interval} * * * * {python_executable} {script_path} run-backup" 
     
    # --- This is the key change --- 
    # Only ask for confirmation in interactive mode 
    if interactive: 
        console.print(Panel(f"The following command will be added to crontab:\n\n[info]{cron_command}[/info]", title="Cronjob Command")) 
        if not Confirm.ask("[prompt]Do you authorize this action?[/prompt]"): 
            log_message("Automatic setup cancelled by user.", "info") 
            return False 
             
    log_message("Attempting to modify system crontab...", "info") 
    try: 
        CRONTAB_PATH = "/usr/bin/crontab" 
        current_crontab_process = subprocess.run([CRONTAB_PATH, '-l'], capture_output=True, text=True, check=False) 
        current_crontab = current_crontab_process.stdout 
        new_lines = [line for line in current_crontab.strip().split('\n') if CRON_JOB_IDENTIFIER not in line and line.strip()] 
        new_lines.append(f"{cron_command} {CRON_JOB_IDENTIFIER}") 
        new_crontab_content = "\n".join(new_lines) + "\n" 

        p = Popen([CRONTAB_PATH, '-'], stdin=PIPE, stdout=PIPE, stderr=PIPE) 
        stdout, stderr = p.communicate(input=new_crontab_content.encode()) 
         
        if p.returncode == 0: 
            log_message("✅ Crontab updated successfully!", "success") 
            print("✅ Crontab updated successfully!") 
            return True 
        else: 
            error_details = stderr.decode().strip() 
            raise Exception(f"crontab command failed. Error: {error_details}") 

    except Exception as e: 
        log_message(f"A critical error occurred while updating crontab: {str(e)}", "danger") 
        print(f"❌ A critical error occurred while updating crontab: {str(e)}") 
        return False 


def main(): 
    """Main function to dispatch tasks based on arguments or run interactively.""" 
    # --- NON-INTERACTIVE MODE (for Bot and Cron) --- 
    if len(sys.argv) > 1: 
        command = sys.argv[1] 

        # First, handle the special silent command before any logging. 
        if command == 'get-db-type': 
            db_type = "Unknown" 
            if os.path.exists("/var/lib/marzban/db.sqlite3"): 
                db_type = "SQLite" 
            try: 
                subprocess.run( 
                    "docker ps --format '{{.Names}} {{.Image}}' | grep -E 'mysql|mariadb' | grep -q 'marzban'", 
                    shell=True, check=True, capture_output=True 
                ) 
                db_type = "MySQL" 
            except subprocess.CalledProcessError: 
                pass 
            print(json.dumps({"database_type": db_type})) 
            sys.exit(0) 

        # NOW, we can log for all OTHER non-interactive commands. 
        logger.info(f"Running in Non-Interactive Mode, command: {command}") 

        config = load_config_file() 
        if not config: 
            print("❌ Error: config.json not found. Please run the script interactively to create it first.") 
            sys.exit(1) 

        if command in ['run-backup', 'do-backup']: 
            try: 
                run_full_backup(config, is_cron=(command == 'run-backup')) 
                sys.exit(0) 
            except Exception as e: 
                sys.exit(1) 
         
        elif command == 'do-restore': 
            if len(sys.argv) < 3: 
                print("❌ Error: Restore command called without a file path.") 
                sys.exit(1) 
            zip_path = sys.argv[2] 
            if not os.path.exists(zip_path): 
                 print(f"❌ Error: Restore file not found: {zip_path}") 
                 sys.exit(1) 
             
            if run_restore_process(zip_path, config): 
                sys.exit(0) 
            else: 
                sys.exit(1) 

        elif command == 'do-auto-backup-setup': 
            if setup_cronjob_flow(interactive=False): 
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
            config = load_config_file() 
            if not config or not config.get('telegram',{}).get('bot_token'): 
                log_message("Telegram details not found, running full setup...", "info") 
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
if __name__ == "__main__": 
    try: 
        main() 
    except KeyboardInterrupt: 
        log_message("\nApplication exited by user.", "warning") 
        logger.info("Application exited by user (KeyboardInterrupt)") 
        sys.exit(0) 
    except Exception as e: 
        log_message(f"An unexpected fatal error occurred: {str(e)}", "danger") 
        logger.error(f"Unexpected fatal error: {str(e)}", exc_info=True) 
        sys.exit(1)
