from google.cloud.firestore import FieldFilter
from telegram import Update
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters,
CallbackContext)
import configparser
import logging
from ChatGPT_HKBU import HKBU_ChatGPT
import firebase_admin
from firebase_admin import credentials, firestore
import logging
from firebase_admin import firestore

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
    in_group = user_data.get('in_group', False)  # Default to False if missing

    if in_group:
        # Broadcast to matched users
        interests = user_data.get('interests', [])
        matches = (
            db.collection('users')
            .where(filter=FieldFilter('interests', 'array_contains_any', interests))
            .where(filter=FieldFilter('__name__', '!=', user_ref))
            .stream()
        )
        reply_message = update.message.text
        for match in matches:
            try:
                context.bot.send_message(chat_id=int(match.id), text=reply_message)
            except Exception as e:
                logging.error(f"Failed to send message to {match.id}: {e}")
    else:
        # Use ChatGPT
        reply_message = chatgpt.submit(update.message.text)
        context.bot.send_message(chat_id=update.effective_chat.id, text=reply_message)

def main():
    # Load your token and create an Updater for your Bot
    config = configparser.ConfigParser()
    config.read('config.ini')
    updater = Updater(token=(config['TELEGRAM']['ACCESS_TOKEN']), use_context=True)
    dispatcher = updater.dispatcher
    global chatgpt
    chatgpt=HKBU_ChatGPT(config)
    try:
        global db  # Declare db as global
        # 初始化 Firebase
        cred = credentials.Certificate("service-account-key.json")
        firebase_admin.initialize_app(cred, {'projectId': 'comp7940-aa'})
        db = firestore.client()

        # Test the database
        doc_ref = db.collection('test').document('test_doc')
        doc_ref.set({'message': 'Hello Firestore!'})
        print("Firestore connection success！")
    except Exception as e:
        print(f"Firestore connection failed: {e}")
        exit(1)

    # You can set this logging module, so you will know when
    # and why things do not work as expected Meanwhile, update your config.ini as:
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO, handlers=[FirestoreHandler(collection='logs')])
    # register a dispatcher to handle message: here we register an echo dispatcher
    # echo_handler = MessageHandler(Filters.text & (~Filters.command), echo)
    chatgpt_handler = MessageHandler(Filters.text & (~Filters.command), equiped_chatgpt1)
    # dispatcher.add_handler(echo_handler)
    # on different commands - answer in Telegram
    dispatcher.add_handler(CommandHandler("hello", hello))
    dispatcher.add_handler(CommandHandler("match", match))
    dispatcher.add_handler(CommandHandler("add", add))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("recommend", equiped_chatgpt))
    dispatcher.add_handler(CommandHandler("interests", interests))
    dispatcher.add_handler(CommandHandler("exit", exit_group))
    dispatcher.add_handler(chatgpt_handler)
    # To start the bot:
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
    update.message.reply_text('Helping you helping you.')
    
def hello(update: Update, context: CallbackContext) -> None:
    logging.info(context.args[0])
    msg = context.args[0]
    print(msg)
    update.message.reply_text('Good day, ' + msg + '!')
 
def equiped_chatgpt(update, context):
    user_input = update.message.text
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
            update.message.reply_text(f"🤝 Matching users:\n{', '.join(match_list)}\n\nYou are now in the group. Use /exit to leave.")

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
            "social"
        }
        user_input = [arg.lower() for arg in context.args]
        user_ref.set({'interests': user_input, 'in_group': False}, merge=True)

        # Validate input
        invalid = [interest for interest in user_input if interest not in allowed_interests]
        if invalid:
            update.message.reply_text(f"Invalid interests: {', '.join(invalid)}.\nAllowed: {', '.join(allowed_interests)}")
            return

        # Save to Firestore (document ID = user ID)
        user_id = str(update.effective_user.id)
        user_ref = db.collection('users').document(user_id)
        user_ref.set({'interests': user_input}, merge=True)  # No 'user_id' field needed
        update.message.reply_text(f"Interests set to: {', '.join(user_input)}")

        
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
        update.message.reply_text(f'Keyword "{msg}" has been counted {count} times.')
    except Exception as e:
        update.message.reply_text(f"Error: {str(e)}")


if __name__ == '__main__':
    main()
