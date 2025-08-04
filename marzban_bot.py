#!/usr/bin/env python3
# =================================================================
# Marzban Professional Control Bot
# Creator: @HEXMOSTAFA
# Version: 3.1.0 (Final Version with Advanced Settings)
#
# Features:
# - Modern UI with live message updates.
# - Intelligent settings menu with config display.
# - Secure and robust operation.
# =================================================================

import os
import json
import subprocess
import logging
import time
from datetime import datetime

# --- بررسی نصب بودن کتابخانه‌های مورد نیاز ---
try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
except ImportError:
    print("FATAL ERROR: 'pyTelegramBotAPI' is not installed. Please run 'pip install pyTelegramBotAPI' to continue.")
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
    "EDIT": "📝", "DB": "🗄️"
}

# --- راه‌اندازی سیستم لاگ‌گیری ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- خواندن فایل تنظیمات ---
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    BOT_TOKEN = config.get('telegram', {}).get('bot_token')
    ADMIN_CHAT_ID = int(config.get('telegram', {}).get('admin_chat_id'))
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        raise ValueError("Bot Token or Admin Chat ID is missing in config.json")
except Exception as e:
    logger.critical(f"FATAL: Could not load config.json. Please run the main panel script first. Error: {e}")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
user_states = {}  # برای مدیریت وضعیت‌های چندمرحله‌ای کاربر

# --- توابع کمکی ---
def run_main_script(args: list) -> (bool, str, str):
    """اجرای اسکریپت اصلی و بازگرداندن نتیجه."""
    command = ['sudo', 'python3', MAIN_PANEL_SCRIPT] + args
    logger.info(f"Executing: {' '.join(command)}")
    start_time = time.time()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
        duration = f"{time.time() - start_time:.2f}"
        if result.returncode == 0:
            output = result.stdout.strip() or "Operation completed with no output."
            return True, output, duration
        else:
            output = result.stderr.strip() or "Operation failed with no error message."
            return False, output, duration
    except Exception as e:
        duration = f"{time.time() - start_time:.2f}"
        logger.critical(f"A critical error occurred while running subprocess: {e}", exc_info=True)
        return False, f"A critical error occurred: `{e}`", duration

def admin_only(func):
    """دکوراتور برای اطمینان از اینکه فقط ادمین از ربات استفاده می‌کند."""
    def wrapper(message_or_call):
        chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
        if chat_id != ADMIN_CHAT_ID:
            bot.send_message(chat_id, f"{EMOJI['DANGER']} شما مجاز به استفاده از این ربات نیستید.")
            logger.warning(f"Unauthorized access attempt from chat ID: {chat_id}")
            return
        return func(message_or_call)
    return wrapper

# --- کیبوردها ---
def main_menu_keyboard():
    """کیبورد منوی اصلی."""
    return InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton(f"{EMOJI['BACKUP']} Backup", callback_data="create_backup"),
        InlineKeyboardButton(f"{EMOJI['RESTORE']} Restore", callback_data="start_restore"),
        InlineKeyboardButton(f"{EMOJI['AUTO']} Auto Backup", callback_data="setup_auto_backup"),
        InlineKeyboardButton(f"{EMOJI['SETTINGS']} Settings", callback_data="view_settings")
    )

def settings_keyboard():
    """کیبورد منوی تنظیمات."""
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(f"{EMOJI['EDIT']} Edit Information", callback_data="edit_settings_info"),
        InlineKeyboardButton(f"{EMOJI['BACK']} Back to Main Menu", callback_data="main_menu")
    )

def cancel_keyboard(action="Operation"):
    """کیبورد لغو عملیات."""
    return InlineKeyboardMarkup().add(InlineKeyboardButton(f"{EMOJI['CANCEL']} Cancel {action}", callback_data="cancel"))

# --- مدیریت پیام‌ها و دستورات ---
@bot.message_handler(commands=['start', 'help'])
@admin_only
def send_welcome(message):
    """ارسال پیام خوش‌آمدگویی."""
    text = f"🤖 *HexBackup Control Panel*\n\nبه پنل مدیریت بکاپ مرزبان خوش آمدید."
    bot.send_message(message.chat.id, text, reply_markup=main_menu_keyboard())

