from google.cloud.firestore import FieldFilter
from telegram import Update
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters,
                          CallbackContext)
#import configparser
import logging
from ChatGPT_HKBU import HKBU_ChatGPT
import firebase_admin
from firebase_admin import credentials, firestore
import logging
from firebase_admin import firestore
import os
import requests

class HKBU_ChatGPT:
    def __init__(self):
        self.basic_url = os.getenv('CHATGPT_BASICURL')
        self.model_name = os.getenv('CHATGPT_MODELNAME')
        self.api_version = os.getenv('CHATGPT_APIVERSION')
        self.access_token = os.getenv('CHATGPT_ACCESS_TOKEN')
        
        if not all([self.basic_url, self.model_name, self.api_version, self.access_token]):
            missing = []
            if not self.basic_url: missing.append('CHATGPT_BASICURL')
            if not self.model_name: missing.append('CHATGPT_MODELNAME')
            if not self.api_version: missing.append('CHATGPT_APIVERSION')
            if not self.access_token: missing.append('CHATGPT_ACCESS_TOKEN')
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")

    def submit(self, message):
        conversation = [{"role": "user", "content": message}]
        url = f"{self.basic_url}/deployments/{self.model_name}/chat/completions/?api-version={self.api_version}"
        headers = {
            'Content-Type': 'application/json',
            'api-key': self.access_token
        }
        payload = {'messages': conversation}
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content']
        except requests.exceptions.RequestException as e:
            return f'Error: {str(e)}'
        except KeyError:
            return 'Error: Invalid API response structure'

class FirestoreHandler(logging.Handler):
    def __init__(self, collection):
        super().__init__()
        self.collection = collection
        self.db = firestore.client()

    def emit(self, record):
        try:
            log_entry = {
                "message": self.format(record),
                "timestamp": firestore.SERVER_TIMESTAMP,
                "level": record.levelname
            }
            self.db.collection(self.collection).add(log_entry)
        except Exception as e:
            print(f"Failed to log to Firestore: {e}")


def equiped_chatgpt1(update, context):
    global chatgpt, db
    user_id = str(update.effective_user.id)
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        context.bot.send_message(chat_id=update.effective_chat.id, text="Set your interests first with /interests!")
        return

    user_data = user_doc.to_dict()
    in_group = user_data.get('in_group', False)

    if in_group:
        interests = user_data.get('interests', [])
        matches = (
            db.collection('users')
            .where(filter=FieldFilter('interests', 'array_contains_any', interests))
            .where(filter=FieldFilter('__name__', '!=', user_ref))
            .stream()
        )
        reply_message = update.message.text
        for match in matches:
            # Use run_async to send messages without blocking
            context.dispatcher.run_async(
                context.bot.send_message,
                chat_id=int(match.id),
                text=reply_message
            )
    else:
        # Run ChatGPT submission asynchronously
        print("chatgpt:")
        reply_message = chatgpt.submit(update.message.text)
        print("reply", reply_message)
        context.bot.send_message(chat_id=update.effective_chat.id, text=reply_message)

def main():
    # Load your token and create an Updater for your Bot
#    config = configparser.ConfigParser()
#    config.read('config.ini')  
    required_vars = [
        'TELEGRAM_ACCESS_TOKEN',
        'CHATGPT_BASICURL',
        'CHATGPT_MODELNAME',
        'CHATGPT_APIVERSION',
        'CHATGPT_ACCESS_TOKEN'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise SystemExit(f"Missing environment variables: {', '.join(missing_vars)}")

  
    updater = Updater(os.environ['TELEGRAM_ACCESS_TOKEN'], use_context=True)
    dispatcher = updater.dispatcher
    global chatgpt
    chatgpt = HKBU_ChatGPT()
    try:
        global db  # Declare db as global
        # Initialize Firebase
        cred = credentials.Certificate("service-account-key.json")
        firebase_admin.initialize_app(cred, {'projectId': 'comp7940-aa-2'})
        db = firestore.client()

        # Test the database
        doc_ref = db.collection('test').document('test_doc')
        doc_ref.set({'message': 'Hello Firestore!'})
        print("Firestore connection successful!")
    except Exception as e:
        print(f"Firestore connection failed: {e}")
        exit(1)
    chatgpt_handler = MessageHandler(Filters.text & (~Filters.command), equiped_chatgpt1)

    # Configure logging
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.INFO,
                        handlers=[FirestoreHandler(collection='logs')])

    # Register command handlers
    dispatcher.add_handler(CommandHandler("hello", hello, run_async=True))
    dispatcher.add_handler(CommandHandler("match", match, run_async=True))
    dispatcher.add_handler(CommandHandler("add", add))
    #dispatcher.add_handler(MessageHandler(Filters.text & (~Filters.command), equiped_chatgpt1, run_async=True))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(chatgpt_handler)
    dispatcher.add_handler(CommandHandler("recommend", equiped_chatgpt))
    dispatcher.add_handler(CommandHandler("interests", interests))
    dispatcher.add_handler(CommandHandler("exit", exit_group))

    # Start the bot
    updater.start_polling()
    updater.idle()


