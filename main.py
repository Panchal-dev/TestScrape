import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from cinevood import get_movie_titles_and_links as cinevood_titles, get_download_links as cinevood_links
from hdhub4u import get_movie_titles_and_links as hdhub4u_titles, get_download_links as hdhub4u_links
from hdmovie2 import get_movie_titles_and_links as hdmovie2_titles, get_download_links as hdmovie2_links
from config import SITE_CONFIG, ALLOWED_IDS, update_site_domain, logger

# States for conversation
MODE_SELECTION, SITE_SELECTION, MOVIE_SEARCH, MOVIE_SELECTION, DOMAIN_UPDATE = range(5)

# Initialize sessions
ACTIVE_SESSIONS = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ALLOWED_IDS:
        await update.message.reply_text("Unauthorized access. Contact admin.")
        return ConversationHandler.END

    if user_id in ACTIVE_SESSIONS:
        await update.message.reply_text("Session already active. Use /cancel to end it.")
        return ConversationHandler.END

    ACTIVE_SESSIONS[user_id] = {"start_time": datetime.now()}
    keyboard = [
        [InlineKeyboardButton("Latest Movies", callback_data="latest")],
        [InlineKeyboardButton("Search Movies", callback_data="search")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose an option:", reply_markup=reply_markup)
    return MODE_SELECTION

async def mode_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in ACTIVE_SESSIONS:
        await query.message.reply_text("Session expired. Use /start to begin.")
        return ConversationHandler.END

    context.user_data["mode"] = query.data
    keyboard = [
        [InlineKeyboardButton("Cinevood", callback_data="cinevood")],
        [InlineKeyboardButton("HDHub4u", callback_data="hdhub4u")],
        [InlineKeyboardButton("HDMovie2", callback_data="hdmovie2")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(f"Select a site for {query.data}:", reply_markup=reply_markup)
    return SITE_SELECTION

async def site_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in ACTIVE_SESSIONS:
        await query.message.reply_text("Session expired. Use /start to begin.")
        return ConversationHandler.END

    if query.data == "cancel":
        del ACTIVE_SESSIONS[user_id]
        await query.message.edit_text("Operation cancelled.")
        return ConversationHandler.END

    context.user_data["site"] = query.data
    mode = context.user_data["mode"]

    if mode == "search":
        await query.message.edit_text("Enter movie name:")
        return MOVIE_SEARCH
    else:
        await fetch_movies(update, context, page=1)
        return MOVIE_SELECTION

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ACTIVE_SESSIONS:
        await update.message.reply_text("Session expired. Use /start to begin.")
        return ConversationHandler.END

    movie_name = update.message.text.strip()
    if not movie_name:
        await update.message.reply_text("Movie name cannot be empty. Try again:")
        return MOVIE_SEARCH

    context.user_data["movie_name"] = movie_name
    await fetch_movies(update, context, page=1)
    return MOVIE_SELECTION

async def fetch_movies(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    user_id = update.effective_user.id
    site = context.user_data["site"]
    mode = context.user_data["mode"]
    movie_name = context.user_data.get("movie_name", None)

    try:
        if site == "cinevood":
            titles, links = cinevood_titles(movie_name, max_pages=1)
        elif site == "hdhub4u":
            titles, links = hdhub4u_titles(movie_name, max_pages=1)
        else:
            titles, links = hdmovie2_titles(movie_name, max_pages=1)

        if not titles:
            await update.message.reply_text("No movies found. Try another site or name.")
            return

        context.user_data["titles"] = titles
        context.user_data["links"] = links
        context.user_data["page"] = page

        # Display 5 movies per page
        start_idx = (page - 1) * 5
        end_idx = start_idx + 5
        page_titles = titles[start_idx:end_idx]

        keyboard = [[InlineKeyboardButton(title, callback_data=str(i + start_idx + 1))] for i, title in enumerate(page_titles)]
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("Previous", callback_data="prev"))
        if end_idx < len(titles):
            nav_buttons.append(InlineKeyboardButton("Next", callback_data="next"))
        nav_buttons.append(InlineKeyboardButton("Back", callback_data="back"))
        keyboard.append(nav_buttons)
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = f"{'Latest' if mode == 'latest' else 'Search'} Movies (Page {page}):\n\n" + "\n".join(page_titles)
        if update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error fetching movies: {e}")
        await update.message.reply_text("Error fetching movies. Try again later.")
        del ACTIVE_SESSIONS[user_id]
        return ConversationHandler.END

async def movie_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in ACTIVE_SESSIONS:
        await query.message.reply_text("Session expired. Use /start to begin.")
        return ConversationHandler.END

    if query.data == "next":
        page = context.user_data["page"] + 1
        await fetch_movies(update, context, page)
        return MOVIE_SELECTION
    elif query.data == "prev":
        page = context.user_data["page"] - 1
        await fetch_movies(update, context, page)
        return MOVIE_SELECTION
    elif query.data == "back":
        keyboard = [
            [InlineKeyboardButton("Cinevood", callback_data="cinevood")],
            [InlineKeyboardButton("HDHub4u", callback_data="hdhub4u")],
            [InlineKeyboardButton("HDMovie2", callback_data="hdmovie2")],
            [InlineKeyboardButton("Cancel", callback_data="cancel")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(f"Select a site for {context.user_data['mode']}:", reply_markup=reply_markup)
        return SITE_SELECTION
    elif query.data == "cancel":
        del ACTIVE_SESSIONS[user_id]
        await query.message.edit_text("Operation cancelled.")
        return ConversationHandler.END

    try:
        selection = int(query.data) - 1
        if selection < 0 or selection >= len(context.user_data["links"]):
            await query.message.edit_text("Invalid selection. Try again.")
            return MOVIE_SELECTION

        movie_url = context.user_data["links"][selection]
        site = context.user_data["site"]

        try:
            if site == "cinevood":
                download_links = cinevood_links(movie_url)
            elif site == "hdhub4u":
                download_links = hdhub4u_links(movie_url)
            else:
                download_links = hdmovie2_links(movie_url)

            if download_links:
                text = "Download Links:\n\n" + "\n".join(download_links)
            else:
                text = "No download links found."

            keyboard = [[InlineKeyboardButton("Back to Movies", callback_data="back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.edit_text(text, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error fetching download links: {e}")
            await query.message.edit_text("Error fetching download links. Try again later.")
            del ACTIVE_SESSIONS[user_id]
            return ConversationHandler.END

        return MOVIE_SELECTION

    except ValueError:
        await query.message.edit_text("Invalid input. Select a movie number.")
        return MOVIE_SELECTION

async def update_domain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ALLOWED_IDS:
        await update.message.reply_text("Unauthorized access. Contact admin.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Cinevood", callback_data="cinevood")],
        [InlineKeyboardButton("HDHub4u", callback_data="hdhub4u")],
        [InlineKeyboardButton("HDMovie2", callback_data="hdmovie2")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select site to update domain:", reply_markup=reply_markup)
    return DOMAIN_UPDATE

async def domain_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in ALLOWED_IDS:
        await query.message.reply_text("Unauthorized access. Contact admin.")
        return ConversationHandler.END

    if query.data == "cancel":
        await query.message.edit_text("Domain update cancelled.")
        return ConversationHandler.END

    context.user_data["site_key"] = query.data
    await query.message.edit_text(f"Enter new domain for {query.data} (e.g., hdmovie2.new):")
    return DOMAIN_UPDATE

async def domain_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ALLOWED_IDS:
        await update.message.reply_text("Unauthorized access. Contact admin.")
        return ConversationHandler.END

    new_domain = update.message.text.strip()
    site_key = context.user_data["site_key"]

    if update_site_domain(site_key, new_domain):
        await update.message.reply_text(f"Domain for {site_key} updated to {new_domain}.")
    else:
        await update.message.reply_text(f"Failed to update domain for {site_key}. Try again.")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[user_id]
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_IDS:
        await update.message.reply_text("Unauthorized access. Contact admin.")
        return

    commands = [
        "/start - Start a new movie search",
        "/latest - View the latest movies",
        "/cancel - Cancel the current operation",
        "/update_domain - Update the domain for a specific site",
        "/cmd - Display this command list",
    ]
    await update.message.reply_text("\n".join(commands))

async def timeout_check(context: ContextTypes.DEFAULT_TYPE):
    current_time = datetime.now()
    for user_id, session in list(ACTIVE_SESSIONS.items()):
        if (current_time - session["start_time"]).total_seconds() > 1800:  # 30 minutes
            del ACTIVE_SESSIONS[user_id]
            await context.bot.send_message(user_id, "Session timed out. Use /start to begin again.")

def main():
    application = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("latest", start),
        ],
        states={
            MODE_SELECTION: [CallbackQueryHandler(mode_selection)],
            SITE_SELECTION: [CallbackQueryHandler(site_selection)],
            MOVIE_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, movie_search)],
            MOVIE_SELECTION: [CallbackQueryHandler(movie_selection)],
            DOMAIN_UPDATE: [
                CallbackQueryHandler(domain_selection),
                MessageHandler(filters.TEXT & ~filters.COMMAND, domain_input),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("update_domain", update_domain))
    application.add_handler(CommandHandler("cmd", cmd))
    application.job_queue.run_repeating(timeout_check, interval=60)

    # Start webhook
    port = int(os.environ.get("PORT", 8080))
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        logger.error("WEBHOOK_URL not set")
        raise ValueError("WEBHOOK_URL environment variable not set")

    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=os.environ["TELEGRAM_BOT_TOKEN"],
        webhook_url=f"{webhook_url}/{os.environ['TELEGRAM_BOT_TOKEN']}",
    )

if __name__ == "__main__":
    main()