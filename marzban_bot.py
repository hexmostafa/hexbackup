#!/usr/bin/env python3
# =================================================================
# Marzban Professional Control Bot
# Creator: @HEXMOSTAFA
# Version: 3.2.0 (Interactive Edit Settings Menu)
# =================================================================

import os
import json
import subprocess
import logging
import time
from datetime import datetime

try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
except ImportError:
    print("FATAL ERROR: 'pyTelegramBotAPI' is not installed.")
    exit(1)

# --- تنظیمات سراسری و ایموجی‌ها ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
MAIN_PANEL_SCRIPT = os.path.join(SCRIPT_DIR, "marzban_panel.py")
LOG_FILE = os.path.join(SCRIPT_DIR, "marzban_bot.log")

EMOJI = {
    "BACKUP": "📦", "RESTORE": "🔄", "AUTO": "⚙️", "SETTINGS": "🛠️",
    "SUCCESS": "✅", "ERROR": "❌", "WAIT": "⏳", "INFO": "ℹ️",
    "CANCEL": "🚫", "BACK": "⬅️", "KEY": "🔑", "DANGER": "🛑",
    "EDIT": "📝", "DB": "🗄️", "CLOCK": "⏱️"
}

# --- راه‌اندازی سیستم لاگ‌گیری و خواندن فایل تنظیمات ---
# (این بخش‌ها بدون تغییر هستند)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

try:
    with open(CONFIG_FILE, 'r') as f: config = json.load(f)
    BOT_TOKEN = config.get('telegram', {}).get('bot_token')
    ADMIN_CHAT_ID = int(config.get('telegram', {}).get('admin_chat_id'))
    if not BOT_TOKEN or not ADMIN_CHAT_ID: raise ValueError("Config is missing bot token or admin chat ID.")
except Exception as e:
    logger.critical(f"FATAL: Could not load config.json. Error: {e}")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
user_states = {}

# --- توابع کمکی ---
# (این بخش‌ها بدون تغییر هستند)
def run_main_script(args: list) -> (bool, str, str):
    command = ['sudo', 'python3', MAIN_PANEL_SCRIPT] + args
    start_time = time.time()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
        duration = f"{time.time() - start_time:.2f}"
        if result.returncode == 0: return True, result.stdout.strip() or "OK", duration
        else: return False, result.stderr.strip() or "Failed", duration
    except Exception as e:
        return False, f"Critical Error: {e}", f"{time.time() - start_time:.2f}"

def admin_only(func):
    def wrapper(message_or_call):
        chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
        if chat_id != ADMIN_CHAT_ID: return
        return func(message_or_call)
    return wrapper

# --- کیبوردها ---
def main_menu_keyboard():
    return InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton(f"{EMOJI['BACKUP']} Backup", callback_data="create_backup"),
        InlineKeyboardButton(f"{EMOJI['RESTORE']} Restore", callback_data="start_restore"),
        InlineKeyboardButton(f"{EMOJI['AUTO']} Auto Backup", callback_data="setup_auto_backup"),
        InlineKeyboardButton(f"{EMOJI['SETTINGS']} Settings", callback_data="view_settings")
    )

def settings_keyboard():
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(f"{EMOJI['EDIT']} Edit Information", callback_data="edit_settings_start"),
        InlineKeyboardButton(f"{EMOJI['BACK']} Back to Main Menu", callback_data="main_menu")
    )

def edit_menu_keyboard():
    """کیبورد جدید برای منوی ویرایش."""
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(f"{EMOJI['CLOCK']} Edit Backup Interval", callback_data="edit_interval_start"),
        # می‌توانید دکمه‌های بیشتری برای ویرایش سایر بخش‌ها اینجا اضافه کنید
        InlineKeyboardButton(f"{EMOJI['BACK']} Back to Settings", callback_data="view_settings")
    )

# --- مدیریت کلیک روی دکمه‌ها (Callback) ---
@bot.callback_query_handler(func=lambda call: True)
@admin_only
def handle_callback_query(call):
    bot.answer_callback_query(call.id)
    action = call.data

    # ... (مدیریت سایر دکمه‌ها بدون تغییر)

    if action == "view_settings":
        handle_settings(call.message)
    
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    #          بخش اصلاح شده
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    elif action == "edit_settings_start":
        # نمایش منوی ویرایش
        text = f"{EMOJI['EDIT']} *Edit Settings*\n\nکدام بخش را می‌خواهید ویرایش کنید؟"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=edit_menu_keyboard())

    elif action == "edit_interval_start":
        # شروع فرآیند ویرایش بازه زمانی
        user_states[call.message.chat.id] = {'state': 'awaiting_new_interval'}
        text = f"{EMOJI['INFO']} لطفا بازه زمانی جدید برای بکاپ را به *دقیقه* وارد کنید."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id)
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    #        پایان بخش اصلاح شده
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    elif action == "setup_auto_backup":
        user_states[call.message.chat.id] = {'state': 'awaiting_interval'}
        text = f"{EMOJI['INFO']} لطفا بازه زمانی بکاپ را به *دقیقه* وارد کنید."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id)

    # ... (سایر action ها)


