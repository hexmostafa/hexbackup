#!/usr/bin/env python3
# =================================================================
# Marzban Professional Control Bot
# Creator: @HEXMOSTAFA
# Version: 3.0 (Modern, UX-Focused, Robust)
#
# Features:
# - Live message updates for a clean chat experience.
# - Emojis and structured messages for clarity.
# - Stopwatch for long operations.
# - Robust error handling and state management.
# =================================================================

import os
import json
import subprocess
import logging
import time
from datetime import datetime

# --- Third-party Library Check ---
try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
except ImportError:
    print("FATAL ERROR: 'pyTelegramBotAPI' is not installed. Please run 'pip install pyTelegramBotAPI' to continue.")
    exit(1)


# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
MAIN_PANEL_SCRIPT = os.path.join(SCRIPT_DIR, "marzban_panel.py")
LOG_FILE = os.path.join(SCRIPT_DIR, "marzban_bot.log")

# --- Emojis for UI ---
EMOJI = {
    "BACKUP": "📦", "RESTORE": "🔄", "AUTO": "⚙️", "SETTINGS": "🛠️",
    "SUCCESS": "✅", "ERROR": "❌", "WAIT": "⏳", "INFO": "ℹ️",
    "CANCEL": "🚫", "BACK": "⬅️", "KEY": "🔑", "DANGER": "🛑"
}

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- Load Configuration ---
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    BOT_TOKEN = config.get('telegram', {}).get('bot_token')
    ADMIN_CHAT_ID = int(config.get('telegram', {}).get('admin_chat_id'))
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        raise ValueError("Bot Token or Admin Chat ID is missing in config.json")
except Exception as e:
    logger.critical(f"FATAL: Could not load or parse config.json. Please run the main panel script first to generate it. Error: {e}")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
user_states = {} # Simple state management: {chat_id: {'state': '...', 'data': {...}}}

# --- Helper Functions ---
def run_main_script(args: list) -> (bool, str, str):
    """Executes the main panel script and returns success status, output, and duration."""
    command = ['sudo', 'python3', MAIN_PANEL_SCRIPT] + args
    logger.info(f"Executing: {' '.join(command)}")
    start_time = time.time()
    try:
        # Increased timeout for potentially long operations like restore
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
        duration = f"{time.time() - start_time:.2f}"
        
        if result.returncode == 0:
            output = result.stdout.strip() or "Operation completed with no output."
            logger.info(f"Script successful. Duration: {duration}s. Output:\n{output}")
            return True, output, duration
        else:
            output = result.stderr.strip() or "Operation failed with no error message."
            logger.error(f"Script failed. Duration: {duration}s. Error:\n{output}")
            return False, output, duration
            
    except subprocess.TimeoutExpired:
        duration = f"{time.time() - start_time:.2f}"
        logger.error(f"Script timed out after 900 seconds.")
        return False, "Operation timed out.", duration
    except Exception as e:
        duration = f"{time.time() - start_time:.2f}"
        logger.critical(f"A critical Python error occurred while running subprocess: {e}", exc_info=True)
        return False, f"A critical error occurred in the bot's execution engine:\n`{e}`", duration

def admin_only(func):
    """Decorator to ensure only the admin can use the bot."""
    def wrapper(message_or_call):
        chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
        if chat_id != ADMIN_CHAT_ID:
            bot.send_message(chat_id, f"{EMOJI['DANGER']} You are not authorized to use this bot.")
            logger.warning(f"Unauthorized access attempt from chat ID: {chat_id}")
            return
        return func(message_or_call)
    return wrapper

# --- Keyboards ---
def main_menu_keyboard():
    return InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton(f"{EMOJI['BACKUP']} Backup", callback_data="create_backup"),
        InlineKeyboardButton(f"{EMOJI['RESTORE']} Restore", callback_data="start_restore"),
        InlineKeyboardButton(f"{EMOJI['AUTO']} Auto Backup", callback_data="setup_auto_backup"),
        InlineKeyboardButton(f"{EMOJI['SETTINGS']} Settings", callback_data="view_settings")
    )

