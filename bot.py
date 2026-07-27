#!/usr/bin/env python3
"""
Social Media Booster Bot - Customizable Telegram Bot
=====================================================
All settings are in config.json - edit that file to customize everything.
"""

import os
import json
import logging
import datetime
from pathlib import Path
from collections import defaultdict

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Load Config ──────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config():
    """Load configuration from config.json."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()

BOT_TOKEN = os.environ.get("BOT_TOKEN", CONFIG.get("bot_token", ""))
ADMIN_USERNAME = CONFIG.get("admin_username", "admin")
CHANNEL_USERNAME = CONFIG.get("channel_username", "")
SHOP_NAME = CONFIG.get("shop_name", "Shop")
WELCOME_MESSAGE = CONFIG.get("welcome_message", "Welcome!")
MORNING_POST_MESSAGE = CONFIG.get("morning_post_message", "")
MORNING_POST_TIME = CONFIG.get("morning_post_time", "08:00")
PAYMENT_METHODS = CONFIG.get("payment_methods", [])
CATEGORIES = CONFIG.get("categories", [])

# Myanmar timezone (UTC+6:30)
MYANMAR_TIMEZONE = pytz.timezone("Asia/Yangon")

# ─── Session Storage ──────────────────────────────────────────────────────────
user_sessions = defaultdict(dict)

# Conversation states
WAITING_SCREENSHOT = 1

# ─── Helper Functions ─────────────────────────────────────────────────────────
def find_category(cat_id: str):
    """Find a category by its ID."""
    for cat in CATEGORIES:
        if cat["id"] == cat_id:
            return cat
    return None


def find_product(cat_id: str, prod_id: str):
    """Find a product within a category."""
    cat = find_category(cat_id)
    if cat is None:
        return None
    for item in cat["items"]:
        if item["id"] == prod_id:
            return item
    return None


def build_welcome_text():
    """Build the welcome message text."""
    return (
        f"🎮 **{SHOP_NAME}** 🎮\n\n"
        f"{WELCOME_MESSAGE}\n\n"
        f"📌 ဝန်ဆောင်မှုများ ကြည့်ရှုရန် အောက်ပါ ခလုတ်ကို နှိပ်ပါ။"
    )


def build_welcome_keyboard():
    """Build the welcome message keyboard."""
    keyboard = [
        [InlineKeyboardButton("🛒 ဝယ်ယူမည် (Buy)", callback_data="buy")],
        [InlineKeyboardButton("📞 Admin ဆက်သွယ်ရန်", url=f"https://t.me/{ADMIN_USERNAME}")],
    ]
    if CHANNEL_USERNAME:
        keyboard.append([InlineKeyboardButton("📢 Channel", url=f"https://t.me/{CHANNEL_USERNAME}")])
    return InlineKeyboardMarkup(keyboard)


# ─── Command Handlers ─────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    text = build_welcome_text()
    keyboard = build_welcome_keyboard()
    await update.message.reply_text(text=text, reply_markup=keyboard, parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    text = (
        f"📋 **{SHOP_NAME} - အကူအညီ**\n\n"
        f"/start - Bot စတင်ရန်\n"
        f"/help - အကူအညီ\n"
        f"/cancel - Order ပယ်ဖျက်ရန်\n\n"
        f"💡 ဝယ်ယူလိုပါက /start နှိပ်ပြီး 'ဝယ်ယူမည်' ခလုတ်ကို နှိပ်ပါ။\n"
        f"⚠️ Admin: @{ADMIN_USERNAME}"
    )
    await update.message.reply_text(text=text, parse_mode="Markdown")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command."""
    user_id = update.effective_user.id
    user_sessions.pop(user_id, None)
    await update.message.reply_text("❌ Order ပယ်ဖျက်ပြီးပါပြီ။\n\nပြန်စရန် /start နှိပ်ပါ။")
    return ConversationHandler.END


# ─── Auto Reply ───────────────────────────────────────────────────────────────
async def auto_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto reply to any non-command message with welcome message."""
    text = build_welcome_text()
    keyboard = build_welcome_keyboard()
    await update.message.reply_text(text=text, reply_markup=keyboard, parse_mode="Markdown")


# ─── Morning Auto Post ────────────────────────────────────────────────────────
async def morning_post(context: ContextTypes.DEFAULT_TYPE):
    """Post morning message to channel."""
    if CHANNEL_USERNAME and MORNING_POST_MESSAGE:
        try:
            channel = f"@{CHANNEL_USERNAME}" if not CHANNEL_USERNAME.startswith("@") else CHANNEL_USERNAME
            await context.bot.send_message(chat_id=channel, text=MORNING_POST_MESSAGE)
            logger.info(f"Morning post sent to {channel}")
        except Exception as e:
            logger.error(f"Failed to send morning post: {e}")


# ─── New Member Welcome ───────────────────────────────────────────────────────
async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome new members in groups."""
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        name = member.first_name or "User"
        text = (
            f"🎉 {name} မင်္ဂလာပါ!\n\n"
            f"{SHOP_NAME} မှ ကြိုဆိုပါတယ်။\n"
            f"ဝယ်ယူလိုပါက Bot ကို message ပို့ပါ။"
        )
        await update.message.reply_text(text=text)


