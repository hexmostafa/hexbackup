#!/usr/bin/env python3
# =================================================================
# Marzban Professional Control Bot - On/Off Toggle Edition
# Creator: @HEXMOSTAFA
# Version: 5.1.0 (Phoenix+)
#
# Features a dedicated On/Off toggle for Auto-Backup for a
# superior and more intuitive user experience.
# =================================================================
import os
import json
import subprocess
import logging
import time
from datetime import datetime
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
MAIN_PANEL_SCRIPT = os.path.join(SCRIPT_DIR, "marzban_panel.py")
LOG_FILE = os.path.join(SCRIPT_DIR, "marzban_bot.log")
BOT_STATE_FILE = os.path.join(SCRIPT_DIR, "bot_state.json")

EMOJI = {
    "PANEL": "📱", "BACKUP": "📦", "RESTORE": "🔄", "SETTINGS": "⚙️",
    "SUCCESS": "✅", "ERROR": "❌", "WAIT": "⏳", "INFO": "ℹ️",
    "WARNING": "⚠️", "BACK": "⬅️", "DANGER": "🛑", "EDIT": "📝",
    "CLOCK": "⏱️", "WELCOME": "👋", "STATUS": "📊", "CONFIRM": "👍",
    "TOGGLE_ON": "🟢", "TOGGLE_OFF": "🔴"
}

# --- Logging & Config/State Loading ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

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
    state = get_bot_state()
    state[key] = value
    with open(BOT_STATE_FILE, 'w') as f: json.dump(state, f, indent=4)

def get_bot_state() -> dict:
    if not os.path.exists(BOT_STATE_FILE): return {}
    try:
        with open(BOT_STATE_FILE, 'r') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return {}

# --- Helper Functions ---
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
    except Exception as e:
        return False, f"A critical Python error occurred: {e}", f"{time.time() - start_time:.2f}"

def admin_only(func):
    def wrapper(message_or_call):
        chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
        if chat_id != ADMIN_CHAT_ID: return
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
    with open(CONFIG_FILE, 'r') as f: current_config = json.load(f)
    is_enabled = 'backup_interval' in current_config.get('telegram', {})
    
    toggle_text = f"{EMOJI['TOGGLE_OFF']} Disable Auto-Backup" if is_enabled else f"{EMOJI['TOGGLE_ON']} Enable Auto-Backup"
    toggle_action = "settings_autobackup_disable" if is_enabled else "settings_autobackup_enable"

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(toggle_text, callback_data=toggle_action))
    if is_enabled:
        markup.add(InlineKeyboardButton(f"{EMOJI['EDIT']} Change Interval", callback_data="settings_edit_interval"))
    markup.add(InlineKeyboardButton(f"{EMOJI['INFO']} View Full Configuration", callback_data="settings_view_config"))
    markup.add(InlineKeyboardButton(f"{EMOJI['BACK']} Back to Main Menu", callback_data="main_menu"))
    return markup

def restore_confirmation_keyboard():
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(f"{EMOJI['CONFIRM']} Yes, I understand. Proceed.", callback_data="restore_confirm"),
        InlineKeyboardButton(f"{EMOJI['BACK']} Cancel & Go Back", callback_data="main_menu")
    )

# --- UI Display Functions ---
def display_main_menu(message_or_call):
    """Displays the main dashboard menu."""
    chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
    message_id = message_or_call.message_id if hasattr(message_or_call, 'message_id') else message_or_call.message.message_id
    
    bot_state = get_bot_state()
    last_backup_time_str = bot_state.get('last_backup_time', 'Never')
    if last_backup_time_str != 'Never':
        last_backup_time_str = datetime.fromisoformat(last_backup_time_str).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    with open(CONFIG_FILE, 'r') as f: current_config = json.load(f)
    interval = current_config.get('telegram', {}).get('backup_interval')
    auto_backup_status = f"{EMOJI['SUCCESS']} Active (Every {interval} mins)" if interval else f"{EMOJI['ERROR']} Inactive"
    
    text = f"""
{EMOJI['PANEL']} *Marzban Control Panel*
{EMOJI['STATUS']} *Dashboard*
> *Last Backup:* `{last_backup_time_str}`
> *Auto-Backup Status:* {auto_backup_status}
"""
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=main_menu_keyboard())
    except telebot.apihelper.ApiTelegramException as e:
        if 'message is not modified' not in e.description:
            bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())

