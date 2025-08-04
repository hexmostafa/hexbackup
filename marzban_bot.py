#!/usr/bin/env python3
# =================================================================
# Marzban Professional Control Bot - UI/UX Focused Edition
# Creator: @HEXMOSTAFA
# Version: 5.0.0 (Phoenix)
#
# A complete redesign focusing on a professional, intuitive,
# and safe user experience.
# =================================================================
import os
import json
import subprocess
import logging
import time
from datetime import datetime
from typing import Tuple, List, Optional

try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
except ImportError:
    print("FATAL ERROR: 'pyTelegramBotAPI' is not installed. Please run 'pip install pyTelegramBotAPI'.")
    exit(1)

# --- Global Configurations & Emojis ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
MAIN_PANEL_SCRIPT = os.path.join(SCRIPT_DIR, "marzban_panel.py")
LOG_FILE = os.path.join(SCRIPT_DIR, "marzban_bot.log")
# A state file to keep track of bot's operational data like last backup time
BOT_STATE_FILE = os.path.join(SCRIPT_DIR, "bot_state.json")

EMOJI = {
    "PANEL": "📱", "BACKUP": "📦", "RESTORE": "🔄", "SETTINGS": "⚙️",
    "SUCCESS": "✅", "ERROR": "❌", "WAIT": "⏳", "INFO": "ℹ️",
    "WARNING": "⚠️", "BACK": "⬅️", "DANGER": "🛑", "EDIT": "📝",
    "CLOCK": "⏱️", "WELCOME": "👋", "STATUS": "📊", "CONFIRM": "👍"
}

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# --- Load Configuration & State ---
try:
    with open(CONFIG_FILE, 'r') as f: config = json.load(f)
    BOT_TOKEN = config.get('telegram', {}).get('bot_token')
    ADMIN_CHAT_ID = int(config.get('telegram', {}).get('admin_chat_id'))
    if not BOT_TOKEN or not ADMIN_CHAT_ID: raise ValueError("Bot Token or Admin Chat ID is missing.")
except Exception as e:
    logger.critical(f"FATAL: Could not load config.json. Error: {e}")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
user_states = {}

def update_bot_state(key: str, value: any):
    """Updates and saves the bot's state (e.g., last backup time)."""
    state = {}
    if os.path.exists(BOT_STATE_FILE):
        with open(BOT_STATE_FILE, 'r') as f:
            try: state = json.load(f)
            except json.JSONDecodeError: pass
    state[key] = value
    with open(BOT_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def get_bot_state() -> dict:
    if not os.path.exists(BOT_STATE_FILE): return {}
    with open(BOT_STATE_FILE, 'r') as f:
        try: return json.load(f)
        except json.JSONDecodeError: return {}

# --- Helper Functions --- (Mostly Unchanged)
def run_main_script(args: List[str]) -> Tuple[bool, str, str]:
    python_executable = subprocess.run(['which', 'python3'], capture_output=True, text=True).stdout.strip() or "python3"
    command = ['sudo', python_executable, MAIN_PANEL_SCRIPT] + args
    start_time = time.time()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=1200)
        duration = f"{time.time() - start_time:.2f}"
        if result.returncode == 0:
            return True, result.stdout.strip() or "Operation successful.", duration
        else:
            error_details = (result.stderr.strip() or "No stderr") + "\n" + (result.stdout.strip() or "No stdout")
            return False, error_details.strip(), duration
    except subprocess.TimeoutExpired:
        return False, "Critical Error: Operation timed out after 20 minutes.", f"{time.time() - start_time:.2f}"
    except Exception as e:
        return False, f"A critical Python error occurred: {e}", f"{time.time() - start_time:.2f}"

def admin_only(func):
    def wrapper(message_or_call):
        chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
        if chat_id != ADMIN_CHAT_ID:
            logger.warning(f"Unauthorized access from chat_id: {chat_id}")
            return
        return func(message_or_call)
    return wrapper

