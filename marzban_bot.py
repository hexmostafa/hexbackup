#!/usr/bin/env python3
# =================================================================
# Marzban Professional Control Bot - Refactored
# Creator: @HEXMOSTAFA
# Re-engineered by AI Assistant
# Version: 8.0 (Object-Oriented, Sexy & Advanced)
# =================================================================
import os
import sys
import json
import subprocess
import logging
import time
from datetime import datetime
from typing import Tuple, List, Optional, Dict, Any
from pathlib import Path
import tempfile

# Dependency check
try:
    import telebot
    from telebot.types import InlineKeyboardMarkup
    from telebot.util import quick_markup
except ImportError:
    print("FATAL ERROR: 'pyTelegramBotAPI' is not installed. Please run 'pip install pyTelegramBotAPI'.")
    sys.exit(1)

# --- Constants ---
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
MAIN_PANEL_SCRIPT = SCRIPT_DIR / "marzban_panel.py" # Assuming this is the main backup/restore script
LOG_FILE = SCRIPT_DIR / "marzban_bot.log"
BOT_STATE_FILE = SCRIPT_DIR / "bot_state.json"

EMOJI: Dict[str, str] = {
    "PANEL": "📱", "BACKUP": "📦", "RESTORE": "🔄", "AUTO": "⚙️", "SETTINGS": "ℹ️",
    "SUCCESS": "✅", "ERROR": "❌", "WAIT": "⏳", "INFO": "📊",
    "WARNING": "⚠️", "BACK": "⬅️", "DANGER": "🛑", "EDIT": "📝",
    "CLOCK": "⏱️", "CONFIRM": "👍", "TOGGLE_ON": "🟢", "TOGGLE_OFF": "🔴"
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


class StateManager:
    """Handles reading and writing state/config files in a centralized way."""
    def __init__(self, config_path: Path, state_path: Path):
        self.config_path = config_path
        self.state_path = state_path
        self.config = self._load_json(self.config_path) or {}
        self.state = self._load_json(self.state_path) or {}

    def _load_json(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            with path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Error loading JSON from {path}: {e}")
            return None

    def _save_json(self, path: Path, data: Dict[str, Any]):
        try:
            with path.open('w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving JSON to {path}: {e}")

    def get_config(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def get_state(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def update_config(self, new_data: Dict[str, Any]):
        self.config.update(new_data)
        self._save_json(self.config_path, self.config)

    def update_state(self, key: str, value: Any):
        self.state[key] = value
        self._save_json(self.state_path, self.state)


class MarzbanControlBot:
    """A sexy, advanced, and well-organized bot to control Marzban panels."""
    
    # --- Callback Data Constants ---
    CB_MAIN_MENU = "main_menu"
    CB_DO_BACKUP = "do_backup"
    CB_RESTORE_START = "restore_start"
    CB_RESTORE_CONFIRM = "restore_confirm"
    CB_AUTOBACKUP_MENU = "autobackup_menu"
    CB_AUTOBACKUP_ENABLE = "autobackup_enable"
    CB_AUTOBACKUP_DISABLE = "autobackup_disable"
    CB_AUTOBACKUP_EDIT = "autobackup_edit_interval"
    CB_SETTINGS_MENU = "settings_info_menu"

    def __init__(self, token: str, admin_id: int):
        self.bot = telebot.TeleBot(token)
        self.admin_id = admin_id
        self.state_manager = StateManager(CONFIG_FILE, BOT_STATE_FILE)
        self.conversational_states: Dict[int, Dict[str, Any]] = {}

        self._register_handlers()
        self._setup_callback_routes()

    def _register_handlers(self):
        """Registers all message and callback handlers."""
        self.bot.message_handler(commands=['start'])(self.admin_only(self.handle_start))
        self.bot.callback_query_handler(func=lambda call: True)(self.admin_only(self.master_callback_handler))
        self.bot.message_handler(
            content_types=['text', 'document'],
            func=lambda msg: self.conversational_states.get(msg.chat.id) is not None
        )(self.admin_only(self.handle_stateful_messages))

    def _setup_callback_routes(self):
        """Maps callback data strings to their handler methods for clean routing."""
        self.callback_routes = {
            self.CB_MAIN_MENU: self.display_main_menu,
            self.CB_DO_BACKUP: self.handle_backup,
            self.CB_RESTORE_START: self.handle_restore_start,
            self.CB_RESTORE_CONFIRM: self.handle_restore_confirm,
            self.CB_AUTOBACKUP_MENU: self.display_autobackup_menu,
            self.CB_SETTINGS_MENU: self.display_settings_info_view,
            self.CB_AUTOBACKUP_ENABLE: self.handle_autobackup_enable,
            self.CB_AUTOBACKUP_DISABLE: self.handle_autobackup_disable,
            self.CB_AUTOBACKUP_EDIT: self.handle_autobackup_enable, # Same action as enable
        }

    def admin_only(self, func):
        """A decorator to restrict bot access to the designated admin."""
        def wrapper(message_or_call):
            chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
            if chat_id != self.admin_id:
                logger.warning(f"Unauthorized access attempt from chat_id: {chat_id}")
                return
            return func(message_or_call)
        return wrapper

    # --- Keyboard Generators ---
    def _get_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        return quick_markup({
            f"{EMOJI['BACKUP']} بکاپ فوری": {'callback_data': self.CB_DO_BACKUP},
            f"{EMOJI['RESTORE']} ریستور از بکاپ": {'callback_data': self.CB_RESTORE_START},
            f"{EMOJI['AUTO']} مدیریت بکاپ خودکار": {'callback_data': self.CB_AUTOBACKUP_MENU},
            f"{EMOJI['SETTINGS']} تنظیمات و اطلاعات": {'callback_data': self.CB_SETTINGS_MENU},
        }, row_width=2)

    def _get_autobackup_menu_keyboard(self) -> InlineKeyboardMarkup:
        interval = self.state_manager.get_config('telegram', {}).get('backup_interval')
        is_enabled = bool(interval)
        
        toggle_text = f"{EMOJI['TOGGLE_OFF']} غیرفعال‌سازی" if is_enabled else f"{EMOJI['TOGGLE_ON']} فعال‌سازی"
        toggle_action = self.CB_AUTOBACKUP_DISABLE if is_enabled else self.CB_AUTOBACKUP_ENABLE
        
        markup_dict = {toggle_text: {'callback_data': toggle_action}}
        if is_enabled:
            markup_dict[f"{EMOJI['EDIT']} تغییر بازه زمانی"] = {'callback_data': self.CB_AUTOBACKUP_EDIT}
        
        markup_dict[f"{EMOJI['BACK']} بازگشت"] = {'callback_data': self.CB_MAIN_MENU}
        return quick_markup(markup_dict, row_width=1)
        
    # --- Display Updaters ---
    def _update_display(self, chat_id: int, message_id: int, text: str, markup: Optional[InlineKeyboardMarkup] = None):
        try:
            self.bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        except telebot.apihelper.ApiTelegramException as e:
            if 'message is not modified' not in e.description:
                logger.error(f"Failed to update display: {e}")

    def display_main_menu(self, call_or_msg):
        chat_id, msg_id = self._get_chat_info(call_or_msg)
        last_backup_iso = self.state_manager.get_state('last_backup_time', 'هیچوقت')
        last_backup = datetime.fromisoformat(last_backup_iso).strftime('%Y-%m-%d %H:%M') if last_backup_iso != 'هیچوقت' else 'هیچوقت'
        
        interval = self.state_manager.get_config('telegram', {}).get('backup_interval')
        auto_status = f"{EMOJI['SUCCESS']} فعال (هر {interval} دقیقه)" if interval else f"{EMOJI['ERROR']} غیرفعال"
        
        text = (
            f"{EMOJI['PANEL']} *پنل مدیریت مرزبان*\n\n"
            f"`- آخرین بکاپ:` {last_backup}\n"
            f"`- بکاپ خودکار:` {auto_status}"
        )
        self._update_display(chat_id, msg_id, text, self._get_main_menu_keyboard())

    def display_autobackup_menu(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        interval = self.state_manager.get_config('telegram', {}).get('backup_interval')
        status = f"در حال حاضر بکاپ خودکار *فعال* است و هر `{interval}` دقیقه یکبار اجرا می‌شود." if interval else "بکاپ خودکار در حال حاضر *غیرفعال* است."
        text = f"{EMOJI['AUTO']} *مدیریت بکاپ خودکار*\n\n{status}\n\nاز دکمه‌های زیر برای مدیریت استفاده کنید."
        self._update_display(chat_id, msg_id, text, self._get_autobackup_menu_keyboard())
        
    def display_settings_info_view(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        config_text = json.dumps(self.state_manager.config, indent=2, ensure_ascii=False)
        text = f"{EMOJI['SETTINGS']} *تنظیمات و اطلاعات*\n\nمحتوای فایل `config.json`:\n\n```json\n{config_text}\n```"
        markup = quick_markup({f"{EMOJI['BACK']} بازگشت": {'callback_data': self.CB_MAIN_MENU}})
        self._update_display(chat_id, msg_id, text, markup)
        
    # --- Handlers ---
    def handle_start(self, message):
        initial_msg = self.bot.send_message(message.chat.id, f"{EMOJI['WAIT']} در حال بارگذاری پنل...")
        self.display_main_menu(initial_msg)

    def master_callback_handler(self, call):
        self.bot.answer_callback_query(call.id)
        handler = self.callback_routes.get(call.data)
        if handler:
            handler(call)
        else:
            logger.warning(f"Unhandled callback data: {call.data}")

    def handle_backup(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        self._update_display(chat_id, msg_id, f"{EMOJI['WAIT']} *در حال ایجاد بکاپ کامل...*")
        
        success, output, duration = self._run_panel_script(['run-backup'])
        
        if success:
            self.state_manager.update_state('last_backup_time', datetime.utcnow().isoformat())
            result_text = f"{EMOJI['SUCCESS']} *بکاپ کامل شد!* `({duration} ثانیه)`"
        else:
            result_text = f"{EMOJI['ERROR']} *عملیات ناموفق بود!* `({duration}s)`\n```{output}```"
        
        self._update_display(chat_id, msg_id, result_text)
        time.sleep(3)
        self.display_main_menu(call)

    def handle_restore_start(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        text = (
            f"{EMOJI['DANGER']} *هشدار بسیار مهم*\n\n"
            "این عمل تمام اطلاعات فعلی شما را با فایل بکاپ *جایگزین* و بازنویسی می‌کند. "
            "این عمل غیرقابل بازگشت است.\n\n"
            "آیا برای ادامه مطمئن هستید؟"
        )
        markup = quick_markup({
            f"{EMOJI['DANGER']} بله، ریستور کن": {'callback_data': self.CB_RESTORE_CONFIRM},
            f"{EMOJI['BACK']} انصراف": {'callback_data': self.CB_MAIN_MENU},
        })
        self._update_display(chat_id, msg_id, text, markup)
        
    def handle_restore_confirm(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        self.conversational_states[chat_id] = {'state': 'awaiting_restore_file', 'message_id': msg_id}
        self._update_display(chat_id, msg_id, f"{EMOJI['INFO']} لطفاً فایل بکاپ با فرمت `.tar.gz` را ارسال کنید.")

    def handle_autobackup_enable(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        self.conversational_states[chat_id] = {'state': 'awaiting_interval', 'message_id': msg_id}
        self._update_display(chat_id, msg_id, f"{EMOJI['CLOCK']} لطفاً بازه زمانی بکاپ خودکار را به *دقیقه* وارد کنید (مثلا: `60`).")
        
    def handle_autobackup_disable(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        self._update_display(chat_id, msg_id, f"{EMOJI['WAIT']} در حال غیرفعال‌سازی...")
        
        config_data = self.state_manager.config
        config_data.get('telegram', {}).pop('backup_interval', None)
        self.state_manager.update_config(config_data)
        
        success, _, _ = self._run_panel_script(['do-auto-backup-setup'])
        result_text = f"{EMOJI['SUCCESS']} بکاپ خودکار غیرفعال شد." if success else f"{EMOJI['ERROR']} خطا در به‌روزرسانی کرون‌جب."
        
        self._update_display(chat_id, msg_id, result_text)
        time.sleep(2)
        self.display_autobackup_menu(call)

    def handle_stateful_messages(self, message):
        chat_id = message.chat.id
        state_info = self.conversational_states.pop(chat_id, None)
        if not state_info: return

        msg_id_to_edit = state_info['message_id']
        try:
            self.bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass

        state = state_info['state']
        if state == 'awaiting_interval':
            self._process_interval_input(message, msg_id_to_edit)
        elif state == 'awaiting_restore_file':
            self._process_restore_file(message, msg_id_to_edit)

    def _process_interval_input(self, message, msg_id_to_edit):
        chat_id = message.chat.id
        try:
            interval = int(message.text)
            if interval <= 0: raise ValueError("Interval must be positive.")
            
            self._update_display(chat_id, msg_id_to_edit, f"{EMOJI['WAIT']} در حال تنظیم بازه زمانی روی `{interval}` دقیقه...")
            
            config_data = self.state_manager.config
            config_data.setdefault('telegram', {})['backup_interval'] = str(interval)
            self.state_manager.update_config(config_data)
            
            success, _, _ = self._run_panel_script(['do-auto-backup-setup'])
            result_text = f"{EMOJI['SUCCESS']} زمان‌بندی با موفقیت به‌روز شد." if success else f"{EMOJI['ERROR']} خطا در به‌روزرسانی کرون‌جب."
            
            self._update_display(chat_id, msg_id_to_edit, result_text)
            time.sleep(2)
            self.display_autobackup_menu(message) # Pass a message-like object
            
        except (ValueError, TypeError):
            self._update_display(chat_id, msg_id_to_edit, f"{EMOJI['ERROR']} ورودی نامعتبر است. لطفاً فقط یک عدد صحیح مثبت وارد کنید.")
            time.sleep(2)
            self.display_autobackup_menu(message)

    def _process_restore_file(self, message, msg_id_to_edit):
        chat_id = message.chat.id
        if message.content_type != 'document' or not message.document.file_name.endswith('.tar.gz'):
            self._update_display(chat_id, msg_id_to_edit, f"{EMOJI['ERROR']} فایل نامعتبر است. لطفاً فایل با فرمت `.tar.gz` ارسال کنید.")
            time.sleep(2)
            self.display_main_menu(message)
            return

        self._update_display(chat_id, msg_id_to_edit, f"{EMOJI['WAIT']} در حال دانلود فایل...")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz", prefix="restore_") as temp_file:
            restore_file_path = Path(temp_file.name)
            try:
                file_info = self.bot.get_file(message.document.file_id)
                downloaded_file = self.bot.download_file(file_info.file_path)
                temp_file.write(downloaded_file)
                temp_file.flush() # Ensure data is written to disk
                
                self._update_display(chat_id, msg_id_to_edit, f"{EMOJI['WARNING']} *در حال ریستور...*\nاین عملیات ممکن است چند دقیقه طول بکشد. لطفاً صبور باشید.")
                
                success, output, duration = self._run_panel_script(['do-restore', str(restore_file_path)])
                
                if success:
                    self.state_manager.update_state('last_backup_time', 'هیچوقت (سیستم ریستور شده)')
                    result_text = f"{EMOJI['SUCCESS']} *ریستور کامل شد!* `({duration}s)`"
                else:
                    result_text = f"{EMOJI['ERROR']} *ریستور ناموفق بود!* `({duration}s)`\n```{output}```"
                
                self._update_display(chat_id, msg_id_to_edit, result_text)
                time.sleep(4)
                self.display_main_menu(message)

            except Exception as e:
                logger.error(f"Error during restore file processing: {e}", exc_info=True)
                self._update_display(chat_id, msg_id_to_edit, f"{EMOJI['ERROR']} خطای پیش‌بینی نشده در پردازش فایل.")
                time.sleep(2)
                self.display_main_menu(message)
            finally:
                if restore_file_path.exists():
                    restore_file_path.unlink()

    # --- Utility Methods ---
    def _run_panel_script(self, args: List[str]) -> Tuple[bool, str, str]:
        """A wrapper for executing the main backup/restore script."""
        venv_python = SCRIPT_DIR / 'venv' / 'bin' / 'python3'
        python_executable = str(venv_python) if venv_python.exists() else "python3"
        command = ['sudo', python_executable, str(MAIN_PANEL_SCRIPT)] + args
        
        start_time = time.time()
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=1200, check=False)
            duration = f"{time.time() - start_time:.2f}"
            
            if result.returncode == 0:
                return True, result.stdout.strip() or "Operation successful.", duration
            else:
                error_details = (result.stderr.strip() or "No stderr") + "\n" + (result.stdout.strip() or "No stdout")
                logger.error(f"Panel script failed. Args: {args}. Error: {error_details.strip()}")
                return False, error_details.strip(), duration
        except Exception as e:
            logger.critical(f"Critical error running panel script: {e}", exc_info=True)
            return False, f"A critical Python error occurred: {e}", f"{time.time() - start_time:.2f}"

    def _get_chat_info(self, call_or_msg) -> Tuple[int, int]:
        """Extracts chat_id and message_id from either a message or a callback query."""
        if isinstance(call_or_msg, telebot.types.CallbackQuery):
            return call_or_msg.message.chat.id, call_or_msg.message.message_id
        return call_or_msg.chat.id, call_or_msg.message_id

    def run(self):
        """Starts the bot's polling loop."""
        logger.info(f"Starting Bot v8.0 for Admin ID: {self.admin_id}...")
        while True:
            try:
                self.bot.infinity_polling(timeout=120, logger_level=logging.WARNING)
            except Exception as e:
                logger.critical(f"Bot polling crashed with error: {e}. Restarting in 10 seconds.", exc_info=True)
                time.sleep(10)


if __name__ == '__main__':
    try:
        config_data = StateManager(CONFIG_FILE, BOT_STATE_FILE).config
        bot_token = config_data.get('telegram', {}).get('bot_token')
        admin_id_str = config_data.get('telegram', {}).get('admin_chat_id')
        
        if not bot_token or not admin_id_str:
            raise ValueError("Bot Token or Admin Chat ID is missing in config.json")
            
        admin_id = int(admin_id_str)
        
        bot_instance = MarzbanControlBot(token=bot_token, admin_id=admin_id)
        bot_instance.run()

    except (ValueError, KeyError) as e:
        logger.critical(f"FATAL: Configuration error in config.json. Please ensure 'bot_token' and 'admin_chat_id' are set. Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred on startup: {e}", exc_info=True)
        sys.exit(1)
