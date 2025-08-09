#!/usr/bin/env python3
# =================================================================
# Marzban Professional Control Bot
# Creator: @HEXMOSTAFA
# Version: 7.1.1 (Clean & Optimized)
# =================================================================
import os
import json
import subprocess
import logging
import time
from datetime import datetime
from typing import Tuple, List, Optional
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.util import quick_markup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
MAIN_PANEL_SCRIPT = os.path.join(SCRIPT_DIR, "marzban_panel.py")
LOG_FILE = os.path.join(SCRIPT_DIR, "marzban_bot.log")
BOT_STATE_FILE = os.path.join(SCRIPT_DIR, "bot_state.json")

EMOJI = {
    "PANEL": "📱", "BACKUP": "📦", "RESTORE": "🔄", "AUTO": "⚙️", "SETTINGS": "ℹ️",
    "SUCCESS": "✅", "ERROR": "❌", "WAIT": "⏳", "INFO": "📊",
    "WARNING": "⚠️", "BACK": "⬅️", "DANGER": "🛑", "EDIT": "📝",
    "CLOCK": "⏱️", "CONFIRM": "👍", "TOGGLE_ON": "🟢", "TOGGLE_OFF": "🔴"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

try:
    with open(CONFIG_FILE, 'r') as f: config = json.load(f)
    BOT_TOKEN = config.get('telegram', {}).get('bot_token')
    ADMIN_CHAT_ID = int(config.get('telegram', {}).get('admin_chat_id'))
    if not BOT_TOKEN or not ADMIN_CHAT_ID: raise ValueError("Bot Token or Admin Chat ID is missing.")
except Exception as e:
    logger.critical(f"FATAL: Could not load config.json. Error: {e}")
    sys.exit(1)

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

def run_main_script(args: List[str]) -> Tuple[bool, str, str]:
    python_executable = subprocess.run(['which', 'python3'], capture_output=True, text=True).stdout.strip() or "python3"
    venv_python = os.path.join(SCRIPT_DIR, 'venv', 'bin', 'python3')
    if os.path.exists(venv_python): python_executable = venv_python
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

def update_display(chat_id: int, message_id: int, text: str, markup: Optional[InlineKeyboardMarkup] = None):
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except telebot.apihelper.ApiTelegramException as e:
        if 'message is not modified' not in e.description: logger.error(f"Failed to update display: {e}")

def main_menu_keyboard():
    return quick_markup({
        f"{EMOJI['BACKUP']} بکاپ فوری": {'callback_data': "do_backup"},
        f"{EMOJI['RESTORE']} ریستور از بکاپ": {'callback_data': "restore_start"},
        f"{EMOJI['AUTO']} مدیریت بکاپ خودکار": {'callback_data': "autobackup_menu"},
        f"{EMOJI['SETTINGS']} تنظیمات و اطلاعات": {'callback_data': "settings_info_menu"},
    }, row_width=2)

def autobackup_menu_keyboard():
    try:
        with open(CONFIG_FILE, 'r') as f: current_config = json.load(f)
        is_enabled = 'backup_interval' in current_config.get('telegram', {})
        toggle_text = f"{EMOJI['TOGGLE_OFF']} غیرفعال‌سازی" if is_enabled else f"{EMOJI['TOGGLE_ON']} فعال‌سازی"
        toggle_action = "autobackup_disable" if is_enabled else "autobackup_enable"
        
        markup_dict = {
            toggle_text: {'callback_data': toggle_action},
        }
        if is_enabled:
            markup_dict[f"{EMOJI['EDIT']} تغییر بازه زمانی"] = {'callback_data': "autobackup_edit_interval"}
        
        markup_dict[f"{EMOJI['BACK']} بازگشت به منوی اصلی"] = {'callback_data': "main_menu"}
        return quick_markup(markup_dict, row_width=1)
    except Exception as e:
        logger.error(f"Error creating autobackup keyboard: {e}")
        return main_menu_keyboard()

def restore_confirmation_keyboard():
    return quick_markup({
        f"{EMOJI['DANGER']} بله، ریستور انجام شود": {'callback_data': "restore_confirm"},
        f"{{EMOJI['BACK']}} انصراف": {'callback_data': "main_menu"},
    }, row_width=1)

def settings_info_keyboard():
    return quick_markup({f"{{EMOJI['BACK']}} بازگشت به منوی اصلی": {'callback_data': "main_menu"}}, row_width=1)

def display_main_menu(chat_id: int, message_id: int):
    bot_state = get_bot_state()
    last_backup = bot_state.get('last_backup_time', 'هیچوقت')
    if last_backup != 'هیچوقت': last_backup = datetime.fromisoformat(last_backup).strftime('%Y-%m-%d %H:%M')
    
    with open(CONFIG_FILE, 'r') as f: config_data = json.load(f)
    interval = config_data.get('telegram', {}).get('backup_interval')
    auto_status = f"{EMOJI['SUCCESS']} فعال (هر {interval} دقیقه)" if interval else f"{EMOJI['ERROR']} غیرفعال"
    
    text = f"{EMOJI['PANEL']} *پنل مدیریت مرزبان*\n\n`آخرین بکاپ:` {last_backup}\n`بکاپ خودکار:` {auto_status}"
    update_display(chat_id, message_id, text, main_menu_keyboard())

def display_autobackup_menu(chat_id: int, message_id: int):
    with open(CONFIG_FILE, 'r') as f: config_data = json.load(f)
    interval = config_data.get('telegram', {}).get('backup_interval')
    status_text = f"در حال حاضر بکاپ خودکار *فعال* است و هر `{interval}` دقیقه یکبار اجرا می‌شود." if interval else "بکاپ خودکار در حال حاضر *غیرفعال* است."
    text = f"{EMOJI['AUTO']} *مدیریت بکاپ خودکار*\n\n{status_text}\n\nاز دکمه‌های زیر برای مدیریت استفاده کنید."
    update_display(chat_id, message_id, text, autobackup_menu_keyboard())

def display_settings_info_view(chat_id: int, message_id: int):
    with open(CONFIG_FILE, 'r') as f: config_text = json.dumps(json.load(f), indent=2)
    text = f"{EMOJI['SETTINGS']} *تنظیمات و اطلاعات*\n\nاین اطلاعات از فایل `config.json` خوانده می‌شود.\n\n```json\n{config_text}\n```"
    update_display(chat_id, message_id, text, settings_info_keyboard())

@bot.message_handler(commands=['start'])
@admin_only
def handle_start(message):
    initial_msg = bot.send_message(message.chat.id, "در حال بارگذاری پنل...")
    display_main_menu(initial_msg.chat.id, initial_msg.message_id)

@bot.callback_query_handler(func=lambda call: True)
@admin_only
def handle_callbacks(call):
    bot.answer_callback_query(call.id)
    action = call.data
    chat_id, msg_id = call.message.chat.id, call.message.message_id

    if action == "main_menu": display_main_menu(chat_id, msg_id)
    elif action == "autobackup_menu": display_autobackup_menu(chat_id, msg_id)
    elif action == "settings_info_menu": display_settings_info_view(chat_id, msg_id)

    elif action == "do_backup":
        update_display(chat_id, msg_id, f"{EMOJI['WAIT']} *در حال ایجاد بکاپ کامل...*", None)
        success, output, duration = run_main_script(['run-backup'])
        if success:
            update_bot_state('last_backup_time', datetime.utcnow().isoformat())
            result_text = f"{EMOJI['SUCCESS']} *بکاپ کامل شد!* `({duration} ثانیه)`"
        else:
            result_text = f"{EMOJI['ERROR']} *عملیات ناموفق بود!*\n```{output}```"
        update_display(chat_id, msg_id, result_text, None)
        time.sleep(3); display_main_menu(chat_id, msg_id)

    elif action == "restore_start":
        text = f"{EMOJI['DANGER']} *هشدار بسیار مهم*\n\nاین عمل تمام اطلاعات فعلی شما را با فایل بکاپ *جایگزین* و بازنویسی می‌کند. این عمل غیرقابل بازگشت است.\n\nآیا برای ادامه مطمئن هستید؟"
        update_display(chat_id, msg_id, text, restore_confirmation_keyboard())

    elif action == "restore_confirm":
        user_states[chat_id] = {'state': 'awaiting_restore_file', 'message_id': msg_id}
        update_display(chat_id, msg_id, f"{EMOJI['INFO']} لطفاً فایل بکاپ با فرمت `.tar.gz` را ارسال کنید.", None)

    elif action == "autobackup_enable":
        user_states[chat_id] = {'state': 'awaiting_interval', 'message_id': msg_id}
        update_display(chat_id, msg_id, f"{EMOJI['CLOCK']} برای فعال‌سازی، لطفاً بازه زمانی را به *دقیقه* وارد کنید (مثلا: `60`).", None)

    elif action == "autobackup_disable":
        update_display(chat_id, msg_id, f"{EMOJI['WAIT']} در حال غیرفعال‌سازی...", None)
        with open(CONFIG_FILE, 'r+') as f: data = json.load(f); data.get('telegram', {}).pop('backup_interval', None); f.seek(0); json.dump(data, f, indent=4); f.truncate()
        success, _, _ = run_main_script(['do-auto-backup-setup'])
        result_text = f"{EMOJI['SUCCESS']} بکاپ خودکار غیرفعال شد." if success else f"{EMOJI['ERROR']} خطا در به‌روزرسانی."
        update_display(chat_id, msg_id, result_text, None)
        time.sleep(2); display_autobackup_menu(chat_id, msg_id)

    elif action == "autobackup_edit_interval":
        user_states[chat_id] = {'state': 'awaiting_interval', 'message_id': msg_id}
        update_display(chat_id, msg_id, f"{EMOJI['CLOCK']} لطفاً بازه زمانی *جدید* را به دقیقه وارد کنید.", None)

@bot.message_handler(content_types=['text', 'document'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_stateful_messages(message):
    chat_id = message.chat.id
    state_info = user_states.pop(chat_id, None)
    if not state_info: return

    msg_id_to_edit = state_info['message_id']
    try: bot.delete_message(chat_id, message.message_id) 
    except Exception: pass

    if state_info['state'] == 'awaiting_interval' and message.content_type == 'text':
        try:
            interval = int(message.text)
            if interval <= 0: raise ValueError("Interval must be positive.")
            update_display(chat_id, msg_id_to_edit, f"{EMOJI['WAIT']} در حال تنظیم بازه زمانی روی `{interval}` دقیقه...", None)
            with open(CONFIG_FILE, 'r+') as f:
                data = json.load(f)
                data.setdefault('telegram', {})['backup_interval'] = str(interval)
                f.seek(0); json.dump(data, f, indent=4); f.truncate()
            success, _, _ = run_main_script(['do-auto-backup-setup'])
            result_text = f"{EMOJI['SUCCESS']} زمان‌بندی با موفقیت به‌روز شد." if success else f"{EMOJI['ERROR']} خطا در به‌روزرسانی."
            update_display(chat_id, msg_id_to_edit, result_text, None)
            time.sleep(2); display_autobackup_menu(chat_id, msg_id_to_edit)
        except (ValueError, TypeError):
            update_display(chat_id, msg_id_to_edit, f"{EMOJI['ERROR']} ورودی نامعتبر است. لطفاً یک عدد وارد کنید.", None)
            time.sleep(2); display_autobackup_menu(chat_id, msg_id_to_edit)

    elif state_info['state'] == 'awaiting_restore_file' and message.content_type == 'document':
        if not message.document.file_name.endswith('.tar.gz'):
            update_display(chat_id, msg_id_to_edit, f"{EMOJI['ERROR']} فایل نامعتبر است. لطفاً فایل `.tar.gz` ارسال کنید.", None)
            time.sleep(2); display_main_menu(chat_id, msg_id_to_edit)
            return

        update_display(chat_id, msg_id_to_edit, f"{EMOJI['WAIT']} در حال دانلود فایل...", None)
        restore_file_path = os.path.join(tempfile.gettempdir(), f"restore_{int(time.time())}.tar.gz")
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            with open(restore_file_path, 'wb') as f: f.write(downloaded_file)
            
            update_display(chat_id, msg_id_to_edit, f"{EMOJI['WARNING']} *در حال ریستور...*\nاین عملیات ممکن است چندین دقیقه طول بکشد. لطفاً منتظر بمانید.", None)
            success, output, duration = run_main_script(['do-restore', restore_file_path])
            if success:
                update_bot_state('last_backup_time', 'هیچوقت (سیستم ریستور شده)')
                result_text = f"{EMOJI['SUCCESS']} *ریستور کامل شد!* `({duration}s)`"
            else:
                result_text = f"{EMOJI['ERROR']} *ریستور ناموفق بود!* `({duration}s)`\n```{output}```"
            update_display(chat_id, msg_id_to_edit, result_text, None)
            time.sleep(4); display_main_menu(chat_id, msg_id_to_edit)
        finally:
            if os.path.exists(restore_file_path): os.remove(restore_file_path)

if __name__ == '__main__':
    logger.info(f"Starting Bot v7.1.1 for Admin ID: {ADMIN_CHAT_ID}...")
    while True:
        try:
            bot.infinity_polling(timeout=120, logger_level=logging.WARNING)
        except Exception as e:
            logger.critical(f"Bot crashed: {e}", exc_info=True)
            time.sleep(10)