def back_to_main_menu_keyboard():
    return InlineKeyboardMarkup().add(InlineKeyboardButton(f"{EMOJI['BACK']} Back to Main Menu", callback_data="main_menu"))

def cancel_keyboard(action="Operation"):
    return InlineKeyboardMarkup().add(InlineKeyboardButton(f"{EMOJI['CANCEL']} Cancel {action}", callback_data="cancel"))

# --- Message Handlers ---
@bot.message_handler(commands=['start', 'help'])
@admin_only
def send_welcome(message):
    text = f"🤖 *HexBackup Control Panel*\n\nWelcome, Admin! This bot helps you manage your Marzban backups.\n\n_Last restart: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
    bot.send_message(message.chat.id, text, reply_markup=main_menu_keyboard())

# --- Main Callback Handler ---
@bot.callback_query_handler(func=lambda call: True)
@admin_only
def handle_callback_query(call):
    """Handles all button clicks from inline keyboards."""
    bot.answer_callback_query(call.id)
    action = call.data

    # Clear any pending state if the user chooses a new top-level action
    if action in ["create_backup", "start_restore", "setup_auto_backup", "view_settings", "main_menu"]:
        user_states.pop(call.message.chat.id, None)

    if action == "main_menu":
        text = "🤖 *HexBackup Control Panel*\n\nWhat would you like to do next?"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())
    elif action == "cancel":
        user_states.pop(call.message.chat.id, None)
        bot.edit_message_text(f"{EMOJI['CANCEL']} Operation cancelled.", call.message.chat.id, call.message.message_id, reply_markup=back_to_main_menu_keyboard())
    elif action == "create_backup":
        handle_backup(call.message)
    elif action == "start_restore":
        handle_restore(call.message)
    elif action == "setup_auto_backup":
        user_states[call.message.chat.id] = {'state': 'awaiting_interval'}
        text = f"{EMOJI['INFO']} Please enter the backup interval in *minutes*.\n\n(e.g., `60` for every hour, `1440` for every day)"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=cancel_keyboard("Setup"))
    elif action == "view_settings":
        # This can be expanded later
        text = "*Settings Menu*\n\nThis section is under development. More features coming soon!"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_to_main_menu_keyboard())

# --- Feature Functions ---
def handle_backup(message):
    bot.edit_message_text(f"{EMOJI['WAIT']} *Creating Full Backup...*\n\nThis may take a moment. The final backup file will be sent here.", message.chat.id, message.message_id)
    
    success, output, duration = run_main_script(['do-backup'])
    
    if success:
        # The panel script sends the file, so we just confirm here.
        final_text = f"{EMOJI['SUCCESS']} *Backup Process Initiated*\n\nYour backup file should arrive shortly.\n\n`Operation finished in {duration} seconds.`"
    else:
        final_text = f"{EMOJI['ERROR']} *Backup Failed*\n\nAn error occurred during the backup process.\n\n*Details:*\n```{output}```"
    
    # Use a new message to show the final status, as the file will be sent separately.
    bot.send_message(message.chat.id, final_text, reply_markup=main_menu_keyboard())

def handle_restore(message):
    user_states[message.chat.id] = {'state': 'awaiting_restore_file'}
    text = f"{EMOJI['DANGER']} *Restore Danger Zone* {EMOJI['DANGER']}\n\nThis is a destructive operation. Please send your `.tar.gz` backup file to proceed."
    bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=cancel_keyboard("Restore"))

