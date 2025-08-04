#!/usr/bin/env python3
# =================================================================
# Marzban Professional Control Bot - Prestige Edition
# Creator: @HEXMOSTAFA
# Version: 6.0.0 (Prestige)
#
# A masterclass in UI/UX design for bots. All interactions happen
# within a single, clean, and dynamic message. No clutter.
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
BOT_STATE_FILE = os.path.join(SCRIPT_DIR, "bot_state.json")

EMOJI = {
    "PANEL": "📱", "BACKUP": "📦", "RESTORE": "🔄", "SETTINGS": "⚙️",
    "SUCCESS": "✅", "ERROR": "❌", "WAIT": "⏳", "INFO": "ℹ️",
    "WARNING": "⚠️", "BACK": "⬅️", "DANGER": "🛑", "EDIT": "📝",
    "CLOCK": "⏱️", "WELCOME": "👋", "STATUS": "📊", "CONFIRM": "👍",
    "TOGGLE_ON": "🟢", "TOGGLE_OFF": "🔴", "CLEAN": "✨"
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

# --- Core Helper Functions ---
def run_main_script(args: List[str]) -> Tuple[bool, str, str]:
    # ... (This function remains unchanged)
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

# --- The Heart of the UI: The Display Engine ---
def update_display(chat_id: int, message_id: int, text: str, markup: Optional[InlineKeyboardMarkup] = None):
    """The single function responsible for all UI updates. Edits a message in place."""
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        # If the message is not modified, ignore. Otherwise, log the error.
        if 'message is not modified' not in e.description:
            logger.error(f"Failed to update display: {e}")

# --- Keyboard Definitions ---
def main_menu_keyboard():
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(f"{EMOJI['BACKUP']} Take Full Backup Now", callback_data="do_backup"),
        InlineKeyboardButton(f"{EMOJI['RESTORE']} Restore from Backup", callback_data="restore_start"),
        InlineKeyboardButton(f"{EMOJI['SETTINGS']} Settings & Auto-Backup", callback_data="settings_menu")
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
        InlineKeyboardButton(f"{EMOJI['DANGER']} Yes, Proceed with Restore", callback_data="restore_confirm"),
        InlineKeyboardButton(f"{EMOJI['BACK']} Cancel", callback_data="main_menu")
    )

# --- UI View Functions ---
def display_main_menu(chat_id: int, message_id: int):
    """Renders the main dashboard view."""
    bot_state = get_bot_state()
    last_backup_time = bot_state.get('last_backup_time', 'Never')
    if last_backup_time != 'Never':
        last_backup_time = datetime.fromisoformat(last_backup_time).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    with open(CONFIG_FILE, 'r') as f: current_config = json.load(f)
    interval = current_config.get('telegram', {}).get('backup_interval')
    auto_backup_status = f"{EMOJI['SUCCESS']} Active (Every {interval} mins)" if interval else f"{EMOJI['ERROR']} Inactive"
    
    text = f"""
{EMOJI['PANEL']} *Marzban Control Panel*
{EMOJI['STATUS']} *Dashboard*
> *Last Backup:* `{last_backup_time}`
> *Auto-Backup:* {auto_backup_status}
"""
    update_display(chat_id, message_id, text, main_menu_keyboard())

def display_settings_menu(chat_id: int, message_id: int):
    """Renders the settings menu view."""
    text = f"{EMOJI['SETTINGS']} *Settings Menu*\n\nManage auto-backup or view your configuration."
    update_display(chat_id, message_id, text, settings_menu_keyboard())

# --- Message & Callback Handlers ---
@bot.message_handler(commands=['start'])
@admin_only
def handle_start(message):
    """Sends the initial message that will be edited throughout the session."""
    bot.send_message(message.chat.id, "Initializing panel...", reply_markup=None)
    time.sleep(0.5)
    display_main_menu(message.chat.id, message.message_id + 1)