# --- Keyboards ---
def main_menu_keyboard():
    return InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton(f"{EMOJI['BACKUP']} New Backup", callback_data="do_backup"),
        InlineKeyboardButton(f"{EMOJI['RESTORE']} Restore Data", callback_data="restore_start"),
        InlineKeyboardButton(f"{EMOJI['SETTINGS']} Settings", callback_data="settings_menu")
    )

def settings_menu_keyboard():
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(f"{EMOJI['EDIT']} Change Auto-Backup Interval", callback_data="settings_edit_interval"),
        InlineKeyboardButton(f"{EMOJI['INFO']} View Full Configuration", callback_data="settings_view_config"),
        InlineKeyboardButton(f"{EMOJI['BACK']} Back to Main Menu", callback_data="main_menu")
    )

def restore_confirmation_keyboard():
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(f"{EMOJI['CONFIRM']} Yes, I understand. Proceed.", callback_data="restore_confirm"),
        InlineKeyboardButton(f"{EMOJI['BACK']} Cancel & Go Back", callback_data="main_menu")
    )

# --- Message Display Functions ---
def display_main_menu(message):
    """Displays the main dashboard menu."""
    bot_state = get_bot_state()
    last_backup_time = bot_state.get('last_backup_time', 'Never')
    if last_backup_time != 'Never':
        last_backup_time = datetime.fromisoformat(last_backup_time).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    with open(CONFIG_FILE, 'r') as f: current_config = json.load(f)
    interval = current_config.get('telegram', {}).get('backup_interval')
    auto_backup_status = f"Active (Every {interval} mins)" if interval else "Inactive"
    
    text = f"""
{EMOJI['PANEL']} *Marzban Control Panel*
{EMOJI['STATUS']} *Dashboard*
> *Last Backup:* `{last_backup_time}`
> *Auto-Backup:* `{auto_backup_status}`
"""
    try:
        bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=main_menu_keyboard())
    except telebot.apihelper.ApiTelegramException: # If message is the same
        bot.send_message(message.chat.id, text, reply_markup=main_menu_keyboard())


# --- Message & Callback Handlers ---
@bot.message_handler(commands=['start'])
@admin_only
def handle_start(message):
    display_main_menu(message)

@bot.callback_query_handler(func=lambda call: True)
@admin_only
def handle_callbacks(call):
    bot.answer_callback_query(call.id)
    action = call.data
    message = call.message

    if action == "main_menu":
        display_main_menu(message)

    elif action == "do_backup":
        bot.edit_message_text(f"{EMOJI['WAIT']} *Creating Backup...*\nThis can take a few minutes. Please wait.", message.chat.id, message.message_id)
        success, output, duration = run_main_script(['do-backup'])
        if success:
            update_bot_state('last_backup_time', datetime.utcnow().isoformat())
            final_text = f"{EMOJI['SUCCESS']} *Backup Complete!*\n\nFile sent to your chat.\n`Operation took {duration} seconds.`"
        else:
            final_text = f"{EMOJI['ERROR']} *Backup Failed!*\n\n*Details:*\n```{output}```"
        bot.edit_message_text(final_text, message.chat.id, message.message_id)
        time.sleep(2) # Give user time to read before showing menu
        display_main_menu(message)

    elif action == "restore_start":
        text = f"""
{EMOJI['DANGER']} *CRITICAL WARNING* {EMOJI['DANGER']}
You are about to restore data. This action will **completely overwrite** your current Marzban configuration and database.

*This cannot be undone.*

Are you absolutely sure you want to proceed?
"""
        bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=restore_confirmation_keyboard())

    elif action == "restore_confirm":
        user_states[message.chat.id] = {'state': 'awaiting_restore_file'}
        text = f"{EMOJI['INFO']} Please send the `.tar.gz` backup file to restore."
        bot.edit_message_text(text, message.chat.id, message.message_id)

    elif action == "settings_menu":
        text = f"{EMOJI['SETTINGS']} *Settings Menu*\n\nHere you can manage auto-backup settings and view your current configuration."
        bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=settings_menu_keyboard())

    elif action == "settings_edit_interval":
        user_states[message.chat.id] = {'state': 'awaiting_interval'}
        text = f"{EMOJI['CLOCK']} Please enter the new auto-backup interval in *minutes* (e.g., `60`).\n\nEnter `0` to disable auto-backup."
        bot.edit_message_text(text, message.chat.id, message.message_id)

    elif action == "settings_view_config":
        with open(CONFIG_FILE, 'r') as f: current_config = json.load(f)
        config_text = json.dumps(current_config, indent=2)
        text = f"{EMOJI['INFO']} *Full Configuration (`config.json`)*\n\n```json\n{config_text}\n```"
        bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(f"{EMOJI['BACK']} Back to Settings", callback_data="settings_menu")))