def display_settings_menu(message):
    text = f"{EMOJI['SETTINGS']} *Settings Menu*\n\nManage auto-backup or view your configuration."
    bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=settings_menu_keyboard())

# --- Core Logic Functions ---
def toggle_auto_backup(enabled: bool, message):
    """Handles the logic for enabling or disabling auto-backup."""
    with open(CONFIG_FILE, 'r+') as f:
        data = json.load(f)
        data.setdefault('telegram', {})
        if not enabled: # Disabling
            data['telegram'].pop('backup_interval', None)
            bot.edit_message_text(f"{EMOJI['WAIT']} Disabling auto-backup...", message.chat.id, message.message_id)
        else: # Enabling
            # Set a default interval, user will be prompted to change it
            data['telegram']['backup_interval'] = data['telegram'].get('backup_interval', '60')
            bot.edit_message_text(f"{EMOJI['WAIT']} Enabling auto-backup...", message.chat.id, message.message_id)
        f.seek(0); json.dump(data, f, indent=4); f.truncate()
    
    success, output, duration = run_main_script(['do-auto-backup-setup'])
    if success:
        action_text = "Enabled" if enabled else "Disabled"
        final_text = f"{EMOJI['SUCCESS']} *Auto-Backup {action_text}*\n\nSystem schedule has been updated."
        bot.edit_message_text(final_text, message.chat.id, message.message_id)
        time.sleep(2)
        if enabled:
            # If enabling, prompt for interval
            user_states[message.chat.id] = {'state': 'awaiting_interval'}
            text = f"{EMOJI['CLOCK']} Auto-backup is now enabled. Please set the interval in *minutes* (e.g., `60`)."
            bot.edit_message_text(text, message.chat.id, message.message_id)
        else:
            display_settings_menu(message) # Go back to settings menu after disabling
    else:
        final_text = f"{EMOJI['ERROR']} *Operation Failed!*\n\n*Details:*\n```{output}```"
        bot.edit_message_text(final_text, message.chat.id, message.message_id)
        time.sleep(4)
        display_settings_menu(message)

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

    # Main Menu Navigation
    if action == "main_menu": display_main_menu(message)
    elif action == "settings_menu": display_settings_menu(message)
    
    # Backup & Restore Actions
    elif action == "do_backup":
        bot.edit_message_text(f"{EMOJI['WAIT']} *Creating Backup...*\nThis might take a moment. Please wait.", message.chat.id, message.message_id)
        success, output, duration = run_main_script(['do-backup'])
        if success:
            update_bot_state('last_backup_time', datetime.utcnow().isoformat())
            final_text = f"{EMOJI['SUCCESS']} *Backup Complete!*\n\nFile sent to your chat.\n`Operation took {duration} seconds.`"
        else:
            final_text = f"{EMOJI['ERROR']} *Backup Failed!*\n\n*Details:*\n```{output}```"
        bot.edit_message_text(final_text, message.chat.id, message.message_id)
        time.sleep(3); display_main_menu(message)

    elif action == "restore_start":
        text = f"{EMOJI['DANGER']} *CRITICAL WARNING*\n\nThis will **overwrite** all current data. This action cannot be undone. Are you sure?"
        bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=restore_confirmation_keyboard())

    elif action == "restore_confirm":
        user_states[message.chat.id] = {'state': 'awaiting_restore_file'}
        text = f"{EMOJI['INFO']} Please send the `.tar.gz` backup file to restore."
        bot.edit_message_text(text, message.chat.id, message.message_id)
        
    # Settings Actions
    elif action == "settings_autobackup_enable": toggle_auto_backup(True, message)
    elif action == "settings_autobackup_disable": toggle_auto_backup(False, message)
    
    elif action == "settings_edit_interval":
        user_states[message.chat.id] = {'state': 'awaiting_interval'}
        text = f"{EMOJI['CLOCK']} Please enter the new auto-backup interval in *minutes*."
        bot.edit_message_text(text, message.chat.id, message.message_id)

    elif action == "settings_view_config":
        with open(CONFIG_FILE, 'r') as f: config_text = json.dumps(json.load(f), indent=2)
        text = f"{EMOJI['INFO']} *Full Configuration (`config.json`)*\n\n```json\n{config_text}\n```"
        bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(f"{EMOJI['BACK']} Back to Settings", callback_data="settings_menu")))

