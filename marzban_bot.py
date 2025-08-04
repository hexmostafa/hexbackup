#!/usr/bin/env python3
# =================================================================
# Marzban Professional Control Bot - Final Version
# Creator: @HEXMOSTAFA
# Version: 4.0.0 (Complete & Stable)
#
# This is a complete, all-in-one bot script with all features integrated.
# =================================================================
import os
import json
import subprocess
import logging
import time
from typing import Tuple, List

try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
except ImportError:
    print("FATAL ERROR: 'pyTelegramBotAPI' is not installed. Please run 'pip install pyTelegramBotAPI'.")
    exit(1)

# --- Global Configurations & Emojis ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
# Make sure this matches the name of your main panel script
MAIN_PANEL_SCRIPT = os.path.join(SCRIPT_DIR, "marzban_panel.py")
LOG_FILE = os.path.join(SCRIPT_DIR, "marzban_bot.log")

EMOJI = {
    "BACKUP": "📦", "RESTORE": "🔄", "AUTO": "⚙️", "SETTINGS": "🛠️",
    "SUCCESS": "✅", "ERROR": "❌", "WAIT": "⏳", "INFO": "ℹ️",
    "CANCEL": "🚫", "BACK": "⬅️", "KEY": "🔑", "DANGER": "🛑",
    "EDIT": "📝", "DB": "🗄️", "CLOCK": "⏱️", "WELCOME": "👋"
}

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Load Configuration ---
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    BOT_TOKEN = config.get('telegram', {}).get('bot_token')
    ADMIN_CHAT_ID = int(config.get('telegram', {}).get('admin_chat_id'))
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        raise ValueError("Bot Token or Admin Chat ID is missing in config.json.")
except Exception as e:
    logger.critical(f"FATAL: Could not load or parse config.json. Error: {e}")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
user_states = {}  # For handling multi-step interactions

# --- Helper Functions ---
def run_main_script(args: List[str]) -> Tuple[bool, str, str]:
    """Executes the main panel script with given arguments."""
    python_executable = subprocess.run(['which', 'python3'], capture_output=True, text=True).stdout.strip() or "python3"
    command = ['sudo', python_executable, MAIN_PANEL_SCRIPT] + args
    start_time = time.time()
    try:
        # Long timeout for potentially long operations like restore
        result = subprocess.run(command, capture_output=True, text=True, timeout=1200)
        duration = f"{time.time() - start_time:.2f}"
        if result.returncode == 0:
            return True, result.stdout.strip() or "Operation successful.", duration
        else:
            # Combine stdout and stderr for a more detailed error message
            error_details = (result.stderr.strip() or "No stderr") + "\n" + (result.stdout.strip() or "No stdout")
            return False, error_details.strip(), duration
    except subprocess.TimeoutExpired:
        return False, "Critical Error: Operation timed out after 20 minutes.", f"{time.time() - start_time:.2f}"
    except Exception as e:
        return False, f"A critical Python error occurred: {e}", f"{time.time() - start_time:.2f}"

def admin_only(func):
    """Decorator to restrict access to the admin only."""
    def wrapper(message_or_call):
        chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
        if chat_id != ADMIN_CHAT_ID:
            logger.warning(f"Unauthorized access attempt from chat_id: {chat_id}")
            return
        return func(message_or_call)
    return wrapper

# --- Keyboards ---
def main_menu_keyboard():
    return InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton(f"{EMOJI['BACKUP']} Create Backup", callback_data="create_backup"),
        InlineKeyboardButton(f"{EMOJI['RESTORE']} Restore from Backup", callback_data="start_restore"),
        InlineKeyboardButton(f"{EMOJI['AUTO']} Auto-Backup Setup", callback_data="setup_auto_backup"),
        InlineKeyboardButton(f"{EMOJI['SETTINGS']} View Settings", callback_data="view_settings")
    )