# ─── Callback Router ──────────────────────────────────────────────────────────
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route inline button callbacks."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "buy":
        await show_categories(query, context)
    elif data == "back_to_categories":
        await show_categories(query, context)
    elif data.startswith("cat|"):
        await show_products(query, context, data)
    elif data.startswith("prod|"):
        await show_payment(query, context, data)
    elif data.startswith("back_to_products|"):
        cat_id = data.replace("back_to_products|", "", 1)
        await show_products(query, context, f"cat|{cat_id}")
    elif data == "cancel_order":
        await cancel_order(query, context)


# ─── Step 1: Show Categories ─────────────────────────────────────────────────
async def show_categories(query, context: ContextTypes.DEFAULT_TYPE):
    """Display product categories."""
    text = f"🛒 **{SHOP_NAME}**\n\nမိမိဝယ်ယူလိုသော ပစ္စည်းကို ရွေးချယ်ပေးပါ။"
    keyboard = []
    for cat in CATEGORIES:
        keyboard.append([
            InlineKeyboardButton(cat["name"], callback_data=f"cat|{cat['id']}")
        ])
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


# ─── Step 2: Show Products ───────────────────────────────────────────────────
async def show_products(query, context: ContextTypes.DEFAULT_TYPE, data: str):
    """Display products in a category."""
    cat_id = data.split("|")[1]
    cat = find_category(cat_id)

    if cat is None:
        await query.edit_message_text("❌ Category not found.")
        return

    user_id = query.from_user.id
    user_sessions[user_id]["category_id"] = cat_id

    text = f"{cat['name']}\n\n{cat['description']}\n\nပက်ကေ့ချ်ရွေးချယ်ပါ:"

    keyboard = []
    for item in cat["items"]:
        keyboard.append([
            InlineKeyboardButton(
                f"{item['name']} – {item['price']}",
                callback_data=f"prod|{cat_id}|{item['id']}",
            )
        ])
    keyboard.append([InlineKeyboardButton("⬅️ ပစ္စည်းပြန်ရွေး (Back)", callback_data="back_to_categories")])

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


# ─── Step 3: Show Payment ────────────────────────────────────────────────────
async def show_payment(query, context: ContextTypes.DEFAULT_TYPE, data: str):
    """Show payment info after product selection."""
    parts = data.split("|")
    cat_id = parts[1]
    prod_id = parts[2]

    product = find_product(cat_id, prod_id)
    if product is None:
        await query.edit_message_text("❌ Product not found.")
        return

    user_id = query.from_user.id
    user_sessions[user_id]["product_id"] = prod_id
    user_sessions[user_id]["category_id"] = cat_id

    # Build payment info
    payment_info = ""
    for pm in PAYMENT_METHODS:
        payment_info += f"{pm['icon']} {pm['name']}\n"
        payment_info += f"   📱 Pay No: `{pm['pay_no']}`\n"
        payment_info += f"   👤 Pay Name: **{pm['pay_name']}**\n\n"

    text = (
        f"🛒 **Order Summary**\n\n"
        f"📦 Product: {product['name']}\n"
        f"📝 Description: {product['description']}\n"
        f"💰 Price: {product['price']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 **ငွေပေးချေရန် အချက်အလက်များ**\n\n"
        f"{payment_info}"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 အထက်ပါ Pay No တစ်ခုခုသို့ ငွေလွှဲပြီး screenshot ပို့ပေးပါ။\n\n"
        f"⚠️ Admin @{ADMIN_USERNAME} စစ်ဆေးပြီးမှ order အတည်ပြုပါမည်။"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ ပစ္စည်းပြန်ရွေး (Back)", callback_data=f"back_to_products|{cat_id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_order")],
    ]

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # Send QR code if exists
    qr_path = Path(__file__).parent / "kbz_qr.jpg"
    if qr_path.exists():
        with open(qr_path, "rb") as qr_file:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=qr_file,
                caption="📱 QR Code - Scan ဖတ်ပြီး ငွေလွှဲနိုင်ပါတယ်။",
            )


