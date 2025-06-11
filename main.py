import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)
import requests
import cloudscraper
from cinevood import get_movie_titles_and_links as cinevood_titles, get_download_links as cinevood_links
from hdhub4u import get_movie_titles_and_links as hdhub4u_titles, get_download_links as hdhub4u_links
from hdmovie2 import get_movie_titles_and_links as hdmovie2_titles, get_download_links as hdmovie2_links
from config import SITE_CONFIG, ALLOWED_IDS, update_site_domain, logger

# States for conversation
MOVIE_NAME, SITE_SELECTION, MOVIE_SELECTION, DOMAIN_UPDATE, DOMAIN_INPUT = range(5)

# Initialize sessions
ACTIVE_SESSIONS = {}

def clear_session(user_id, context: CallbackContext):
    """Clear active session for a user."""
    if user_id in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[user_id]
        logger.debug(f"Cleared session for user {user_id}")
    context.user_data.clear()

def start(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    if user_id not in ALLOWED_IDS:
        update.message.reply_text("Unauthorized access. Contact admin.")
        return ConversationHandler.END

    clear_session(user_id, context)
    ACTIVE_SESSIONS[user_id] = {"start_time": datetime.now()}
    update.message.reply_text("Enter movie name to search:")
    return MOVIE_NAME

def movie_name(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    if user_id not in ACTIVE_SESSIONS:
        update.message.reply_text("Session expired. Use /start_movie to begin.")
        return ConversationHandler.END

    movie_name = update.message.text.strip()
    if not movie_name:
        update.message.reply_text("Movie name cannot be empty. Try again:")
        return MOVIE_NAME

    context.user_data["movie_name"] = movie_name
    context.user_data["mode"] = "search"
    keyboard = [
        [InlineKeyboardButton("Cinevood", callback_data="cinevood")],
        [InlineKeyboardButton("HDHub4u", callback_data="hdhub4u")],
        [InlineKeyboardButton("HDMovie2", callback_data="hdmovie2")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(f"Select a site to search for '{movie_name}':", reply_markup=reply_markup)
    return SITE_SELECTION

def latest_movies(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    if user_id not in ALLOWED_IDS:
        update.message.reply_text("Unauthorized access. Contact admin.")
        return ConversationHandler.END

    clear_session(user_id, context)
    ACTIVE_SESSIONS[user_id] = {"start_time": datetime.now()}
    context.user_data["mode"] = "latest"
    keyboard = [
        [InlineKeyboardButton("Cinevood", callback_data="cinevood")],
        [InlineKeyboardButton("HDHub4u", callback_data="hdhub4u")],
        [InlineKeyboardButton("HDMovie2", callback_data="hdmovie2")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select a site for latest movies:", reply_markup=reply_markup)
    return SITE_SELECTION

def site_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    if user_id not in ACTIVE_SESSIONS:
        query.message.reply_text("Session expired. Use /start_movie to begin.")
        return ConversationHandler.END

    if query.data == "cancel":
        clear_session(user_id, context)
        query.message.edit_text("Operation cancelled.")
        return ConversationHandler.END

    context.user_data["site"] = query.data
    fetch_movies(update, context, page=1)
    return MOVIE_SELECTION

def fetch_movies(update: Update, context: CallbackContext, page: int):
    user_id = update.effective_user.id
    site = context.user_data["site"]
    mode = context.user_data.get("mode", "search")
    movie_name = context.user_data.get("movie_name", None) if mode == "search" else None

    try:
        logger.debug(f"Fetching movies: site={site}, mode={mode}, movie_name={movie_name}, page={page}")
        if site == "cinevood":
            titles, links = cinevood_titles(movie_name, max_pages=1)
        elif site == "hdhub4u":
            titles, links = hdhub4u_titles(movie_name, max_pages=1)
        else:
            titles, links = hdmovie2_titles(movie_name, max_pages=1)

        if not titles:
            query = update.callback_query
            query.message.edit_text("No movies found. Try another site or name.")
            clear_session(user_id, context)
            return ConversationHandler.END

        context.user_data["titles"] = titles
        context.user_data["links"] = links
        context.user_data["page"] = page

        start_idx = (page - 1) * 10  # Changed to 10 for 10-button gap
        end_idx = start_idx + 10
        page_titles = titles[start_idx:end_idx]

        keyboard = [[InlineKeyboardButton(title, callback_data=str(i + start_idx + 1))] for i, title in enumerate(page_titles)]
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("Previous", callback_data="prev"))
        if end_idx < len(titles):
            nav_buttons.append(InlineKeyboardButton("Next", callback_data="next"))
        nav_buttons.append(InlineKeyboardButton("Back to Sites", callback_data="back_to_sites"))
        keyboard.append(nav_buttons)
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = f"{'Search' if mode == 'search' else 'Latest'} Movies (Page {page}):\n\n" + "\n".join(page_titles)
        query = update.callback_query
        query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error fetching movies: {e}")
        query = update.callback_query
        query.message.edit_text("Error fetching movies. Try again later.")
        clear_session(user_id, context)
        return ConversationHandler.END

def movie_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    if user_id not in ACTIVE_SESSIONS:
        query.message.reply_text("Session expired. Use /start_movie to begin.")
        return ConversationHandler.END

    if query.data == "cancel":
        clear_session(user_id, context)
        query.message.edit_text("Operation cancelled.")
        return ConversationHandler.END
    elif query.data == "next":
        page = context.user_data["page"] + 1
        fetch_movies(update, context, page)
        return MOVIE_SELECTION
    elif query.data == "prev":
        page = context.user_data["page"] - 1
        fetch_movies(update, context, page)
        return MOVIE_SELECTION
    elif query.data == "back_to_sites":
        mode = context.user_data.get("mode", "search")
        keyboard = [
            [InlineKeyboardButton("Cinevood", callback_data="cinevood")],
            [InlineKeyboardButton("HDHub4u", callback_data="hdhub4u")],
            [InlineKeyboardButton("HDMovie2", callback_data="hdmovie2")],
            [InlineKeyboardButton("Cancel", callback_data="cancel")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = f"Select a site to search for '{context.user_data['movie_name']}'" if mode == "search" else "Select a site for latest movies:"
        query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return SITE_SELECTION
    elif query.data == "back_to_list":
        page = context.user_data.get("page", 1)
        fetch_movies(update, context, page)
        return MOVIE_SELECTION

    try:
        selection = int(query.data) - 1
        if selection < 0 or selection >= len(context.user_data["links"]):
            query.message.edit_text("Invalid selection. Try again.")
            return MOVIE_SELECTION

        movie_url = context.user_data["links"][selection]
        site = context.user_data["site"]

        try:
            logger.debug(f"Fetching download links for {movie_url} from {site}")
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

            keyboard = [
                [InlineKeyboardButton("Back to Movie List", callback_data="back_to_list")],
                [InlineKeyboardButton("Back to Sites", callback_data="back_to_sites")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error fetching download links for {movie_url}: {e}")
            query.message.edit_text("Error fetching download links. Try again later.")
            return MOVIE_SELECTION

        return MOVIE_SELECTION

    except ValueError:
        query.message.edit_text("Invalid input. Select a valid option.")
        return MOVIE_SELECTION

def update_domain(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    if user_id not in ALLOWED_IDS:
        update.message.reply_text("Unauthorized access. Contact admin.")
        return ConversationHandler.END

    clear_session(user_id, context)
    ACTIVE_SESSIONS[user_id] = {"start_time": datetime.now()}
    keyboard = [
        [InlineKeyboardButton("Cinevood", callback_data="cinevood")],
        [InlineKeyboardButton("HDHub4u", callback_data="hdhub4u")],
        [InlineKeyboardButton("HDMovie2", callback_data="hdmovie2")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select site to update domain:", reply_markup=reply_markup)
    return DOMAIN_UPDATE

def domain_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    if user_id not in ACTIVE_SESSIONS:
        query.message.reply_text("Session expired. Use /update_domain to retry.")
        return ConversationHandler.END

    if query.data == "cancel":
        clear_session(user_id, context)
        query.message.edit_text("Operation cancelled.")
        return ConversationHandler.END

    context.user_data["site_key"] = query.data
    query.message.edit_text(f"Enter new domain for {query.data} (e.g., hdmovie2.new):")
    return DOMAIN_INPUT

def domain_input(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    if user_id not in ACTIVE_SESSIONS:
        update.message.reply_text("Session expired. Use /update_domain to retry.")
        return ConversationHandler.END

    new_domain = update.message.text.strip()
    site_key = context.user_data["site_key"]

    if update_site_domain(site_key, new_domain):
        update.message.reply_text(f"Domain for {site_key} updated to {new_domain}.")
    else:
        update.message.reply_text(f"Failed to update domain for {site_key}. Try again.")

    clear_session(user_id, context)
    return ConversationHandler.END

def status(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_IDS:
        update.message.reply_text("Unauthorized access. Contact admin.")
        return

    clear_session(user_id, context)
    scraper = cloudscraper.create_scraper()
    status_text = "Current Site Status:\n\n"
    for site_key, domain in SITE_CONFIG.items():
        url = f"https://{domain}/"
        try:
            response = scraper.get(url, timeout=5)
            status_code = response.status_code
            status_text += f"{site_key.capitalize()}: {status_code} {'OK' if status_code == 200 else 'Error'}\n"
        except Exception as e:
            logger.error(f"Error checking status for {site_key}: {e}")
            status_text += f"{site_key.capitalize()}: Error ({str(e)})\n"

    update.message.reply_text(status_text)

def cancel(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    clear_session(user_id, context)
    update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_IDS:
        update.message.reply_text("Unauthorized access. Contact admin.")
        return

    clear_session(user_id, context)
    commands = [
        "/start_movie - Start a new movie search",
        "/latest_movies - View latest movies",
        "/status - Check current site status",
        "/update_domain - Update domain for a site",
        "/cancel - Cancel current operation",
        "/cmd - Display this command list",
    ]
    update.message.reply_text("\n".join(commands))

def timeout_check(context: CallbackContext):
    current_time = datetime.now()
    for user_id, session in list(ACTIVE_SESSIONS.items()):
        if (current_time - session["start_time"]).total_seconds() > 1800:  # 30 minutes
            clear_session(user_id, context)
            context.bot.send_message(user_id, "Session timed out. Use /start_movie to begin again.")

def main():
    updater = Updater(os.environ["TELEGRAM_BOT_TOKEN"], use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start_movie", start),
            CommandHandler("latest_movies", latest_movies),
            CommandHandler("update_domain", update_domain),
        ],
        states={
            MOVIE_NAME: [MessageHandler(Filters.text & ~Filters.command, movie_name)],
            SITE_SELECTION: [CallbackQueryHandler(site_selection)],
            MOVIE_SELECTION: [CallbackQueryHandler(movie_selection)],
            DOMAIN_UPDATE: [CallbackQueryHandler(domain_selection)],
            DOMAIN_INPUT: [MessageHandler(Filters.text & ~Filters.command, domain_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("cmd", cmd))
    updater.job_queue.run_repeating(timeout_check, interval=30)

    port = int(os.environ.get("PORT", 8080))
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        logger.error("WEBHOOK_URL not set")
        raise ValueError("WEBHOOK_URL environment variable not set")

    updater.start_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=os.environ["TELEGRAM_BOT_TOKEN"],
        webhook_url=f"{webhook_url}/{os.environ['TELEGRAM_BOT_TOKEN']}",
    )
    updater.idle()

if __name__ == "__main__":
    main()