@bot.callback_query_handler(func=lambda call: True)
@admin_only
def handle_callbacks(call):
    bot.answer_callback_query(call.id)
    action = call.data
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    # Navigation
    if action == "main_menu": display_main_menu(chat_id, message_id)
    elif action == "settings_menu": display_settings_menu(chat_id, message_id)
    
    # Backup
    elif action == "do_backup":
        update_display(chat_id, message_id, f"{EMOJI['WAIT']} *Creating Full Backup...*\nThis might take a moment.", None)
        success, output, duration = run_main_script(['do-backup'])
        if success:
            update_bot_state('last_backup_time', datetime.utcnow().isoformat())
            result_text = f"{EMOJI['SUCCESS']} *Backup Complete!*\nFile sent to chat. `({duration}s)`"
        else:
            result_text = f"{EMOJI['ERROR']} *Backup Failed!*\n```{output}```"
        update_display(chat_id, message_id, result_text, None)
        time.sleep(3)
        display_main_menu(chat_id, message_id)

    # Restore
    elif action == "restore_start":
        text = f"{EMOJI['DANGER']} *CRITICAL WARNING*\n\nThis will **overwrite all data**. This cannot be undone. Are you sure?"
        update_display(chat_id, message_id, text, restore_confirmation_keyboard())

    elif action == "restore_confirm":
        user_states[chat_id] = {'state': 'awaiting_restore_file', 'message_id': message_id}
        update_display(chat_id, message_id, f"{EMOJI['INFO']} Please send the `.tar.gz` backup file to restore.", None)
        
    # Settings
    elif action == "settings_autobackup_enable":
        user_states[chat_id] = {'state': 'awaiting_interval', 'message_id': message_id}
        update_display(chat_id, message_id, f"{EMOJI['CLOCK']} To enable auto-backup, please enter the interval in *minutes* (e.g., 60).", None)

    elif action == "settings_autobackup_disable":
        update_display(chat_id, message_id, f"{EMOJI['WAIT']} Disabling auto-backup...", None)
        with open(CONFIG_FILE, 'r+') as f: data = json.load(f); data.get('telegram', {}).pop('backup_interval', None); f.seek(0); json.dump(data, f, indent=4); f.truncate()
        success, _, _ = run_main_script(['do-auto-backup-setup'])
        result_text = f"{EMOJI['SUCCESS']} Auto-backup disabled." if success else f"{EMOJI['ERROR']} Failed to update schedule."
        update_display(chat_id, message_id, result_text, None)
        time.sleep(2)
        display_settings_menu(chat_id, message_id)

    elif action == "settings_edit_interval":
        user_states[chat_id] = {'state': 'awaiting_interval', 'message_id': message_id}
        update_display(chat_id, message_id, f"{EMOJI['CLOCK']} Please enter the new interval in *minutes*.", None)
        
    elif action == "settings_view_config":
        with open(CONFIG_FILE, 'r') as f: config_text = json.dumps(json.load(f), indent=2)
        text = f"{EMOJI['INFO']} *Configuration (`config.json`)*\n```json\n{config_text}\n```"
        update_display(chat_id, message_id, text, InlineKeyboardMarkup().add(InlineKeyboardButton(f"{EMOJI['BACK']} Back to Settings", callback_data="settings_menu")))

@bot.message_handler(content_types=['text'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_stateful_text(message):
    chat_id = message.chat.id
    state_info = user_states.pop(chat_id, None)
    if not state_info or state_info['state'] != 'awaiting_interval': return
    
    message_id_to_edit = state_info['message_id']
    user_message_id = message.message_id
    
    try: bot.delete_message(chat_id, user_message_id) # Clean up user's message
    except Exception: pass
    
    try:
        interval = int(message.text)
        if interval <= 0: raise ValueError("Interval must be positive.")
        update_display(chat_id, message_id_to_edit, f"{EMOJI['WAIT']} Setting interval to `{interval}` minutes and updating schedule...", None)
        with open(CONFIG_FILE, 'r+') as f: data = json.load(f); data.setdefault('telegram', {})['backup_interval'] = str(interval); f.seek(0); json.dump(data, f, indent=4); f.truncate()
        success, _, _ = run_main_script(['do-auto-backup-setup'])
        result_text = f"{EMOJI['SUCCESS']} Schedule updated successfully!" if success else f"{EMOJI['ERROR']} Failed to update schedule."
        update_display(chat_id, message_id_to_edit, result_text, None)
        time.sleep(2)
        display_settings_menu(chat_id, message_id_to_edit)
    except (ValueError, TypeError):
        update_display(chat_id, message_id_to_edit, f"{EMOJI['ERROR']} Invalid input. Please enter a positive number.", None)
        time.sleep(2)
        display_settings_menu(chat_id, message_id_to_edit)

@bot.message_handler(content_types=['document'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_restore_document(message):
    chat_id = message.chat.id
    state_info = user_states.pop(chat_id, None)
    if not state_info or state_info['state'] != 'awaiting_restore_file': return

    message_id_to_edit = state_info['message_id']
    try: bot.delete_message(chat_id, message.message_id) # Clean up file message
    except Exception: pass

    if not message.document.file_name.endswith('.tar.gz'):
        update_display(chat_id, message_id_to_edit, f"{EMOJI['ERROR']} Invalid file. Please send a `.tar.gz`.", None)
        time.sleep(2); display_main_menu(chat_id, message_id_to_edit)
        return

    update_display(chat_id, message_id_to_edit, f"{EMOJI['WAIT']} Downloading file...", None)
    restore_file_path = os.path.join("/tmp", f"restore_{int(time.time())}.tar.gz")
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(restore_file_path, 'wb') as f: f.write(downloaded_file)
        
        update_display(chat_id, message_id_to_edit, f"{EMOJI['WARNING']} *Restore in progress...*\nThis will take several minutes. Please wait.", None)
        success, output, duration = run_main_script(['do-restore', restore_file_path])
        if success:
            update_bot_state('last_backup_time', 'Never (Just Restored)')
            result_text = f"{EMOJI['SUCCESS']} *Restore Complete!*\nSystem restored and restarted. `({duration}s)`"
        else:
            result_text = f"{EMOJI['ERROR']} *Restore Failed!*\n```{output}```"
        update_display(chat_id, message_id_to_edit, result_text, None)
        time.sleep(4)
        display_main_menu(chat_id, message_id_to_edit)
    finally:
        if os.path.exists(restore_file_path): os.remove(restore_file_path)

# --- Bot Execution ---
if __name__ == '__main__':
    logger.info(f"Starting Bot v6.0 (Prestige) for Admin ID: {ADMIN_CHAT_ID}...")
    while True:
        try:
            bot.infinity_polling(timeout=120, logger_level=logging.WARNING)
        except Exception as e:
            logger.critical(f"Bot crashed: {e}", exc_info=True)
            time.sleep(10)