@bot.message_handler(content_types=['text'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_stateful_text(message):
    state_info = user_states.pop(message.chat.id, None)
    if not state_info or state_info['state'] != 'awaiting_interval': return
    
    try:
        interval = int(message.text)
        if interval <= 0: raise ValueError("Interval must be positive.")
        with open(CONFIG_FILE, 'r+') as f:
            data = json.load(f)
            data.setdefault('telegram', {})['backup_interval'] = str(interval)
            f.seek(0); json.dump(data, f, indent=4); f.truncate()
        
        bot.send_message(message.chat.id, f"{EMOJI['WAIT']} Interval set to `{interval}` minutes. Updating system schedule...")
        success, output, duration = run_main_script(['do-auto-backup-setup'])
        final_text = f"{EMOJI['SUCCESS']} *Schedule Updated!*\n\n`Took {duration}s`" if success else f"{EMOJI['ERROR']} *Update Failed!*\n\n```{output}```"
        bot.send_message(message.chat.id, final_text)
        time.sleep(2); display_settings_menu(message)
    except (ValueError, TypeError):
        bot.send_message(message.chat.id, f"{EMOJI['ERROR']} Invalid input. Please enter a positive number (e.g., 60).")
        display_settings_menu(message)

@bot.message_handler(content_types=['document'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_restore_document(message):
    state_info = user_states.pop(message.chat.id, None)
    if not state_info or state_info['state'] != 'awaiting_restore_file': return
    if not message.document.file_name.endswith('.tar.gz'):
        bot.send_message(message.chat.id, f"{EMOJI['ERROR']} Invalid file type. Please send a `.tar.gz` archive.")
        display_main_menu(message)
        return

    bot.edit_message_text(f"{EMOJI['WAIT']} Downloading file...", message.chat.id, message.message_id)
    restore_file_path = os.path.join("/tmp", f"restore_{int(time.time())}.tar.gz")
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(restore_file_path, 'wb') as f: f.write(downloaded_file)
        
        bot.send_message(message.chat.id, f"{EMOJI['WARNING']} *Restore in progress...*\nThis will take several minutes. The bot will be unresponsive until it's done.")
        success, output, duration = run_main_script(['do-restore', restore_file_path])
        if success:
            update_bot_state('last_backup_time', 'Never (Just Restored)')
            final_text = f"{EMOJI['SUCCESS']} *Restore Complete!*\n\nSystem restored and restarted.\n`Took {duration}s`"
        else:
            final_text = f"{EMOJI['ERROR']} *Restore Failed!*\n\n```{output}```"
        bot.send_message(message.chat.id, final_text)
        time.sleep(3); display_main_menu(message)
    finally:
        if os.path.exists(restore_file_path): os.remove(restore_file_path)

# --- Bot Execution ---
if __name__ == '__main__':
    logger.info(f"Starting Bot v5.1 (Phoenix+) for Admin ID: {ADMIN_CHAT_ID}...")
    while True:
        try:
            bot.infinity_polling(timeout=120, logger_level=logging.WARNING)
        except Exception as e:
            logger.critical(f"Bot crashed: {e}", exc_info=True)
            time.sleep(10)
