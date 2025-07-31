#!/usr/bin/env python3
# =================================================================
# Marzban Professional Control Bot
# Creator: @HEXMOSTAFA
# Version: 2.0 (Classic, Interactive, Professional)
# =================================================================

import os
import json
import subprocess
import logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
MAIN_PANEL_SCRIPT = os.path.join(SCRIPT_DIR, "marzban_panel.py")
LOG_FILE = os.path.join(SCRIPT_DIR, "marzban_bot.log")

# --- Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    BOT_TOKEN = config['telegram']['bot_token']
    ADMIN_CHAT_ID = int(config['telegram']['admin_chat_id'])
except Exception as e:
    logger.critical(f"FATAL: Could not load config.json. Run the panel script first. Error: {e}")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
user_states = {} # A simple dictionary to keep track of what the user is doing

# --- Helper Functions ---
def run_main_script(args):
    command = ['sudo', 'python3', MAIN_PANEL_SCRIPT] + args
    logger.info(f"Executing: {' '.join(command)}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        output = result.stdout + "\n" + result.stderr
        return output or "Operation finished."
    except Exception as e:
        logger.critical(f"Subprocess execution error: {e}")
        return f"❌ Critical Python error: {e}"

def admin_only(func):
    def wrapper(message_or_call):
        chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
        if chat_id != ADMIN_CHAT_ID:
            bot.send_message(chat_id, "⛔️ You are not authorized.")
            return
        return func(message_or_call)
    return wrapper

# --- Keyboards ---
def main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📦 Backup", callback_data="create_backup"),
        InlineKeyboardButton("🔄 Restore", callback_data="start_restore"),
        InlineKeyboardButton("⚙️ Auto Backup", callback_data="start_auto_backup"),
        InlineKeyboardButton("🛠️ Settings", callback_data="open_settings")
    )
    return markup

def cancel_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    return markup

# --- Main Menu Handler ---
@bot.message_handler(commands=['start', 'help'])
@admin_only
def send_welcome(message):
    text = "🤖 *Marzban Control Bot*\n\nWelcome! Please select an option:"
    bot.send_message(message.chat.id, text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")

# --- Callback Query Handler (Handles all button clicks) ---
@bot.callback_query_handler(func=lambda call: True)
@admin_only
def handle_callback_query(call):
    bot.answer_callback_query(call.id) # To make the button "un-press"
    
    if call.data == "create_backup":
        handle_backup(call.message)
    elif call.data == "start_restore":
        handle_restore(call.message)
    elif call.data == "start_auto_backup":
        handle_auto_backup_setup(call.message)
    elif call.data == "open_settings":
        handle_settings(call.message)
    elif call.data == "main_menu":
        text = "🤖 *Marzban Control Bot*\n\nWelcome back! Please select an option:"
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")
    elif call.data == "cancel":
        user_states.pop(call.message.chat.id, None) # Clear user state
        text = "Operation cancelled."
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text)
        send_welcome(call.message) # Show main menu again

# --- Feature Handlers ---
def handle_backup(message):
    bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text="⏳ Starting full backup...")
    run_main_script(['do-backup'])
    bot.send_message(message.chat.id, "Backup process initiated. The file will be sent here shortly.")
    send_welcome(message) # Go back to main menu

def handle_restore(message):
    user_states[message.chat.id] = 'awaiting_restore_file'
    bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=message.message_id,
        text="🛑 **DANGER ZONE** 🛑\nPlease send your `.zip` backup file to proceed.",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )

def handle_auto_backup_setup(message):
    user_states[message.chat.id] = 'awaiting_interval'
    bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=message.message_id,
        text="Please enter the desired backup interval in **minutes** (e.g., `60` for every hour).",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )

def handle_settings(message):
    bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text="🔍 Fetching system info...")
    db_info_raw = "" # Initialize to capture output even on error
    try:
        # Step 1: Run the panel script to get the DB type
        db_info_raw = run_main_script(['get-db-type'])
        
        # Step 2: Try to parse the output as JSON
        db_info = json.loads(db_info_raw)
        db_type = db_info.get("database_type", "Unknown")

    except json.JSONDecodeError as e:
        # This block runs IF the output is NOT valid JSON
        db_type = "Error: Invalid Response"
        logger.error(f"JSONDecodeError: Could not parse panel script output.")
        logger.error(f"--- RAW OUTPUT FROM PANEL SCRIPT ---")
        logger.error(db_info_raw)
        logger.error(f"--- END OF RAW OUTPUT ---")
        logger.error(f"Specific JSON error: {e}")
        bot.send_message(message.chat.id, "Panel returned an invalid response. Check bot logs for details.")

    except Exception as e:
        # This block catches any other errors
        db_type = "Error: General Exception"
        logger.error(f"An unexpected error occurred in handle_settings: {e}", exc_info=True)
        bot.send_message(message.chat.id, f"An unexpected error occurred: {e}")


    # Step 3: Display the result in the settings menu
    text = f"⚙️ **Settings**\n\nDatabase Type: **{db_type}**"
    markup = InlineKeyboardMarkup()
    if db_type == "MySQL":
        markup.add(InlineKeyboardButton("🔑 Change MySQL Credentials", callback_data="change_mysql_creds"))
    markup.add(InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu"))
    
    # Use edit_message_text to update the original "Fetching..." message
    bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=text, reply_markup=markup, parse_mode="Markdown")
    