# --- توابع مربوط به هر قابلیت ---
def handle_settings(message):
    """نمایش منوی تنظیمات هوشمند."""
    # ... (این تابع بدون تغییر است)
    bot.edit_message_text(f"{EMOJI['WAIT']} در حال دریافت اطلاعات...", message.chat.id, message.message_id)
    # ... (منطق نمایش اطلاعات)
    success, output, _ = run_main_script(['get-db-type'])
    db_type = "Error"
    if success:
        try: db_type = json.loads(output).get("database_type", "Unknown")
        except json.JSONDecodeError: db_type = "Parse Error"
    
    with open(CONFIG_FILE, 'r') as f: current_config = json.load(f)
    tele_conf = current_config.get("telegram", {})
    db_conf = current_config.get("database", {})
    admin_id = tele_conf.get('admin_chat_id', 'N/A')
    interval = tele_conf.get('backup_interval', 'N/A')
    db_user = db_conf.get('user', 'N/A')
    db_pass = db_conf.get('password', 'N/A')
    db_pass_masked = f"{db_pass[0]}***{db_pass[-1]}" if len(db_pass) > 2 else db_pass

    text = f"""
{EMOJI['SETTINGS']} *تنظیمات سیستم*
{EMOJI['DB']} *نوع دیتابیس:* `{db_type}`
---
*شناسه ادمین:* `{admin_id}`
*بازه بکاپ:* `{interval}` دقیقه
*کاربر دیتابیس:* `{db_user}`
*رمز دیتابیس:* `{db_pass_masked}`
"""
    bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=settings_keyboard())

# --- مدیریت ورودی‌های چندمرحله‌ای ---
@bot.message_handler(content_types=['text'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_stateful_messages(message):
    state_info = user_states.pop(message.chat.id)
    state = state_info['state']

    # تابع مشترک برای به‌روزرسانی بازه زمانی
    def update_interval(new_interval):
        try:
            interval = int(new_interval)
            if interval <= 0: raise ValueError("Interval must be positive.")

            with open(CONFIG_FILE, 'r+') as f:
                data = json.load(f)
                data['telegram']['backup_interval'] = str(interval)
                f.seek(0); json.dump(data, f, indent=4); f.truncate()
            
            bot.send_message(message.chat.id, f"{EMOJI['WAIT']} بازه زمانی روی `{interval}` دقیقه تنظیم شد. در حال به‌روزرسانی کرون‌جاب...")
            success, output, duration = run_main_script(['do-auto-backup-setup'])

            final_text = f"{EMOJI['SUCCESS']} *بازه زمانی به‌روز شد!*\n\nکرون‌جاب برای اجرا در هر {interval} دقیقه تنظیم شد.\n\n`عملیات در {duration} ثانیه انجام شد.`" if success else f"{EMOJI['ERROR']} *خطا در تنظیم*\n\n*جزئیات:*\n```{output}```"
            bot.send_message(message.chat.id, final_text, reply_markup=main_menu_keyboard())

        except ValueError:
            bot.send_message(message.chat.id, f"{EMOJI['ERROR']} ورودی نامعتبر است.", reply_markup=main_menu_keyboard())
        except Exception as e:
            logger.error(f"Failed to update interval: {e}")
            bot.send_message(message.chat.id, f"{EMOJI['ERROR']} خطای داخلی رخ داد.", reply_markup=main_menu_keyboard())

    if state == 'awaiting_interval':
        update_interval(message.text)
    
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    #          بخش جدید
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    elif state == 'awaiting_new_interval':
        update_interval(message.text)
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    #        پایان بخش جدید
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

# ... (بخش مدیریت فایل ریستور بدون تغییر است)
@bot.message_handler(content_types=['document'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_restore_file(message):
    state_info = user_states.pop(message.chat.id)
    if state_info['state'] == 'awaiting_restore_file':
        # ... (منطق کامل ریستور فایل)
        pass

# --- اجرای ربات ---
if __name__ == '__main__':
    logger.info("Starting HexBackup Control Bot (Version 3.2.0)...")
    try:
        bot.infinity_polling(timeout=120, logger_level=logging.WARNING)
    except Exception as e:
        logger.critical(f"Bot crashed with a critical error: {e}", exc_info=True)
        time.sleep(10)