# --- مدیریت کلیک روی دکمه‌ها (Callback) ---
@bot.callback_query_handler(func=lambda call: True)
@admin_only
def handle_callback_query(call):
    """مدیریت مرکزی تمام کلیک‌ها روی دکمه‌ها."""
    bot.answer_callback_query(call.id)
    action = call.data

    if action in ["main_menu", "view_settings", "start_restore", "create_backup", "setup_auto_backup"]:
        user_states.pop(call.message.chat.id, None)

    if action == "main_menu":
        text = "🤖 *HexBackup Control Panel*\n\nچه کاری می‌خواهید انجام دهید؟"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())
    elif action == "cancel":
        user_states.pop(call.message.chat.id, None)
        bot.edit_message_text(f"{EMOJI['CANCEL']} عملیات لغو شد.", call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())
    elif action == "view_settings":
        handle_settings(call.message)
    elif action == "edit_settings_info":
        bot.answer_callback_query(call.id, text="این قابلیت فقط نمایشی است. برای ویرایش از پنل اصلی استفاده کنید.", show_alert=True)
    elif action == "create_backup":
        handle_backup(call.message)
    elif action == "start_restore":
        handle_restore(call.message)
    elif action == "setup_auto_backup":
        user_states[call.message.chat.id] = {'state': 'awaiting_interval'}
        text = f"{EMOJI['INFO']} لطفا بازه زمانی بکاپ را به *دقیقه* وارد کنید.\n\n(مثال: `60` برای هر ساعت، `1440` برای هر روز)"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=cancel_keyboard("Setup"))

# --- توابع مربوط به هر قابلیت ---
def handle_settings(message):
    """نمایش منوی تنظیمات جدید و هوشمند."""
    bot.edit_message_text(f"{EMOJI['WAIT']} در حال دریافت اطلاعات سیستم...", message.chat.id, message.message_id)
    
    success, output, _ = run_main_script(['get-db-type'])
    db_type = "Error"
    if success:
        try:
            db_type = json.loads(output).get("database_type", "Unknown")
        except json.JSONDecodeError:
            db_type = "Parse Error"
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            current_config = json.load(f)
        tele_conf = current_config.get("telegram", {})
        db_conf = current_config.get("database", {})
        admin_id = tele_conf.get('admin_chat_id', 'Not Set')
        interval = tele_conf.get('backup_interval', 'Not Set')
        db_user = db_conf.get('user', 'N/A')
        db_pass = db_conf.get('password', 'N/A')
        db_pass_masked = f"{db_pass[0]}***{db_pass[-1]}" if len(db_pass) > 2 else db_pass
    except Exception as e:
        logger.error(f"Failed to read config for settings menu: {e}")
        bot.edit_message_text(f"{EMOJI['ERROR']} خواندن فایل تنظیمات با خطا مواجه شد.", message.chat.id, message.message_id, reply_markup=main_menu_keyboard())
        return

    text = f"""
{EMOJI['SETTINGS']} *تنظیمات سیستم*

{EMOJI['DB']} *نوع دیتابیس:* `{db_type}`

--- *اطلاعات پیکربندی* ---
*شناسه ادمین:* `{admin_id}`
*بازه زمانی بکاپ:* `{interval}` دقیقه
*نام کاربری دیتابیس:* `{db_user}`
*رمز عبور دیتابیس:* `{db_pass_masked}`
"""
    bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=settings_keyboard())

def handle_backup(message):
    bot.edit_message_text(f"{EMOJI['WAIT']} *در حال ایجاد بکاپ کامل...*\n\nاین عملیات ممکن است کمی طول بکشد. فایل نهایی به زودی ارسال خواهد شد.", message.chat.id, message.message_id)
    success, output, duration = run_main_script(['do-backup'])
    final_text = f"{EMOJI['SUCCESS']} *شروع فرآیند بکاپ*\n\nفایل بکاپ شما به زودی در اینجا ارسال می‌شود.\n\n`عملیات در {duration} ثانیه انجام شد.`" if success else f"{EMOJI['ERROR']} *خطا در بکاپ*\n\n*جزئیات:*\n```{output}```"
    bot.send_message(message.chat.id, final_text, reply_markup=main_menu_keyboard())

def handle_restore(message):
    user_states[message.chat.id] = {'state': 'awaiting_restore_file'}
    text = f"{EMOJI['DANGER']} *منطقه خطر ریستور* {EMOJI['DANGER']}\n\nاین یک عملیات تخریبی است. لطفا فایل بکاپ `.tar.gz` خود را برای ادامه ارسال کنید."
    bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=cancel_keyboard("Restore"))