def settings_keyboard():
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(f"{EMOJI['EDIT']} Edit Backup Interval", callback_data="edit_interval_start"),
        InlineKeyboardButton(f"{EMOJI['BACK']} Back to Main Menu", callback_data="main_menu")
    )

# --- Message & Callback Handlers ---

@bot.message_handler(commands=['start'])
@admin_only
def handle_start(message):
    """Handles the /start command and displays the main menu."""
    text = f"{EMOJI['WELCOME']} *Marzban Control Bot*\n\nHello! Please choose an option from the menu below."
    bot.send_message(message.chat.id, text, reply_markup=main_menu_keyboard())

@bot.callback_query_handler(func=lambda call: True)
@admin_only
def handle_callback_query(call):
    """Handles all button clicks."""
    bot.answer_callback_query(call.id)
    action = call.data
    message = call.message

    if action == "main_menu":
        text = "*Main Menu*\n\nPlease choose an option."
        bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=main_menu_keyboard())

    elif action == "create_backup":
        bot.edit_message_text(f"{EMOJI['WAIT']} *Creating Backup...*\nThis might take a moment. The bot will notify you upon completion.", message.chat.id, message.message_id)
        success, output, duration = run_main_script(['do-backup'])
        final_text = f"{EMOJI['SUCCESS']} *Manual backup sent to Telegram!*\n\n`Operation took {duration} seconds.`" if success else f"{EMOJI['ERROR']} *Backup Failed!*\n\n*Details:*\n```{output}```"
        bot.edit_message_text(final_text, message.chat.id, message.message_id, reply_markup=main_menu_keyboard())

    elif action == "start_restore":
        user_states[message.chat.id] = {'state': 'awaiting_restore_file'}
        text = f"{EMOJI['DANGER']} *Restore Process*\n\nPlease send the `.tar.gz` backup file now.\n\n*Warning: This is a destructive operation and will overwrite current data.*"
        bot.edit_message_text(text, message.chat.id, message.message_id)

    elif action == "view_settings":
        display_settings(message)

    elif action == "edit_interval_start":
        user_states[message.chat.id] = {'state': 'awaiting_new_interval'}
        text = f"{EMOJI['INFO']} Please enter the new auto-backup interval in *minutes* (e.g., `60`)."
        bot.edit_message_text(text, message.chat.id, message.message_id)

    elif action == "setup_auto_backup":
        user_states[message.chat.id] = {'state': 'awaiting_interval'}
        text = f"{EMOJI['INFO']} To set up automatic backups, please enter the interval in *minutes* (e.g., `60`)."
        bot.edit_message_text(text, message.chat.id, message.message_id)

def display_settings(message):
    """Fetches and displays current settings."""
    bot.edit_message_text(f"{EMOJI['WAIT']} Fetching system information...", message.chat.id, message.message_id)
    with open(CONFIG_FILE, 'r') as f: current_config = json.load(f)
    tele_conf = current_config.get("telegram", {})
    db_conf = current_config.get("database", {})
    interval = tele_conf.get('backup_interval', 'Not Set')
    db_user = db_conf.get('user', 'N/A')
    db_pass = db_conf.get('password', 'N/A')
    db_pass_masked = f"{db_pass[0]}***{db_pass[-1]}" if len(str(db_pass)) > 2 else "Not Set"

    text = f"""
{EMOJI['SETTINGS']} *Current System Settings*
---
*Admin Chat ID:* `{tele_conf.get('admin_chat_id', 'N/A')}`
*Auto-Backup Interval:* `{interval}` minutes
*Database User:* `{db_user}`
*Database Password:* `{db_pass_masked}`
"""
    bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=settings_keyboard())

