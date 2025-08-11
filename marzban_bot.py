#!/usr/bin/env python3
# =================================================================
# Marzban Holographic Control Bot - Refactored
# Creator: @HEXMOSTAFA
# Re-engineered by AI Assistant
# Version: 9.2 (Final Polling Fix)
# =================================================================
import os
import sys
import json
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path
import tempfile
import tarfile

try:
    import telebot
    from telebot.async_telebot import AsyncTeleBot
    from telebot.types import InlineKeyboardMarkup
    from telebot.util import quick_markup
except ImportError:
    print("FATAL ERROR: 'pyTelegramBotAPI' is not installed. Please run 'pip install pyTelegramBotAPI'.")
    sys.exit(1)

# --- Constants ---
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
MAIN_PANEL_SCRIPT = SCRIPT_DIR / "marzban_panel.py"
LOG_FILE = SCRIPT_DIR / "marzban_backup.log"
BOT_LOG_FILE = SCRIPT_DIR / "marzban_bot.log"
BOT_STATE_FILE = SCRIPT_DIR / "bot_state.json"

EMOJI: Dict[str, str] = {
    "PANEL": "📱", "BACKUP": "📦", "RESTORE": "🔄", "AUTO": "⚙️",
    "SETTINGS": "ℹ️", "STATUS": "📊", "LOGS": "📋", "SUCCESS": "✅", "ERROR": "❌",
    "WAIT": "⏳", "INFO": "🔵", "WARNING": "⚠️", "BACK": "⬅️", "DANGER": "🛑",
    "EDIT": "📝", "CLOCK": "⏱️", "CONFIRM": "👍", "TOGGLE_ON": "🟢", "TOGGLE_OFF": "🔴"
}

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(BOT_LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class StateManager:
    """Handles sync reading/writing of state/config files in a centralized way."""
    def __init__(self, config_path: Path, state_path: Path):
        self.config_path = config_path
        self.state_path = state_path
    
    def _load_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists(): return {}
        try:
            with path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError): return {}

    def _save_json(self, path: Path, data: Dict[str, Any]):
        with path.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    def get_config(self) -> Dict[str, Any]:
        return self._load_json(self.config_path)

    def get_state(self) -> Dict[str, Any]:
        return self._load_json(self.state_path)

    def update_config(self, new_data: Dict[str, Any]):
        current_config = self.get_config()
        current_config.update(new_data)
        self._save_json(self.config_path, current_config)

    def update_state(self, key: str, value: Any):
        current_state = self.get_state()
        current_state[key] = value
        self._save_json(self.state_path, current_state)