def exit_group(update: Update, context: CallbackContext) -> None:
    global db
    try:
        user_id = str(update.effective_user.id)
        user_ref = db.collection('users').document(user_id)
        user_ref.set({'in_group': False}, merge=True)  # Set flag to exit group
        update.message.reply_text("🚪 You have left the group. Now chatting with ChatGPT.")
    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")


def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    help_text = """
Available commands:
/hello <name> - Greet the bot
/match - Find users with similar interests
/add <keyword> - Count a keyword
/interests <interest1> <interest2>... - Set your interests
/exit - Leave the group chat
/recommend <topic> - Get event recommendations
/help - Show this help message
"""
    update.message.reply_text(help_text)


def hello(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("Please provide your name, e.g., /hello Alice")
        return

    logging.info(context.args[0])
    msg = context.args[0]
    print(msg)
    update.message.reply_text('Good day, ' + msg + '!')


def equiped_chatgpt(update, context):
    if not context.args:
        update.message.reply_text("Please provide a topic, e.g., /recommend gaming")
        return

    user_input = ' '.join(context.args)
    # Custom prompt for event recommendations
    prompt = f"Recommend virtual events related to {user_input}. Keep the response under 100 words."
    reply_message = chatgpt.submit(prompt)
    context.bot.send_message(chat_id=update.effective_chat.id, text=reply_message)


def match(update: Update, context: CallbackContext) -> None:
    global db
    try:
        user_id = str(update.effective_user.id)
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        user_ref.set({'in_group': True}, merge=True)  # Enable group mode

        if not user_doc.exists:
            update.message.reply_text("Set your interests first with /interests!")
            return

        # Get interests from Firestore document
        user_data = user_doc.to_dict()
        interests = user_data.get('interests', [])

        if not interests:
            update.message.reply_text("Your interest list is empty!")
            return

        # Query Firestore with composite index
        matches = (
            db.collection('users')
            .where(filter=FieldFilter('interests', 'array_contains_any', interests))
            .where(filter=FieldFilter('__name__', '!=', user_ref))  # Compare document path, not ID string
            .stream()
        )

        # Extract matching user IDs (document IDs)
        match_list = [f"User {str(match.id)}" for match in matches]

        if not match_list:
            update.message.reply_text("🔍 No users with similar interests found.")
        else:
            update.message.reply_text(
                f"🤝 Matching users:\n{', '.join(match_list)}\n\nYou are now in the group. Use /exit to leave.")

    except Exception as e:
        logging.error(f"Match failed: {str(e)}", exc_info=True)
        update.message.reply_text("❌ An error occurred. Please try again.")


def interests(update: Update, context: CallbackContext) -> None:
    global db
    try:
        # Validate input
        allowed_interests = {
            "gaming",
            "vr",
            "social",
            "music",
            "sports",
            "technology",
            "art",
            "movies"
        }

        if not context.args:
            update.message.reply_text(
                f"Please provide your interests.\nAllowed interests: {', '.join(allowed_interests)}")
            return

        user_input = [arg.lower() for arg in context.args]

        # Validate input
        invalid = [interest for interest in user_input if interest not in allowed_interests]
        if invalid:
            update.message.reply_text(
                f"Invalid interests: {', '.join(invalid)}.\nAllowed: {', '.join(allowed_interests)}")
            return

        # Save to Firestore (document ID = user ID)
        user_id = str(update.effective_user.id)
        user_ref = db.collection('users').document(user_id)
        user_ref.set({
            'interests': user_input,
            'in_group': False  # Reset group status when interests change
        }, merge=True)
        update.message.reply_text(f"🎯 Interests set to: {', '.join(user_input)}")

    except Exception as e:
        update.message.reply_text(f"Error: {str(e)}")


def add(update: Update, context: CallbackContext) -> None:
    global db
    try:
        if not context.args:
            update.message.reply_text("Usage: /add <keyword>")
            return

        msg = context.args[0].lower()  # Case-insensitive
        doc_ref = db.collection('counts').document(msg)

        # Update count
        if doc_ref.get().exists:
            doc_ref.update({'count': firestore.Increment(1)})
        else:
            doc_ref.set({'count': 1})

        # Fetch updated count
        count = doc_ref.get().to_dict().get('count', 1)
        update.message.reply_text(f'✅ Keyword "{msg}" has been counted {count} times.')
    except Exception as e:
        update.message.reply_text(f"Error: {str(e)}")


if __name__ == '__main__':
    main()
