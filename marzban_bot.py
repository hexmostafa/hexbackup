#!/usr/bin/env python3
# =================================================================
# Marzban Holographic Control Bot
# Creator: @HEXMOSTAFA
# Re-engineered by AI Assistant
# Version: 9.0 (Async, Live Feedback, Luxury Edition)
# =================================================================
import os
import sys
import json
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import tempfile

try:
    import telebot
    from telebot.async_telebot import AsyncTeleBot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
except ImportError:
    print("FATAL ERROR: 'pyTelegramBotAPI' is not installed. Please run 'pip install pyTelegramBotAPI'.")
    sys.exit(1)

# --- Constants ---
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
MAIN_PANEL_SCRIPT = SCRIPT_DIR / "marzban_panel.py"
LOG_FILE = SCRIPT_DIR / "marzban_bot.log"
BOT_STATE_FILE = SCRIPT_DIR / "bot_state.json"

EMOJI: Dict[str, str] = {
    "PANEL": " holographic_interface: ", "BACKUP": "📦", "RESTORE": "🔄", "AUTO": "⚙️",
    "SETTINGS": "ℹ️", "STATUS": "📊", "LOGS": "📋", "SUCCESS": "✅", "ERROR": "❌",
    "WAIT": "⏳", "INFO": "🔵", "WARNING": "⚠️", "BACK": "⬅️", "DANGER": "🛑",
    "EDIT": "📝", "CLOCK": "⏱️", "CONFIRM": "👍", "TOGGLE_ON": "🟢", "TOGGLE_OFF": "🔴"
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
    """Handles sync reading/writing of state/config files."""
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

    CB_PREFIX = "v9:"
    CB_MAIN_MENU = f"{CB_PREFIX}main_menu"
    # ... (other callbacks)

    def __init__(self, token: str, admin_id: int):
        self.bot = AsyncTeleBot(token, parse_mode="Markdown")
        self.admin_id = admin_id
        self.state_manager = StateManager(CONFIG_FILE, BOT_STATE_FILE)
        self.conversational_states: Dict[int, Dict[str, Any]] = {}
        self._register_handlers()

    def _register_handlers(self):
        # Using decorators for async handlers
        @self.bot.message_handler(commands=['start'])
        @self.admin_only
        async def handle_start(message):
            initial_msg = await self.bot.send_message(message.chat.id, f"{EMOJI['WAIT']} Initializing Interface...")
            await self.display_main_menu(initial_msg)

        @self.bot.callback_query_handler(func=lambda call: True)
        @self.admin_only
        async def master_callback_handler(call):
            await self.bot.answer_callback_query(call.id)
            # Simplified routing
            action_map = {
                self.CB_MAIN_MENU: self.display_main_menu,
                "do_backup": self.handle_backup,
                "restore_start": self.handle_restore_start,
                "restore_confirm": self.handle_restore_confirm,
                "autobackup_menu": self.display_autobackup_menu,
                "autobackup_enable": self.handle_autobackup_set_interval,
                "autobackup_disable": self.handle_autobackup_disable,
                "autobackup_edit_interval": self.handle_autobackup_set_interval,
                "system_status": self.handle_system_status,
                "view_logs": self.display_logs_menu,
                "view_backup_log": lambda c: self.handle_view_log(c, LOG_FILE),
                "view_bot_log": lambda c: self.handle_view_log(c, BOT_STATE_FILE.with_suffix('.log')),
            }
            handler = action_map.get(call.data)
            if handler:
                await handler(call)

        @self.bot.message_handler(content_types=['text', 'document'], func=lambda msg: self.conversational_states.get(msg.chat.id) is not None)
        @self.admin_only
        async def handle_stateful_messages(message):
            # Logic for handling states like awaiting files or text input
            chat_id = message.chat.id
            state_info = self.conversational_states.pop(chat_id, None)
            if not state_info: return

            await self.bot.delete_message(chat_id, message.message_id)
            
            state = state_info['state']
            if state == 'awaiting_interval':
                await self._process_interval_input(message, state_info['message_id'])
            elif state == 'awaiting_restore_file':
                await self._process_restore_file(message, state_info['message_id'])
    
    # ... (rest of the methods will be async)

    async def _update_display(self, chat_id: int, message_id: int, text: str, markup: Optional[InlineKeyboardMarkup] = None):
        try:
            await self.bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            if 'message is not modified' not in e.description:
                logger.error(f"Failed to update display: {e}")
    
    async def display_main_menu(self, call_or_msg):
        chat_id, msg_id = self._get_chat_info(call_or_msg)
        state = self.state_manager.get_state()
        config = self.state_manager.get_config()
        
        last_backup_iso = state.get('last_backup_time', 'هیچوقت')
        last_backup = datetime.fromisoformat(last_backup_iso).strftime('%Y-%m-%d %H:%M') if last_backup_iso != 'هیچوقت' else 'هیچوقت'
        
        interval = config.get('telegram', {}).get('backup_interval')
        auto_status = f"{EMOJI['TOGGLE_ON']} فعال (هر {interval} دقیقه)" if interval else f"{EMOJI['TOGGLE_OFF']} غیرفعال"
        
        text = (
            f"*{EMOJI['PANEL']}Holographic Control Interface*\n\n"
            f"`System Time...: ` {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"`Last Backup..: ` {last_backup}\n"
            f"`Auto Backup..: ` {auto_status}\n\n"
            "Awaiting command..."
        )
        markup = quick_markup({
            f"{EMOJI['BACKUP']} Backup": {'callback_data': "do_backup"},
            f"{EMOJI['RESTORE']} Restore": {'callback_data': "restore_start"},
            f"{EMOJI['AUTO']} Auto Backup": {'callback_data': "autobackup_menu"},
            f"{EMOJI['STATUS']} System Status": {'callback_data': "system_status"},
            f"{EMOJI['LOGS']} View Logs": {'callback_data': "view_logs"},
        }, row_width=2)
        await self._update_display(chat_id, msg_id, text, markup)
    
    # ... more async methods for handling each action
    
    async def run_panel_script_streamed(self, args: List[str], call) -> Tuple[bool, str]:
        chat_id, msg_id = self._get_chat_info(call)
        
        venv_python = SCRIPT_DIR / 'venv' / 'bin' / 'python3'
        python_executable = str(venv_python) if venv_python.exists() else "python3"
        command = ['sudo', python_executable, str(MAIN_PANEL_SCRIPT)] + args
        
        start_time = time.time()
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        full_output = ""
        last_update_time = time.time()
        
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            decoded_line = line.decode('utf-8').strip()
            full_output += decoded_line + "\n"
            
            # Throttle updates to avoid hitting Telegram API limits
            if time.time() - last_update_time > 1.5:
                progress_text = f"{EMOJI['WAIT']} *Operation in progress...*\n\n`{decoded_line}`"
                await self._update_display(chat_id, msg_id, progress_text)
                last_update_time = time.time()

        await process.wait()
        duration = f"{time.time() - start_time:.2f}"
        
        if process.returncode == 0:
            return True, duration
        else:
            stderr_output = await process.stderr.read()
            error = stderr_output.decode('utf-8').strip()
            full_output += f"\n--- STDERR ---\n{error}"
            logger.error(f"Script failed. Args: {args}. Output:\n{full_output}")
            return False, f"{duration}s\n`{full_output}`"
            
    # ... other methods like _process_restore_file will use the new streamed runner
    
    def run(self):
        logger.info(f"Starting Bot v9.0 for Admin ID: {self.admin_id}...")
        try:
            asyncio.run(self.bot.polling(non_stop=True, logger_level=logging.WARNING))
        except Exception as e:
            logger.critical(f"Bot polling crashed with error: {e}. Please restart.", exc_info=True)


if __name__ == '__main__':
    try:
        config = StateManager(CONFIG_FILE, BOT_STATE_FILE).get_config()
        bot_token = config.get('telegram', {}).get('bot_token')
        admin_id_str = config.get('telegram', {}).get('admin_chat_id')
        
        if not bot_token or not admin_id_str:
            raise ValueError("Bot Token or Admin Chat ID is missing in config.json")
            
        bot_instance = MarzbanControlBot(token=bot_token, admin_id=int(admin_id_str))
        bot_instance.run()

    except (ValueError, KeyError) as e:
        logger.critical(f"FATAL: Config error. Ensure 'bot_token' and 'admin_chat_id' are set. Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred on startup: {e}", exc_info=True)
        sys.exit(1)