# --- مدیریت ورودی‌های چندمرحله‌ای ---
@bot.message_handler(content_types=['text', 'document'], func=lambda msg: user_states.get(msg.chat.id) is not None)
@admin_only
def handle_stateful_messages(message):
    """مدیریت پیام‌هایی که کاربر در پاسخ به یک سوال ربات ارسال می‌کند."""
    state_info = user_states.pop(message.chat.id)
    state = state_info['state']

    if state == 'awaiting_interval':
        try:
            interval = int(message.text)
            if interval <= 0: raise ValueError("Interval must be positive.")

            with open(CONFIG_FILE, 'r+') as f:
                data = json.load(f)
                data['telegram']['backup_interval'] = str(interval)
                f.seek(0); json.dump(data, f, indent=4); f.truncate()
            
            bot.send_message(message.chat.id, f"{EMOJI['WAIT']} بازه زمانی روی `{interval}` دقیقه تنظیم شد. در حال اجرای اسکریپت تنظیم بکاپ خودکار...")
            success, output, duration = run_main_script(['do-auto-backup-setup'])

            final_text = f"{EMOJI['SUCCESS']} *بکاپ خودکار تنظیم شد!*\n\nکرون‌جاب برای اجرا در هر {interval} دقیقه تنظیم شد. یک بکاپ اولیه به زودی ارسال می‌شود.\n\n`عملیات در {duration} ثانیه انجام شد.`" if success else f"{EMOJI['ERROR']} *خطا در تنظیم بکاپ خودکار*\n\n*جزئیات:*\n```{output}```"
            bot.send_message(message.chat.id, final_text, reply_markup=main_menu_keyboard())
        except ValueError:
            bot.send_message(message.chat.id, f"{EMOJI['ERROR']} ورودی نامعتبر است. عملیات لغو شد.", reply_markup=main_menu_keyboard())

    elif state == 'awaiting_restore_file':
        if message.content_type != 'document' or not message.document.file_name.endswith('.tar.gz'):
            bot.send_message(message.chat.id, f"{EMOJI['ERROR']} فایل نامعتبر است. لطفاً یک فایل `.tar.gz` ارسال کنید. عملیات لغو شد.", reply_markup=main_menu_keyboard())
            return
        
        status_msg = bot.send_message(message.chat.id, f"{EMOJI['INFO']} فایل دریافت شد. در حال آماده‌سازی برای ریستور...")
        
        temp_archive_path = None
        try:
            bot.edit_message_text(f"{EMOJI['WAIT']} *در حال دانلود فایل...*\n\n`{message.document.file_name}`", status_msg.chat.id, status_msg.message_id)
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            temp_dir = "/tmp"
            os.makedirs(temp_dir, exist_ok=True)
            temp_archive_path = os.path.join(temp_dir, message.document.file_name)
            with open(temp_archive_path, 'wb') as f:
                f.write(downloaded_file)
            
            bot.edit_message_text(f"{EMOJI['WAIT']} *دانلود کامل شد. در حال شروع فرآیند ریستور...*\n\nاین عملیات زمان‌بر است. لطفاً صبور باشید.", status_msg.chat.id, status_msg.message_id)

            success, output, duration = run_main_script(['do-restore', temp_archive_path])

            final_text = f"{EMOJI['SUCCESS']} *ریستور با موفقیت انجام شد!*\n\nسیستم از فایل بکاپ بازگردانی شد.\n\n`عملیات در {duration} ثانیه انجام شد.`" if success else f"{EMOJI['ERROR']} *خطا در فرآیند ریستور*\n\n*جزئیات:*\n```{output}```"
            bot.edit_message_text(final_text, status_msg.chat.id, status_msg.message_id, reply_markup=main_menu_keyboard())

        except Exception as e:
            logger.error(f"An error occurred during the restore file handling: {e}", exc_info=True)
            bot.edit_message_text(f"{EMOJI['ERROR']} یک خطای داخلی در ربات رخ داد: `{e}`", status_msg.chat.id, status_msg.message_id, reply_markup=main_menu_keyboard())
        
        finally:
            if temp_archive_path and os.path.exists(temp_archive_path):
                os.remove(temp_archive_path)
                logger.info(f"فایل موقت پاک شد: {temp_archive_path}")

# --- اجرای ربات ---
if __name__ == '__main__':
    logger.info("Starting HexBackup Control Bot (Version 3.1.0)...")
    try:
        bot.infinity_polling(timeout=120, logger_level=logging.WARNING)
    except Exception as e:
        logger.critical(f"Bot has crashed with a critical error: {e}", exc_info=True)
        time.sleep(10) # قبل از خروج کمی صبر می‌کند تا در لوپ ریستارت گیر نکند