@bot.callback_query_handler(func=lambda call: call.data == 'change_mysql_creds')
@admin_only
def change_mysql_creds_start(call):
    user_states[call.message.chat.id] = 'awaiting_mysql_user'
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Please enter the new MySQL username:", reply_markup=cancel_keyboard())


# --- Message Handlers for Multi-Step Conversations ---
@bot.message_handler(content_types=['text', 'document'], func=lambda message: user_states.get(message.chat.id))
@admin_only
def handle_user_input(message):
    state_info = user_states.pop(message.chat.id) # Get and remove current state
    state = state_info if isinstance(state_info, str) else state_info.get('state')

    # --- Logic for awaiting a restore file ---
    if state == 'awaiting_restore_file':
        if message.content_type != 'document' or not message.document.file_name.endswith('.zip'):
            bot.send_message(message.chat.id, "❌ Invalid file. Please send a `.zip` backup file. Operation cancelled.")
            send_welcome(message)
            return

        temp_zip_path = None
        try:
            bot.send_message(message.chat.id, "✅ File received. Downloading...")
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            temp_dir = "/tmp"
            os.makedirs(temp_dir, exist_ok=True)
            temp_zip_path = os.path.join(temp_dir, message.document.file_name)
            with open(temp_zip_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            bot.send_message(message.chat.id, f"📥 Download complete. Starting restore process from `{temp_zip_path}`. This will take a while...", parse_mode="Markdown")
            
            result_message = run_main_script(['do-restore', temp_zip_path])
            
            bot.send_message(message.chat.id, f"**✨ Restore Process Finished**\n\n`{result_message}`", parse_mode="Markdown")
        
        except Exception as e:
            error_msg = f"An error occurred during the restore process: {e}"
            logger.error(error_msg, exc_info=True)
            bot.send_message(message.chat.id, f"❌ {error_msg}")
        
        finally:
            if temp_zip_path and os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
                logger.info(f"Cleaned up temporary file: {temp_zip_path}")
            send_welcome(message)

    # --- Logic for awaiting backup interval ---
    elif state == 'awaiting_interval':
        try:
            interval = int(message.text)
            if interval <= 0: raise ValueError
            with open(CONFIG_FILE, 'r+') as f:
                data = json.load(f)
                data['telegram']['backup_interval'] = str(interval)
                f.seek(0); json.dump(data, f, indent=4); f.truncate()
            bot.send_message(message.chat.id, f"✅ Interval set to {interval} minutes. Now setting up cronjob...")
            result = run_main_script(['do-auto-backup-setup'])
            bot.send_message(message.chat.id, f"**Setup Finished**\n`{result}`", parse_mode="Markdown")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Invalid number. Operation cancelled.")
        send_welcome(message)

    # --- Logic for awaiting new MySQL username ---
    elif state == 'awaiting_mysql_user':
        username = message.text
        # Save the username and set the next state to await the password
        user_states[message.chat.id] = {'state': 'awaiting_mysql_pass', 'username': username}
        bot.send_message(message.chat.id, "✅ Username received. Now please enter the new MySQL password:", reply_markup=cancel_keyboard())

    # --- Logic for awaiting new MySQL password ---
    elif state == 'awaiting_mysql_pass':
        db_user = state_info['username']
        db_pass = message.text
        bot.delete_message(message.chat.id, message.message_id) # Delete password message for security
        try:
            with open(CONFIG_FILE, 'r+') as f:
                data = json.load(f)
                if 'database' not in data: data['database'] = {}
                data['database']['user'] = db_user
                data['database']['password'] = db_pass
                f.seek(0); json.dump(data, f, indent=4); f.truncate()
            bot.send_message(message.chat.id, "✅ MySQL credentials updated successfully!")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Failed to save credentials: {e}")
        send_welcome(message)


if __name__ == '__main__':
    logger.info("Marzban Professional Control Bot is starting...")
    bot.infinity_polling()