class MarzbanControlBot:
    """An advanced, async bot for managing Marzban with a luxurious feel."""
    
    CB_MAIN_MENU = "main_menu"
    CB_DO_BACKUP = "do_backup"
    CB_RESTORE_START = "restore_start"
    CB_RESTORE_CONFIRM = "restore_confirm"
    CB_AUTOBACKUP_MENU = "autobackup_menu"
    CB_AUTOBACKUP_ENABLE = "autobackup_enable"
    CB_AUTOBACKUP_DISABLE = "autobackup_disable"
    CB_AUTOBACKUP_EDIT = "autobackup_edit_interval"
    CB_SYSTEM_STATUS = "system_status"
    CB_LOGS_MENU = "view_logs"
    CB_VIEW_BACKUP_LOG = "view_backup_log"
    CB_VIEW_BOT_LOG = "view_bot_log"

    def __init__(self, token: str, admin_id: int):
        self.bot = AsyncTeleBot(token, parse_mode="Markdown")
        self.admin_id = admin_id
        self.state_manager = StateManager(CONFIG_FILE, BOT_STATE_FILE)
        self.conversational_states: Dict[int, Dict[str, Any]] = {}
        self._register_handlers()

    def _register_handlers(self):
        @self.bot.message_handler(commands=['start'])
        @self.admin_only
        async def handle_start(message):
            initial_msg = await self.bot.send_message(message.chat.id, f"{EMOJI['WAIT']} Initializing Interface...")
            await self.display_main_menu(initial_msg)

        @self.bot.callback_query_handler(func=lambda call: True)
        @self.admin_only
        async def master_callback_handler(call):
            await self.bot.answer_callback_query(call.id)
            action_map = {
                self.CB_MAIN_MENU: self.display_main_menu,
                self.CB_DO_BACKUP: self.handle_backup,
                self.CB_RESTORE_START: self.handle_restore_start,
                self.CB_RESTORE_CONFIRM: self.handle_restore_confirm,
                self.CB_AUTOBACKUP_MENU: self.display_autobackup_menu,
                self.CB_AUTOBACKUP_ENABLE: self.handle_autobackup_set_interval,
                self.CB_AUTOBACKUP_DISABLE: self.handle_autobackup_disable,
                self.CB_AUTOBACKUP_EDIT: self.handle_autobackup_set_interval,
                self.CB_SYSTEM_STATUS: self.handle_system_status,
                self.CB_LOGS_MENU: self.display_logs_menu,
                self.CB_VIEW_BACKUP_LOG: lambda c: self.handle_view_log(c, LOG_FILE),
                self.CB_VIEW_BOT_LOG: lambda c: self.handle_view_log(c, BOT_LOG_FILE),
            }
            handler = action_map.get(call.data)
            if handler:
                await handler(call)

        @self.bot.message_handler(content_types=['text', 'document'], func=lambda msg: self.conversational_states.get(msg.chat.id) is not None)
        @self.admin_only
        async def handle_stateful_messages(message):
            chat_id = message.chat.id
            state_info = self.conversational_states.pop(chat_id, None)
            if not state_info: return

            try: await self.bot.delete_message(chat_id, message.message_id)
            except Exception: pass
            
            state = state_info['state']
            if state == 'awaiting_interval':
                await self._process_interval_input(message, state_info['message_id'])
            elif state == 'awaiting_restore_file':
                await self._process_restore_file(message, state_info['message_id'])

    def admin_only(self, func):
        async def wrapper(message_or_call):
            chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
            if chat_id != self.admin_id:
                logger.warning(f"Unauthorized access attempt from chat_id: {chat_id}")
                return
            await func(message_or_call)
        return wrapper

    # --- Keyboard Generators ---
    def _get_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        return quick_markup({
            f"{EMOJI['BACKUP']} Backup": {'callback_data': self.CB_DO_BACKUP},
            f"{EMOJI['RESTORE']} Restore": {'callback_data': self.CB_RESTORE_START},
            f"{EMOJI['AUTO']} Auto Backup": {'callback_data': self.CB_AUTOBACKUP_MENU},
            f"{EMOJI['STATUS']} System Status": {'callback_data': self.CB_SYSTEM_STATUS},
            f"{EMOJI['LOGS']} View Logs": {'callback_data': self.CB_LOGS_MENU},
        }, row_width=2)

    def _get_autobackup_menu_keyboard(self) -> InlineKeyboardMarkup:
        config = self.state_manager.get_config()
        interval = config.get('telegram', {}).get('backup_interval')
        is_enabled = bool(interval)
        
        toggle_text = f"{EMOJI['TOGGLE_OFF']} غیرفعال‌سازی" if is_enabled else f"{EMOJI['TOGGLE_ON']} فعال‌سازی"
        toggle_action = self.CB_AUTOBACKUP_DISABLE if is_enabled else self.CB_AUTOBACKUP_ENABLE
        
        markup_dict = {toggle_text: {'callback_data': toggle_action}}
        if is_enabled:
            markup_dict[f"{EMOJI['EDIT']} تغییر بازه زمانی"] = {'callback_data': self.CB_AUTOBACKUP_EDIT}
        
        markup_dict[f"{EMOJI['BACK']} بازگشت"] = {'callback_data': self.CB_MAIN_MENU}
        return quick_markup(markup_dict, row_width=1)

    # --- Display Updaters ---
    async def _update_display(self, chat_id: int, message_id: int, text: str, markup: Optional[InlineKeyboardMarkup] = None):
        try:
            await self.bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        except telebot.apihelper.ApiTelegramException as e:
            if 'message is not modified' not in e.description:
                logger.error(f"Failed to update display: {e}")
    
    async def display_main_menu(self, call_or_msg):
        chat_id, msg_id = self._get_chat_info(call_or_msg)
        state = self.state_manager.get_state()
        config = self.state_manager.get_config()
        
        last_backup_str = state.get('last_backup_time', 'هیچوقت')
        last_backup_display = last_backup_str
        
        if last_backup_str and 'ریستور' not in last_backup_str and last_backup_str != 'هیچوقت':
            try:
                last_backup_display = datetime.fromisoformat(last_backup_str).strftime('%Y-%m-%d %H:%M')
            except (ValueError, TypeError):
                logger.warning(f"Could not parse date: '{last_backup_str}'. Displaying as is.")
        
        interval = config.get('telegram', {}).get('backup_interval')
        auto_status = f"{EMOJI['TOGGLE_ON']} فعال (هر {interval} دقیقه)" if interval else f"{EMOJI['TOGGLE_OFF']} غیرفعال"
        
        text = (
            f"*{EMOJI['PANEL']} Holographic Control Interface*\n\n"
            f"`System Time..: ` `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"`Last Backup..: ` `{last_backup_display}`\n"
            f"`Auto Backup..: ` {auto_status}\n\n"
            "Awaiting command..."
        )
        await self._update_display(chat_id, msg_id, text, self._get_main_menu_keyboard())

    async def display_autobackup_menu(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        config = self.state_manager.get_config()
        interval = config.get('telegram', {}).get('backup_interval')
        status = f"در حال حاضر بکاپ خودکار *فعال* است و هر `{interval}` دقیقه یکبار اجرا می‌شود." if interval else "بکاپ خودکار در حال حاضر *غیرفعال* است."
        text = f"{EMOJI['AUTO']} *مدیریت بکاپ خودکار*\n\n{status}\n\nاز دکمه‌های زیر برای مدیریت استفاده کنید."
        await self._update_display(chat_id, msg_id, text, self._get_autobackup_menu_keyboard())
    
    async def display_logs_menu(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        text = f"{EMOJI['LOGS']} *مشاهده لاگ‌ها*\n\nکدام فایل لاگ را می‌خواهید مشاهده کنید؟ (نمایش ۲۰ خط آخر)"
        markup = quick_markup({
            "📋 لاگ پنل (Backup/Restore)": {'callback_data': self.CB_VIEW_BACKUP_LOG},
            "🤖 لاگ ربات (Bot)": {'callback_data': self.CB_VIEW_BOT_LOG},
            f"{EMOJI['BACK']} بازگشت": {'callback_data': self.CB_MAIN_MENU},
        }, row_width=1)
        await self._update_display(chat_id, msg_id, text, markup)
        
    # --- Action Handlers ---
    async def handle_backup(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        success, result, duration = await self.run_panel_script_streamed(['run-backup'], call)
        if success:
            self.state_manager.update_state('last_backup_time', datetime.utcnow().isoformat())
            result_text = f"{EMOJI['SUCCESS']} *بکاپ کامل شد!* `({duration} ثانیه)`"
        else:
            result_text = f"{EMOJI['ERROR']} *عملیات ناموفق بود!*\n`{result}`"
        
        await self._update_display(chat_id, msg_id, result_text)
        await asyncio.sleep(4)
        await self.display_main_menu(call)

    async def handle_restore_start(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        text = (
            f"{EMOJI['DANGER']} *هشدار بسیار مهم*\n\n"
            "این عمل تمام اطلاعات فعلی شما را با فایل بکاپ *جایگزین* می‌کند. این عمل غیرقابل بازگشت است.\n\n"
            "آیا برای ادامه مطمئن هستید؟"
        )
        markup = quick_markup({
            f"{EMOJI['DANGER']} بله، ریستور کن": {'callback_data': self.CB_RESTORE_CONFIRM},
            f"{EMOJI['BACK']} انصراف": {'callback_data': self.CB_MAIN_MENU},
        })
        await self._update_display(chat_id, msg_id, text, markup)
        
    async def handle_restore_confirm(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        self.conversational_states[chat_id] = {'state': 'awaiting_restore_file', 'message_id': msg_id}
        await self._update_display(chat_id, msg_id, f"{EMOJI['INFO']} لطفاً فایل بکاپ با فرمت `.tar.gz` را ارسال کنید.")

    async def handle_autobackup_set_interval(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        self.conversational_states[chat_id] = {'state': 'awaiting_interval', 'message_id': msg_id}
        await self._update_display(chat_id, msg_id, f"{EMOJI['CLOCK']} لطفاً بازه زمانی بکاپ خودکار را به *دقیقه* وارد کنید (مثلا: `60`).")
        
    async def handle_autobackup_disable(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        await self._update_display(chat_id, msg_id, f"{EMOJI['WAIT']} در حال غیرفعال‌سازی...")
        
        config_data = self.state_manager.get_config()
        config_data.get('telegram', {}).pop('backup_interval', None)
        self.state_manager._save_json(CONFIG_FILE, config_data)
        
        success, output, _ = await self._run_panel_script(['do-auto-backup-setup'])
        result_text = f"{EMOJI['SUCCESS']} بکاپ خودکار غیرفعال شد." if success else f"{EMOJI['ERROR']} خطا در به‌روزرسانی کرون‌جب:\n`{output}`"
        
        await self._update_display(chat_id, msg_id, result_text)
        await asyncio.sleep(2)
        await self.display_autobackup_menu(call)
        
    async def handle_system_status(self, call):
        chat_id, msg_id = self._get_chat_info(call)
        await self._update_display(chat_id, msg_id, f"{EMOJI['WAIT']} در حال دریافت اطلاعات سیستم...")
        
        try:
            tasks = [
                asyncio.create_subprocess_shell("docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE),
                asyncio.create_subprocess_shell("uptime -p", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE),
                asyncio.create_subprocess_shell("free -h", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE),
                asyncio.create_subprocess_shell("df -h /", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            ]
            results = await asyncio.gather(*(p.communicate() for p in await asyncio.gather(*tasks)))
            
            stdout_ps, stdout_up, stdout_mem, stdout_disk = (res[0].decode('utf-8') for res in results)
            
            status_text = (
                f"{EMOJI['STATUS']} *وضعیت سیستم*\n\n"
                f"*Docker Containers:*\n```\n{stdout_ps}\n```\n"
                f"*Uptime:*\n`{stdout_up.strip()}`\n\n"
                f"*Memory Usage:*\n```\n{stdout_mem}\n```\n"
                f"*Disk Usage (Root):*\n```\n{stdout_disk}\n```"
            )
        except Exception as e:
            status_text = f"{EMOJI['ERROR']} *خطا در دریافت اطلاعات سیستم:*\n`{e}`"

        markup = quick_markup({f"{EMOJI['BACK']} بازگشت": {'callback_data': self.CB_MAIN_MENU}})
        await self._update_display(chat_id, msg_id, status_text, markup)
    
    async def handle_view_log(self, call, log_path: Path):
        chat_id, msg_id = self._get_chat_info(call)
        await self._update_display(chat_id, msg_id, f"{EMOJI['WAIT']} در حال خواندن فایل لاگ...")
        
        try:
            if not log_path.exists():
                raise FileNotFoundError(f"فایل لاگ پیدا نشد: {log_path.name}")

            proc = await asyncio.create_subprocess_shell(f"tail -n 20 {log_path}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                log_content = stdout.decode('utf-8', errors='ignore').strip()
                text = f"{EMOJI['LOGS']} *نمایش 20 خط آخر از `{log_path.name}`*\n\n```\n{log_content or 'فایل لاگ خالی است.'}\n```"
            else:
                text = f"{EMOJI['ERROR']} *خطا در خواندن لاگ:*\n`{stderr.decode('utf-8', errors='ignore')}`"
        
        except Exception as e:
            text = f"{EMOJI['ERROR']} *خطا در پردازش فایل لاگ:*\n`{e}`"

        markup = quick_markup({f"{EMOJI['BACK']} بازگشت": {'callback_data': self.CB_LOGS_MENU}})
        await self._update_display(chat_id, msg_id, text, markup)
        
    async def _process_interval_input(self, message, msg_id_to_edit):
        chat_id = message.chat.id
        call_obj = telebot.types.CallbackQuery(id=0, from_user=message.from_user, data="", chat_instance="", json_string="", message=message)
        
        try:
            interval = int(message.text)
            if interval <= 0: raise ValueError("Interval must be positive.")
            
            await self._update_display(chat_id, msg_id_to_edit, f"{EMOJI['WAIT']} در حال تنظیم بازه زمانی روی `{interval}` دقیقه...")
            
            config_data = self.state_manager.get_config()
            config_data.setdefault('telegram', {})['backup_interval'] = str(interval)
            self.state_manager._save_json(CONFIG_FILE, config_data)
            
            success, output, _ = await self._run_panel_script(['do-auto-backup-setup'])
            result_text = f"{EMOJI['SUCCESS']} زمان‌بندی با موفقیت به‌روز شد." if success else f"{EMOJI['ERROR']} خطا در به‌روزرسانی کرون‌جب:\n`{output}`"
            
            await self._update_display(chat_id, msg_id_to_edit, result_text)
            await asyncio.sleep(2)
            await self.display_autobackup_menu(call_obj)
            
        except (ValueError, TypeError):
            await self._update_display(chat_id, msg_id_to_edit, f"{EMOJI['ERROR']} ورودی نامعتبر است. لطفاً فقط یک عدد صحیح مثبت وارد کنید.")
            await asyncio.sleep(3)
            await self.display_autobackup_menu(call_obj)

    async def _process_restore_file(self, message, msg_id_to_edit):
        chat_id = message.chat.id
        call_obj = telebot.types.CallbackQuery(id=0, from_user=message.from_user, data="", chat_instance="", json_string="", message=message)
        
        if message.content_type != 'document' or not message.document.file_name.endswith('.tar.gz'):
            await self._update_display(chat_id, msg_id_to_edit, f"{EMOJI['ERROR']} فایل نامعتبر است. لطفاً فایل با فرمت `.tar.gz` ارسال کنید.")
            await asyncio.sleep(3)
            await self.display_main_menu(call_obj)
            return

        await self._update_display(chat_id, msg_id_to_edit, f"{EMOJI['WAIT']} در حال دانلود فایل...")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz", prefix="restore_") as temp_file:
            restore_file_path = Path(temp_file.name)
            try:
                file_info = await self.bot.get_file(message.document.file_id)
                downloaded_file = await self.bot.download_file(file_info.file_path)
                temp_file.write(downloaded_file)
                temp_file.flush()

                with tarfile.open(restore_file_path, "r:gz") as tar:
                    members = tar.getnames()
                    if not any(m.startswith('filesystem/') for m in members) or not any(m.startswith('db_dumps/') for m in members):
                        raise ValueError("فایل بکاپ ساختار معتبری ندارد.")

                success, result, duration = await self.run_panel_script_streamed(['do-restore', str(restore_file_path)], call_obj)
                
                if success:
                    self.state_manager.update_state('last_backup_time', 'هیچوقت (سیستم ریستور شده)')
                    result_text = f"{EMOJI['SUCCESS']} *ریستور کامل شد!* `({duration}s)`"
                else:
                    result_text = f"{EMOJI['ERROR']} *ریستور ناموفق بود!*\n`{result}`"
                
                await self._update_display(chat_id, msg_id_to_edit, result_text)
                await asyncio.sleep(4)
                await self.display_main_menu(call_obj)

            except Exception as e:
                logger.error(f"Error during restore file processing: {e}", exc_info=True)
                await self._update_display(chat_id, msg_id_to_edit, f"{EMOJI['ERROR']} خطای پیش‌بینی نشده در پردازش فایل:\n`{e}`")
                await asyncio.sleep(3)
                await self.display_main_menu(call_obj)
            finally:
                if restore_file_path.exists():
                    restore_file_path.unlink()

    # --- Utility Methods ---
    async def _run_panel_script(self, args: List[str]) -> Tuple[bool, str, str]:
        """Runs the panel script and waits for completion (for short tasks)."""
        venv_python = SCRIPT_DIR / 'venv' / 'bin' / 'python3'
        python_executable = str(venv_python) if venv_python.exists() else "python3"
        command = ['sudo', python_executable, str(MAIN_PANEL_SCRIPT)] + args
        
        start_time = time.time()
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        duration = f"{time.time() - start_time:.2f}"
        
        if process.returncode == 0:
            return True, stdout.decode('utf-8').strip(), duration
        else:
            error = stderr.decode('utf-8').strip() + "\n" + stdout.decode('utf-8').strip()
            return False, error.strip(), duration
            
    async def run_panel_script_streamed(self, args: List[str], call) -> Tuple[bool, str, str]:
        """Runs the panel script and streams live feedback (for long tasks)."""
        chat_id, msg_id = self._get_chat_info(call)
        
        venv_python = SCRIPT_DIR / 'venv' / 'bin' / 'python3'
        python_executable = str(venv_python) if venv_python.exists() else "python3"
        command = ['sudo', '-E', python_executable, str(MAIN_PANEL_SCRIPT)] + args
        
        start_time = time.time()
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )

        full_output = ""
        last_update_time = time.time()
        
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes: break
            
            decoded_line = line_bytes.decode('utf-8', errors='ignore').strip()
            if not decoded_line: continue
            
            full_output += decoded_line + "\n"
            
            if time.time() - last_update_time > 1.5:
                progress_text = f"{EMOJI['WAIT']} *عملیات در حال انجام...*\n\n`{decoded_line}`"
                await self._update_display(chat_id, msg_id, progress_text)
                last_update_time = time.time()

        await process.wait()
        duration = f"{time.time() - start_time:.2f}"
        
        if process.returncode == 0:
            return True, full_output, duration
        else:
            logger.error(f"Panel script failed. Args: {args}. Output:\n{full_output}")
            return False, full_output, duration

    def _get_chat_info(self, call_or_msg) -> Tuple[int, int]:
        if isinstance(call_or_msg, telebot.types.CallbackQuery):
            return call_or_msg.message.chat.id, call_or_msg.message.message_id
        return call_or_msg.chat.id, call_or_msg.message_id

    async def run(self):
        """Starts the bot's polling loop."""
        logger.info(f"Starting Bot v9.2 for Admin ID: {self.admin_id}...")
        while True:
            try:
                # <<< CHANGE: Removed the unsupported 'logger_level' argument >>>
                await self.bot.polling(non_stop=True, timeout=120)
            except Exception as e:
                logger.critical(f"Bot polling crashed with error: {e}. Restarting in 10 seconds.", exc_info=True)
                await asyncio.sleep(10)


if __name__ == '__main__':
    try:
        config = StateManager(CONFIG_FILE, BOT_STATE_FILE).get_config()
        bot_token = config.get('telegram', {}).get('bot_token')
        admin_id_str = config.get('telegram', {}).get('admin_chat_id')
        
        if not bot_token or not admin_id_str:
            raise ValueError("Bot Token or Admin Chat ID is missing in config.json")
            
        bot_instance = MarzbanControlBot(token=bot_token, admin_id=int(admin_id_str))
        asyncio.run(bot_instance.run())

    except (ValueError, KeyError) as e:
        logger.critical(f"FATAL: Config error. Ensure 'bot_token' and 'admin_chat_id' are set. Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred on startup: {e}", exc_info=True)
        sys.exit(1)
