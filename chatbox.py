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
    global chatgpt
    reply_message = chatgpt.submit(update.message.text)
    logging.info("Update: " + str(update))
    logging.info("context: " + str(context))
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
        # 初始化 Firebase
        cred = credentials.Certificate("service-account-key.json")
        firebase_admin.initialize_app(cred, {'projectId': 'comp7940-aa'})
        db = firestore.client()

        # 测试写入数据
        doc_ref = db.collection('test').document('test_doc')
        doc_ref.set({'message': 'Hello Firestore!'})
        print("Firestore 连接成功！")
    except Exception as e:
        print(f"Firestore 连接失败: {e}")
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
    dispatcher.add_handler(CommandHandler("recommand", equiped_chatgpt))
    dispatcher.add_handler(CommandHandler("set_interests", set_interests))
    dispatcher.add_handler(chatgpt_handler)
    # To start the bot:
    updater.start_polling()
    updater.idle()
    
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
    try:
        user_id = update.effective_user.id
        user_ref = db.collection('users').document(str(user_id))
        user_doc = user_ref.get()

        if not user_doc.exists:
            update.message.reply_text("Use /set_interests set your interest！")
            return

        user_data = user_doc.to_dict()
        interests = user_data.get('interests', [])

        if not interests:
            update.message.reply_text("interest list is empty！")
            return
        matches = db.collection('users') \
            .where('interests', 'array_contains_any', interests) \
            .where('user_id', '!=', user_id) \
            .stream()

        match_list = [f"User {match.id}" for match in matches]
        if not match_list:
            update.message.reply_text("not find the same interest user")
        else:
            update.message.reply_text(f"Finding users：\n{', '.join(match_list)}")
    except Exception as e:
        logging.error(f"Fail：{str(e)}")
        update.message.reply_text("Fail, retry again.")
def set_interests(update: Update, context: CallbackContext) -> None:
    try:
        user_id = update.effective_user.id
        interests = context.args  # 例如：/set_interests gaming VR
        user_ref = db.collection('users').document(str(user_id))
        user_ref.set({'interests': interests}, merge=True)
        update.message.reply_text(f"Setting interest：{', '.join(interests)}")
    except Exception as e:
        update.message.reply_text(f"Setting fail：{str(e)}")

def add(update: Update, context: CallbackContext) -> None:
    try:
        msg = context.args[0]
        doc_ref = db.collection('counts').document(msg)
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.update({'count': firestore.Increment(1)})
        else:
            doc_ref.set({'count': 1})
        update.message.reply_text(f'You have said {msg} for {doc_ref.get().to_dict()["count"]} times.')
    except (IndexError, ValueError):
        update.message.reply_text('Usage: /add <keyword>')


if __name__ == '__main__':
    main()