@bot.message_handler(content_types=['text'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_stateful_text(message):
    """Handles text input when the bot is waiting for it (e.g., interval setup)."""
    state_info = user_states.pop(message.chat.id, None)
    if not state_info: return
    state = state_info['state']

    if state in ['awaiting_interval', 'awaiting_new_interval']:
        try:
            interval = int(message.text)
            if interval <= 0: raise ValueError("Interval must be a positive number.")

            with open(CONFIG_FILE, 'r+') as f:
                data = json.load(f)
                data.setdefault('telegram', {})['backup_interval'] = str(interval)
                f.seek(0); json.dump(data, f, indent=4); f.truncate()

            bot.send_message(message.chat.id, f"{EMOJI['WAIT']} Interval set to `{interval}` minutes. Updating system schedule (cronjob)...")
            success, output, duration = run_main_script(['do-auto-backup-setup'])
            final_text = f"{EMOJI['SUCCESS']} *Auto-Backup Setup Complete!*\n\nSchedule updated to run every {interval} minutes.\n\n`Operation took {duration} seconds.`" if success else f"{EMOJI['ERROR']} *Setup Failed!*\n\n*Details:*\n```{output}```"
            bot.send_message(message.chat.id, final_text, reply_markup=main_menu_keyboard())

        except ValueError:
            bot.send_message(message.chat.id, f"{EMOJI['ERROR']} Invalid input. Please enter a positive number (e.g., 60).", reply_markup=main_menu_keyboard())
        except Exception as e:
            logger.error(f"Failed to update interval: {e}")
            bot.send_message(message.chat.id, f"{EMOJI['ERROR']} An internal error occurred while saving the configuration.", reply_markup=main_menu_keyboard())

@bot.message_handler(content_types=['document'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_restore_file(message):
    """Handles the backup file uploaded for restoration."""
    state_info = user_states.pop(message.chat.id, None)
    if not state_info or state_info['state'] != 'awaiting_restore_file': return

    if not message.document.file_name.endswith('.tar.gz'):
        bot.send_message(message.chat.id, f"{EMOJI['ERROR']} Invalid file type. Please send a `.tar.gz` file.", reply_markup=main_menu_keyboard())
        return

    bot.send_message(message.chat.id, f"{EMOJI['WAIT']} Downloading file `{message.document.file_name}`...")
    restore_file_path = None
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        temp_dir = "/tmp"
        os.makedirs(temp_dir, exist_ok=True)
        restore_file_path = os.path.join(temp_dir, f"restore_{int(time.time())}.tar.gz")
        with open(restore_file_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.send_message(message.chat.id, f"{EMOJI['DANGER']} *Starting restore process...*\nThis will take several minutes. The bot will notify you upon completion. Please do not send other commands.")
        success, output, duration = run_main_script(['do-restore', restore_file_path])
        final_text = f"{EMOJI['SUCCESS']} *Restore Completed Successfully!*\n\nMarzban has been restored and restarted.\n\n`Operation took {duration} seconds.`" if success else f"{EMOJI['ERROR']} *Restore Failed!*\n\n*Details:*\n```{output}```"
        bot.send_message(message.chat.id, final_text, reply_markup=main_menu_keyboard())

    except Exception as e:
        logger.error(f"Error during restore file handling: {e}", exc_info=True)
        bot.send_message(message.chat.id, f"{EMOJI['ERROR']} A critical error occurred while handling the file: {e}", reply_markup=main_menu_keyboard())
    finally:
        # Clean up the downloaded file
        if restore_file_path and os.path.exists(restore_file_path):
            os.remove(restore_file_path)

# --- Bot Execution ---
if __name__ == '__main__':
    logger.info(f"Starting HexBackup Control Bot (Version 4.0.0) for Admin ID: {ADMIN_CHAT_ID}...")
    # This loop ensures the bot restarts automatically if it crashes
    while True:
        try:
            bot.infinity_polling(timeout=120, logger_level=logging.WARNING)
        except Exception as e:
            logger.critical(f"Bot crashed with a critical error: {e}", exc_info=True)
            logger.info("Restarting bot in 10 seconds...")
            time.sleep(10)