# --- State-Based Input Handler ---
@bot.message_handler(content_types=['text', 'document'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_stateful_messages(message):
    state_info = user_states.pop(message.chat.id)
    state = state_info['state']

    if state == 'awaiting_interval':
        try:
            interval = int(message.text)
            if interval <= 0: raise ValueError("Interval must be positive.")

            # Update config.json with the new interval
            with open(CONFIG_FILE, 'r+') as f:
                data = json.load(f)
                data['telegram']['backup_interval'] = str(interval)
                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
            
            bot.send_message(message.chat.id, f"{EMOJI['WAIT']} Interval set to `{interval}` minutes. Now running the auto-backup setup script...")
            success, output, duration = run_main_script(['do-auto-backup-setup'])

            if success:
                final_text = f"{EMOJI['SUCCESS']} *Auto Backup Configured!*\n\nCronjob has been set up to run every {interval} minutes.\n\n`Setup finished in {duration} seconds.`"
            else:
                final_text = f"{EMOJI['ERROR']} *Auto Backup Setup Failed*\n\n*Details:*\n```{output}```"
            
            bot.send_message(message.chat.id, final_text, reply_markup=main_menu_keyboard())

        except ValueError:
            bot.send_message(message.chat.id, f"{EMOJI['ERROR']} Invalid input. Please enter a positive number. Operation cancelled.", reply_markup=main_menu_keyboard())
        except Exception as e:
            logger.error(f"Failed to set interval: {e}", exc_info=True)
            bot.send_message(message.chat.id, f"{EMOJI['ERROR']} An unexpected error occurred while saving the configuration.", reply_markup=main_menu_keyboard())

    elif state == 'awaiting_restore_file':
        if message.content_type != 'document' or not message.document.file_name.endswith('.tar.gz'):
            bot.send_message(message.chat.id, f"{EMOJI['ERROR']} Invalid file type. Please send a `.tar.gz` archive. Restore cancelled.", reply_markup=main_menu_keyboard())
            return
        
        status_msg = bot.send_message(message.chat.id, f"{EMOJI['INFO']} File received. Preparing for restore...")
        
        temp_archive_path = None
        try:
            bot.edit_message_text(f"{EMOJI['WAIT']} *Downloading file...*\n\n`{message.document.file_name}`", status_msg.chat.id, status_msg.message_id)
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            temp_dir = "/tmp"
            os.makedirs(temp_dir, exist_ok=True)
            temp_archive_path = os.path.join(temp_dir, message.document.file_name)
            with open(temp_archive_path, 'wb') as f:
                f.write(downloaded_file)
            
            bot.edit_message_text(f"{EMOJI['WAIT']} *Download Complete. Starting Restore...*\n\nThis is a long process. Please wait.", status_msg.chat.id, status_msg.message_id)

            success, output, duration = run_main_script(['do-restore', temp_archive_path])

            if success:
                final_text = f"{EMOJI['SUCCESS']} *Restore Completed!*\n\nThe system has been restored from the backup.\n\n`Process finished in {duration} seconds.`"
            else:
                final_text = f"{EMOJI['ERROR']} *Restore Failed*\n\nAn error occurred during the restore process.\n\n*Details:*\n```{output}```"
            
            bot.edit_message_text(final_text, status_msg.chat.id, status_msg.message_id, reply_markup=main_menu_keyboard())

        except Exception as e:
            logger.error(f"An error occurred during the restore file handling: {e}", exc_info=True)
            bot.edit_message_text(f"{EMOJI['ERROR']} A critical error occurred in the bot: `{e}`", status_msg.chat.id, status_msg.message_id, reply_markup=main_menu_keyboard())
        
        finally:
            if temp_archive_path and os.path.exists(temp_archive_path):
                os.remove(temp_archive_path)
                logger.info(f"Cleaned up temporary file: {temp_archive_path}")

if __name__ == '__main__':
    logger.info("Starting HexBackup Control Bot (Version 3.0)...")
    try:
        bot.infinity_polling(timeout=120, logger_level=logging.WARNING)
    except Exception as e:
        logger.critical(f"Bot has crashed with a critical error: {e}", exc_info=True)
        time.sleep(10) # Wait before exiting, in case it's in a restart loop