# ─── Cancel Order ─────────────────────────────────────────────────────────────
async def cancel_order(query, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current order."""
    user_id = query.from_user.id
    user_sessions.pop(user_id, None)
    await query.edit_message_text("❌ Order ပယ်ဖျက်ပြီးပါပြီ။\n\nပြန်စရန် /start နှိပ်ပါ။")


# ─── Screenshot Handler ───────────────────────────────────────────────────────
async def conversation_entry_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wrapper for ConversationHandler entry."""
    query = update.callback_query
    await query.answer()
    data = query.data
    await show_payment(query, context, data)
    return WAITING_SCREENSHOT


async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle screenshot from customer."""
    user_id = update.effective_user.id
    session = user_sessions.get(user_id, {})

    cat_id = session.get("category_id", "unknown")
    prod_id = session.get("product_id", "unknown")
    product = find_product(cat_id, prod_id)
    product_name = product["name"] if product else "Unknown"
    product_price = product["price"] if product else "Unknown"

    user = update.effective_user
    user_name = user.first_name or "User"
    user_username = f"@{user.username}" if user.username else f"ID: {user_id}"

    # Notify admin
    admin_text = (
        f"🔔 **New Order!**\n\n"
        f"👤 Customer: {user_name} ({user_username})\n"
        f"📦 Product: {product_name}\n"
        f"💰 Price: {product_price}\n\n"
        f"📸 Payment screenshot attached below."
    )

    try:
        # Forward photo to admin
        admin_chat = f"@{ADMIN_USERNAME}" if not ADMIN_USERNAME.startswith("@") else ADMIN_USERNAME
        if update.message.photo:
            photo = update.message.photo[-1]
            await context.bot.send_photo(
                chat_id=ADMIN_USERNAME.replace("@", ""),
                photo=photo.file_id,
                caption=admin_text,
                parse_mode="Markdown",
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=ADMIN_USERNAME.replace("@", ""),
                document=update.message.document.file_id,
                caption=admin_text,
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

    # Confirm to customer
    confirm_text = (
        f"✅ **ကျေးဇူးတင်ပါတယ်!**\n\n"
        f"📦 Product: {product_name}\n"
        f"💰 Price: {product_price}\n\n"
        f"Payment screenshot လက်ခံရရှိပါပြီ။\n"
        f"Admin စစ်ဆေးပြီး မကြာမီ deliver လုပ်ပေးပါမယ်။\n\n"
        f"⏳ ကျေးဇူးပြု၍ စောင့်ဆိုင်းပေးပါ။"
    )
    await update.message.reply_text(text=confirm_text, parse_mode="Markdown")

    # Clear session
    user_sessions.pop(user_id, None)
    return ConversationHandler.END


# ─── Build Conversation Handler ───────────────────────────────────────────────
def build_buy_conversation() -> ConversationHandler:
    """Build the buying flow conversation handler."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(conversation_entry_payment, pattern=r"^prod\|"),
        ],
        states={
            WAITING_SCREENSHOT: [
                MessageHandler(
                    filters.PHOTO | filters.Document.ALL,
                    receive_screenshot,
                ),
                CommandHandler("cancel", cmd_cancel),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
        ],
        allow_reentry=True,
    )


# ─── Application Factory ─────────────────────────────────────────────────────
def create_application() -> Application:
    """Create and configure the Telegram application."""
    token = BOT_TOKEN
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        raise RuntimeError(
            "BOT_TOKEN not set! Either:\n"
            "1. Set environment variable: export BOT_TOKEN='your-token'\n"
            "2. Or edit config.json and set bot_token"
        )

    app = Application.builder().token(token).connect_timeout(30).read_timeout(30).write_timeout(30).build()

    # Schedule morning post
    if MORNING_POST_MESSAGE and CHANNEL_USERNAME:
        job_queue = app.job_queue
        hour, minute = map(int, MORNING_POST_TIME.split(":"))
        morning_time = datetime.time(hour=hour, minute=minute, tzinfo=MYANMAR_TIMEZONE)
        job_queue.run_daily(morning_post, morning_time, days=(0, 1, 2, 3, 4, 5, 6), name="Morning Post")
        logger.info(f"Morning post scheduled daily at {MORNING_POST_TIME} Myanmar time to @{CHANNEL_USERNAME}")

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("help", cmd_help))

    # New member welcome
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_handler))

    # Buying conversation
    app.add_handler(build_buy_conversation())

    # Inline callback router
    app.add_handler(CallbackQueryHandler(callback_router))

    # Auto reply (must be last - catches all other messages)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
        auto_reply_handler,
    ))

    return app


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    """Start the bot."""
    logger.info(f"Starting {SHOP_NAME} bot...")
    logger.info(f"Admin: @{ADMIN_USERNAME}")
    logger.info(f"Categories: {len(CATEGORIES)}")

    app = create_application()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