@bot.message_handler(content_types=['text'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_stateful_text(message):
    state_info = user_states.pop(message.chat.id, None)
    if not state_info: return
    
    if state_info['state'] == 'awaiting_interval':
        try:
            interval = int(message.text)
            if interval < 0: raise ValueError("Interval cannot be negative.")

            with open(CONFIG_FILE, 'r+') as f:
                data = json.load(f)
                data.setdefault('telegram', {})
                if interval == 0:
                    data['telegram'].pop('backup_interval', None)
                    action_text = "disabled"
                else:
                    data['telegram']['backup_interval'] = str(interval)
                    action_text = f"set to `{interval}` minutes"
                f.seek(0); json.dump(data, f, indent=4); f.truncate()
            
            bot.send_message(message.chat.id, f"{EMOJI['WAIT']} Auto-backup has been {action_text}. Applying changes to system schedule...")
            success, output, duration = run_main_script(['do-auto-backup-setup'])
            final_text = f"{EMOJI['SUCCESS']} *Schedule Updated!*\n\n`Operation took {duration} seconds.`" if success else f"{EMOJI['ERROR']} *Update Failed!*\n\n*Details:*\n```{output}```"
            bot.send_message(message.chat.id, final_text)
            time.sleep(2)
            display_main_menu(message)
        except (ValueError, TypeError):
            bot.send_message(message.chat.id, f"{EMOJI['ERROR']} Invalid input. Please enter a number (e.g., 60 or 0).")
            display_main_menu(message)

@bot.message_handler(content_types=['document'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_restore_document(message):
    state_info = user_states.pop(message.chat.id, None)
    if not state_info or state_info['state'] != 'awaiting_restore_file': return

    if not message.document.file_name.endswith('.tar.gz'):
        bot.send_message(message.chat.id, f"{EMOJI['ERROR']} Invalid file. Please send a `.tar.gz` archive.")
        display_main_menu(message)
        return

    bot.send_message(message.chat.id, f"{EMOJI['WAIT']} Downloading file...")
    restore_file_path = None
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        restore_file_path = os.path.join("/tmp", f"restore_{int(time.time())}.tar.gz")
        with open(restore_file_path, 'wb') as f: f.write(downloaded_file)

        bot.send_message(message.chat.id, f"{EMOJI['WARNING']} *Restore in progress...*\nThis will take several minutes. The bot will be unresponsive until it's done.")
        success, output, duration = run_main_script(['do-restore', restore_file_path])
        if success:
            update_bot_state('last_backup_time', 'Never (Just Restored)')
            final_text = f"{EMOJI['SUCCESS']} *Restore Complete!*\n\nYour system has been restored and restarted.\n`Operation took {duration} seconds.`"
        else:
            final_text = f"{EMOJI['ERROR']} *Restore Failed!*\n\n*Details:*\n```{output}```"
        bot.send_message(message.chat.id, final_text)
        time.sleep(2)
        display_main_menu(message)
    finally:
        if restore_file_path and os.path.exists(restore_file_path): os.remove(restore_file_path)

# --- Bot Execution ---
if __name__ == '__main__':
    logger.info(f"Starting Bot v5.0 (Phoenix) for Admin ID: {ADMIN_CHAT_ID}...")
    while True:
        try:
            bot.infinity_polling(timeout=120, logger_level=logging.WARNING)
        except Exception as e:
            logger.critical(f"Bot crashed: {e}", exc_info=True)
            time.sleep(10)
