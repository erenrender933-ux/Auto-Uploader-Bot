from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import Config

OWNER = filters.user(Config.OWNER_ID)

START_TEXT = (
    "<b>Anime Auto Uploader Bot</b>\n\n"
    "1. Send anime files to me\n"
    "2. Send /start_process\n"
    "3. I will detect anime, season, episode and language, "
    "upload to the target channel and post in the main channels.\n\n"
    "Use /help to see all commands."
)

HELP_TEXT = (
    "<b>Commands</b>\n\n"
    "/start_process - start uploading the queued files\n"
    "/queue - show queued files\n"
    "/clear - clear the queue\n"
    "/cancel - cancel the running process\n\n"
    "<b>Settings</b>\n"
    "/settings - show all settings\n"
    "/settarget -100xxxx - change target channel\n"
    "/addmain -100xxxx - add a main channel\n"
    "/delmain -100xxxx - remove a main channel\n"
    "/setwatermark text - change watermark text\n"
    "/watermark on|off - toggle watermark\n"
    "/setformat format - change rename format\n"
    "/setmeta title | author - change metadata\n"
    "/setjoin link - change Join Now link"
)


@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    buttons = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Join Now", url=Config.JOIN_LINK)]]
    )
    await message.reply_text(START_TEXT, reply_markup=buttons)


@Client.on_message(filters.command("help") & filters.private & OWNER)
async def help_cmd(client: Client, message: Message):
    await message.reply_text(HELP_TEXT)
