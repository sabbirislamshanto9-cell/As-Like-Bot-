#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║          AS FF LIKE BOT - Telegram Bot                         ║
║           Free Fire Auto Like Bot                                ║
║           AS LIKE BOT                                        ║
╚══════════════════════════════════════════════════════════════════╝

Setup:
1. pip install python-telegram-bot aiohttp
2. Fill in BOT_TOKEN and ADMIN_ID below
3. Add your channel links in REQUIRED_CHANNELS
4. python main.py
"""

import os
import sys
import json
import random
import re
import asyncio
import logging
import subprocess
import importlib
import importlib.metadata
from urllib.parse import quote

# -------------------------------------------------------------------
# TELEGRAM PACKAGE FIX
# Some hosting panels see `from telegram ...` and incorrectly install
# the unrelated `telegram` PyPI package. This bot requires
# `python-telegram-bot` (the distribution that provides the `telegram`
# module). Repair the package before importing it.
# -------------------------------------------------------------------
def _ensure_python_telegram_bot():
    """Ensure a recent python-telegram-bot version that supports button styles.
    Older installations can silently make /start and Order History fail when
    style=... is passed to KeyboardButton/InlineKeyboardButton.
    """
    required = (22, 7)
    try:
        installed = importlib.metadata.version("python-telegram-bot")
        parts = tuple(int(x) for x in installed.split(".")[:2])
        if parts >= required:
            return
    except Exception:
        pass

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", "telegram"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except Exception:
        pass

    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-U",
        "python-telegram-bot>=22.7,<23"
    ])
    importlib.invalidate_caches()



_ensure_python_telegram_bot()

import aiohttp
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# Premium/custom emoji support for ALL Telegram keyboard buttons.
# Custom emoji in a keyboard button is sent through icon_custom_emoji_id,
# not as <tg-emoji> HTML inside the button text.
_OriginalInlineKeyboardButton = InlineKeyboardButton
_OriginalKeyboardButton = KeyboardButton

def strip_premium_emoji_tags(text):
    return re.sub(r'<tg-emoji\s+emoji-id=["\']\d+["\']>(.*?)</tg-emoji>', r'\1', str(text), flags=re.S)

_LEGACY_BUTTON_PREFIX_RE = re.compile(
    r'^\s*(?:(?:↩️|↩|🔙|⬅️|⬅|◀️|◀|↪️|➡️|➡)\s*)+',
    flags=re.UNICODE,
)

def clean_keyboard_label(text):
    """Return plain keyboard text; all visual emoji come from Telegram's native custom icon."""
    text = strip_premium_emoji_tags(text)
    # Remove ordinary Unicode emoji/symbols from old saved labels.
    text = re.sub(
        r'[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]',
        '', str(text)
    )
    text = _LEGACY_BUTTON_PREFIX_RE.sub('', text)
    return re.sub(r'\s{2,}', ' ', text).strip()

def _premium_button_text(text):
    return clean_keyboard_label(text)

def InlineKeyboardButton(text, *args, **kwargs):
    return _OriginalInlineKeyboardButton(_premium_button_text(text), *args, **kwargs)

def KeyboardButton(text, *args, **kwargs):
    return _OriginalKeyboardButton(_premium_button_text(text), *args, **kwargs)

from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from aiohttp import web


# -------------------------------------------------------------------
# PREMIUM EMOJI SHORTCUT
# -------------------------------------------------------------------
PREMIUM_STAR_HTML = '<tg-emoji emoji-id="6235459831302460476">⭐</tg-emoji>'
# Telegram Premium/Custom Emoji icon used by the button system.
# Source: InlineKeyboardButton(..., icon_custom_emoji_id=...) logic supplied by user.
# Native Telegram custom-emoji icons for buttons.
# Dedicated Telegram Premium/custom emoji IDs for each main-menu button.
# Change any ID here later; no other code needs to be edited.
PREMIUM_BUTTON_EMOJIS = {
    "balance": "6122737740309078397",
    "add_money": "6125307655465474978",
    "like_history": "5251443675161976035",
    "order_history": "6122923729572864025",
    "auto_package": "6122925752502460840",
    "bonus_220": "6122689499236410478",
    "daily_free": "6123083734284509430",
    "referral": "6122981410983652307",
    "customer_care": "6122811278739121204",
    "tutorial": "6123204598959189818",
}
PREMIUM_REPLY_BUTTON_ICON_ID = PREMIUM_BUTTON_EMOJIS["balance"]
PREMIUM_INLINE_BUTTON_ICON_ID = PREMIUM_BUTTON_EMOJIS["balance"]
PREMIUM_BUTTON_ICON_ID = PREMIUM_REPLY_BUTTON_ICON_ID

def premium_label(label, emoji_id='6159087504529038102', fallback='⭐'):
    """Use this for any button label; change only emoji_id when needed."""
    return f"<tg-emoji emoji-id='{emoji_id}'>{fallback}</tg-emoji> {label}"

# Dedicated icon map is defined above.
def premium_button_label(key, label, fallback=""):
    # Kept for compatibility with existing editable content. The actual
    # button icon is supplied natively through icon_custom_emoji_id.
    emoji_id = PREMIUM_BUTTON_EMOJIS.get(key, PREMIUM_BUTTON_ICON_ID)
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji> {label}'.strip()


# -------------------------------------------------------------------
# PREMIUM / CUSTOM EMOJI COMPATIBILITY
# -------------------------------------------------------------------
# Custom emoji must be sent as Telegram MessageEntity objects, not as
# ordinary HTML text. The editor already stores and restores entities;
# this helper keeps that behavior explicit and prevents accidental
# conversion of custom emoji into plain Unicode characters.
def premium_emoji_entities(message):
    """Return custom-emoji entities from an incoming Telegram message."""
    entities = getattr(message, "entities", None) or []
    return [
        e for e in entities
        if getattr(e, "type", "") == "custom_emoji"
        and getattr(e, "custom_emoji_id", None)
    ]

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION - EDIT THESE VALUES
# ═══════════════════════════════════════════════════════════════════

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0").strip() or "0")

# Single API Config
API_BASE = "https://aryan-shanto-fflikebot2-0.vercel.app/like"
# Separate API used only for /like requests from the free-like group.
FREE_API_BASE = "https://asfreelike.vercel.app/like"
# API_KEY IS NO LONGER USED AS PER YOUR REQUEST

# Pre-Authorized Groups/Channels list (These don't need manual /allow command)
PRE_AUTHORIZED_GROUPS = [
    -1004220352794,                          # Replace with your actual Channel/Group Chat ID
]

# Required channels users MUST join
REQUIRED_CHANNELS = [
    {"name": "AS TEAM BD Official", "link": "https://t.me/Asteambd_official"},
]

# Daily reset time (4:00 AM)
RESET_HOUR = 4
RESET_MINUTE = 0
BD_TZ = ZoneInfo("Asia/Dhaka")
AUTO_LIKE_DAILY_ESTIMATE = 210  # ETA: estimated 210 likes/day; API decides actual likes per call
FREE_LIKE_DAILY_LIMIT = 50
FREE_LIKE_UNLIMITED = False
DAILY_FREE_LIKE_URL = "https://t.me/asfflikebd"

# -------------------------------------------------------------------
# BOHUDUR PAYMENT CONFIG
# -------------------------------------------------------------------
# Put your Bohudur API key here (or set BOHUDUR_API_KEY in the hosting
# environment). Never publish the real key in a frontend.
BOHUDUR_API_KEY = os.environ.get("BOHUDUR_API_KEY", "YOUR_BOHUDUR_API_KEY")

# Public HTTPS base URL of this bot. Render normally provides
# RENDER_EXTERNAL_URL automatically; on other hosting panels set
# PUBLIC_BASE_URL manually, e.g. https://your-domain.example
PUBLIC_BASE_URL = (
    os.environ.get("PUBLIC_BASE_URL")
    or os.environ.get("RENDER_EXTERNAL_URL")
    or ""
).rstrip("/")

BOHUDUR_BASE_URL = "https://request.bohudur.one"
BOHUDUR_RETURN_PATH = "/bohudur/return"
BOHUDUR_SUCCESS_WEBHOOK_PATH = "/bohudur/webhook/success"
BOHUDUR_CANCEL_WEBHOOK_PATH = "/bohudur/webhook/cancel"
BOHUDUR_PAYMENT_LIMIT_MIN = 10
BOHUDUR_PAYMENT_LIMIT_MAX = 100000
BOHUDUR_PAYMENT_PRESETS = (50, 100, 200, 500, 1000)

FIRST_220_LIKE = 200

# Auto-like time (4:00 AM BD)
AUTO_LIKE_HOUR = 4
AUTO_LIKE_MINUTE = 0

# Valid Free Fire regions
FIXED_REGION = "BD"

# AS LIKE BOT - USER MENU / BALANCE / REFERRAL CONFIG
BOT_NAME = "AS FF LIKE BOT"
ADMIN_USERNAME = "As_owner99"
ADMIN_URL = "https://t.me/As_owner99"
REFERRAL_REWARD = 5
REFERRAL_MIN_NEW_USER = True
# These packages are shown in the menu but are not orderable yet.
COMING_SOON_PACKAGES = set()

# Change these prices whenever you want.
AUTO_LIKE_PACKAGES = [
    (100, 5),
    (200, 10),
    (500, 25),
    (1000, 40),
    (2000, 60),
    (5000, 100),
    (10000, 200),
]


# ═══════════════════════════════════════════════════════════════════
# EMOJI POOL - Random emojis for each user
# ═══════════════════════════════════════════════════════════════════

EMOJI_POOL = [
    "🔥", "⚡", "🎯", "🏆", "💎", "🚀", "⭐", "💥",
    "🎮", "🎲", "🎪", "🎭", "🎨", "🎰", "🎱", "🎳",
    "🎸", "🎺", "🎻", "🎹", "🎷", "🎤", "🎧", "🎬",
    "🌟", "✨", "💫", "🌠", "🌈", "☄️", "🔮", "💀",
    "👑", "🎓", "🎖️", "🏅", "🥇", "🥈", "🥉", "🎁",
    "🎀", "🎊", "🎉", "🎈", "🎄", "🎃", "🎅", "🤖",
    "👾", "👽", "🛸", "🌍", "🌎", "🌏", "🌕", "☀️",
]

# ═══════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logger.info("MAIN MENU ICONS LOADED: auto_package=%s like_history=%s", PREMIUM_BUTTON_EMOJIS.get("auto_package"), PREMIUM_BUTTON_EMOJIS.get("like_history"))

# ═══════════════════════════════════════════════════════════════════
# DATA MANAGER - JSON File Storage
# ═══════════════════════════════════════════════════════════════════

# Keep all bot data beside main.py, regardless of the directory from which
# the process is started. This prevents the bot from silently creating a
# second, empty bot_data folder when the hosting panel uses another CWD.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "bot_data")
os.makedirs(DATA_DIR, exist_ok=True)

# Older builds used a single JSON file. We only use these files for a safe
# one-time migration when the new per-store files do not already exist.
LEGACY_DATA_FILES = (
    os.path.join(BASE_DIR, "data.json"),
    os.path.join(BASE_DIR, "bot_data.json"),
)

FILES = {
    "users": os.path.join(DATA_DIR, "users.json"),
    "groups": os.path.join(DATA_DIR, "groups.json"),
    "channels": os.path.join(DATA_DIR, "channels.json"),
    "auto_like": os.path.join(DATA_DIR, "auto_like.json"),
    "target_like": os.path.join(DATA_DIR, "target_like.json"),
    "daily_usage": os.path.join(DATA_DIR, "daily_usage.json"),
    "unlimited": os.path.join(DATA_DIR, "unlimited.json"),
    "vip": os.path.join(DATA_DIR, "vip.json"),
    "broadcast_users": os.path.join(DATA_DIR, "broadcast_users.json"),
    "group_status": os.path.join(DATA_DIR, "group_status.json"),
    "like_stats": os.path.join(DATA_DIR, "like_stats.json"),
    "user_stats": os.path.join(DATA_DIR, "user_stats.json"),
    "referrals": os.path.join(DATA_DIR, "referrals.json"),
    "orders": os.path.join(DATA_DIR, "orders.json"),
    "packages": os.path.join(DATA_DIR, "packages.json"),
    "filters": os.path.join(DATA_DIR, "filters.json"),
    "settings": os.path.join(DATA_DIR, "settings.json"),
    "money_stats": os.path.join(DATA_DIR, "money_stats.json"),
    "content": os.path.join(DATA_DIR, "content.json"),
    "payments": os.path.join(DATA_DIR, "payments.json"),
}


def load_data(key):
    path = FILES.get(key)
    if not path:
        return {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            logger.exception("Failed to load data file: %s", path)
            return {}
    return {}


def save_data(key, data):
    path = FILES.get(key)
    if not path:
        return False
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        return True
    except Exception:
        logger.exception("Failed to save data file: %s", path)
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False


def migrate_legacy_data():
    """Import compatible records from old single-file data stores once.

    Existing bot_data/*.json files always win, so this cannot overwrite
    current data. Unsupported/unknown legacy keys are deliberately ignored.
    """
    missing = {key for key, path in FILES.items() if not os.path.exists(path)}
    if not missing:
        return

    for legacy_path in LEGACY_DATA_FILES:
        if not os.path.exists(legacy_path):
            continue
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                legacy = json.load(f)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            logger.exception("Failed to read legacy data file: %s", legacy_path)
            continue
        if not isinstance(legacy, dict):
            continue

        # Newer single-file builds used these direct store names.
        for key in list(missing):
            if key in legacy:
                if save_data(key, legacy[key]):
                    missing.discard(key)

        # Compatibility with the older compact auto-like build.
        if "auto_like" in missing and "autolikes" in legacy:
            if save_data("auto_like", legacy.get("autolikes", {})):
                missing.discard("auto_like")

        if "group_status" in missing and "enabled_groups" in legacy:
            if save_data("group_status", legacy.get("enabled_groups", {})):
                missing.discard("group_status")

        if not missing:
            break

migrate_legacy_data()


def get_filter_store():
    data = load_data("filters")
    return data if isinstance(data, dict) else {}


def set_filter(trigger, response):
    data = get_filter_store()
    data[str(trigger).strip().lower()] = {"trigger": str(trigger).strip(), "response": str(response), "updated_at": bd_timestamp()}
    save_data("filters", data)


def remove_filter(trigger):
    data = get_filter_store()
    data.pop(str(trigger).strip().lower(), None)
    save_data("filters", data)

def get_filter_response(text):
    return get_filter_store().get(str(text or "").strip().lower())


def get_free_limit():
    global FREE_LIKE_DAILY_LIMIT, FREE_LIKE_UNLIMITED
    settings = load_data("settings")
    if isinstance(settings, dict) and "free_like_unlimited" in settings:
        FREE_LIKE_UNLIMITED = bool(settings.get("free_like_unlimited"))
        if "free_like_daily_limit" in settings:
            FREE_LIKE_DAILY_LIMIT = max(0, int(settings.get("free_like_daily_limit", FREE_LIKE_DAILY_LIMIT)))
    return None if FREE_LIKE_UNLIMITED else max(0, int(FREE_LIKE_DAILY_LIMIT))


def load_packages():
    """Load editable package configuration from JSON, falling back to defaults."""
    default_packages = [(int(likes), int(price)) for likes, price in AUTO_LIKE_PACKAGES]
    try:
        data = load_data("packages")
        if isinstance(data, list) and data:
            packages = []
            for item in data:
                if isinstance(item, dict):
                    likes = int(item.get("likes", 0))
                    price = int(item.get("price", 0))
                elif isinstance(item, (list, tuple)) and len(item) == 2:
                    likes, price = int(item[0]), int(item[1])
                else:
                    continue
                if likes > 0 and price >= 0:
                    packages.append((likes, price))
            if packages:
                return sorted(set(packages), key=lambda x: x[0])
    except Exception as e:
        logger.error("Failed to load packages.json: %s", e)
    return sorted(default_packages, key=lambda x: x[0])


def save_packages(packages):
    """Persist packages so admin edits survive bot restarts."""
    clean = []
    seen = set()
    for likes, price in packages:
        likes, price = int(likes), int(price)
        if likes > 0 and price >= 0 and likes not in seen:
            clean.append((likes, price))
            seen.add(likes)
    clean.sort(key=lambda x: x[0])
    save_data("packages", [{"likes": likes, "price": price} for likes, price in clean])
    return clean


# Load the editable package list once the data manager is ready.
AUTO_LIKE_PACKAGES = load_packages()
_saved_settings = load_data("settings")
if isinstance(_saved_settings, dict) and str(_saved_settings.get("referral_reward", "")).isdigit():
    REFERRAL_REWARD = int(_saved_settings["referral_reward"])
if isinstance(_saved_settings, dict) and str(_saved_settings.get("auto_like_daily_estimate", "")).isdigit():
    AUTO_LIKE_DAILY_ESTIMATE = max(1, int(_saved_settings["auto_like_daily_estimate"]))


# ═══════════════════════════════════════════════════════════════════
# TELEGRAM CONTENT EDITOR
# ═══════════════════════════════════════════════════════════════════

EDITABLE_CONTENT_DEFAULTS = {
    "help_user": "{emoji} AS LIKE BOT - USER MENU {emoji}\n\n🎮 How to use:\n/like <uid>\nExample: /like 123456789\n\n⚠️ Rules:\n• Daily Free Like limit সর্বোচ্চ 50 Likes\n• VIP ব্যবহারকারীরা VIP সময়ের মধ্যে সীমাহীন লাইক নিতে পারবেন\n• Reset at 4:00 AM daily\n• Daily Free Like-এর জন্য Official Group/Channel-এ Join করুন\n• Bot works in allowed groups\n\n⚡ AS LIKE BOT ⚡",
    "help_admin": "{emoji} AS LIKE BOT - ADMIN PANEL {emoji}\n\n🔐 Admin Commands:\n/allow <group_id> - Allow bot in group\n/removegroup <group_id> - Remove group\n/add <name> <link> - Add verify channel\n/removechannel <name> - Remove channel\n/broadcast <message> - Message all users\n/addpoints <telegram_user_id> <points> - User-কে points দিন\n/setpoints <telegram_user_id> <points> - User-এর balance set করুন\n/balance - Balance commands\n/unlimit <uid> - Unlimited likes\n/removeunlimit <uid> - Remove unlimited\n/packages - Package list\n/setpackage <likes> <price> - Add/update package\n/editpackage <number> <likes> <price> - Edit package\n/removepackage <likes> - Remove package\n/botedit - Edit bot notices/messages\n/editallow <userid> - Give edit permission\n/editremove <userid> - Remove edit permission\n/vip <telegram_user_id> <days> - VIP দিন\n/vipremove <telegram_user_id> - VIP বাতিল\n/autolike <uid> <days> - Auto daily like\n/removeauto <uid> - Remove auto like\n/autolist - List auto-like UIDs\n/likeinfo <uid> - Total/today likes info\n/tlike <uid> <target_limit> - Daily like until target\n/removetlike <uid> - Remove target like\n/tlist - List target likes\n/stats - Bot statistics\n/grouplist - Allowed groups\n/on - এই গ্রুপে bot চালু\n/off - এই গ্রুপে bot বন্ধ\n\n⚡ AS LIKE BOT ⚡",
    "welcome": "🙂 WELCOME 🙂\n🕊️ Name: {name}\n🖊 Username: {username}\n👤 User ID: {user_id}\n🗓 Date: {date}\n⏰ Time: {time}\n🗓 Day: {day}\n━━━━━━━━━━━━━━━━━━\n✅ আমাদের গ্রুপে আপনাকে স্বাগতম ✅\n💘 আপনার সুন্দর সময় কাটুক আমাদের সাথে...!!\n\n💎 Balance: {balance} Points\n⚡ {bot_name}",
    "bot_on": "🟢 GLOBAL BOT ON\n\nসব group এবং bot functionality চালু হয়েছে.",
    "bot_off": "🔴 GLOBAL BOT OFF\n\nসাধারণ user-এর bot/like functionality বন্ধ হয়েছে। Admin commands চালু থাকবে.",
    "balance": "💰 {bot_name} BALANCE\n\n👤 User ID: {user_id}\n💎 Available Points: {balance}\n\n➕ Point পেতে Refer & Earn ব্যবহার করুন।",
    "add_money": "💳 ADD MONEY\n\nশুধু bKash দিয়ে Balance Add করুন।\nআপনার User ID: {user_id}\n\nনিচের bKash Payment button থেকে amount select করে secure checkout-এ payment করুন।\n\n⚡ Payment successful হলে verified payment অনুযায়ী আপনার Points automatically add হবে।",
    "like_history": "{bot_name} — LIKE USE HISTORY\n\n👤 User ID: {user_id}\n❤️ মোট পাওয়া Likes: {total_likes}\n📅 আজকে পাওয়া Likes: {today_likes}\n🔁 Successful Requests: {runs}\n➕ Last Request: {last_likes} Likes",
    "order_history": "📜 {bot_name} — {status_label}\n\n{orders}",
    "auto_package": "{bot_name} — AUTO LIKE PACKAGE\n\nআপনার পছন্দের package number select করুন:\n\n{packages}\nℹ️ Package select করার পর আপনার Free Fire UID দিতে হবে।\n💰 Package-এর price আপনার bot balance থেকে কাটা হবে।",
    "daily_free": "🎁 DAILY FREE LIKE\n━━━━━━━━━━━━━━━━━━\nপ্রতিদিন Free Like নিতে আমাদের Official Group/Channel-এ Join করুন।\n\n❤️ Daily Free Like Limit: {limit} Likes\n🔄 Daily Limit প্রতিদিন ভোর ৪:০০টায় Reset হবে।\n\n📢 প্রথমে নিচের Official Group/Channel-এ Join করুন।\nতারপর গ্রুপের মধ্যে /like <UID> ব্যবহার করুন।\n\n⚠️ Like না এলে আপনার Daily Like Limit/Like Stock শেষ হয়ে থাকতে পারে।",
    "referral": "👻 REFER AND EARN\n\nপ্রতি সফল নতুন referral-এ আপনি {reward} Points পাবেন।\n\n🔗 আপনার Referral Link:\n{link}\n\n💰 বর্তমান Balance: {balance} Points\n👥 মোট Referral: {count} জন\n🎁 Referral থেকে আয়: {earned} Points",
    "customer_care": "🆘 CUSTOMER CARE\n\nযেকোনো সমস্যা, Balance, Package বা সাহায্যের জন্য Admin-এর সাথে যোগাযোগ করুন।",
    "tutorial": "TUTORIAL VIDEO\n\nTutorial video দেখতে নিচের YouTube link-এ click করুন।\n\nhttps://youtube.com/@as_owner99?si=eV8QCx6gJqJjteFd",
    "bonus_200": "200 LIKE BONUS\n━━━━━━━━━━━━━━━━━━\n\nএকজন Telegram user একবার মাত্র 200 Like নিতে পারবেন।\n💳 Price: 5 Points\n\nনিচের Confirm button চাপুন, তারপর আপনার Free Fire UID দিন।\n⚠️ শুধু BD Server UID ব্যবহার করুন।",
    "package_selected": "✅ PACKAGE SELECTED\n━━━━━━━━━━━━━━━━━━\n📦 Package: {likes:,} Likes\n💳 Price: {price} Points\n💰 Current Balance: {balance} Points\n\n🎮 এখন আপনার BD Server Free Fire UID পাঠান:\nউদাহরণ: 123456789\n\n⚡ Order তৈরি হওয়ার পর UID-তে Auto Like চালু হবে।\n⚡ UID confirm হওয়ার পরই first Like attempt হবে।\n💳 Order confirm হলেই {price} Points সঙ্গে সঙ্গে কেটে নেওয়া হবে।",
    "uid_invalid": "❌ UID সঠিক নয়।\n\nশুধু সংখ্যার Free Fire UID দিন অথবা CANCEL চাপুন।",
    "order_confirmed": "🎉 ORDER CONFIRMED\n━━━━━━━━━━━━━━━━━━\n🆔 Order ID: {order_id}\n🎮 UID: {uid}\n📦 Ordered: {likes:,} Likes\n❤️ First Attempt: ভোর ৪:০০টায় হবে\n⏳ Remaining: Order History-তে latest progress দেখুন\n📅 Estimated Time: {eta}\n💳 Cost: {price} Points\n💰 Balance After Charge: {balance} Points\n\n🤖 Auto Like: ACTIVE\n⚡ Like delivery প্রতিদিন শুধু ভোর ৪:০০টায় হবে; বাকি Likes পরের cycle-এ দেওয়া হবে।\n\n📢 NOTICE\nLike stock/API response কম হলে remaining Likes পরের cycle-এ আবার চেষ্টা হবে।\n\n📜 Order History থেকে progress দেখতে পারবেন।",
    "verify_success": "✅ VERIFIED SUCCESSFULLY!\n\nYou can now use the bot!\n\nUse /like <uid> to get likes",
    "verify_failed": "❌ NOT VERIFIED!\n\nYou haven't joined all channels yet!\nJoin all channels first, then click Verify again.",
    "like_success": "✅ Like Sent Successfully!\n━━━━━━━━━━━━━━━━━━\n👤 Name: {player_name}\n❤️ Like Before: {before}\n❤️ Like After: {after}\n➕ Like Given: {likes_given}\n🆔 UID: {uid}\n⏰ Bangladesh Time: {time}\n━━━━━━━━━━━━━━━━━━\n⚡ AS LIKE BOT ⚡",
}

MENU_LABEL_DEFAULTS = {
    "balance": "𝐁𝐀𝐋𝐀𝐍𝐂𝐄",
    "add_money": "𝐀𝐃𝐃 𝐌𝐎𝐍𝐄𝐘",
    "like_history": "LIKE USE HISTORY",
    "order_history": "ORDER HISTORY",
    "auto_package": "AUTO LIKE PACKAGE",
    "bonus_220": "200 LIKE",
    "daily_free": "𝐃𝐀𝐈𝐋𝐘 𝐅𝐑𝐄𝐄 𝐋𝐈𝐊𝐄",
    "referral": "𝐑𝐄𝐅𝐄𝐑 𝐀𝐍𝐃 𝐄𝐀𝐑𝐍",
    "customer_care": "𝐂𝐔𝐒𝐓𝐎𝐌𝐄𝐑 𝐂𝐀𝐑𝐄",
    "tutorial": "𝐓𝐔𝐓𝐎𝐑𝐈𝐀𝐋",
}


def get_menu_labels():
    settings = load_data("settings")
    saved = settings.get("menu_labels", {}) if isinstance(settings, dict) else {}
    result = dict(MENU_LABEL_DEFAULTS)
    if isinstance(saved, dict):
        for key in result:
            value = saved.get(key)
            if isinstance(value, str) and value.strip():
                result[key] = clean_keyboard_label(value)

    # Normalize the two main menu labels to their correct keys. Older versions
    # accidentally stored these two labels under the opposite keys; do not let
    # that legacy state move the buttons/icons into the wrong positions.
    if result.get("like_history") == "AUTO LIKE PACKAGE" and result.get("auto_package") == "LIKE USE HISTORY":
        result["like_history"] = "LIKE USE HISTORY"
        result["auto_package"] = "AUTO LIKE PACKAGE"
    if result.get("bonus_220") == "220 LIKE":
        result["bonus_220"] = "200 LIKE"
    return result

def get_menu_label(key):
    return get_menu_labels().get(key, MENU_LABEL_DEFAULTS.get(key, key))

PAYMENT_LABEL_DEFAULTS = {
    50: "50 TK",
    100: "100 TK",
    200: "200 TK",
    500: "500 TK",
    1000: "1000 TK",
}

def get_payment_label(amount):
    amount = int(amount)
    settings = load_data("settings")
    saved = settings.get("payment_labels", {}) if isinstance(settings, dict) else {}
    value = saved.get(str(amount))
    if isinstance(value, str) and value.strip():
        return clean_keyboard_label(value)
    return PAYMENT_LABEL_DEFAULTS.get(amount, f"{amount} TK")

def save_payment_label(amount, label):
    amount = int(amount)
    if amount not in PAYMENT_LABEL_DEFAULTS:
        return False
    settings = load_data("settings")
    if not isinstance(settings, dict):
        settings = {}
    labels = settings.get("payment_labels", {})
    if not isinstance(labels, dict):
        labels = {}
    labels[str(amount)] = clean_keyboard_label(str(label).strip())
    settings["payment_labels"] = labels
    return save_data("settings", settings)

def save_menu_label(key, label):
    if key not in MENU_LABEL_DEFAULTS:
        return False
    settings = load_data("settings")
    if not isinstance(settings, dict):
        settings = {}
    labels = settings.get("menu_labels", {})
    if not isinstance(labels, dict):
        labels = {}
    labels[key] = clean_keyboard_label(str(label).strip())
    settings["menu_labels"] = labels
    return save_data("settings", settings)

def _content_store():
    data = load_data("content")
    return data if isinstance(data, dict) else {}

def get_content(key):
    value = _content_store().get(key)
    if isinstance(value, dict) and "text" in value:
        return str(value["text"])
    return str(value) if isinstance(value, str) else EDITABLE_CONTENT_DEFAULTS.get(key, "")

def _serialize_entities(entities):
    result=[]
    for e in entities or []:
        result.append({"type":e.type,"offset":e.offset,"length":e.length,
                       "url":getattr(e,"url",None),"language":getattr(e,"language",None),
                       "custom_emoji_id":getattr(e,"custom_emoji_id",None)})
    return result

def _deserialize_entities(items):
    from telegram import MessageEntity
    out=[]
    for item in items or []:
        try:
            kw={"type":item.get("type"),"offset":int(item.get("offset",0)),"length":int(item.get("length",0))}
            for k in ("url","language","custom_emoji_id"):
                if item.get(k): kw[k]=item[k]
            out.append(MessageEntity(**kw))
        except Exception:
            logger.exception("Could not restore Telegram entity")
    return out

def get_content_record(key):
    value=_content_store().get(key)
    if isinstance(value,dict) and ("text" in value or "media_file_id" in value):
        text = str(value.get("text", value.get("caption", "")))
        # A previous editor bug could save the whole editor instruction as the
        # Order History content. Never treat that UI prompt as the real template.
        if key == "order_history" and (
            text.lstrip().startswith("✏️ EDIT: 📜 Order History")
            or "নতুন text/message পাঠান। Photo/Video পাঠালে সেটিও save হবে।" in text
            and "❌ Cancel করতে /start দিন।" in text
        ):
            return EDITABLE_CONTENT_DEFAULTS.get(key, ""), [], False
        entities = value.get("entities", value.get("caption_entities", []))
        return text,_deserialize_entities(entities),True
    return EDITABLE_CONTENT_DEFAULTS.get(key,""),[],False

def get_content_media(key):
    value = _content_store().get(key)
    if isinstance(value, dict) and value.get("media_file_id"):
        media_type = str(value.get("media_type", "")).lower()
        if media_type in ("photo", "video"):
            return media_type, str(value["media_file_id"])
    return None, None

def save_content(key,text,entities=None,editor_id=None,media_type=None,media_file_id=None):
    store=_content_store()
    record={"text":str(text),"entities":_serialize_entities(entities),
            "updated_by":str(editor_id) if editor_id is not None else None,
            "updated_at":bd_timestamp()}
    if media_type in ("photo", "video") and media_file_id:
        record["media_type"] = media_type
        record["media_file_id"] = str(media_file_id)
    store[key]=record
    return save_data("content",store)

def render_content(key,**values):
    raw=get_content(key)
    try: return raw.format(**values)
    except Exception: return raw

def _u16_len(value):
    return len(value.encode("utf-16-le")) // 2


def _u16_to_py_index(text, offset):
    """Convert Telegram UTF-16 offset to a Python string index."""
    target=max(0,int(offset or 0)); units=0
    for i,ch in enumerate(text):
        next_units=units+_u16_len(ch)
        if next_units > target:
            return i
        units=next_units
        if units == target:
            return i+1
    return len(text)


def render_content_entities(key, **values):
    """Render editable content and keep Premium/Custom Emoji entities aligned."""
    raw, entities, custom=get_content_record(key)
    if not custom or not entities:
        return render_content(key, **values), [], False

    # Current bot templates use simple named fields such as {name}, {balance:,}, etc.
    # Build an old-character-index -> new-character-index map while formatting.
    pattern=re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)([^{}]*)\}")
    parts=[]; boundary=[None]*(len(raw)+1); old_pos=0; new_pos=0
    for match in pattern.finditer(raw):
        literal=raw[old_pos:match.start()]
        parts.append(literal)
        for i in range(len(literal)+1):
            boundary[old_pos+i]=new_pos+i
        new_pos += len(literal); old_pos=match.end()
        field=match.group(1); spec=match.group(2) or ""
        value=values.get(field, match.group(0))
        try:
            replacement=format(value, spec.lstrip(":").strip()) if spec else str(value)
        except Exception:
            replacement=str(value)
        parts.append(replacement)
        # Placeholder itself maps to the replacement end; entities normally do not span fields.
        boundary[match.start()]=new_pos
        for i in range(match.start()+1,match.end()+1):
            boundary[i]=new_pos+len(replacement)
        new_pos += len(replacement)
    tail=raw[old_pos:]
    parts.append(tail)
    for i in range(len(tail)+1):
        boundary[old_pos+i]=new_pos+i
    rendered="".join(parts)

    adjusted=[]
    for e in entities:
        try:
            old_start=_u16_to_py_index(raw,e.offset)
            old_end=_u16_to_py_index(raw,e.offset+e.length)
            new_start=boundary[old_start] if boundary[old_start] is not None else old_start
            new_end=boundary[old_end] if boundary[old_end] is not None else old_end
            kw={"type":e.type,"offset":_u16_len(rendered[:new_start]),"length":_u16_len(rendered[new_start:new_end])}
            for name in ("url","language","custom_emoji_id"):
                value=getattr(e,name,None)
                if value: kw[name]=value
            from telegram import MessageEntity
            adjusted.append(MessageEntity(**kw))
        except Exception:
            logger.exception("Could not adjust editable Telegram entity for %s", key)
    return rendered, adjusted, True


def add_premium_page_emoji(text, entities=None):
    """Prefix page text with a native Telegram custom emoji and preserve offsets."""
    text = str(text or "")
    prefix = "⭐ "
    # Do not duplicate if the page already starts with the native custom emoji HTML.
    if text.startswith(PREMIUM_STAR_HTML):
        return text, entities or [], False
    try:
        from telegram import MessageEntity
        shift = _u16_len(prefix)
        adjusted = []
        for e in (entities or []):
            kw = {"type": e.type, "offset": int(e.offset) + shift, "length": int(e.length)}
            for name in ("url", "language", "custom_emoji_id"):
                value = getattr(e, name, None)
                if value:
                    kw[name] = value
            adjusted.append(MessageEntity(**kw))
        premium_entity = MessageEntity(
            type="custom_emoji", offset=0, length=_u16_len("⭐"),
            custom_emoji_id=str(PREMIUM_BUTTON_EMOJIS.get("balance", "6235459831302460476")),
        )
        return prefix + text, [premium_entity] + adjusted, True
    except Exception:
        logger.exception("Could not create premium page emoji entity")
        return text, entities or [], False


async def reply_editable_content(message, key, reply_markup=None, **values):
    """Send an editable content item with a native Premium/custom emoji on every page."""
    text, entities, custom=render_content_entities(key, **values)
    if custom and entities:
        text, entities, _ = add_premium_page_emoji(text, entities)
        return await message.reply_text(text, entities=entities, reply_markup=reply_markup)
    if PREMIUM_STAR_HTML in text:
        return await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    text, entities, _ = add_premium_page_emoji(text, [])
    return await message.reply_text(text, entities=entities, reply_markup=reply_markup)

def content_send_kwargs(key):
    raw, entities, custom = get_content_record(key)
    if custom and entities:
        return {"entities": entities}
    return {}

def get_edit_allowed_users():
    settings=load_data("settings")
    raw=settings.get("edit_allowed_users",[]) if isinstance(settings,dict) else []
    return {int(x) for x in raw if str(x).isdigit()} if isinstance(raw,list) else set()

def set_edit_allowed_users(ids):
    settings=load_data("settings")
    if not isinstance(settings,dict): settings={}
    settings["edit_allowed_users"]=sorted({int(x) for x in ids})
    save_data("settings",settings)

def can_bot_edit(user_id):
    return is_admin(user_id) or int(user_id) in get_edit_allowed_users()

async def _is_duplicate_user_action(context, action_key, window=0.9):
    """Ignore accidental repeated Telegram clicks/messages within a short window."""
    try:
        now = asyncio.get_running_loop().time()
    except Exception:
        return False
    store = context.user_data.setdefault("_action_debounce", {})
    previous = store.get(str(action_key))
    store[str(action_key)] = now
    # Keep the cache tiny.
    if len(store) > 20:
        cutoff = now - max(window, 2.0)
        for k, value in list(store.items()):
            if value < cutoff:
                store.pop(k, None)
    return previous is not None and (now - previous) < window

EDIT_LABELS={
    "welcome":"🌟 Welcome","balance":"💰 Balance Notice","add_money":"💳 Add Money",
    "order_history":"📜 Order History","auto_package":"Auto Like Package",
    "bonus_200":"200 Like Bonus",
    "daily_free":"🎁 Daily Free Like","referral":"👻 Referral Notice",
    "customer_care":"🆘 Customer Care","package_selected":"🎮 Package → UID",
    "uid_invalid":"⚠️ Invalid UID","order_confirmed":"🎉 Order Confirmed",
    "verify_success":"✅ Verify Success","verify_failed":"❌ Verify Failed",
    "like_success":"❤️ Like Sent Page",
    "menu_balance":"🔘 Balance Button","menu_add_money":"🔘 Add Money Button",
    "menu_like_history":"🔘 Like History Button","menu_order_history":"🔘 Order History Button",
    "menu_auto_package":"🔘 Auto Like Package Button","menu_bonus_220":"🔘 220 Like Button",
    "menu_daily_free":"🔘 Daily Free Like Button","menu_referral":"🔘 Refer & Earn Button",
    "menu_customer_care":"🔘 Customer Care Button",
    "menu_tutorial":"🔘 Tutorial Video Button",
    "tutorial":"Tutorial Video Page",
    "help_user":"/help — User Text",
    "help_admin":"/help — Admin Text",
    "payment_50":"💳 Add Money — 50 TK Button",
    "payment_100":"💳 Add Money — 100 TK Button",
    "payment_200":"💳 Add Money — 200 TK Button",
    "payment_500":"💳 Add Money — 500 TK Button",
    "payment_1000":"💳 Add Money — 1000 TK Button",
    "bot_on":"Bot ON Page",
    "bot_off":"Bot OFF Page",
}

def build_botedit_keyboard():
    rows=[]; keys=list(EDIT_LABELS)
    for i in range(0,len(keys),2):
        row=[make_inline_button(EDIT_LABELS[keys[i]],callback_data=f"botedit_select:{keys[i]}",style="primary")]
        if i+1<len(keys):
            row.append(make_inline_button(EDIT_LABELS[keys[i+1]],callback_data=f"botedit_select:{keys[i+1]}",style="primary"))
        rows.append(row)
    rows.append([make_inline_button("❌ CLOSE",callback_data="botedit_close",style="danger")])
    return InlineKeyboardMarkup(rows)

async def botedit_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    if not can_bot_edit(update.effective_user.id):
        await message.reply_text("❌ /botedit permission নেই। Admin-এর permission লাগবে।"); return
    await message.reply_text(
        "🛠️ AS FF LIKE BOT — CONTENT EDITOR\n\n"
        "যেটা edit করতে চান select করুন। Current text দেখাবে, তারপর নতুন message পাঠালেই save হবে।\n\n"
        "💎 Premium/Custom Emoji message হিসেবে পাঠালে entity-সহ save হবে।",
        reply_markup=build_botedit_keyboard())

async def botedit_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    query=update.callback_query
    if await _is_duplicate_user_action(context, f"callback:{query.data}"):
        try:
            await query.answer()
        except Exception:
            pass
        return

    if not can_bot_edit(query.from_user.id):
        await query.answer("Edit permission নেই।",show_alert=True); return
    await query.answer()
    data=query.data or ""
    if data=="botedit_close":
        context.user_data.pop("editing_content",None)
        await query.edit_message_text("🛠️ Content Editor বন্ধ করা হয়েছে।"); return
    key=data.split(":",1)[1] if ":" in data else ""
    if key not in EDIT_LABELS: return
    preview_entities = None
    if key.startswith("menu_"):
        menu_key=key[len("menu_"):]
        current=get_menu_label(menu_key)
        instruction="নতুন button text পাঠান। Button-এর color ও Premium icon code থেকে fixed থাকবে।"
    elif key.startswith("payment_"):
        amount=int(key[len("payment_"):])
        current=get_payment_label(amount)
        instruction="নতুন Add Money amount button text পাঠান। যেমন: 50 TK"
    else:
        current, preview_entities, _ = get_content_record(key)
        media_type,_=get_content_media(key)
        media_note=f"\n🖼️ Saved media: {media_type.upper()}" if media_type else ""
        instruction="নতুন text/message পাঠান। Photo/Video পাঠালে সেটিও save হবে। Premium/Custom Emoji থাকলে সরাসরি message হিসেবে পাঠান।"
        current=f"{current}{media_note}"
    context.user_data["editing_content"]=key
    edit_kwargs = {}
    if preview_entities:
        edit_kwargs["entities"] = preview_entities
    await query.edit_message_text(
        f"✏️ EDIT: {EDIT_LABELS[key]}\n\n{instruction}\n\n📋 Current text নিচের আলাদা message-এ দেওয়া হলো। শুধু ওই message-টাই Copy করে পরিবর্তন করে পাঠান।\n❌ Cancel করতে /start দিন.")
    try:
        if preview_entities:
            await context.bot.send_message(chat_id=query.from_user.id, text=current, entities=preview_entities)
        else:
            await context.bot.send_message(chat_id=query.from_user.id, text=current)
    except Exception:
        logger.exception("Could not send copyable editor text")

async def editallow_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    if not is_admin(update.effective_user.id): return
    if len(context.args)!=1 or not context.args[0].isdigit():
        await message.reply_text("❌ Format: /editallow <userid>"); return
    uid=int(context.args[0]); ids=get_edit_allowed_users(); ids.add(uid); set_edit_allowed_users(ids)
    await message.reply_text(f"✅ Edit permission দেওয়া হয়েছে: {uid}")

async def editremove_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args)!=1 or not context.args[0].isdigit():
        await update.message.reply_text("❌ Format: /editremove <userid>"); return
    uid=int(context.args[0]); ids=get_edit_allowed_users(); ids.discard(uid); set_edit_allowed_users(ids)
    await update.message.reply_text(f"✅ Edit permission remove করা হয়েছে: {uid}\nআগের saved edits ঠিক থাকবে।")

async def edit_content_message(update:Update,context:ContextTypes.DEFAULT_TYPE):
    key=context.user_data.get("editing_content")
    if not key or not can_bot_edit(update.effective_user.id): return False
    message=update.message
    if not message:
        return True

    if key.startswith("menu_"):
        if not message.text or not message.text.strip():
            await message.reply_text("❌ Button label-এর জন্য শুধু text message পাঠান।")
            return True
        menu_key=key[len("menu_"):]
        if save_menu_label(menu_key, message.text):
            context.user_data.pop("editing_content",None)
            await message.reply_text(f"✅ {EDIT_LABELS.get(key,key)} successfully saved!\n\nনতুন button: {message.text}")
        else:
            await message.reply_text("❌ Button label save করা যায়নি।")
        return True

    if key.startswith("payment_"):
        if not message.text or not message.text.strip():
            await message.reply_text("❌ Add Money button-এর জন্য শুধু text message পাঠান।")
            return True
        amount=int(key[len("payment_"):])
        if save_payment_label(amount, message.text):
            context.user_data.pop("editing_content",None)
            await message.reply_text(f"✅ {EDIT_LABELS.get(key,key)} successfully saved!\n\nনতুন button: {message.text}")
        else:
            await message.reply_text("❌ Add Money button label save করা যায়নি।")
        return True

    media_type=None
    media_file_id=None
    if message.photo:
        if key != "like_success":
            await message.reply_text("❌ Photo শুধু ❤️ Like Sent Page-এর জন্য ব্যবহার করুন।")
            return True
        media_type="photo"
        media_file_id=message.photo[-1].file_id
        text=message.caption or ""
        entities=message.caption_entities or []
    elif message.video:
        if key != "like_success":
            await message.reply_text("❌ Video শুধু ❤️ Like Sent Page-এর জন্য ব্যবহার করুন।")
            return True
        media_type="video"
        media_file_id=message.video.file_id
        text=message.caption or ""
        entities=message.caption_entities or []
    elif message.text:
        text=message.text
        entities=message.entities or []
    else:
        await message.reply_text("❌ Text, Photo অথবা Video পাঠিয়ে edit করুন।")
        return True

    if save_content(key,text,entities,update.effective_user.id,media_type,media_file_id):
        context.user_data.pop("editing_content",None)
        media_note=f" + {media_type.upper()}" if media_type else ""
        await message.reply_text(f"✅ {EDIT_LABELS.get(key,key)} successfully saved{media_note}!")
    else:
        await message.reply_text("❌ Save করা যায়নি। bot_data folder writable কিনা দেখুন।")
    return True

# ═══════════════════════════════════════════════════════════════════
# FORMATTING HELPERS
# ═══════════════════════════════════════════════════════════════════

def format_bold(text):
    """Return plain text safely. Avoid Telegram Markdown entity parsing errors."""
    return str(text)


def is_admin(user_id):
    return user_id == ADMIN_ID


def now_bd():
    return datetime.now(BD_TZ)

def get_today():
    return now_bd().strftime("%Y-%m-%d")

def bd_timestamp():
    return now_bd().strftime("%Y-%m-%d %H:%M:%S")


def can_use_like(user_id, target_uid=None):
    """Allow one successful free-like request per Telegram user per BD day.
    Bot admin and VIP users are exempt."""
    if is_admin(user_id) or is_vip(user_id):
        return True
    usage = load_data("daily_usage")
    info = usage.get(str(user_id), {}) if isinstance(usage, dict) else {}
    return info.get("date") != get_today()


def mark_like_used(user_id, target_uid=None):
    """Mark the Telegram user as having used today's free-like request."""
    if is_admin(user_id) or is_vip(user_id):
        return
    usage = load_data("daily_usage")
    if not isinstance(usage, dict):
        usage = {}
    usage[str(user_id)] = {
        "date": get_today(),
        "count": 1,
        "uid": str(target_uid or ""),
        "used_at": bd_timestamp(),
    }
    save_data("daily_usage", usage)


def is_global_enabled():
    settings = load_data("settings")
    return bool(settings.get("global_enabled", True)) if isinstance(settings, dict) else True


def set_global_enabled(enabled):
    settings = load_data("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings["global_enabled"] = bool(enabled)
    settings["global_updated_at"] = bd_timestamp()
    save_data("settings", settings)


def record_money_added(user_id, amount):
    """Track admin-added money/points for today's user statistics."""
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return
    if amount <= 0:
        return
    stats = load_data("money_stats")
    if not isinstance(stats, dict):
        stats = {}
    key = str(user_id)
    today = get_today()
    info = stats.get(key, {})
    total_added = int(info.get("total_added", 0) or 0)
    if info.get("date") != today:
        info = {"date": today, "today_added": 0, "total_added": total_added}
    info["today_added"] = int(info.get("today_added", 0) or 0) + amount
    info["total_added"] = total_added + amount
    stats[key] = info
    save_data("money_stats", stats)


def get_money_stats(user_id):
    stats = load_data("money_stats")
    info = stats.get(str(user_id), {}) if isinstance(stats, dict) else {}
    return {
        "today_added": int(info.get("today_added", 0) or 0) if info.get("date") == get_today() else 0,
        "total_added": int(info.get("total_added", 0) or 0),
    }


def reset_daily_usage():

    """Reset daily usage at 4 AM"""
    save_data("daily_usage", {})
    logger.info("Daily usage reset at 4:00 AM")


def is_group_allowed(chat_id):
    """Check if group is allowed (Pre-authorized lists always return True)"""
    if chat_id in PRE_AUTHORIZED_GROUPS:
        return True
    groups = load_data("groups")
    return str(chat_id) in groups


def is_group_enabled(chat_id):
    """Return True when group commands are enabled. Default is ON."""
    statuses = load_data("group_status")
    return statuses.get(str(chat_id), {}).get("enabled", True)


async def is_group_admin_member(chat_id, user_id, context):
    """Return True when the Telegram user is a group administrator/creator."""
    if is_admin(user_id):
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        logger.exception("Could not check group admin status for %s/%s", chat_id, user_id)
        return False


def set_group_enabled(chat_id, enabled):
    statuses = load_data("group_status")
    statuses[str(chat_id)] = {
        "enabled": bool(enabled),
        "updated_at": datetime.now().isoformat()
    }
    save_data("group_status", statuses)


def allow_group(chat_id):
    """Allow bot to work in a group"""
    groups = load_data("groups")
    groups[str(chat_id)] = {"allowed": True, "added_at": datetime.now().isoformat()}
    save_data("groups", groups)


def remove_group(chat_id):
    """Remove group from allowed list"""
    groups = load_data("groups")
    if str(chat_id) in groups:
        del groups[str(chat_id)]
        save_data("groups", groups)


def add_channel(name, link):
    """Add verification channel"""
    channels = load_data("channels")
    channels[name] = {"link": link, "added_at": datetime.now().isoformat()}
    save_data("channels", channels)


def remove_channel(name):
    """Remove verification channel"""
    channels = load_data("channels")
    if name in channels:
        del channels[name]
        save_data("channels", channels)


def get_channels():
    """Get verification channels, excluding the removed AS LIKE BOT channel."""
    channels = load_data("channels")
    if "Channel 2" in channels:
        channels.pop("Channel 2", None)
        save_data("channels", channels)
    return channels


def add_auto_like(uid, region, days):
    """Add UID to auto-like list with duration in days"""
    auto = load_data("auto_like")
    auto[str(uid)] = {
        "region": region.upper(),
        "days_left": int(days),
        "added_at": datetime.now().isoformat()
    }
    save_data("auto_like", auto)


def remove_auto_like(uid):
    """Remove UID from auto-like list"""
    auto = load_data("auto_like")
    if str(uid) in auto:
        del auto[str(uid)]
        save_data("auto_like", auto)


def get_auto_like_list():
    """Get all auto-like UIDs"""
    return load_data("auto_like")


def record_like_stats(uid, likes_given, source="manual"):
    """Record total and today's likes for a UID."""
    stats = load_data("like_stats")
    key = str(uid)
    today = get_today()

    info = stats.get(key, {
        "total_likes": 0,
        "today_likes": 0,
        "date": today,
        "runs": 0,
        "last_likes": 0,
    })

    if info.get("date") != today:
        info["date"] = today
        info["today_likes"] = 0

    try:
        likes_given = int(likes_given or 0)
    except (ValueError, TypeError):
        likes_given = 0

    info["total_likes"] = int(info.get("total_likes", 0)) + max(0, likes_given)
    info["today_likes"] = int(info.get("today_likes", 0)) + max(0, likes_given)
    info["runs"] = int(info.get("runs", 0)) + 1
    info["last_likes"] = max(0, likes_given)
    info["last_at"] = datetime.now().isoformat()

    stats[key] = info
    save_data("like_stats", stats)


def get_like_stats(uid):
    """Return stored like statistics for a UID."""
    stats = load_data("like_stats")
    key = str(uid)
    info = stats.get(key, {})
    today = get_today()

    if info.get("date") != today:
        info["today_likes"] = 0

    return {
        "total_likes": int(info.get("total_likes", 0)),
        "today_likes": int(info.get("today_likes", 0)),
        "runs": int(info.get("runs", 0)),
        "last_likes": int(info.get("last_likes", 0)),
        "last_at": info.get("last_at", "N/A"),
    }


def add_target_like(uid, region, target_limit):
    """Add UID with target likes limit"""
    targets = load_data("target_like")
    targets[str(uid)] = {
        "region": region.upper(),
        "target_limit": max(0, int(target_limit)),
        "likes_sent": 0,
        "added_at": datetime.now().isoformat()
    }
    save_data("target_like", targets)


def remove_target_like(uid):
    """Remove UID from target like list"""
    targets = load_data("target_like")
    if str(uid) in targets:
        del targets[str(uid)]
        save_data("target_like", targets)


def add_unlimited(uid, region):
    """Add UID to unlimited likes list"""
    unlimited = load_data("unlimited")
    unlimited[uid] = {"region": region.upper(), "added_at": datetime.now().isoformat()}
    save_data("unlimited", unlimited)


def remove_unlimited(uid):
    """Remove UID from unlimited list"""
    unlimited = load_data("unlimited")
    if uid in unlimited:
        del unlimited[uid]
        save_data("unlimited", unlimited)


def is_unlimited(uid):
    """Check if UID has unlimited likes"""
    unlimited = load_data("unlimited")
    return uid in unlimited


def add_vip(user_id, days):
    """Add a Telegram user to VIP for a number of days."""
    vip = load_data("vip")
    start = datetime.now()
    vip[str(user_id)] = {
        "days": int(days),
        "expires_at": (start + timedelta(days=int(days))).isoformat(),
        "added_at": start.isoformat(),
    }
    save_data("vip", vip)


def remove_vip(user_id):
    """Remove a Telegram user from VIP."""
    vip = load_data("vip")
    vip.pop(str(user_id), None)
    save_data("vip", vip)


def is_vip(user_id):
    """Return True while the user's VIP period is active."""
    vip = load_data("vip")
    info = vip.get(str(user_id))
    if not info:
        return False
    try:
        expires_at = datetime.fromisoformat(info["expires_at"])
    except (KeyError, ValueError, TypeError):
        remove_vip(user_id)
        return False
    if datetime.now() >= expires_at:
        remove_vip(user_id)
        return False
    return True


def add_broadcast_user(user_id):
    """Add user to broadcast list"""
    users = load_data("broadcast_users")
    users[str(user_id)] = True
    save_data("broadcast_users", users)


def get_broadcast_users():
    """Get all broadcast user IDs"""
    users = load_data("broadcast_users")
    return [int(uid) for uid in users.keys()]


def get_user_emoji(user_id):
    """Get a consistent random emoji for each user"""
    users = load_data("users")
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"emoji": random.choice(EMOJI_POOL), "balance": 0}
        save_data("users", users)
    return users[uid].get("emoji", "🔥")


# ═══════════════════════════════════════════════════════════════════
# USER BALANCE / REFERRAL / HISTORY
# ═══════════════════════════════════════════════════════════════════

def ensure_user(user_id, telegram_user=None):
    users = load_data("users")
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"emoji": random.choice(EMOJI_POOL), "balance": 0, "referrals": 0, "first_220_claimed": False}
    users[uid].setdefault("balance", 0)
    users[uid].setdefault("referrals", 0)
    users[uid].setdefault("first_220_claimed", False)
    if telegram_user is not None:
        users[uid]["first_name"] = telegram_user.first_name or "Unknown"
        users[uid]["username"] = telegram_user.username or ""
    save_data("users", users)
    return users[uid]


def get_balance(user_id):
    return int(ensure_user(user_id).get("balance", 0))


def add_balance(user_id, amount):
    users = load_data("users")
    uid = str(user_id)
    users.setdefault(uid, {"emoji": random.choice(EMOJI_POOL)})
    users[uid]["balance"] = int(users[uid].get("balance", 0)) + int(amount)
    save_data("users", users)
    return users[uid]["balance"]


def set_balance(user_id, amount):
    users = load_data("users")
    uid = str(user_id)
    users.setdefault(uid, {"emoji": random.choice(EMOJI_POOL)})
    users[uid]["balance"] = max(0, int(amount))
    save_data("users", users)
    return users[uid]["balance"]


def record_user_like_usage(user_id, likes_given):
    stats = load_data("user_stats")
    key = str(user_id)
    today = get_today()
    info = stats.get(key, {"total_likes": 0, "today_likes": 0, "date": today, "runs": 0})
    if info.get("date") != today:
        info["date"] = today
        info["today_likes"] = 0
    try:
        likes_given = max(0, int(likes_given or 0))
    except (ValueError, TypeError):
        likes_given = 0
    info["total_likes"] = int(info.get("total_likes", 0)) + likes_given
    info["today_likes"] = int(info.get("today_likes", 0)) + likes_given
    info["runs"] = int(info.get("runs", 0)) + 1
    info["last_likes"] = likes_given
    info["last_at"] = datetime.now().isoformat()
    stats[key] = info
    save_data("user_stats", stats)


def get_user_like_usage(user_id):
    stats = load_data("user_stats")
    info = stats.get(str(user_id), {})
    if info.get("date") != get_today():
        info["today_likes"] = 0
    return {
        "total_likes": int(info.get("total_likes", 0)),
        "today_likes": int(info.get("today_likes", 0)),
        "runs": int(info.get("runs", 0)),
        "last_likes": int(info.get("last_likes", 0)),
    }


def process_referral(user_id, payload):
    """Register a genuine Telegram deep-link referral and reward exactly once."""
    if not payload or not str(payload).startswith("ref_"):
        return None

    uid = str(user_id).strip()
    referrer = str(payload)[4:].strip()
    if not uid.isdigit() or not referrer.isdigit() or referrer == uid:
        return None

    referrals = load_data("referrals")
    if not isinstance(referrals, dict):
        referrals = {}
    if uid in referrals:
        return None

    users = load_data("users")
    if not isinstance(users, dict):
        users = {}
    current_user = users.get(uid) if isinstance(users.get(uid), dict) else {}
    if current_user.get("referred_by"):
        return None

    # The referrer must have started the bot before; create a safe record if
    # the users file was rebuilt so a valid referral link does not lose reward.
    if referrer not in users:
        users[referrer] = {
            "emoji": random.choice(EMOJI_POOL),
            "balance": 0,
            "referrals": 0,
            "first_220_claimed": False,
        }

    users.setdefault(uid, {
        "emoji": random.choice(EMOJI_POOL),
        "balance": 0,
        "referrals": 0,
        "first_220_claimed": False,
    })
    users[referrer].setdefault("balance", 0)
    users[referrer].setdefault("referrals", 0)
    users[referrer].setdefault("first_220_claimed", False)

    reward = max(0, int(REFERRAL_REWARD))
    referrals[uid] = {
        "referrer": referrer,
        "reward": reward,
        "created_at": datetime.now().isoformat(),
    }
    users[referrer]["referrals"] = int(users[referrer].get("referrals", 0)) + 1
    users[referrer]["balance"] = int(users[referrer].get("balance", 0)) + reward
    users[uid]["referred_by"] = referrer

    # Save the balance and referral record together as far as the JSON store allows.
    if not save_data("users", users):
        logger.error("Referral user balance persistence failed: %s -> %s", uid, referrer)
        return None
    if not save_data("referrals", referrals):
        logger.error("Referral record persistence failed: %s -> %s", uid, referrer)
        return None

    return {
        "referrer": int(referrer),
        "reward": reward,
        "balance": int(users[referrer]["balance"]),
    }


def get_referral_stats(user_id):
    referrals = load_data("referrals")
    mine = [info for info in referrals.values() if str(info.get("referrer")) == str(user_id)]
    return {"count": len(mine), "earned": sum(int(x.get("reward", 0)) for x in mine)}



def _next_order_id():
    orders = load_data("orders")
    if not isinstance(orders, dict):
        orders = {}
    nums = []
    for key in orders:
        try:
            nums.append(int(str(key).replace("AS", "")))
        except Exception:
            pass
    return f"AS{(max(nums) + 1 if nums else 1001)}"


def create_order(user_id, uid, likes_requested, price):
    orders = load_data("orders")
    if not isinstance(orders, dict):
        orders = {}
    order_id = _next_order_id()
    user_info = load_data("users").get(str(user_id), {})
    if not isinstance(user_info, dict):
        user_info = {}
    orders[order_id] = {
        "order_id": order_id,
        "user_id": str(user_id),
        "user_name": user_info.get("first_name", "Unknown"),
        "username": user_info.get("username", ""),
        "uid": str(uid),
        "likes_requested": int(likes_requested),
        "likes_sent": 0,
        "remaining_likes": int(likes_requested),
        "price": int(price),
        "region": FIXED_REGION,
        "status": "active",
        "created_at": bd_timestamp(),
        "started_at": bd_timestamp(),
        "last_run_at": None,
        "last_attempt_at": None,
        "last_likes": 0,
        "last_note": "Order accepted; Auto Like scheduled.",
        "completed_at": None,
        "paid_at": bd_timestamp(),
        "charged_at": bd_timestamp(),
        "payment_method": "Points",
    }
    save_data("orders", orders)
    return orders[order_id]


def get_orders(user_id=None, limit=None):
    orders = load_data("orders")
    if not isinstance(orders, dict):
        return []
    items = list(orders.values())
    if user_id is not None:
        items = [x for x in items if str(x.get("user_id")) == str(user_id)]
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items[:limit] if limit else items


def get_order(order_id):
    orders = load_data("orders")
    return orders.get(str(order_id)) if isinstance(orders, dict) else None


def update_order(order_id, **changes):
    orders = load_data("orders")
    if not isinstance(orders, dict) or str(order_id) not in orders:
        return None
    orders[str(order_id)].update(changes)
    save_data("orders", orders)
    return orders[str(order_id)]


def format_eta(remaining_likes):
    """Estimate remaining delivery time using the fixed 210 likes/day rate."""
    remaining = max(0, int(remaining_likes or 0))
    if remaining <= 0:
        return "Complete"
    per_day = max(1, int(AUTO_LIKE_DAILY_ESTIMATE or 210))
    days = (remaining + per_day - 1) // per_day
    if days == 1:
        return "প্রায় 1 দিন"
    return f"প্রায় {days} দিন"


def _order_status_label(status):
    return {
        "active": "🟢 RUNNING",
        "completed": "✅ COMPLETE",
        "cancelled": "🛑 CANCELLED",
        "payment_pending": "💳 RUNNING",
    }.get(status, str(status or "UNKNOWN").upper())


def _order_history_status_label(status_filter):
    return {"running":"RUNNING ORDERS", "complete":"COMPLETE ORDERS"}.get(status_filter,"ORDER HISTORY")

def order_history_text(user_id, limit=8, status_filter=None, all_users=False, apply_template=True):
    """Render filtered order cards. Admin sees all users; users see their own orders."""
    if status_filter not in ("running", "complete"):
        return ""
    orders=get_orders(None if all_users else user_id, limit=None)
    if status_filter == "running":
        orders=[o for o in orders if o.get("status") in ("active","payment_pending")]
    else:
        orders=[o for o in orders if o.get("status") in ("completed","cancelled")]
    orders=orders[:limit] if limit else orders
    if not orders:
        order_body="❌ কোনো order নেই।"
    else:
        users=load_data("users") if all_users else {}
        cards=[]
        for o in orders:
            requested=int(o.get("likes_requested",0) or 0); sent=int(o.get("likes_sent",0) or 0); remaining=max(0,requested-sent)
            info=users.get(str(o.get("user_id")),{}) if isinstance(users,dict) else {}
            if not isinstance(info,dict): info={}
            name=info.get("first_name") or o.get("user_name") or "Unknown"
            username=f"@{info.get('username')}" if info.get("username") else (f"@{o.get('username')}" if o.get("username") else "No username")
            cards.append("\n".join([
                f"🆔 Order ID: {o.get('order_id','N/A')}", f"👤 Name: {name}", f"🔗 Username: {username}",
                f"🪪 User ID: {o.get('user_id','N/A')}", f"🎮 UID: {o.get('uid','N/A')}", f"📦 Ordered: {requested:,} Likes",
                f"❤️ Like Sent: {sent:,}", f"⏳ Remaining: {remaining:,}", f"📊 Progress: {sent:,}/{requested:,} Likes", f"📅 Days Passed: {((datetime.now()-datetime.fromisoformat(str(o.get("created_at")).replace(" ","T"))).days if o.get("created_at") else 0)}",
                f"📅 ETA: {format_eta(remaining) if o.get('status') in ('active','payment_pending') else '—'}",
                f"💳 Cost: {int(o.get('price',0) or 0)} Points", f"📌 Status: {_order_status_label(o.get('status'))}",
                f"🗓️ Order Time: {o.get('created_at','N/A')}", f"⏰ Last Like Time: {o.get('last_run_at') or 'Not sent yet'}",
                f"ℹ️ Note: {o.get('last_note') or '—'}", "━━━━━━━━━━━━━━━━━━"
            ]))
        order_body="\n".join(cards)
    if not apply_template:
        return order_body
    raw=get_content("order_history")
    try:
        return raw.format(bot_name=BOT_NAME,status_label=_order_history_status_label(status_filter),orders=order_body)
    except Exception:
        return f"📜 {BOT_NAME} — {_order_history_status_label(status_filter)}\n\n{order_body}"

def build_order_history_keyboard(admin=False, status_filter=None, user_id=None):
    """Initial screen: ONLY Running/Complete/Back. Filtered screen: order actions + Back."""
    if status_filter not in ("running", "complete"):
        return InlineKeyboardMarkup([
            [make_inline_button("🟢 RUNNING", callback_data="order_history:running", style="success"),
             make_inline_button("✅ COMPLETE", callback_data="order_history:complete", style="primary")],
            [make_inline_button("🔙 BACK", callback_data="order_history:back", style="danger")],
        ])
    orders=get_orders(None if admin else user_id,limit=None)
    if status_filter == "running":
        orders=[o for o in orders if o.get("status") in ("active","payment_pending")]
    else:
        orders=[o for o in orders if o.get("status") in ("completed","cancelled")]
    buttons=[]
    if status_filter == "running":
        for o in orders[:8]:
            if o.get("status") in ("active","payment_pending"):
                buttons.append([make_inline_button(
                    f"🛑 CANCEL {o.get('order_id')}",
                    callback_data=f"cancel_order_ui:{o.get('order_id')}:running",
                    style="danger")])
    buttons.append([make_inline_button("🔙 BACK", callback_data="order_history:back", style="primary")])
    return InlineKeyboardMarkup(buttons)


def classify_api_result(result):
    """Return a user-safe reason without exposing raw API errors."""
    if not isinstance(result, dict):
        return "temporary"
    raw = " ".join(str(result.get(k, "")) for k in ("error", "message", "reason", "detail", "status_message")).lower()
    if any(word in raw for word in ("invalid uid", "uid not found", "player not found", "account not found", "invalid player")):
        return "uid"
    if any(word in raw for word in ("europe", "india", "indonesia", "brazil", "singapore", "mena", "not bd", "wrong region", "invalid region", "unsupported region")):
        return "region"
    return "temporary"

def make_keyboard_button(text, style=None, icon_custom_emoji_id=PREMIUM_BUTTON_ICON_ID):
    """Build a Telegram reply-keyboard button with native Bot API styling."""
    text = strip_premium_emoji_tags(text)
    kwargs = {}
    if style in ("primary", "success", "danger"):
        kwargs["style"] = style
    if icon_custom_emoji_id:
        kwargs["icon_custom_emoji_id"] = str(icon_custom_emoji_id)
    try:
        return _OriginalKeyboardButton(text, **kwargs)
    except (TypeError, ValueError):
        # Keep the keyboard usable if the host has an older PTB build.
        fallback = {}
        if style in ("primary", "success", "danger"):
            fallback["style"] = style
        try:
            return _OriginalKeyboardButton(text, **fallback)
        except (TypeError, ValueError):
            return _OriginalKeyboardButton(text)


def make_inline_button(text, callback_data=None, style=None, url=None,
                       icon_custom_emoji_id=None):
    """Build an inline/page button; normal emoji are allowed here. Main reply keyboard uses native Premium icons."""
    text = strip_premium_emoji_tags(text)
    kwargs = {}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if style in ("primary", "success", "danger"):
        kwargs["style"] = style
    if icon_custom_emoji_id:
        kwargs["icon_custom_emoji_id"] = str(icon_custom_emoji_id)
    try:
        return _OriginalInlineKeyboardButton(text, **kwargs)
    except (TypeError, ValueError):
        fallback = {k:v for k,v in kwargs.items() if k in ("callback_data", "url", "style")}
        try:
            return _OriginalInlineKeyboardButton(text, **fallback)
        except (TypeError, ValueError):
            return _OriginalInlineKeyboardButton(
                text, **{k:v for k,v in kwargs.items() if k in ("callback_data", "url")}
            )


def build_main_menu():
    """Build a completely fresh main reply keyboard.

    IMPORTANT: these two mappings are intentionally explicit so an old saved
    label/config cannot swap their native Telegram custom-emoji icons.
    """
    m = get_menu_labels()

    # Exact native Telegram button icon IDs requested for these two buttons.
    # Keep these explicit rather than deriving them from the button text.
    auto_like_package_icon = "6122925752502460840"

    return ReplyKeyboardMarkup([
        [make_keyboard_button(m["balance"], "success", PREMIUM_BUTTON_EMOJIS["balance"]),
         make_keyboard_button(m["add_money"], "primary", PREMIUM_BUTTON_EMOJIS["add_money"])],
                [make_keyboard_button(m["order_history"], "success", PREMIUM_BUTTON_EMOJIS["order_history"]),
         make_keyboard_button(m["auto_package"], "primary", auto_like_package_icon)],
        [make_keyboard_button(m["bonus_220"], "success", PREMIUM_BUTTON_EMOJIS["bonus_220"]),
         make_keyboard_button(m["daily_free"], "success", PREMIUM_BUTTON_EMOJIS["daily_free"])],
        [make_keyboard_button(m["referral"], "primary", PREMIUM_BUTTON_EMOJIS["referral"])],
        [make_keyboard_button(m["customer_care"], "danger", PREMIUM_BUTTON_EMOJIS["customer_care"])],
        [make_keyboard_button(m["tutorial"], "primary", PREMIUM_BUTTON_EMOJIS["tutorial"])],
    ], resize_keyboard=True, is_persistent=False)


def package_text():
    packages = "\n".join(f"{i}. ❤️ {l:,} Likes — {p} TK" for i,(l,p) in enumerate(AUTO_LIKE_PACKAGES,1))
    return render_content("auto_package", bot_name=BOT_NAME, packages=packages)



# ═══════════════════════════════════════════════════════════════════
# BOHUDUR PAYMENT AUTOMATION — bKASH ADD MONEY
# ═══════════════════════════════════════════════════════════════════

PAYMENT_LOCK = asyncio.Lock()


def _payment_store():
    data = load_data("payments")
    return data if isinstance(data, dict) else {}


def _save_payment(paymentkey, record):
    store = _payment_store()
    store[str(paymentkey)] = dict(record)
    return save_data("payments", store)


def _get_payment(paymentkey):
    return _payment_store().get(str(paymentkey))


def _make_payment_email(user):
    # Bohudur requires a syntactically valid email. The bot does not ask the
    # Telegram user for a separate email, so use a unique non-delivery address.
    return f"telegram_{int(user.id)}@example.com"


def _sanitize_bohudur_full_name(user):
    """Return a conservative gateway-compatible full name."""
    raw = getattr(user, "full_name", None) or getattr(user, "first_name", None) or ""
    raw = str(raw)
    cleaned = re.sub(r"[^A-Za-z ]+", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()[:100].strip()
    if not re.search(r"[A-Za-z]", cleaned):
        cleaned = "Telegram User"
    return cleaned


def _bohudur_headers():
    return {
        "Content-Type": "application/json",
        "AH-BOHUDUR-API-KEY": BOHUDUR_API_KEY.strip(),
    }


def _bohudur_public_url(path):
    if not PUBLIC_BASE_URL:
        return ""
    return f"{PUBLIC_BASE_URL}{path}"


def build_add_money_keyboard():
    rows = []
    for amount in BOHUDUR_PAYMENT_PRESETS:
        rows.append([
            make_inline_button(
                get_payment_label(amount),
                callback_data=f"addmoney_amount:{amount}",
                style="success",
            )
        ])
    rows.append([
        make_inline_button(
            "✏️ CUSTOM AMOUNT",
            callback_data="addmoney_custom",
            style="primary",
        )
    ])
    rows.append([
        make_inline_button("❌ CANCEL", callback_data="addmoney_cancel", style="danger")
    ])
    return InlineKeyboardMarkup(rows)


async def create_bohudur_payment(user, amount):
    if not BOHUDUR_API_KEY or BOHUDUR_API_KEY == "YOUR_BOHUDUR_API_KEY":
        return {"ok": False, "error": "BOHUDUR_API_KEY is not configured in main.py/hosting environment."}

    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid amount."}

    if amount < BOHUDUR_PAYMENT_LIMIT_MIN or amount > BOHUDUR_PAYMENT_LIMIT_MAX:
        return {
            "ok": False,
            "error": f"Amount must be between {BOHUDUR_PAYMENT_LIMIT_MIN} and {BOHUDUR_PAYMENT_LIMIT_MAX} TK.",
        }

    # A public HTTPS URL is needed for automatic webhook verification.
    success_url = _bohudur_public_url(BOHUDUR_SUCCESS_WEBHOOK_PATH)
    cancel_url = _bohudur_public_url(BOHUDUR_CANCEL_WEBHOOK_PATH)
    redirect_url = _bohudur_public_url(BOHUDUR_RETURN_PATH)

    payload = {
        "full_name": _sanitize_bohudur_full_name(user),
        "email": _make_payment_email(user),
        "amount": amount,
        "return_type": "GET",
        "redirect_url": redirect_url or "default",
        "cancel_url": cancel_url or "default",
        "metadata": {
            "bot": BOT_NAME,
            "user_id": int(user.id),
            "purpose": "add_money",
            "gateway": "bkash",
        },
    }

    if success_url and cancel_url:
        payload["webhook"] = {
            "success": success_url,
            "cancel": cancel_url,
        }

    session = await _get_api_session()
    try:
        async with session.post(
            f"{BOHUDUR_BASE_URL}/create/v2/",
            headers=_bohudur_headers(),
            json=payload,
        ) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = {"message": await resp.text()}
    except Exception as exc:
        logger.exception("Bohudur create payment request failed")
        return {"ok": False, "error": f"Payment gateway connection failed: {exc}"}

    if (
        resp.status == 200
        and isinstance(data, dict)
        and data.get("status") == "success"
        and int(data.get("responseCode", 0) or 0) == 200
        and data.get("paymentkey")
        and data.get("payment_url")
    ):
        paymentkey = str(data["paymentkey"])
        _save_payment(paymentkey, {
            "paymentkey": paymentkey,
            "user_id": int(user.id),
            "amount": amount,
            "status": "CREATED",
            "credited": False,
            "created_at": bd_timestamp(),
        })
        return {
            "ok": True,
            "paymentkey": paymentkey,
            "payment_url": str(data["payment_url"]),
            "amount": amount,
        }

    code = data.get("responseCode") if isinstance(data, dict) else None
    msg = data.get("message", "Unable to create payment.") if isinstance(data, dict) else "Unable to create payment."
    return {"ok": False, "error": f"Bohudur error {code}: {msg}" if code else str(msg)}


async def query_bohudur_payment(paymentkey):
    session = await _get_api_session()
    try:
        async with session.post(
            f"{BOHUDUR_BASE_URL}/query/v2/",
            headers=_bohudur_headers(),
            json={"paymentkey": str(paymentkey)},
        ) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = {"message": await resp.text()}
    except Exception as exc:
        logger.exception("Bohudur query failed for %s", paymentkey)
        return {"status": "ERROR", "message": str(exc)}

    if not isinstance(data, dict):
        return {"status": "ERROR", "message": "Invalid query response."}
    return data


async def execute_bohudur_payment(paymentkey):
    session = await _get_api_session()
    try:
        async with session.post(
            f"{BOHUDUR_BASE_URL}/execute/v2/",
            headers=_bohudur_headers(),
            json={"paymentkey": str(paymentkey)},
        ) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = {"message": await resp.text()}
    except Exception as exc:
        logger.exception("Bohudur execute failed for %s", paymentkey)
        return {"status": "ERROR", "message": str(exc)}

    if not isinstance(data, dict):
        return {"status": "ERROR", "message": "Invalid execute response."}
    return data


async def finalize_bohudur_payment(paymentkey, notify_user=True):
    """Verify with Query, execute once, then credit the user's balance exactly once."""
    async with PAYMENT_LOCK:
        record = _get_payment(paymentkey)
        if not isinstance(record, dict):
            logger.warning("Unknown Bohudur paymentkey: %s", paymentkey)
            return False, "unknown_payment"

        if record.get("credited"):
            return True, "already_credited"

        query = await query_bohudur_payment(paymentkey)
        status = str(query.get("status", "")).upper()

        if status == "CANCELLED":
            record.update({"status": "CANCELLED", "updated_at": bd_timestamp()})
            _save_payment(paymentkey, record)
            return False, "cancelled"

        if status == "PENDING":
            record.update({"status": "PENDING", "updated_at": bd_timestamp()})
            _save_payment(paymentkey, record)
            return False, "pending"

        if status == "EXECUTED":
            # If another request executed it first, do NOT credit again unless
            # our own persistent record already says it was credited.
            record.update({"status": "EXECUTED", "updated_at": bd_timestamp()})
            _save_payment(paymentkey, record)
            return False, "executed_not_recorded"

        if status != "COMPLETED":
            record.update({"status": status or "UNKNOWN", "updated_at": bd_timestamp()})
            _save_payment(paymentkey, record)
            return False, "not_completed"

        executed = await execute_bohudur_payment(paymentkey)
        exec_status = str(executed.get("status", "")).upper()

        if exec_status == "EXECUTED":
            amount = int(record.get("amount", 0) or 0)
            # Credit only from our stored payment record, never from an
            # untrusted webhook amount.
            new_balance = add_balance(record["user_id"], amount)
            record.update({
                "status": "EXECUTED",
                "credited": True,
                "credited_amount": amount,
                "credited_at": bd_timestamp(),
                "balance_after": new_balance,
            })
            _save_payment(paymentkey, record)

            if notify_user:
                try:
                    await TELEGRAM_APPLICATION.bot.send_message(
                        chat_id=int(record["user_id"]),
                        text=(
                            "✅ PAYMENT SUCCESSFUL\n\n"
                            f"💳 Method: bKash\n"
                            f"💰 Added: {amount} TK\n"
                            f"💎 Balance: {new_balance} Points\n"
                            f"🆔 Payment: {paymentkey}\n\n"
                            f"⚡ {BOT_NAME}"
                        ),
                    )
                except Exception:
                    logger.exception("Could not notify user after payment %s", paymentkey)
            return True, "credited"

        # 3108 means it was already executed. Do not guess whether our balance
        # was credited, because execute is one-time and this protects against
        # duplicate webhook deliveries.
        record.update({"status": exec_status or "EXECUTE_FAILED", "updated_at": bd_timestamp()})
        _save_payment(paymentkey, record)
        return False, "execute_failed"


async def addmoney_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await _is_duplicate_user_action(context, f"callback:{query.data}"):
        try:
            await query.answer()
        except Exception:
            pass
        return
    if not query:
        return
    await query.answer()
    user = query.from_user
    ensure_user(user.id, user)

    data = query.data or ""
    if data == "addmoney_cancel":
        context.user_data.pop("addmoney_waiting_amount", None)
        await query.edit_message_text("❌ Add Money cancelled.")
        return

    if data == "addmoney_custom":
        context.user_data["addmoney_waiting_amount"] = True
        await query.edit_message_text(
            "✏️ CUSTOM bKash AMOUNT\n\n"
            f"Minimum: {BOHUDUR_PAYMENT_LIMIT_MIN} TK\n"
            f"Maximum: {BOHUDUR_PAYMENT_LIMIT_MAX} TK\n\n"
            "এখন শুধু amount লিখুন। উদাহরণ: 150"
        )
        return

    if not data.startswith("addmoney_amount:"):
        return

    try:
        amount = int(data.split(":", 1)[1])
    except (ValueError, TypeError):
        await query.edit_message_text("❌ Invalid amount.")
        return

    await query.edit_message_text("⏳ bKash payment তৈরি করা হচ্ছে...")
    result = await create_bohudur_payment(user, amount)
    if not result.get("ok"):
        await context.bot.send_message(
            chat_id=user.id,
            text=f"❌ Payment তৈরি করা যায়নি।\n\n{result.get('error', 'Unknown error')}",
            reply_markup=build_add_money_keyboard(),
        )
        return

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            "💳 bKASH PAYMENT READY\n\n"
            f"💰 Amount: {amount} TK\n"
            f"🆔 Payment Key: {result['paymentkey']}\n\n"
            "নিচের button-এ click করে Bohudur secure checkout-এ payment complete করুন।\n"
            "Payment successful হওয়ার পর verified payment অনুযায়ী balance automatically add হবে।"
        ),
        reply_markup=InlineKeyboardMarkup([
            [make_inline_button("💳 PAY WITH bKASH", url=result["payment_url"], style="success")],
            [make_inline_button("🔄 CHECK PAYMENT", callback_data=f"addmoney_check:{result['paymentkey']}", style="primary")],
        ]),
    )


async def addmoney_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await _is_duplicate_user_action(context, f"callback:{query.data}"):
        try:
            await query.answer()
        except Exception:
            pass
        return
    if not query:
        return
    await query.answer("Payment status check করা হচ্ছে...")
    user = query.from_user
    data = query.data or ""
    paymentkey = data.split(":", 1)[1] if ":" in data else ""
    record = _get_payment(paymentkey)

    if not isinstance(record, dict) or int(record.get("user_id", 0)) != int(user.id):
        await query.answer("এই payment আপনার নয়।", show_alert=True)
        return

    ok, state = await finalize_bohudur_payment(paymentkey, notify_user=False)
    record = _get_payment(paymentkey) or record

    if ok and state == "credited":
        await query.edit_message_text(
            "✅ PAYMENT VERIFIED\n\n"
            f"💳 Method: bKash\n"
            f"💰 Added: {int(record.get('amount', 0))} TK\n"
            f"💎 Current Balance: {get_balance(user.id)} Points\n\n"
            f"⚡ {BOT_NAME}"
        )
    elif state == "already_credited":
        await query.edit_message_text(
            "✅ PAYMENT ALREADY ADDED\n\n"
            f"💎 Current Balance: {get_balance(user.id)} Points"
        )
    elif state == "pending":
        await query.edit_message_text(
            "⏳ PAYMENT PENDING\n\n"
            "Payment এখনো COMPLETED হয়নি। Payment complete করার পর আবার CHECK PAYMENT চাপুন।",
            reply_markup=InlineKeyboardMarkup([
                [make_inline_button("🔄 CHECK PAYMENT", callback_data=f"addmoney_check:{paymentkey}", style="primary")]
            ]),
        )
    elif state == "cancelled":
        await query.edit_message_text("❌ PAYMENT CANCELLED\n\nকোনো balance add করা হয়নি।")
    else:
        await query.edit_message_text(
            "⚠️ Payment এখনো verify করা যায়নি। কিছুক্ষণ পরে আবার CHECK PAYMENT চাপুন।",
            reply_markup=InlineKeyboardMarkup([
                [make_inline_button("🔄 CHECK PAYMENT", callback_data=f"addmoney_check:{paymentkey}", style="primary")]
            ]),
        )


async def bohudur_webhook_success(request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    paymentkey = str(payload.get("paymentkey", "")).strip()
    if paymentkey:
        try:
            await finalize_bohudur_payment(paymentkey, notify_user=True)
        except Exception:
            logger.exception("Bohudur success webhook processing failed for %s", paymentkey)

    return web.json_response({"ok": True}, status=200)


async def bohudur_webhook_cancel(request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    paymentkey = str(payload.get("paymentkey", "")).strip()
    if paymentkey:
        record = _get_payment(paymentkey)
        if isinstance(record, dict):
            record.update({"status": "CANCELLED", "updated_at": bd_timestamp()})
            _save_payment(paymentkey, record)

    return web.json_response({"ok": True}, status=200)


async def bohudur_return(request):
    paymentkey = str(request.query.get("paymentkey", "")).strip()
    if paymentkey:
        # The webhook remains the authoritative path; this only gives a
        # friendly browser response after checkout.
        await finalize_bohudur_payment(paymentkey, notify_user=True)
    return web.Response(
        text="Payment received. You can return to Telegram and check your balance.",
        content_type="text/plain",
    )


def build_admin_contact_keyboard():
    return InlineKeyboardMarkup([
        [make_inline_button("👤 CONTACT ADMIN", url=ADMIN_URL, style="primary")]
    ])


def build_package_keyboard():
    buttons = []
    for index, (likes, price) in enumerate(AUTO_LIKE_PACKAGES, start=1):
        buttons.append([
            make_inline_button(
                f"{index}. ❤️ {likes:,} Likes — {price} TK",
                callback_data=f"package_select_{index}", style="primary"
            )
        ])
    buttons.append([make_inline_button("❌ CANCEL", callback_data="package_cancel", style="danger")])
    return InlineKeyboardMarkup(buttons)


async def package_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select a package; no likes are sent and no balance is deducted at selection time."""
    query = update.callback_query
    if await _is_duplicate_user_action(context, f"callback:{query.data}"):
        try:
            await query.answer()
        except Exception:
            pass
        return
    await query.answer()
    user = query.from_user
    ensure_user(user.id, user)
    data = query.data or ""

    if data in ("package_cancel", "package_uid_cancel"):
        context.user_data.pop("pending_package", None)
        await query.edit_message_text(
            format_bold("❌ Package order cancelled.\n\nকোনো order তৈরি হয়নি এবং কোনো Point কাটা হয়নি.")
        )
        return
    if not data.startswith("package_select_"):
        return
    try:
        index = int(data.rsplit("_", 1)[1])
        likes, price = AUTO_LIKE_PACKAGES[index - 1]
    except (ValueError, IndexError):
        await query.edit_message_text(format_bold("❌ এই package আর available নেই। আবার package list খুলুন।"))
        return

    if likes in COMING_SOON_PACKAGES:
        context.user_data.pop("pending_package", None)
        await query.edit_message_text(format_bold(f"📦 {likes:,} LIKES\n\n🚧 COMING SOON!\n\nএই package এখনো চালু হয়নি।"))
        return

    balance = get_balance(user.id)
    if balance < price:
        context.user_data.pop("pending_package", None)
        await query.edit_message_text(format_bold(
            f"❌ পর্যাপ্ত Balance নেই!\n\n📦 Selected: {likes:,} Likes\n💳 Package Price: {price} Points\n💰 Your Balance: {balance} Points\n\nআগে Balance Add Money করে নিন।"
        ), reply_markup=build_admin_contact_keyboard())
        return

    context.user_data["pending_package"] = {"likes": likes, "price": price, "selected_at": bd_timestamp()}
    await query.edit_message_text(
        format_bold(render_content("package_selected",likes=likes,price=price,balance=balance)),
        reply_markup=InlineKeyboardMarkup([[make_inline_button("❌ CANCEL",callback_data="package_uid_cancel",style="danger")]]))


async def process_package_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create a long-running auto-like order and attempt delivery immediately."""
    pending = context.user_data.get("pending_package")
    if not pending:
        return False
    user = update.effective_user
    uid = (update.message.text or "").strip()
    if not uid.isdigit():
        await update.message.reply_text(
            format_bold(render_content("uid_invalid")),
            reply_markup=InlineKeyboardMarkup([[make_inline_button("❌ CANCEL",callback_data="package_uid_cancel",style="danger")]]))
        return True

    likes_requested = int(pending.get("likes", 0))
    price = int(pending.get("price", 0))
    balance = get_balance(user.id)
    if likes_requested <= 0:
        context.user_data.pop("pending_package", None)
        await update.message.reply_text(format_bold("❌ Package configuration ভুল। Admin-কে জানান।"))
        return True
    if balance < price:
        context.user_data.pop("pending_package", None)
        await update.message.reply_text(format_bold(f"❌ আপনার Balance কম।\n\n💳 Required: {price} Points\n💰 Current Balance: {balance} Points"), reply_markup=build_admin_contact_keyboard())
        return True

    # Avoid duplicate active orders for the same UID.
    active = [o for o in get_orders(limit=None) if str(o.get("uid")) == uid and o.get("status") in ("active", "payment_pending")]
    if active:
        context.user_data.pop("pending_package", None)
        o = active[0]
        remaining = max(0, int(o.get("likes_requested", 0)) - int(o.get("likes_sent", 0)))
        await update.message.reply_text(format_bold(
            f"⚠️ এই UID-তে একটি active order already আছে।\n\n🆔 Order: {o.get('order_id')}\n🎮 UID: {uid}\n❤️ Sent: {o.get('likes_sent', 0):,}\n⏳ Remaining: {remaining:,}\n📅 ETA: {format_eta(remaining)}"
        ))
        return True

    new_balance = add_balance(user.id, -price)
    try:
        order = create_order(user.id, uid, likes_requested, price)
    except Exception:
        add_balance(user.id, price)
        raise
    auto = load_data("auto_like")
    auto[uid] = {
        "region": FIXED_REGION,
        "days_left": max(3650, (likes_requested + max(1, AUTO_LIKE_DAILY_ESTIMATE) - 1) // max(1, AUTO_LIKE_DAILY_ESTIMATE) + 5),
        "added_at": bd_timestamp(),
        "order_id": order["order_id"],
        "order_mode": "package",
    }
    save_data("auto_like", auto)
    context.user_data.pop("pending_package", None)

    # No API call here: paid Auto Like starts only in the daily 04:00 BD cycle.

    await reply_editable_content(update.message,"order_confirmed",
        order_id=order["order_id"],uid=uid,likes=likes_requested,eta=format_eta(likes_requested),price=price,balance=new_balance)
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=format_bold(
            f"🆕 NEW PACKAGE ORDER\n\n🆔 {order['order_id']}\n👤 User: {user.id}\n🎮 UID: {uid}\n📦 {likes_requested:,} Likes\n💳 {price} Points\n⏰ Auto Like: 4:00 AM BD\n💰 Payment: DEDUCTED ON ORDER"
        ))
    except Exception:
        logger.exception("Could not notify admin about order %s", order["order_id"])
    return True


async def menu_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (update.message.text or "").strip()
    if await _is_duplicate_user_action(context, f"menu:{text}"):
        return
    ensure_user(user.id, user)
    add_broadcast_user(user.id)
    if await edit_content_message(update, context):
        return

    # Custom Add Money amount entry.
    if (
        update.effective_chat
        and update.effective_chat.type == "private"
        and context.user_data.get("addmoney_waiting_amount")
    ):
        context.user_data.pop("addmoney_waiting_amount", None)
        if not text.isdigit():
            await update.message.reply_text(
                "❌ শুধু numeric amount দিন। উদাহরণ: 150",
                reply_markup=build_add_money_keyboard(),
            )
            return
        amount = int(text)
        if amount < BOHUDUR_PAYMENT_LIMIT_MIN or amount > BOHUDUR_PAYMENT_LIMIT_MAX:
            await update.message.reply_text(
                f"❌ Amount {BOHUDUR_PAYMENT_LIMIT_MIN}–{BOHUDUR_PAYMENT_LIMIT_MAX} TK-এর মধ্যে দিন।",
                reply_markup=build_add_money_keyboard(),
            )
            return

        await update.message.reply_text("⏳ bKash payment তৈরি করা হচ্ছে...")
        result = await create_bohudur_payment(user, amount)
        if not result.get("ok"):
            await update.message.reply_text(
                f"❌ Payment তৈরি করা যায়নি।\n\n{result.get('error', 'Unknown error')}",
                reply_markup=build_add_money_keyboard(),
            )
            return

        await update.message.reply_text(
            "💳 bKASH PAYMENT READY\n\n"
            f"💰 Amount: {amount} TK\n"
            f"🆔 Payment Key: {result['paymentkey']}\n\n"
            "নিচের button-এ click করে Bohudur secure checkout-এ payment complete করুন।",
            reply_markup=InlineKeyboardMarkup([
                [make_inline_button("💳 PAY WITH bKASH", url=result["payment_url"], style="success")],
                [make_inline_button("🔄 CHECK PAYMENT", callback_data=f"addmoney_check:{result['paymentkey']}", style="primary")],
            ]),
        )
        return

    # Keep navigation buttons responsive even while the like service is OFF.

    pending_filter=context.user_data.get("pending_filter_trigger")
    if pending_filter and is_admin(user.id):
        set_filter(pending_filter, text); context.user_data.pop("pending_filter_trigger",None)
        await update.message.reply_text(format_bold(f"✅ FILTER SAVED\n\nTrigger: {pending_filter}\nReply: {text}")); return
    if update.effective_chat and update.effective_chat.type in ["group","supergroup"]:
        match=get_filter_response(text)
        if match:
            await update.message.reply_text(str(match.get("response",""))); return
        # Do not expose private menu/interface in groups.
        return

    # Pending UID states are private-chat only, so random group messages
    # can never be mistaken for UID input.
    if update.effective_chat and update.effective_chat.type == "private":
        if context.user_data.get("pending_first_220"):
            if await process_first_220_uid(update, context):
                return
        if context.user_data.get("pending_package"):
            if text == "❌ CANCEL PACKAGE":
                context.user_data.pop("pending_package", None)
                await update.message.reply_text(format_bold("❌ Package order cancelled."))
                return
            if await process_package_uid(update, context):
                return

    normalized_text = clean_keyboard_label(text)
    def menu_is(key):
        return normalized_text == clean_keyboard_label(get_menu_label(key))

    if menu_is("balance"):
        await reply_editable_content(update.message,"balance",bot_name=BOT_NAME,user_id=user.id,balance=get_balance(user.id))

    elif menu_is("add_money"):
        await reply_editable_content(
            update.message,
            "add_money",
            reply_markup=build_add_money_keyboard(),
            user_id=user.id,
        )

    elif menu_is("order_history"):
        admin_user=is_admin(user.id)
        await update.message.reply_text("📜 ORDER HISTORY — SELECT A PAGE", reply_markup=build_order_history_keyboard(admin_user,None,user.id))

    elif text == "🎟️ REDEEM CODES":
        await update.message.reply_text(format_bold("🎟️ REDEEM CODES\n\n🚧 Coming Soon!\n\nRedeem Code System খুব শীঘ্রই চালু হবে."))

    elif menu_is("auto_package"):
        packages = "\n".join(f"{i}. ❤️ {l:,} Likes — {p} TK" for i,(l,p) in enumerate(AUTO_LIKE_PACKAGES,1))
        await reply_editable_content(
            update.message, "auto_package",
            reply_markup=build_package_keyboard(),
            bot_name=BOT_NAME, packages=packages
        )

    elif menu_is("bonus_220"):
        users = load_data("users")
        claimed = bool(users.get(str(user.id), {}).get("first_220_claimed", False)) if isinstance(users,dict) else False
        if claimed:
            await update.message.reply_text(format_bold(render_content("bonus_200")))
        else:
            keyboard = InlineKeyboardMarkup([
                [make_inline_button("✅ CONFIRM & GET 200 LIKE", callback_data="bonus220_confirm", style="success")],
                [make_inline_button("❌ CANCEL", callback_data="bonus220_cancel", style="danger")],
            ])
            await reply_editable_content(update.message,"bonus_200",reply_markup=keyboard)

    elif menu_is("daily_free"):
        keyboard=InlineKeyboardMarkup([[make_inline_button(
            "📢 JOIN & GET DAILY FREE LIKE",url=DAILY_FREE_LIKE_URL,style="success")]])
        lim=get_free_limit()
        await reply_editable_content(update.message,"daily_free",reply_markup=keyboard,limit=lim if lim is not None else "Unlimited")

    elif menu_is("referral"):
        bot_username=(await context.bot.get_me()).username
        referral_link=f"https://t.me/{bot_username}?start=ref_{user.id}"
        ref_stats=get_referral_stats(user.id)
        share_url=("https://t.me/share/url?url="+quote(referral_link)+
                   "&text="+quote(f"🎁 {BOT_NAME} — Join & Earn Points!"))
        reply_markup=InlineKeyboardMarkup([
                [make_inline_button("📤 SHARE REFERRAL LINK",url=share_url,style="primary")],
                [make_inline_button("🔗 OPEN MY LINK",url=referral_link,style="success")],
            ])
        await reply_editable_content(update.message,"referral",reply_markup=reply_markup,
            reward=REFERRAL_REWARD,link=referral_link,balance=get_balance(user.id),
            count=ref_stats["count"],earned=ref_stats["earned"])

    elif menu_is("customer_care"):
        await reply_editable_content(update.message,"customer_care",reply_markup=build_admin_contact_keyboard())

    elif menu_is("tutorial"):
        tutorial_url = "https://youtube.com/@as_owner99?si=eV8QCx6gJqJjteFd"
        markup = InlineKeyboardMarkup([[make_inline_button("OPEN YOUTUBE TUTORIAL", url=tutorial_url, style="success")]])
        await reply_editable_content(update.message, "tutorial", reply_markup=markup)


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the full admin control panel."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only."))
        return
    users = load_data("users")
    referrals = load_data("referrals")
    text = (
        "👑 AS LIKE BOT — ADMIN PANEL\n\n"
        "👥 USER MANAGEMENT\n"
        "/users — সব bot user-এর Telegram ID দেখুন\n"
        "/user <id> — একজন user-এর details\n"
        "/addpoints <id> <points> — points দিন\n"
        "/setpoints <id> <points> — balance set করুন\n"
        "/vip <id> <days> — VIP দিন\n"
        "/vipremove <id> — VIP বাতিল\n"
        "/unlimit <uid> — UID unlimited করুন\n"
        "/removeunlimit <uid> — unlimited remove\n\n"
        "🎁 REFERRAL\n"
        "/refstats — referral statistics\n"
        "/setrefreward <points> — referral reward পরিবর্তন\n"
        "/botedit — সব editable notice/message edit\n"
        "/editallow <userid> — edit permission দিন\n"
        "/editremove <userid> — edit permission remove\n\n"
        "📦 LIKE / PACKAGE\n"
        "/packages — current package list\n"
        "/setpackage <likes> <price> — package add/update\n"
        "/editpackage <number> <likes> <price> — package edit\n"
        "/removepackage <likes> — package remove\n"
        "/autolike <uid> <days> — Auto Like\n"
        "/removeauto <uid> — Auto Like remove\n"
        "/autolist — Auto Like list\n"
        "/likeinfo <uid> — Like info\n"
        "/tlike <uid> <limit> — Target Like\n"
        "/removetlike <uid> — Target Like remove\n"
        "/tlist — Target Like list\n\n"
        "📜 ORDER MANAGEMENT\n"
        "/orders — সব package order\n"
        "/order <order_id> — order details\n"
        "/cancelorder <order_id> — order cancel\n"
        "/setdailyestimate <likes> — ETA estimate change\n"
        "/autorestart — bot restart/off/API fail হলে pending Auto Like এখনই retry\n"
        "/setfreelimit <50|100|unlimited> — Free Like cap\n"
        "/filter <word> — auto reply filter add\n"
        "/filterlist / /filterremove <word>\n\n"
        "📊 BOT CONTROL\n"
        "/stats — statistics\n"
        "/broadcast <message> — সবাইকে message\n"
        "/allow <group_id> / /removegroup <group_id>\n"
        "/add <name> <link> / /removechannel <name>\n"
        "/grouplist — allowed groups\n"
        "/on / /off — group bot control\n\n"
        f"📌 Registered Users: {len(users)}\n"
        f"🎁 Referral Records: {len(referrals)}\n"
        f"⚡ {BOT_NAME}"
    )
    await update.message.reply_text(format_bold(text))


async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only paginated user list; avoids Telegram message-size failures."""
    if not is_admin(update.effective_user.id):
        return
    users = load_data("users")
    if not isinstance(users, dict) or not users:
        await update.message.reply_text("👥 এখনো কোনো user registered নেই।")
        return
    items = list(users.items())
    size = 20
    try:
        page = max(1, int(context.args[0])) if context.args else 1
    except ValueError:
        page = 1
    pages = max(1, (len(items) + size - 1) // size)
    page = min(page, pages)
    chunk = items[(page-1)*size:page*size]
    lines = [f"👑 {BOT_NAME} — USER LIST", f"👥 Total: {len(items)} | 📄 Page: {page}/{pages}", "━━━━━━━━━━━━━━━━━━"]
    for n,(uid,info) in enumerate(chunk,start=(page-1)*size+1):
        info = info if isinstance(info,dict) else {}
        u = get_user_like_usage(uid); m = get_money_stats(uid)
        uname = f"@{info.get('username')}" if info.get('username') else "No username"
        lines.append(f"{n}. 👤 {info.get('first_name','Unknown')} | 🆔 {uid}\n🔗 {uname} | 💰 {int(info.get('balance',0))} P | 👥 Ref: {int(info.get('referrals',0))}\n❤️ Today: {u['today_likes']} | Total: {u['total_likes']} | 💵 Added: {m['total_added']} TK\n━━━━━━━━━━━━━━━━━━")
    nav=[]
    if page>1: nav.append(make_inline_button("⬅️ Previous",callback_data=f"users_page:{page-1}",style="primary"))
    if page<pages: nav.append(make_inline_button("Next ➡️",callback_data=f"users_page:{page+1}",style="primary"))
    await update.message.reply_text("\n".join(lines),reply_markup=InlineKeyboardMarkup([nav]) if nav else None)


async def users_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Previous/Next buttons for the admin /users list."""
    query = update.callback_query
    if await _is_duplicate_user_action(context, f"callback:{query.data}"):
        try:
            await query.answer()
        except Exception:
            pass
        return
    if not is_admin(query.from_user.id):
        await query.answer("Admin only.", show_alert=True)
        return

    try:
        page = max(1, int((query.data or "").split(":", 1)[1]))
    except (ValueError, IndexError):
        await query.answer("Invalid page.", show_alert=True)
        return

    users = load_data("users")
    if not isinstance(users, dict) or not users:
        await query.edit_message_text("👥 এখনো কোনো user registered নেই।")
        return

    items = list(users.items())
    size = 20
    pages = max(1, (len(items) + size - 1) // size)
    page = min(page, pages)
    chunk = items[(page - 1) * size:page * size]

    lines = [
        f"👑 {BOT_NAME} — USER LIST",
        f"👥 Total: {len(items)} | 📄 Page: {page}/{pages}",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for n, (uid, info) in enumerate(chunk, start=(page - 1) * size + 1):
        info = info if isinstance(info, dict) else {}
        u = get_user_like_usage(uid)
        m = get_money_stats(uid)
        uname = f"@{info.get('username')}" if info.get('username') else "No username"
        lines.append(
            f"{n}. 👤 {info.get('first_name', 'Unknown')} | 🆔 {uid}\n"
            f"🔗 {uname} | 💰 {int(info.get('balance', 0))} P | "
            f"👥 Ref: {int(info.get('referrals', 0))}\n"
            f"❤️ Today: {u['today_likes']} | Total: {u['total_likes']} | "
            f"💵 Added: {m['total_added']} TK\n"
            "━━━━━━━━━━━━━━━━━━"
        )

    nav = []
    if page > 1:
        nav.append(
            make_inline_button(
                "⬅️ Previous",
                callback_data=f"users_page:{page - 1}",
            )
        )
    if page < pages:
        nav.append(
            make_inline_button(
                "Next ➡️",
                callback_data=f"users_page:{page + 1}",
            )
        )

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([nav]) if nav else None,
    )


async def user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only."))
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(format_bold("Format: /user <telegram_user_id>"))
        return
    uid = context.args[0]
    info = ensure_user(uid)
    ref = get_referral_stats(uid)
    usage = get_user_like_usage(uid)
    await update.message.reply_text(format_bold(
        f"👤 USER DETAILS\n\n🆔 ID: {uid}\n"
        f"👤 Name: {info.get('first_name', 'Unknown')}\n"
        f"🔗 Username: @{info.get('username')}\n" if info.get('username') else f"👤 USER DETAILS\n\n🆔 ID: {uid}\n👤 Name: {info.get('first_name', 'Unknown')}\n"
        f"💰 Balance: {info.get('balance', 0)} Points\n"
        f"👥 Referrals: {ref['count']}\n"
        f"🎁 Referral Earned: {ref['earned']} Points\n"
        f"❤️ Total Likes: {usage['total_likes']}\n"
        f"📅 Today Likes: {usage['today_likes']}\n"
        f"💵 Added Today: {get_money_stats(uid)['today_added']} TK\n"
        f"💵 Total Added: {get_money_stats(uid)['total_added']} TK"
    ))


async def refstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only."))
        return
    referrals = load_data("referrals")
    users = load_data("users")
    total_reward = sum(int(x.get("reward", 0)) for x in referrals.values())
    ranked = sorted(((uid, int(info.get("referrals", 0))) for uid, info in users.items()), key=lambda x: x[1], reverse=True)
    lines = ["🎁 REFERRAL STATISTICS", f"Total successful referrals: {len(referrals)}", f"Total points paid: {total_reward}", "", "🏆 Top Referrers:"]
    for uid, count in ranked[:20]:
        if count:
            lines.append(f"🆔 {uid} — {count} referrals")
    await update.message.reply_text(format_bold("\n".join(lines)))


async def setrefreward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global REFERRAL_REWARD
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only."))
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(format_bold("Format: /setrefreward <points>"))
        return
    REFERRAL_REWARD = int(context.args[0])
    settings = load_data("settings")
    if not isinstance(settings, dict): settings = {}
    settings["referral_reward"] = REFERRAL_REWARD
    save_data("settings", settings)
    await update.message.reply_text(format_bold(f"✅ Referral reward set to {REFERRAL_REWARD} Points."))


def package_admin_text():
    if not AUTO_LIKE_PACKAGES:
        return "📦 No packages configured."
    return "\n".join(
        f"{index}. 📦 {likes:,} Likes = {price} TK"
        for index, (likes, price) in enumerate(AUTO_LIKE_PACKAGES, start=1)
    )


async def packages_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only."))
        return
    await update.message.reply_text(format_bold("📦 CURRENT PACKAGES\n\n" + package_admin_text() + "\n\n/setpackage <likes> <price>\n/removepackage <likes>"))


async def setpackage_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: add or update a package by its like amount."""
    global AUTO_LIKE_PACKAGES

    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            format_bold("❌ Admin access only."),
        )
        return

    if len(context.args) != 2 or not all(x.isdigit() for x in context.args):
        await update.message.reply_text(
            format_bold(
                "❌ Format:\n/setpackage <likes> <price>\n\n"
                "Example:\n/setpackage 500 25"
            ),
        )
        return

    likes, price = map(int, context.args)
    if likes <= 0 or price < 0:
        await update.message.reply_text(
            format_bold("❌ Likes অবশ্যই 0-এর বেশি এবং price 0 বা তার বেশি হতে হবে।"),
        )
        return

    AUTO_LIKE_PACKAGES = [(l, p) for l, p in AUTO_LIKE_PACKAGES if l != likes]
    AUTO_LIKE_PACKAGES.append((likes, price))
    AUTO_LIKE_PACKAGES = save_packages(AUTO_LIKE_PACKAGES)

    await update.message.reply_text(
        format_bold(
            f"✅ Package saved!\n\n"
            f"❤️ Likes: {likes:,}\n"
            f"💳 Price: {price} TK\n\n"
            f"Restart করলেও এই package থাকবে।"
        ),
    )


async def editpackage_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: edit a package by its visible package number."""
    global AUTO_LIKE_PACKAGES

    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            format_bold("❌ Admin access only."),
        )
        return

    if len(context.args) != 3 or not all(x.isdigit() for x in context.args):
        await update.message.reply_text(
            format_bold(
                "❌ Format:\n/editpackage <number> <likes> <price>\n\n"
                "Example:\n/editpackage 1 100 5\n\n"
                "বর্তমান number দেখতে /packages ব্যবহার করুন।"
            ),
        )
        return

    index, likes, price = map(int, context.args)
    if index < 1 or index > len(AUTO_LIKE_PACKAGES) or likes <= 0 or price < 0:
        await update.message.reply_text(
            format_bold("❌ Package number/likes/price সঠিক নয়। /packages দিয়ে list দেখুন।"),
        )
        return

    old_likes, _old_price = AUTO_LIKE_PACKAGES[index - 1]
    # Prevent duplicate like amounts after editing.
    if any(i != index - 1 and p[0] == likes for i, p in enumerate(AUTO_LIKE_PACKAGES)):
        await update.message.reply_text(
            format_bold("❌ এই Likes amount-এর package আগে থেকেই আছে।"),
        )
        return

    AUTO_LIKE_PACKAGES[index - 1] = (likes, price)
    AUTO_LIKE_PACKAGES = save_packages(AUTO_LIKE_PACKAGES)

    await update.message.reply_text(
        format_bold(
            f"✅ Package edited successfully!\n\n"
            f"📌 Package No: {index}\n"
            f"🔄 Old Likes: {old_likes:,}\n"
            f"❤️ New Likes: {likes:,}\n"
            f"💳 New Price: {price} TK\n\n"
            f"User menu-তেও নতুন value দেখাবে।"
        ),
    )


async def removepackage_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: remove a package and persist the change."""
    global AUTO_LIKE_PACKAGES

    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            format_bold("❌ Admin access only."),
        )
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(
            format_bold("Format: /removepackage <likes>"),
        )
        return

    likes = int(context.args[0])
    before = len(AUTO_LIKE_PACKAGES)
    AUTO_LIKE_PACKAGES = [(l, p) for l, p in AUTO_LIKE_PACKAGES if l != likes]

    if len(AUTO_LIKE_PACKAGES) == before:
        msg = "❌ Package not found."
    else:
        AUTO_LIKE_PACKAGES = save_packages(AUTO_LIKE_PACKAGES)
        msg = f"✅ {likes:,} Likes package removed and saved."

    await update.message.reply_text(
        format_bold(msg),
    )


async def orderhistory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    admin_user = is_admin(user.id)
    await update.message.reply_text(
        "📜 ORDER HISTORY — SELECT A PAGE",
        reply_markup=build_order_history_keyboard(admin_user, None, user.id),
    )


async def order_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reliable Order History navigation.

    The first screen contains only Running / Complete / Back.  Selecting a
    status loads the orders after the click.  Rendering failures fall back to
    plain text so a bad editable template can never make the button appear dead.
    """
    query = update.callback_query
    if await _is_duplicate_user_action(context, f"callback:{query.data}"):
        try:
            await query.answer()
        except Exception:
            pass
        return
    if not query:
        return
    user = query.from_user
    data = (query.data or "").strip()

    try:
        # Always acknowledge the callback immediately.
        await query.answer()
    except Exception:
        pass

    try:
        selected = data.split(":", 1)[1] if ":" in data else ""
        if selected == "back":
            # Back closes Order History and returns to the main menu.
            context.user_data.pop("order_history_page", None)
            try:
                await query.edit_message_text("ORDER HISTORY CLOSED")
            except Exception:
                pass
            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text="Main menu",
                    reply_markup=build_main_menu(),
                )
            except Exception:
                pass
            return

        if selected not in ("running", "complete"):
            try:
                await query.answer("Invalid option. আবার চেষ্টা করুন।", show_alert=True)
            except Exception:
                pass
            return

        context.user_data["order_history_page"] = selected
        admin_user = is_admin(user.id)

        # Build the order list independently of the editable template.
        order_body = order_history_text(
            user.id,
            limit=8,
            status_filter=selected,
            all_users=admin_user,
            apply_template=False,
        )
        title = f"📜 {BOT_NAME} — {_order_history_status_label(selected)}"
        plain_text = f"{title}\n\n{order_body}"
        markup = build_order_history_keyboard(admin_user, selected, user.id)

        # Try the editable Order History template, but NEVER let it break the UI.
        try:
            rendered, entities, custom = render_content_entities(
                "order_history",
                bot_name=BOT_NAME,
                status_label=_order_history_status_label(selected),
                orders=order_body,
            )
            if custom and entities:
                await query.edit_message_text(
                    rendered,
                    entities=entities,
                    reply_markup=markup,
                )
            else:
                await query.edit_message_text(
                    format_bold(rendered),
                    reply_markup=markup,
                )
        except Exception:
            logger.exception("Editable Order History rendering failed; using plain fallback")
            try:
                await query.edit_message_text(
                    format_bold(plain_text),
                    reply_markup=markup,
                )
            except Exception:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=plain_text,
                    reply_markup=markup,
                )
    except Exception:
        logger.exception("Order History callback failed: %s", data)
        try:
            await query.answer("Order History load করতে সমস্যা হয়েছে। আবার চাপুন।", show_alert=True)
        except Exception:
            pass


async def cancel_order_ui_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    query=update.callback_query
    if await _is_duplicate_user_action(context, f"callback:{query.data}"):
        try:
            await query.answer()
        except Exception:
            pass
        return

    user=query.from_user
    data=query.data or ""
    if not data.startswith("cancel_order_ui:"):
        return
    parts=data.split(":")
    order_id=parts[1] if len(parts) > 1 else ""
    selected=parts[2] if len(parts) > 2 and parts[2] in ("running","complete","all") else context.user_data.get("order_history_page","all")
    await query.answer()

    order=get_order(order_id)
    if not order:
        await query.answer("Order পাওয়া যায়নি।",show_alert=True); return
    if not is_admin(user.id) and str(order.get("user_id"))!=str(user.id):
        await query.answer("Permission নেই।",show_alert=True); return
    if order.get("status") not in ("active","payment_pending"):
        await query.answer("Order already closed.",show_alert=True); return

    price=int(order.get("price",0) or 0)
    uid=str(order.get("uid",""))
    auto=load_data("auto_like")
    if isinstance(auto,dict) and isinstance(auto.get(uid),dict) and str(auto[uid].get("order_id"))==str(order_id):
        auto.pop(uid,None)
        save_data("auto_like",auto)
    if not order.get("refunded"):
        add_balance(order.get("user_id"),price)
    update_order(order_id,status="cancelled",refunded=True,cancelled_at=bd_timestamp(),
                 last_note="Cancelled by user/admin; charged points refunded.")

    context.user_data["order_history_page"] = selected
    admin_user=is_admin(user.id)
    if selected not in ("running","complete"):
        selected="running"
    order_body=order_history_text(user.id,limit=8,status_filter=selected,all_users=admin_user,apply_template=False)
    markup = build_order_history_keyboard(admin_user,selected,user.id)
    plain_text = f"📜 {BOT_NAME} — {_order_history_status_label(selected)}\n\n{order_body}"
    try:
        rendered, entities, custom=render_content_entities("order_history",bot_name=BOT_NAME,
            status_label=_order_history_status_label(selected),orders=order_body)
        if custom and entities:
            await query.edit_message_text(rendered, entities=entities, reply_markup=markup)
        else:
            await query.edit_message_text(format_bold(rendered), reply_markup=markup)
    except Exception:
        logger.exception("Cancel UI order-history render failed; using plain fallback")
        try:
            await query.edit_message_text(format_bold(plain_text), reply_markup=markup)
        except Exception:
            await context.bot.send_message(chat_id=user.id, text=plain_text, reply_markup=markup)
    try:
        await context.bot.send_message(
            chat_id=int(order.get("user_id")),
            text=format_bold(
                f"🛑 ORDER CANCELLED\n\n🆔 Order ID: {order_id}\n🎮 UID: {uid}\n"
                f"💳 Refunded: {price} Points\n💰 Current Balance: {get_balance(order.get('user_id'))} Points"
            )
        )
    except Exception:
        logger.exception("Cancellation notification failed")

async def redeem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_bold("🎟️ REDEEM CODE\n\n🚧 COMING SOON!\n\nRedeem Code System খুব শীঘ্রই চালু হবে।"))


async def orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    orders=get_orders(limit=50)
    if not orders:
        await update.message.reply_text(f"📜 {BOT_NAME} — ALL ORDERS\n\n❌ কোনো order নেই।"); return
    users=load_data("users")
    lines=[f"📜 {BOT_NAME} — ALL ORDERS","━━━━━━━━━━━━━━━━━━"]
    buttons=[]
    status_map={"active":"🟢 ACTIVE","completed":"✅ DONE","cancelled":"🛑 CANCELLED","payment_pending":"💳 PENDING"}
    for o in orders:
        req=int(o.get("likes_requested",0)); sent=int(o.get("likes_sent",0)); left=max(0,req-sent)
        info=users.get(str(o.get("user_id")),{}) if isinstance(users,dict) else {}
        name=info.get("first_name","Unknown") if isinstance(info,dict) else "Unknown"
        uname=f"@{info.get('username')}" if isinstance(info,dict) and info.get("username") else "No username"
        lines.append(
            f"🆔 {o.get('order_id','N/A')} • {status_map.get(o.get('status'),str(o.get('status','')).upper())}\n"
            f"👤 {name} | {uname} | ID: {o.get('user_id','N/A')}\n"
            f"🎮 UID: {o.get('uid','N/A')} | 📦 {req:,} Likes\n"
            f"❤️ Sent: {sent:,} | ⏳ Left: {left:,} | 💎 Cost: {int(o.get('price',0))} P\n"
            f"🗓 {o.get('created_at','N/A')} | ⏰ Last: {o.get('last_run_at') or 'Not started'}\n"
            f"ℹ️ {o.get('last_note') or '—'}\n━━━━━━━━━━━━━━━━━━"
        )
        if o.get("status") in ("active","payment_pending"):
            buttons.append([make_inline_button(f"🛑 Cancel {o.get('order_id')}",callback_data=f"admin_cancel_order:{o.get('order_id')}",style="danger")])
    await update.message.reply_text("\n".join(lines),reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)


async def admin_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await _is_duplicate_user_action(context, f"callback:{query.data}"):
        try:
            await query.answer()
        except Exception:
            pass
        return
    if not is_admin(query.from_user.id):
        await query.answer("Admin only.", show_alert=True)
        return
    data = query.data or ""
    if not data.startswith("admin_cancel_order:"):
        return
    order_id = data.split(":", 1)[1]
    o = get_order(order_id)
    if not o or o.get("status") not in ("active", "payment_pending"):
        await query.answer("Order already closed/not found.", show_alert=True)
        return
    price = int(o.get("price", 0) or 0)
    uid = str(o.get("uid"))
    update_order(order_id, status="cancelled", last_note="Cancelled by admin; charged points refunded.", completed_at=bd_timestamp())
    auto = load_data("auto_like")
    if isinstance(auto, dict) and uid in auto and auto[uid].get("order_id") == order_id:
        auto.pop(uid, None)
        save_data("auto_like", auto)
    if price > 0:
        add_balance(o.get("user_id"), price)
        try:
            await context.bot.send_message(
                chat_id=int(o.get("user_id")),
                text=format_bold(f"🛑 ORDER CANCELLED\n\n🆔 {order_id}\n🎮 UID: {uid}\n💰 {price} Points refund করা হয়েছে."),
            )
        except Exception:
            logger.exception("Could not notify refunded user %s", o.get("user_id"))
    await query.answer("Cancelled + refund done.")
    await query.edit_message_text(format_bold(f"🛑 Order {order_id} cancelled.\n💰 {price} Points refunded."))


async def order_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only."))
        return
    if len(context.args) != 1:
        await update.message.reply_text(format_bold("Format: /order <order_id>"))
        return
    o = get_order(context.args[0])
    if not o:
        await update.message.reply_text(format_bold("❌ Order পাওয়া যায়নি।"))
        return
    requested = int(o.get("likes_requested", 0)); sent = int(o.get("likes_sent", 0)); remaining = max(0, requested-sent)
    await update.message.reply_text(format_bold(
        f"📦 ORDER DETAILS\n━━━━━━━━━━━━━━━━━━\n🆔 {o.get('order_id')}\n👤 User: {o.get('user_id')}\n🎮 UID: {o.get('uid')}\n📦 Ordered: {requested:,}\n❤️ Sent: {sent:,}\n⏳ Remaining: {remaining:,}\n📅 ETA: {format_eta(remaining)}\n💳 Price: {o.get('price', 0)} Points\n📌 Status: {o.get('status')}\n🗓️ Created: {o.get('created_at')}\n⏰ Last Run: {o.get('last_run_at') or 'N/A'}\nℹ️ {o.get('last_note') or 'N/A'}"
    ))


async def cancelorder_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only."))
        return
    if len(context.args) != 1:
        await update.message.reply_text(format_bold("Format: /cancelorder <order_id>"))
        return
    order_id = context.args[0]
    o = get_order(order_id)
    if not o:
        await update.message.reply_text(format_bold("❌ Order পাওয়া যায়নি।"))
        return
    if o.get("status") not in ("active", "payment_pending"):
        await update.message.reply_text(format_bold(f"⚠️ Order {order_id} already closed."))
        return
    price = int(o.get("price", 0) or 0)
    update_order(order_id, status="cancelled", last_note="Cancelled by admin; charged points refunded.", completed_at=bd_timestamp())
    auto = load_data("auto_like"); uid = str(o.get("uid"))
    if isinstance(auto, dict) and uid in auto and auto[uid].get("order_id") == order_id:
        auto.pop(uid, None); save_data("auto_like", auto)
    if price > 0:
        add_balance(o.get("user_id"), price)
    await update.message.reply_text(format_bold(f"🛑 Order {order_id} cancelled.\n💰 {price} Points refunded."))


async def setdailyestimate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_LIKE_DAILY_ESTIMATE
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only.")); return
    if len(context.args) != 1 or not context.args[0].isdigit() or int(context.args[0]) <= 0:
        await update.message.reply_text(format_bold("Format: /setdailyestimate <likes>\nExample: /setdailyestimate 210")); return
    AUTO_LIKE_DAILY_ESTIMATE = int(context.args[0])
    settings = load_data("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings["auto_like_daily_estimate"] = AUTO_LIKE_DAILY_ESTIMATE
    save_data("settings", settings)
    await update.message.reply_text(format_bold(f"✅ Daily estimate set to {AUTO_LIKE_DAILY_ESTIMATE} likes/day.\nনতুন ও existing order-এর ETA এতে হিসাব হবে।"))


async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(format_bold(
            f"💰 Your Balance: {get_balance(user.id)} Points"
        ))
        return
    await update.message.reply_text(format_bold(
        "💰 BALANCE ADMIN COMMANDS\n\n"
        "/addpoints <user_id> <points> — User-কে points দিন\n"
        "/setpoints <user_id> <points> — User-এর balance set করুন"
    ))


async def addpoints_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ You are not authorized!"))
        return
    if len(context.args) != 2 or not context.args[0].isdigit() or not context.args[1].lstrip("-").isdigit():
        await update.message.reply_text(format_bold(
            "❌ Format:\n/addpoints <telegram_user_id> <points>\nExample: /addpoints 123456789 50"
        ))
        return
    target, amount = context.args[0], int(context.args[1])
    new_balance = add_balance(target, amount)
    if amount > 0:
        record_money_added(target, amount)
    await update.message.reply_text(format_bold(
        f"✅ Points updated!\n\n👤 User: {target}\n➕ Change: {amount}\n💰 New Balance: {new_balance}"
    ))


async def setpoints_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ You are not authorized!"))
        return
    if len(context.args) != 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
        await update.message.reply_text(format_bold(
            "❌ Format:\n/setpoints <telegram_user_id> <points>"
        ))
        return
    target, amount = context.args[0], int(context.args[1])
    old_balance = get_balance(target)
    new_balance = set_balance(target, amount)
    if new_balance > old_balance:
        record_money_added(target, new_balance - old_balance)
    await update.message.reply_text(format_bold(
        f"✅ Balance set successfully!\n\n👤 User: {target}\n💰 New Balance: {new_balance}"
    ))


# ═══════════════════════════════════════════════════════════════════
# FREE FIRE API CLIENT - UPDATED FOR NO KEY
# ═══════════════════════════════════════════════════════════════════

API_SESSION = None
API_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=25)
API_RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}


def _api_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _normalize_api_result(data, http_status=200):
    """Normalize common API response variants without changing the API contract."""
    if not isinstance(data, dict):
        return {"status": 0, "error": "Invalid API JSON response.", "retryable": False}

    result = dict(data)
    result["status"] = _api_int(result.get("status", 0), 0)

    # Accept the API's normal field plus harmless aliases used by some versions.
    likes = result.get("LikesGivenByAPI")
    if likes is None:
        for key in ("likes_given", "likesGiven", "likes", "LikesGiven", "likes_given_by_api"):
            if key in result:
                likes = result[key]
                break
    result["LikesGivenByAPI"] = max(0, _api_int(likes, 0))
    result["retryable"] = False
    result["http_status"] = http_status
    return result


async def _get_api_session():
    global API_SESSION
    if API_SESSION is None or API_SESSION.closed:
        connector = aiohttp.TCPConnector(limit=20, limit_per_host=8, ttl_dns_cache=300, enable_cleanup_closed=True)
        API_SESSION = aiohttp.ClientSession(connector=connector, timeout=API_REQUEST_TIMEOUT)
    return API_SESSION


async def send_like_api(uid, region, retries=2, base_url=None):
    """Call the Like API reliably.

    Retries are ONLY used for transient transport/server failures (timeouts,
    connection errors, 408/429/5xx). A valid API response, including a zero-like
    or account-limit response, is returned immediately so the bot never tries to
    bypass the API's own account/rate limits.
    """
    url = (base_url or API_BASE).rstrip("/")
    params = {"uid": str(uid), "server_name": str(region).upper()}
    session = await _get_api_session()

    for attempt in range(max(0, int(retries)) + 1):
        try:
            async with session.get(url, params=params) as resp:
                raw_text = await resp.text()
                if resp.status != 200:
                    retryable = resp.status in API_RETRYABLE_HTTP
                    logger.warning("Like API HTTP %s for UID %s (attempt %s/%s)", resp.status, uid, attempt + 1, retries + 1)
                    if retryable and attempt < retries:
                        retry_after = _api_int(resp.headers.get("Retry-After"), 0)
                        delay = min(8, max(1, retry_after) if retry_after else 2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
                    return {"status": 0, "error": f"API HTTP {resp.status}", "retryable": retryable, "http_status": resp.status}

                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError:
                    logger.warning("Like API returned non-JSON for UID %s", uid)
                    if attempt < retries:
                        await asyncio.sleep(min(8, 2 ** attempt))
                        continue
                    return {"status": 0, "error": "Invalid API JSON response.", "retryable": True, "http_status": resp.status}

                return _normalize_api_result(data, resp.status)

        except (asyncio.TimeoutError, aiohttp.ClientConnectionError, aiohttp.ClientPayloadError) as exc:
            logger.warning("Like API connection error for UID %s (attempt %s/%s): %s", uid, attempt + 1, retries + 1, exc)
            if attempt < retries:
                await asyncio.sleep(min(8, 2 ** attempt))
                continue
            return {"status": 0, "error": "API connection temporarily unavailable.", "retryable": True}
        except Exception as exc:
            logger.exception("Unexpected Like API error for UID %s: %s", uid, exc)
            return {"status": 0, "error": "Unexpected API client error.", "retryable": False}

    return {"status": 0, "error": "API request failed.", "retryable": True}


# ═══════════════════════════════════════════════════════════════════
# CHANNEL VERIFICATION
# ═══════════════════════════════════════════════════════════════════

async def check_channel_membership(user_id, context):
    """Check if user has joined all required channels"""
    channels = get_channels()
    if not channels:
        channels = {ch["name"]: {"link": ch["link"]} for ch in REQUIRED_CHANNELS}

    not_joined = []
    for name, info in channels.items():
        try:
            link = info.get("link", "")
            if "/" in link:
                parts = link.rstrip("/").split("/")
                username = parts[-1]
                if username.startswith("+"):
                    continue
                member = await context.bot.get_chat_member(f"@{username}", user_id)
                # Telegram can return member statuses: creator, administrator, member,
                # restricted, left, kicked. Restricted users are joined when is_member=True.
                if member.status in ["left", "kicked"] or (
                    member.status == "restricted" and not getattr(member, "is_member", False)
                ):
                    not_joined.append({"name": name, "link": link})
            else:
                not_joined.append({"name": name, "link": link})
        except Exception as e:
            logger.error(f"Channel check error for {name}: {e}")
            not_joined.append({"name": name, "link": info.get("link", "")})

    return not_joined


def build_verify_keyboard():
    """Build verification keyboard with channel buttons"""
    channels = get_channels()
    if not channels:
        channels = {ch["name"]: {"link": ch["link"]} for ch in REQUIRED_CHANNELS}

    buttons = []
    for name, info in channels.items():
        buttons.append([make_inline_button(f"📢 Join {name}", url=info["link"], style="success")])
    buttons.append([make_inline_button("✅ Verify", callback_data="verify_channels", style="success")])
    return InlineKeyboardMarkup(buttons)


# ═══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def _send_fresh_main_menu(bot, chat_id, text, **kwargs):
    """Force Telegram clients to discard the previous reply keyboard first.

    Telegram clients can retain a previously displayed ReplyKeyboardMarkup.
    Removing it in one message and immediately sending the new keyboard in the
    next message makes /start reliably apply changed custom-emoji button IDs.
    """
    try:
        await bot.send_message(chat_id=chat_id, text="⁣", reply_markup=ReplyKeyboardRemove())
    except Exception:
        logger.exception("Could not remove old reply keyboard during refresh")
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh the current bot UI with /start.

    /start always sends a brand-new current welcome/menu message. It does not
    delete or reset saved user data, balance, history, claims, etc.
    """
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or chat is None:
        return

    # /start is also the documented way to cancel the content-editor state.
    if user:
        try:
            context.user_data.pop("editing_content", None)
        except Exception:
            pass

        # Keep user data intact; only make sure the user record exists.
        try:
            add_broadcast_user(user.id)
            ensure_user(user.id, user)
        except Exception:
            logger.exception("/start user data refresh failed")

    # Referral processing is kept compatible with the existing /start payload.
    if user and context.args:
        try:
            process_referral(user.id, context.args[0])
        except Exception:
            logger.exception("Referral processing failed for user %s", user.id)

    # Nothing below this point should be able to escape into the global error
    # handler. Previously get_balance()/build_main_menu() ran outside the
    # protected send block, so an unexpected local data/keyboard error made
    # /start show the generic "temporary error" message instead of refreshing.
    try:
        username = f"@{user.username}" if user and user.username else "No username"
        current = now_bd()

        try:
            balance = get_balance(user.id) if user else 0
        except Exception:
            logger.exception("/start balance lookup failed")
            balance = 0

        values = dict(
            name=user.first_name if user else "Unknown",
            username=username,
            user_id=user.id if user else 0,
            date=current.strftime("%d-%m-%Y"),
            time=current.strftime("%I:%M %p"),
            day=current.strftime("%A"),
            balance=balance,
            bot_name=BOT_NAME,
        )

        # Private chat gets the CURRENT main menu every time /start is used.
        # is_persistent=False is intentional: Telegram clients are then asked
        # to replace the old reply keyboard with the newly generated one.
        # This makes changed custom-emoji IDs take effect after /start.
        # If a custom-icon/style keyboard is rejected by the installed PTB
        # build, fall back to a plain reply keyboard instead of failing /start.
        markup = None
        if chat.type == "private":
            try:
                # Build the reply keyboard fresh on EVERY /start. This reads the
                # current PREMIUM_BUTTON_EMOJIS mapping, so changed icon IDs are
                # included in the newly sent keyboard instead of reusing an old one.
                markup = build_main_menu()
            except Exception:
                logger.exception("/start main menu build failed; using plain keyboard")
                try:
                    m = get_menu_labels()
                    markup = ReplyKeyboardMarkup(
                        [
                            [KeyboardButton(m["balance"]), KeyboardButton(m["add_money"])],
                            [KeyboardButton(m["order_history"]), KeyboardButton(m["auto_package"])],
                            [KeyboardButton(m["bonus_220"]), KeyboardButton(m["daily_free"])],
                            [KeyboardButton(m["referral"])],
                            [KeyboardButton(m["customer_care"])],
                            [KeyboardButton(m.get("tutorial", get_menu_label("tutorial")))],
                        ],
                        resize_keyboard=True,
                    )
                except Exception:
                    logger.exception("/start plain keyboard build failed")
                    markup = None

        try:
            raw, entities, custom = get_content_record("welcome")
            if custom and entities:
                text_to_send, rendered_entities, _ = render_content_entities("welcome", **values)
                text_to_send, rendered_entities, _ = add_premium_page_emoji(text_to_send, rendered_entities)
                try:
                    await _send_fresh_main_menu(
                        context.bot,
                        chat.id,
                        text_to_send,
                        entities=rendered_entities,
                        reply_markup=markup,
                    )
                    return
                except Exception:
                    logger.exception("/start custom-emoji welcome failed; using plain text")

            text = format_bold(render_content("welcome", **values))
            text, _, _ = add_premium_page_emoji(text, [])
        except Exception:
            logger.exception("/start welcome content failed")
            text = "💎 AS LIKE BOT\\n\\nনিচের menu থেকে option select করুন।"

        try:
            if chat.type == "private" and markup is not None:
                await _send_fresh_main_menu(
                    context.bot, chat.id, text, reply_markup=markup
                )
            else:
                await context.bot.send_message(
                    chat_id=chat.id, text=text, reply_markup=markup
                )
            return
        except Exception:
            logger.exception("/start final send failed")

        # Last-resort send: no custom entities and no keyboard. This prevents
        # an editable welcome/menu problem from making /start look broken.
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text="💎 AS LIKE BOT\\n\\nনিচের menu থেকে option select করুন।",
                reply_markup=markup,
            )
        except Exception:
            logger.exception("/start emergency send failed")
    except Exception:
        logger.exception("/start unexpected error")
        # Do not call the global error handler's "temporary error" message
        # again here; try one minimal reply so /start itself remains usable.
        try:
            await message.reply_text(
                "💎 AS LIKE BOT\\n\\nMenu refresh করতে নিচের buttons ব্যবহার করুন।",
                reply_markup=markup if chat.type == "private" else None,
            )
        except Exception:
            logger.exception("/start minimal reply failed")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command using editable user/admin templates."""
    user = update.effective_user
    add_broadcast_user(user.id)
    emoji = get_user_emoji(user.id)
    key = "help_admin" if is_admin(user.id) else "help_user"
    vip_button = None
    if not is_admin(user.id):
        vip_button = InlineKeyboardMarkup([
            [make_inline_button("💎 VIP নিতে Admin-এর সাথে Contact করুন", url="https://t.me/As_owner99", style="primary")]
        ])
    await reply_editable_content(update.message, key, reply_markup=vip_button, emoji=emoji)


async def like_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Free /like works only in the authorized free-like group.
    Non-admin private /like requests are redirected to the free-like group."""
    user = update.effective_user
    chat = update.effective_chat
    add_broadcast_user(user.id)
    ensure_user(user.id, user)
    emoji = get_user_emoji(user.id)

    if chat.type == "private" and not is_admin(user.id):
        await update.message.reply_text(
            format_bold(
                "📢 FREE LIKE GROUP\n\n"
                "এখানে সরাসরি /like ব্যবহার করা যাবে না।\n"
                "Free Like Group-এ গিয়ে /like <UID> দিন।"
            ),
            reply_markup=InlineKeyboardMarkup([
                [make_inline_button("📢 OPEN FREE LIKE GROUP", url=DAILY_FREE_LIKE_URL, style="primary")]
            ]),
        )
        return

    if not is_global_enabled() and not is_admin(user.id):
        await update.message.reply_text(
            format_bold("🛑 BOT IS CURRENTLY OFF\n\nAdmin আবার ON না করা পর্যন্ত Like নেওয়া যাবে না."),
        )
        return

    group_admin = False
    if chat.type in ["group", "supergroup"]:
        if not is_group_allowed(chat.id):
            await update.message.reply_text(
                format_bold(f"{emoji} এই group authorized নয়। Admin-এর কাছে group allow করান."),
            )
            return
        if not is_group_enabled(chat.id) and not is_admin(user.id):
            await update.message.reply_text(
                format_bold("🛑 BOT IS OFF IN THIS GROUP!\n\nAdmin /on দিলে আবার চালু হবে."),
            )
            return
        group_admin = await is_group_admin_member(chat.id, user.id, context)
    else:
        group_admin = is_admin(user.id)

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(
            format_bold(
                f"{emoji} সঠিকভাবে command দিন\n\n"
                "/like <UID>\nExample: /like 123456789\n\n"
                "⚠️ শুধু সংখ্যার Free Fire UID দিন."
            ),
        )
        return

    uid = context.args[0].strip()
    region = FIXED_REGION
    auto_list = get_auto_like_list()
    targets = load_data("target_like")

    if uid in auto_list and not is_admin(user.id):
        await update.message.reply_text(
            format_bold(f"❌ এই UID-তে active Auto-Like আছে.\n📅 Remaining: {auto_list[uid].get('days_left', 0)} Days\n\n👑 শুধু Admin এই UID-তে manual /like দিতে পারবেন."),
        )
        return

    if uid in targets and not is_admin(user.id):
        await update.message.reply_text(
            format_bold(
                f"❌ এই UID-তে active Target-Like আছে.\n"
                f"📈 Progress: {targets[uid].get('likes_sent', 0)}/{targets[uid].get('target_limit', 0)} Likes\n\n"
                "👑 শুধু Admin এই UID-তে manual /like দিতে পারবেন."
            ),
        )
        return

    not_joined = await check_channel_membership(user.id, context)
    if not_joined:
        await update.message.reply_text(
            format_bold("📢 আগে Required Channel/Group-এ Join করুন, তারপর Verify করুন."),
            reply_markup=build_verify_keyboard(),
        )
        return

    # Ordinary group members: exactly one successful /like per BD day.
    if chat.type in ["group", "supergroup"] and not group_admin and not is_admin(user.id) and not is_vip(user.id):
        if not can_use_like(user.id):
            await update.message.reply_text(
                format_bold(
                    "❌ আপনি আজকের Free Like ইতিমধ্যে নিয়েছেন।\n\n"
                    "⏰ ভোর ৪:০০টায় আবার ১টি Like request নিতে পারবেন."
                ),
            )
            return

    # Keep the existing API-side per-UID safety cap.
    free_limit = get_free_limit()
    if free_limit is not None and not is_unlimited(uid) and not is_admin(user.id) and not is_vip(user.id) and not group_admin:
        target_stats = get_like_stats(uid)
        if int(target_stats.get("today_likes", 0)) >= free_limit:
            await update.message.reply_text(
                format_bold(
                    f"❌ এই UID-এর API daily limit শেষ।\n\n"
                    f"🎮 UID: {uid}\n❤️ আজকে পাওয়া: {target_stats.get('today_likes', 0)} Likes\n"
                    f"🔄 ভোর ৪:০০টায় reset হবে."
                ),
            )
            return

    msg = await update.message.reply_text(
        format_bold(f"{emoji} আপনার Like request process হচ্ছে...\n\n🎮 UID: {uid}\n⏳ একটু অপেক্ষা করুন..."),
    )
    try:
        # Only group /like requests use the dedicated free-like API.
        # Admin/private and all paid/auto-like flows keep using API_BASE.
        request_api = FREE_API_BASE if chat.type in ["group", "supergroup"] else API_BASE
        result = await send_like_api(uid, region, retries=2, base_url=request_api)
    except Exception:
        logger.exception("Free Like API request failed for UID %s", uid)
        result = {"status": 0, "error": "temporary", "retryable": True}

    if result.get("error"):
        reason = classify_api_result(result)
        if reason == "uid":
            error_text = f"⚠️ UID ERROR\n\n🎮 UID: {uid}\n❌ এই UID-তে Like দেওয়া যায়নি। সঠিক Free Fire UID দিন."
        elif reason == "region":
            error_text = f"⚠️ BD SERVER REQUIRED\n\n🎮 UID: {uid}\n❌ শুধু Bangladesh Server-এর UID দিন."
        else:
            error_text = (
                f"⚠️ LIKE SERVICE TEMPORARILY UNAVAILABLE\n\n🎮 UID: {uid}\n"
                "❌ Like service এখন response দেয়নি।\nℹ️ সফল না হওয়ায় আজকের user limit কাটা হয়নি."
            )
        await msg.edit_text(format_bold(error_text))
        return

    likes_given = max(0, int(result.get("LikesGivenByAPI", 0) or 0))
    if result.get("status") in [1, 2] and likes_given > 0:
        success_text = render_content(
            "like_success",
            player_name=result.get('PlayerNickname', 'Unknown'),
            before=result.get('LikesbeforeCommand', 'N/A'),
            after=result.get('LikesafterCommand', 'N/A'),
            likes_given=likes_given,
            uid=uid,
            time=bd_timestamp(),
        )
        if chat.type in ["group", "supergroup"] and not group_admin and not is_admin(user.id) and not is_vip(user.id):
            mark_like_used(user.id, uid)
        record_like_stats(uid, likes_given, source="manual")
        record_user_like_usage(user.id, likes_given)

        media_type, media_file_id = get_content_media("like_success")
        if media_type and media_file_id:
            try:
                raw_caption, caption_entities, custom = get_content_record("like_success")
                try:
                    caption = raw_caption.format(
                        player_name=result.get('PlayerNickname', 'Unknown'),
                        before=result.get('LikesbeforeCommand', 'N/A'),
                        after=result.get('LikesafterCommand', 'N/A'),
                        likes_given=likes_given,
                        uid=uid,
                        time=bd_timestamp(),
                    )
                except Exception:
                    caption = raw_caption
                kwargs = {}
                if custom and caption == raw_caption and caption_entities:
                    caption, caption_entities, _ = add_premium_page_emoji(caption, caption_entities)
                    kwargs["caption_entities"] = caption_entities
                else:
                    caption, caption_entities, _ = add_premium_page_emoji(caption, [])
                    kwargs["caption_entities"] = caption_entities
                await msg.delete()
                if media_type == "photo":
                    await context.bot.send_photo(chat_id=chat.id, photo=media_file_id, caption=caption or None, **kwargs)
                else:
                    await context.bot.send_video(chat_id=chat.id, video=media_file_id, caption=caption or None, **kwargs)
            except Exception:
                logger.exception("Like success media delivery failed; falling back to text")
                await msg.edit_text(format_bold(success_text))
        else:
            success_text, success_entities, _ = add_premium_page_emoji(success_text, [])
            try:
                await msg.edit_text(success_text, entities=success_entities)
            except Exception:
                await msg.edit_text(format_bold(success_text))
        return

    reason = classify_api_result(result)
    if reason == "uid":
        error_text = f"⚠️ UID ERROR\n\n🎮 UID: {uid}\n❌ এই UID-তে Like দেওয়া যায়নি। সঠিক UID দিন."
    elif reason == "region":
        error_text = f"⚠️ BD SERVER REQUIRED\n\n🎮 UID: {uid}\n❌ শুধু Bangladesh Server-এর UID দিন."
    elif result.get("retryable"):
        error_text = f"⚠️ LIKE SERVICE BUSY\n\n🎮 UID: {uid}\n❌ সাময়িক সমস্যা হয়েছে। পরে আবার চেষ্টা করুন."
    else:
        error_text = f"⚠️ LIKE NOT AVAILABLE\n\n🎮 UID: {uid}\n❌ এই মুহূর্তে Like দেওয়া যায়নি."
    await msg.edit_text(format_bold(error_text))


def has_claimed_first_220(user_id):
    users = load_data("users")
    return bool(isinstance(users, dict) and users.get(str(user_id), {}).get("first_220_claimed", False))


def claim_first_220(user_id):
    users = load_data("users")
    if not isinstance(users, dict):
        users = {}
    uid = str(user_id)
    info = users.get(uid)
    if not isinstance(info, dict):
        return False
    if bool(info.get("first_220_claimed", False)):
        return False
    info["first_220_claimed"] = True
    info["first_220_claimed_at"] = bd_timestamp()
    users[uid] = info
    return save_data("users", users)


async def first_220_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await _is_duplicate_user_action(context, f"callback:{query.data}"):
        try:
            await query.answer()
        except Exception:
            pass
        return
    await query.answer()
    user = query.from_user
    ensure_user(user.id, user)
    data = query.data or ""

    if not is_global_enabled() and not is_admin(user.id):
        await query.answer("Bot is currently OFF.", show_alert=True)
        return

    if data == "bonus220_cancel":
        context.user_data.pop("pending_first_220", None)
        await query.edit_message_text(format_bold("❌ 200 Like cancelled.\n\nMenu থেকে আবার 200 LIKE চাপতে পারবেন।"))
        return

    if data != "bonus220_confirm":
        return

    if has_claimed_first_220(user.id):
        context.user_data.pop("pending_first_220", None)
        await query.edit_message_text(format_bold("❌ আপনার one-time 200 Like ইতিমধ্যে ব্যবহার করা হয়েছে."))
        return

    balance = get_balance(user.id)
    if balance < 5:
        await query.edit_message_text(
            format_bold(f"❌ পর্যাপ্ত Balance নেই!\n\n💳 200 Like-এর Price: 5 Points\n💰 আপনার Balance: {balance} Points\n\nআগে Balance Add Money করুন।"),
            reply_markup=build_admin_contact_keyboard(),
        )
        return

    context.user_data["pending_first_220"] = {"confirmed_at": bd_timestamp()}
    await query.edit_message_text(
        format_bold("✅ 200 LIKE CONFIRMED\n━━━━━━━━━━━━━━━━━━\n🎮 এখন আপনার Free Fire UID পাঠান।\nউদাহরণ: 123456789\n\n💳 5 Points charge হবে।\n⚡ এই Telegram ID দিয়ে শুধু একবার নেওয়া যাবে।\n⚠️ শুধু BD Server UID ব্যবহার করুন."),
        reply_markup=InlineKeyboardMarkup([[make_inline_button("❌ CANCEL", callback_data="bonus220_cancel", style="danger")]]),
    )


async def process_first_220_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_first_220")
    if not pending:
        return False

    user = update.effective_user
    uid = (update.message.text or "").strip()
    if not uid.isdigit():
        await update.message.reply_text(format_bold("❌ সঠিক Free Fire UID দিন।\n\nশুধু সংখ্যা দিন।"))
        return True

    if has_claimed_first_220(user.id):
        context.user_data.pop("pending_first_220", None)
        await update.message.reply_text(format_bold("❌ আপনার one-time 200 Like ইতিমধ্যে ব্যবহার করা হয়েছে."))
        return True

    not_joined = await check_channel_membership(user.id, context)
    if not_joined:
        await update.message.reply_text(
            format_bold("📢 আগে Required Channel/Group-এ Join করুন, তারপর Verify করে আবার UID দিন."),
            reply_markup=build_verify_keyboard(),
        )
        return True

    balance = get_balance(user.id)
    if balance < 5:
        context.user_data.pop("pending_first_220", None)
        await update.message.reply_text(format_bold("❌ Balance কম। 200 Like নিতে 5 Points লাগবে."), reply_markup=build_admin_contact_keyboard())
        return True

    # One Telegram ID gets one paid 200-like attempt. Consume and charge before
    # the single API request so a zero/partial API response cannot be retried.
    if not claim_first_220(user.id):
        context.user_data.pop("pending_first_220", None)
        await update.message.reply_text(format_bold("❌ আপনার one-time 200 Like ইতিমধ্যে ব্যবহার করা হয়েছে."))
        return True
    add_balance(user.id, -5)
    context.user_data.pop("pending_first_220", None)

    msg = await update.message.reply_text(format_bold(f"🚀 200 LIKE PROCESSING\n\n🎮 UID: {uid}\n⏳ Please wait..."))
    try:
        result = await send_like_api(uid, FIXED_REGION, retries=2)
    except Exception:
        logger.exception("200 Like API request failed for UID %s", uid)
        result = {"status": 0, "error": "temporary"}

    given = 0
    if isinstance(result, dict) and result.get("status") in [1, 2]:
        try:
            given = max(0, min(FIRST_220_LIKE, int(result.get("LikesGivenByAPI", 0) or 0)))
        except Exception:
            given = 0
    if given > 0:
        record_like_stats(uid, given, source="first_200")
        record_user_like_usage(user.id, given)
        player_name = result.get("PlayerNickname", "Unknown") if isinstance(result, dict) else "Unknown"
        await msg.edit_text(format_bold(
            "🎉 200 LIKE COMPLETED\n━━━━━━━━━━━━━━━━━━\n"
            f"👤 Name: {player_name}\n🆔 UID: {uid}\n❤️ Delivered: {given:,} Likes\n💳 Cost: 5 Points\n\n"
            "✅ এই Telegram ID-এর one-time 200 Like claim সম্পন্ন।\n"
            "ℹ️ API যত Like দিয়েছে সেটাই final; আবার retry করা যাবে না।"
        ))
    else:
        reason = classify_api_result(result if isinstance(result, dict) else {})
        if reason == "region":
            text = f"⚠️ BD SERVER REQUIRED\n\n🎮 UID: {uid}\n❌ এই UID-টি BD Server-এর নয়।\n🇧🇩 শুধু Bangladesh Server-এর UID দিন।\n\n💳 5 Points charge হয়েছে এবং one-time attempt শেষ হয়েছে।"
        else:
            text = (f"⚠️ 200 LIKE ATTEMPT COMPLETED\n\n🎮 UID: {uid}\n❤️ API কোনো Like দেয়নি।\n💳 Cost: 5 Points\n\n"
                    "ℹ️ One-time attempt শেষ; একই Telegram ID দিয়ে আবার নেওয়া যাবে না।")
        await msg.edit_text(format_bold(text))
    return True

async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verify button click"""
    query = update.callback_query
    if await _is_duplicate_user_action(context, f"callback:{query.data}"):
        try:
            await query.answer()
        except Exception:
            pass
        return
    await query.answer()
    user = query.from_user

    not_joined = await check_channel_membership(user.id, context)
    if not_joined:
        text, entities, custom = render_content_entities("verify_failed")
        await query.edit_message_text(
            text if custom and entities else format_bold(text),
            **({"entities": entities} if custom and entities else {"parse_mode": None}),
            reply_markup=build_verify_keyboard(),
        )
    else:
        text=render_content("verify_success")
        raw, entities, custom = get_content_record("verify_success")
        await query.edit_message_text(
            raw if custom and entities else format_bold(text),
            **({"entities": entities} if custom and entities else {"parse_mode": None})
        )


# ═══════════════════════════════════════════════════════════════════
async def _group_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, enabled: bool):
    """Private /on,/off controls whole bot; group /on,/off controls only that group."""
    chat = update.effective_chat
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(format_bold("❌ Bot ON/OFF করতে শুধু Bot Admin পারবে."))
        return

    if chat.type == "private":
        set_global_enabled(enabled)
        await reply_editable_content(update.message, "bot_on" if enabled else "bot_off")
        return

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(format_bold("❌ /on বা /off private admin chat অথবা group-এ ব্যবহার করুন."))
        return

    set_group_enabled(chat.id, enabled)
    await reply_editable_content(update.message, "bot_on" if enabled else "bot_off")


async def on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _group_toggle(update, context, True)


async def off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _group_toggle(update, context, False)


# ADMIN COMMANDS
# ═══════════════════════════════════════════════════════════════════

async def allow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /allow command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    if not context.args:
        text = (
            "❌ WRONG FORMAT!\n\n"
            "Correct: /allow <group_id>\n"
            "Example: /allow -1001234567890"
        )
        await update.message.reply_text(format_bold(text))
        return

    group_id = context.args[0]
    allow_group(group_id)
    text = (
        f"✅ GROUP ALLOWED!\n\n"
        f"Group ID: {group_id}\n"
        f"Bot will now work in this group!\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await update.message.reply_text(format_bold(text))


async def removegroup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /removegroup command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    if not context.args:
        text = "❌ Correct: /removegroup <group_id>"
        await update.message.reply_text(format_bold(text))
        return

    group_id = context.args[0]
    remove_group(group_id)
    text = (
        f"✅ Group {group_id} removed!\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await update.message.reply_text(format_bold(text))


async def addchannel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    if len(context.args) < 2:
        text = (
            "❌ WRONG FORMAT!\n\n"
            "Correct: /add <button_name> <channel_link>\n"
            "Example: /add MyChannel https://t.me/mychannel"
        )
        await update.message.reply_text(format_bold(text))
        return

    name = context.args[0]
    link = context.args[1]
    add_channel(name, link)
    text = (
        f"✅ CHANNEL ADDED!\n\n"
        f"Name: {name}\n"
        f"Link: {link}\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await update.message.reply_text(format_bold(text))


async def removechannel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /removechannel command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    if not context.args:
        text = "❌ Correct: /removechannel <name>"
        await update.message.reply_text(format_bold(text))
        return

    name = context.args[0]
    remove_channel(name)
    text = (
        f"✅ Channel {name} removed!\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await update.message.reply_text(format_bold(text))


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    if not context.args:
        text = "❌ Correct: /broadcast <message>"
        await update.message.reply_text(format_bold(text))
        return

    message = " ".join(context.args)
    users = get_broadcast_users()
    sent = 0
    failed = 0

    status_msg = await update.message.reply_text(
        format_bold("📢 Broadcasting..."),
    )

    for uid in users:
        try:
            text = (
                f"📢 MESSAGE FROM ADMIN 📢\n\n"
                f"{message}\n\n"
                f"⚡ AS LIKE BOT ⚡"
            )
            await context.bot.send_message(
                uid, format_bold(text)
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast failed for {uid}: {e}")

    text = (
        f"✅ BROADCAST COMPLETE!\n\n"
        f"Sent: {sent}\n"
        f"Failed: {failed}\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await status_msg.edit_text(format_bold(text))


async def vip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only: /vip <telegram_user_id> <days>"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(format_bold("❌ You are not authorized!"))
        return
    if len(context.args) < 2:
        await update.message.reply_text(format_bold("❌ সঠিক ফরম্যাট:\n/vip <telegram_user_id> <days>\n\nউদাহরণ:\n/vip 15985683337 30"))
        return
    target_user_id, days = context.args[0], context.args[1]
    if not target_user_id.isdigit() or not days.isdigit() or int(days) <= 0:
        await update.message.reply_text(format_bold("❌ User ID এবং Days অবশ্যই সঠিক সংখ্যা হতে হবে।"))
        return
    add_vip(target_user_id, int(days))
    await update.message.reply_text(format_bold(f"✅ VIP সফলভাবে চালু হয়েছে!\n\n👤 Telegram ID: {target_user_id}\n📅 মেয়াদ: {days} দিন\n💎 এই সময়ের মধ্যে দৈনিক লিমিট প্রযোজ্য হবে না।"))


async def vipremove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only: /vipremove <telegram_user_id>"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(format_bold("❌ You are not authorized!"))
        return
    if len(context.args) < 1:
        await update.message.reply_text(format_bold("❌ সঠিক ফরম্যাট:\n/vipremove <telegram_user_id>"))
        return
    target_user_id = context.args[0]
    if not target_user_id.isdigit():
        await update.message.reply_text(format_bold("❌ Telegram User ID অবশ্যই সংখ্যা হতে হবে।"))
        return
    remove_vip(target_user_id)
    await update.message.reply_text(format_bold(f"✅ VIP বাতিল করা হয়েছে।\n\n👤 Telegram ID: {target_user_id}"))


async def unlimit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unlimit command - fixed region"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    if len(context.args) < 1:
        text = (
            "❌ WRONG FORMAT!\n\n"
            "Correct: /unlimit <uid>\n"
            "Example: /unlimit 15985683337"
        )
        await update.message.reply_text(format_bold(text))
        return

    uid = context.args[0]
    if not uid.isdigit():
        await update.message.reply_text(
            format_bold("❌ UID must be a number!"),
        )
        return

    add_unlimited(uid, FIXED_REGION)
    text = (
        f"✅ UNLIMITED LIKE ADDED!\n\n"
        f"UID: {uid}\n"
        f"No daily limit for this UID!\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await update.message.reply_text(format_bold(text))


async def removeunlimit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /removeunlimit command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    if not context.args:
        text = "❌ Correct: /removeunlimit <uid>"
        await update.message.reply_text(format_bold(text))
        return

    uid = context.args[0]
    remove_unlimited(uid)
    text = (
        f"✅ UID {uid} removed from unlimited list!\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await update.message.reply_text(format_bold(text))


async def autolike_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /autolike command with format: /autolike <uid> <days>"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    if len(context.args) < 2:
        text = (
            "❌ WRONG FORMAT!\n\n"
            "Correct: /autolike <uid> <days>\n"
            "Example: /autolike 15985683337 30"
        )
        await update.message.reply_text(format_bold(text))
        return

    uid = context.args[0]
    days = context.args[1]

    if not uid.isdigit() or not days.isdigit() or int(days) <= 0:
        await update.message.reply_text(
            format_bold("❌ UID and Days must be valid numbers!"),
        )
        return

    add_auto_like(uid, FIXED_REGION, days)
    text = (
        f"✅ AUTO LIKE ADDED!\n\n"
        f"UID: {uid}\n"
        f"Duration: {days} Days\n"
        f"Daily like at {AUTO_LIKE_HOUR}:00 AM!\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await update.message.reply_text(format_bold(text))


async def removeauto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /removeauto command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    if not context.args:
        text = "❌ Correct: /removeauto <uid>"
        await update.message.reply_text(format_bold(text))
        return

    uid = context.args[0]
    remove_auto_like(uid)
    text = (
        f"✅ UID {uid} removed from auto-like list!\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await update.message.reply_text(format_bold(text))


async def likeinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only: show like statistics for a UID."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!")
        )
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            format_bold("❌ Correct: /likeinfo <uid>\nExample: /likeinfo 123456789")
        )
        return

    uid = context.args[0]
    stats = get_like_stats(uid)
    auto_info = get_auto_like_list().get(uid)
    target_info = load_data("target_like").get(uid)

    text = (
        f"📊 LIKE INFO\n\n"
        f"🆔 UID: {uid}\n"
        f"❤️ Total likes recorded: {stats['total_likes']}\n"
        f"📅 Today's likes: {stats['today_likes']}\n"
        f"🔁 Successful runs: {stats['runs']}\n"
        f"➕ Last run likes: {stats['last_likes']}\n"
    )

    if auto_info:
        text += (
            f"\n🤖 AUTO LIKE: ACTIVE\n"
            f"📆 Days left: {auto_info.get('days_left', 0)}\n"
            f"⏰ Schedule: {AUTO_LIKE_HOUR}:00 AM\n"
        )
    elif target_info:
        text += (
            f"\n🎯 TARGET LIKE: ACTIVE\n"
            f"📈 Progress: {target_info.get('likes_sent', 0)}/{target_info.get('target_limit', 0)}\n"
            f"⏰ Schedule: {AUTO_LIKE_HOUR}:00 AM\n"
        )
    else:
        text += "\nℹ️ No active Auto-Like/Target-Like setup for this UID.\n"

    text += "\n⚡ AS LIKE BOT ⚡"

    await update.message.reply_text(
        format_bold(text)
    )


async def autolist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /autolist command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    auto_list = get_auto_like_list()
    if not auto_list:
        text = "📋 Auto-like list is empty!"
    else:
        lines = ["📋 AUTO LIKE LIST:\n"]
        for uid, info in auto_list.items():
            lines.append(f"🆔 {uid} | 📅 Remaining: {info.get('days_left', 0)} Days")
        text = "\n".join(lines)
        text += "\n\n⚡ AS LIKE BOT ⚡"

    await update.message.reply_text(format_bold(text))


async def tlike_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tlike command with format: /tlike <uid> <target_limit>"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    if len(context.args) < 2:
        text = (
            "❌ WRONG FORMAT!\n\n"
            "Correct: /tlike <uid> <target_limit>\n"
            "Example: /tlike 15985683337 200"
        )
        await update.message.reply_text(format_bold(text))
        return

    uid = context.args[0]
    target_limit = context.args[1]

    if not uid.isdigit() or (target_limit.lower() != "unlimited" and (not target_limit.isdigit() or int(target_limit) <= 0)):
        await update.message.reply_text(
            format_bold("❌ UID and Target Limit must be valid numbers!"),
        )
        return

    limit = 0 if target_limit.lower() == "unlimited" else int(target_limit)
    add_target_like(uid, FIXED_REGION, limit)
    text = (
        f"✅ TARGET LIKE ADDED!\n\n"
        f"UID: {uid}\n"
        f"Target Limit: {'∞ Unlimited' if limit == 0 else f'{limit} Likes'}\n"
        f"API যত Likes দেয় তত যাবে; limit শুধু {'unlimited' if limit == 0 else 'target cap'} হিসেবে কাজ করবে.\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await update.message.reply_text(format_bold(text))


async def removetlike_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /removetlike command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    if not context.args:
        text = "❌ Correct: /removetlike <uid>"
        await update.message.reply_text(format_bold(text))
        return

    uid = context.args[0]
    remove_target_like(uid)
    text = (
        f"✅ UID {uid} removed from target-like list!\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await update.message.reply_text(format_bold(text))


async def tlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tlist command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    targets = load_data("target_like")
    if not targets:
        text = "📋 Target-like list is empty!"
    else:
        lines = ["📋 TARGET LIKE LIST:\n"]
        for uid, info in targets.items():
            lines.append(f"🆔 {uid} | 📈 Progress: {info.get('likes_sent', 0)}/{info.get('target_limit', 0)}")
        text = "\n".join(lines)
        text += "\n\n⚡ AS LIKE BOT ⚡"

    await update.message.reply_text(format_bold(text))


async def filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only.")); return
    if not context.args:
        await update.message.reply_text(format_bold("Format: /filter <word>\nতারপর পরের message-এ auto reply text পাঠান.")); return
    trigger=" ".join(context.args).strip(); context.user_data["pending_filter_trigger"]=trigger
    await update.message.reply_text(format_bold(f"🧩 FILTER SETUP\n\nTrigger: {trigger}\n\nএখন পরের message-এ bot-এর reply পাঠান."))

async def filterlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only.")); return
    data=get_filter_store()
    if not data:
        await update.message.reply_text(format_bold("🧩 কোনো filter নেই।")); return
    lines=["🧩 FILTER LIST","━━━━━━━━━━━━━━━━━━"]
    for key,item in data.items(): lines.append(f"• {item.get('trigger',key)} → {item.get('response','')}")
    await update.message.reply_text(format_bold("\n".join(lines)))

async def filterremove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only.")); return
    if not context.args:
        await update.message.reply_text(format_bold("Format: /filterremove <word>")); return
    trigger=" ".join(context.args).strip(); remove_filter(trigger)
    await update.message.reply_text(format_bold(f"✅ Filter removed: {trigger}"))

async def setfreelimit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global FREE_LIKE_DAILY_LIMIT, FREE_LIKE_UNLIMITED
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only.")); return
    if len(context.args)!=1:
        await update.message.reply_text(format_bold("Format: /setfreelimit <50|100|unlimited>")); return
    v=context.args[0].lower()
    if v in ("unlimited","none"):
        FREE_LIKE_UNLIMITED=True
        save_data("settings", {"free_like_unlimited": True, "free_like_daily_limit": FREE_LIKE_DAILY_LIMIT})
        msg="∞ Free Like limit এখন Unlimited."
    elif v.isdigit() and int(v)>=0:
        FREE_LIKE_UNLIMITED=False; FREE_LIKE_DAILY_LIMIT=int(v)
        save_data("settings", {"free_like_unlimited": False, "free_like_daily_limit": FREE_LIKE_DAILY_LIMIT})
        msg=f"✅ Free Like daily limit set to {FREE_LIKE_DAILY_LIMIT}."
    else: msg="❌ Value দিন: 50, 100 অথবা unlimited."
    await update.message.reply_text(format_bold(msg))

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    users = load_data("broadcast_users")
    groups = load_data("groups")
    channels = get_channels()
    auto_list = get_auto_like_list()
    targets = load_data("target_like")
    unlimited = load_data("unlimited")
    usage = load_data("daily_usage")

    text = (
        f"📊 BOT STATISTICS 📊\n\n"
        f"Bot Status: {'ON' if is_global_enabled() else 'OFF'}\n"
        f"Total Users: {len(users)}\n"
        f"Today's Active: {len(usage)}\n"
        f"Allowed Groups: {len(groups)}\n"
        f"Channels: {len(channels)}\n"
        f"Auto-Like UIDs: {len(auto_list)}\n"
        f"Target-Like UIDs: {len(targets)}\n"
        f"Unlimited UIDs: {len(unlimited)}\n"
        f"VIP Users: {len(load_data('vip'))}\n\n"
        f"⚡ AS LIKE BOT ⚡"
    )
    await update.message.reply_text(format_bold(text))


async def grouplist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /grouplist command"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(
            format_bold("❌ You are not authorized!"),
        )
        return

    groups = load_data("groups")
    lines = ["📋 ALLOWED GROUPS:\n"]
    
    if PRE_AUTHORIZED_GROUPS:
        lines.append("⚙️ Pre-Authorized (From Code):")
        for gid in PRE_AUTHORIZED_GROUPS:
            lines.append(f"🆔 {gid}")
        lines.append("")

    if groups:
        lines.append("📝 Manually Allowed:")
        for gid, info in groups.items():
            lines.append(f"🆔 {gid}")
    
    if len(lines) == 1:
        text = "📋 No groups allowed yet!"
    else:
        text = "\n".join(lines)
        text += "\n\n⚡ AS LIKE BOT ⚡"

    await update.message.reply_text(format_bold(text))


# ═══════════════════════════════════════════════════════════════════
# AUTO-LIKE RECOVERY / CATCH-UP
# ═══════════════════════════════════════════════════════════════════

AUTO_LIKE_CYCLE_LOCK = asyncio.Lock()


def _same_bd_day(timestamp):
    if not timestamp:
        return False
    try:
        return datetime.fromisoformat(str(timestamp)).strftime("%Y-%m-%d") == get_today()
    except (TypeError, ValueError):
        return False


async def process_auto_like_cycle(application, force=False, reason="scheduled"):
    """Process one daily auto-like batch only during the 04:00 BD window."""
    now = now_bd()
    if now.hour != AUTO_LIKE_HOUR or now.minute != AUTO_LIKE_MINUTE:
        logger.warning("Auto-like cycle blocked outside 04:00 BD: %s | reason=%s", now.isoformat(), reason)
        return 0, 0, 0

    async with AUTO_LIKE_CYCLE_LOCK:
        admin_report = [
            "📢 AUTO-LIKE REPORT",
            f"🗓️ {bd_timestamp()} BD",
            f"🔁 Reason: {reason}",
        ]
        processed = successful = failed = 0
        orders = load_data("orders")
        if not isinstance(orders, dict):
            orders = {}
        auto_list = load_data("auto_like")
        if not isinstance(auto_list, dict):
            auto_list = {}

        for order_id, order in list(orders.items()):
            if order.get("status") not in ("active", "payment_pending"):
                continue
            uid = str(order.get("uid", ""))
            requested = int(order.get("likes_requested", 0) or 0)
            sent = int(order.get("likes_sent", 0) or 0)
            remaining = max(0, requested - sent)
            if not uid or remaining <= 0:
                continue
            if _same_bd_day(order.get("last_run_at")):
                continue
            processed += 1
            run_time = bd_timestamp()
            update_order(order_id, last_attempt_at=run_time)
            try:
                result = await send_like_api(uid, FIXED_REGION, retries=2)
            except Exception:
                logger.exception("Auto-like API request failed for order %s", order_id)
                result = {"status": 0, "error": "temporary", "retryable": True}
            likes_given = max(0, _api_int(result.get("LikesGivenByAPI"), 0)) if isinstance(result, dict) else 0

            if isinstance(result, dict) and result.get("status") in [1, 2] and likes_given > 0:
                successful += 1
                new_sent = min(requested, sent + likes_given)
                new_remaining = max(0, requested - new_sent)
                update_order(
                    order_id,
                    likes_sent=new_sent,
                    remaining_likes=new_remaining,
                    last_run_at=run_time,
                    last_attempt_at=run_time,
                    last_likes=likes_given,
                    last_note=f"{likes_given:,} Likes delivered at {run_time} BD.",
                )
                record_like_stats(uid, min(likes_given, max(0, requested - sent)), source="package_auto")
                if new_remaining <= 0:
                    update_order(
                        order_id,
                        status="completed",
                        completed_at=run_time,
                        last_note=f"Order complete at {run_time} BD.",
                    )
                    auto_list.pop(uid, None)
                    admin_report.append(f"✅ {order_id} | UID {uid} | COMPLETE | +{likes_given}")
                    try:
                        await application.bot.send_message(
                            chat_id=int(order.get("user_id")),
                            text=format_bold(
                                f"🎉 ORDER COMPLETED\n\n"
                                f"🆔 Order ID: {order_id}\n"
                                f"🎮 UID: {uid}\n"
                                f"❤️ Like Sent: {new_sent:,}\n"
                                f"⏰ Bangladesh Time: {run_time}"
                            ),
                        )
                    except Exception:
                        logger.exception("Could not notify user for completed order %s", order_id)
                else:
                    admin_report.append(
                        f"✅ {order_id} | UID {uid} | +{likes_given} | "
                        f"Progress {new_sent}/{requested} | ETA {format_eta(new_remaining)}"
                    )
            else:
                failed += 1
                reason_code = classify_api_result(result)
                note = "BD Server UID নয়।" if reason_code == "region" else "API Like দেয়নি; পরের cycle/restart-এ retry হবে।"
                # IMPORTANT: do not set last_run_at on failure; restart can retry today.
                update_order(order_id, last_attempt_at=run_time, last_likes=0, last_note=note)
                admin_report.append(f"⚠️ {order_id} | UID {uid} | 0 Likes | {note}")
            await asyncio.sleep(1.0)

        targets = load_data("target_like")
        if not isinstance(targets, dict):
            targets = {}
        for uid, info in list(targets.items()):
            if _same_bd_day(info.get("last_run_at")):
                continue
            target_limit = int(info.get("target_limit", 0) or 0)
            sent_so_far = int(info.get("likes_sent", 0) or 0)
            if target_limit > 0 and sent_so_far >= target_limit:
                targets.pop(uid, None)
                continue
            processed += 1
            attempt_time = bd_timestamp()
            info["last_attempt_at"] = attempt_time
            result = await send_like_api(uid, FIXED_REGION, retries=2)
            likes_given = max(0, _api_int(result.get("LikesGivenByAPI"), 0)) if isinstance(result, dict) else 0
            if isinstance(result, dict) and result.get("status") in [1, 2] and likes_given > 0:
                info["likes_sent"] = sent_so_far + likes_given
                info["last_run_at"] = attempt_time
                record_like_stats(uid, likes_given, source="target")
                successful += 1
                admin_report.append(f"🎯 TARGET | {uid} | +{likes_given}")
                if target_limit > 0 and info["likes_sent"] >= target_limit:
                    targets.pop(uid, None)
                else:
                    targets[uid] = info
            else:
                failed += 1
                targets[uid] = info
                admin_report.append(f"⚠️ TARGET | {uid} | 0 Likes | retry later")
            await asyncio.sleep(1.0)
        save_data("target_like", targets)

        for uid, info in list(auto_list.items()):
            if info.get("order_id"):
                continue
            if _same_bd_day(info.get("last_run_at")):
                continue
            days_left = int(info.get("days_left", 0) or 0)
            if days_left <= 0:
                auto_list.pop(uid, None)
                continue
            processed += 1
            attempt_time = bd_timestamp()
            info["last_attempt_at"] = attempt_time
            result = await send_like_api(uid, FIXED_REGION, retries=2)
            likes_given = max(0, _api_int(result.get("LikesGivenByAPI"), 0)) if isinstance(result, dict) else 0
            if isinstance(result, dict) and result.get("status") in [1, 2] and likes_given > 0:
                info["days_left"] = days_left - 1
                info["last_run_at"] = attempt_time
                record_like_stats(uid, likes_given, source="auto")
                successful += 1
                admin_report.append(f"🤖 LEGACY AUTO | {uid} | +{likes_given} | Days Left {info['days_left']}")
                if info["days_left"] <= 0:
                    auto_list.pop(uid, None)
                else:
                    auto_list[uid] = info
            else:
                failed += 1
                auto_list[uid] = info
                admin_report.append(f"⚠️ LEGACY AUTO | {uid} | 0 Likes | retry later")
            await asyncio.sleep(1.0)

        save_data("auto_like", auto_list)
        admin_report += [
            "",
            f"📊 Processed: {processed}",
            f"✅ Successful: {successful}",
            f"⚠️ Failed/0: {failed}",
            "⚡ AS FF LIKE BOT",
        ]
        try:
            await application.bot.send_message(
                chat_id=ADMIN_ID,
                text=format_bold("\n".join(admin_report)),
            )
        except Exception:
            logger.exception("Failed to send auto-like report")
        return processed, successful, failed


async def autorestart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(format_bold("❌ Admin access only."))
        return
    await update.message.reply_text(format_bold("🔄 AUTO-RESTART CHECK\\n\\nAuto Like শুধুমাত্র ভোর ৪:০০ BD-তে চলবে। এখন কোনো API request পাঠানো হবে না."))
    try:
        processed, successful, failed = await process_auto_like_cycle(context.application, force=False, reason="/autorestart")
        await update.message.reply_text(format_bold(
            f"✅ AUTO-RESTART COMPLETE\\n\\n📊 Processed: {processed}\\n✅ Successful: {successful}\\n⚠️ Failed: {failed}\\n⏰ Bangladesh Time: {bd_timestamp()}"
        ))
    except Exception:
        logger.exception("/autorestart failed")
        await update.message.reply_text(format_bold("❌ Auto-restart failed. Error log check করুন."))


# ═══════════════════════════════════════════════════════════════════
# SCHEDULER - Daily Reset & Auto Like
# ═══════════════════════════════════════════════════════════════════

async def run_daily_reset(application):
    """Reset daily usage at 4:00 AM"""
    while True:
        now = now_bd()
        target = now.replace(hour=RESET_HOUR, minute=RESET_MINUTE, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        logger.info(f"Next daily reset scheduled in {wait_seconds/3600:.1f} hours")
        await asyncio.sleep(wait_seconds)
        reset_daily_usage()


async def run_auto_like(application):
    """Run at 04:00 BD and recover missed/failed deliveries on the next run."""
    while True:
        try:
            now = now_bd()
            target = now.replace(hour=AUTO_LIKE_HOUR, minute=AUTO_LIKE_MINUTE, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            wait_seconds = max(1, (target - now).total_seconds())
            logger.info("Next auto-like run at %s (BD), in %.1f hours", target.isoformat(), wait_seconds / 3600)
            await asyncio.sleep(wait_seconds)
            await process_auto_like_cycle(application, force=False, reason="04:00 scheduled")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Auto-like scheduler cycle failed; retrying in 60 seconds")
            await asyncio.sleep(60)


# ═══════════════════════════════════════════════════════════════════
# MAIN (Async Server Startup)
# ═══════════════════════════════════════════════════════════════════

async def babylike_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Only the bot owner can use /Babylike; all other users get no response."""
    user=update.effective_user; chat=update.effective_chat
    if not is_admin(user.id):
        return
    if chat.type not in ("group","supergroup"):
        await update.message.reply_text("⚡ /Babylike শুধু গ্রুপে ব্যবহার করা যাবে।"); return
    if len(context.args)!=1 or not context.args[0].isdigit():
        await update.message.reply_text("⚡ Format: /Babylike <UID>"); return
    uid=context.args[0]
    msg=await update.message.reply_text(f"💎 {BOT_NAME}\n\n🎮 UID: {uid}\n⏳ Like পাঠানো হচ্ছে...\n")
    try: result=await send_like_api(uid,FIXED_REGION,retries=2)
    except Exception: result={"status":0,"error":"temporary"}
    likes=max(0,int(result.get("LikesGivenByAPI",0) or 0)) if isinstance(result,dict) else 0
    if result.get("status") in [1,2] and likes>0:
        record_like_stats(uid,likes,source="Babylike")
        text=(f"💎 {BOT_NAME}\n\n🎮 UID: {uid}\n👤 Name: {result.get('PlayerNickname','Unknown')}\n"
              f"📉 Before: {result.get('LikesbeforeCommand','N/A')}\n📈 After: {result.get('LikesafterCommand','N/A')}\n"
              f"❤️ +{likes} Likes Sent\n\n✨ Like successfully delivered.")
    else:
        text=f"💎 {BOT_NAME}\n\n🎮 UID: {uid}\n⚠️ Like service এখন response দেয়নি বা UID সঠিক নয়।"
    await msg.edit_text(text)

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log handler exceptions and tell the user instead of leaving commands/buttons dead."""
    logger.exception("Unhandled Telegram update error", exc_info=context.error)
    try:
        if isinstance(update, Update):
            if update.callback_query:
                await update.callback_query.answer("একটি error হয়েছে। আবার চেষ্টা করুন।", show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text("❌ সাময়িক error হয়েছে। আবার /start দিন।")
    except Exception:
        logger.exception("Could not send error notification")


TELEGRAM_APPLICATION = None


async def main_async():
    global TELEGRAM_APPLICATION
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing inside main.py.")
    # Build application
    application = Application.builder().token(BOT_TOKEN).build()
    TELEGRAM_APPLICATION = application

    # Command handlers
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("like", like_cmd))
    application.add_handler(CommandHandler("Babylike", babylike_cmd))
    application.add_handler(CommandHandler("orderhistory", orderhistory_cmd))
    application.add_handler(CommandHandler("botedit", botedit_cmd))
    application.add_handler(CommandHandler("editallow", editallow_cmd))
    application.add_handler(CommandHandler("editremove", editremove_cmd))
    application.add_handler(CommandHandler("redeem", redeem_cmd))
    application.add_handler(CommandHandler("on", on_cmd))
    application.add_handler(CommandHandler("off", off_cmd))

    # Admin commands
    application.add_handler(CommandHandler("allow", allow_cmd))
    application.add_handler(CommandHandler("removegroup", removegroup_cmd))
    application.add_handler(CommandHandler("add", addchannel_cmd))
    application.add_handler(CommandHandler("removechannel", removechannel_cmd))
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    application.add_handler(CommandHandler("vip", vip_cmd))
    application.add_handler(CommandHandler("vipremove", vipremove_cmd))
    application.add_handler(CommandHandler("unlimit", unlimit_cmd))
    application.add_handler(CommandHandler("removeunlimit", removeunlimit_cmd))
    application.add_handler(CommandHandler("autolike", autolike_cmd))
    application.add_handler(CommandHandler("removeauto", removeauto_cmd))
    application.add_handler(CommandHandler("autolist", autolist_cmd))
    application.add_handler(CommandHandler("likeinfo", likeinfo_cmd))
    application.add_handler(CommandHandler("tlike", tlike_cmd))
    application.add_handler(CommandHandler("removetlike", removetlike_cmd))
    application.add_handler(CommandHandler("tlist", tlist_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("grouplist", grouplist_cmd))
    application.add_handler(CommandHandler("balance", balance_cmd))
    application.add_handler(CommandHandler("addpoints", addpoints_cmd))
    application.add_handler(CommandHandler("setpoints", setpoints_cmd))
    application.add_handler(CommandHandler("admin", admin_cmd))
    application.add_handler(CommandHandler("users", users_cmd))
    application.add_handler(CommandHandler("user", user_cmd))
    application.add_handler(CommandHandler("refstats", refstats_cmd))
    application.add_handler(CommandHandler("setrefreward", setrefreward_cmd))
    application.add_handler(CommandHandler("filter", filter_cmd))
    application.add_handler(CommandHandler("filterlist", filterlist_cmd))
    application.add_handler(CommandHandler("filterremove", filterremove_cmd))
    application.add_handler(CommandHandler("setfreelimit", setfreelimit_cmd))
    application.add_handler(CommandHandler("packages", packages_cmd))
    application.add_handler(CommandHandler("setpackage", setpackage_cmd))
    application.add_handler(CommandHandler("editpackage", editpackage_cmd))
    application.add_handler(CommandHandler("removepackage", removepackage_cmd))
    application.add_handler(CommandHandler("orders", orders_cmd))
    application.add_handler(CommandHandler("order", order_cmd))
    application.add_handler(CommandHandler("cancelorder", cancelorder_cmd))
    application.add_handler(CommandHandler("setdailyestimate", setdailyestimate_cmd))
    application.add_handler(CommandHandler("autorestart", autorestart_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_button_handler))

    # Callback handler
    application.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify_channels$"))
    application.add_handler(CallbackQueryHandler(addmoney_callback, pattern=r"^addmoney_(amount:\d+|custom|cancel)$"))
    application.add_handler(CallbackQueryHandler(addmoney_check_callback, pattern=r"^addmoney_check:"))
    application.add_handler(CallbackQueryHandler(users_page_callback, pattern=r"^users_page:\d+$"))
    application.add_handler(CallbackQueryHandler(first_220_callback, pattern=r"^bonus220_(confirm|cancel)$"))
    application.add_handler(CallbackQueryHandler(package_callback, pattern=r"^package_(select_\d+|cancel|uid_cancel)$"))
    application.add_handler(CallbackQueryHandler(admin_order_callback, pattern=r"^admin_cancel_order:"))
    application.add_handler(CallbackQueryHandler(order_history_callback, pattern=r"^order_history:(running|complete|back)$"))
    application.add_handler(CallbackQueryHandler(cancel_order_ui_callback, pattern=r"^cancel_order_ui:"))
    application.add_handler(CallbackQueryHandler(botedit_callback, pattern=r"^botedit_(select:|close$)"))

    application.add_error_handler(global_error_handler)

    # Initialize and start Telegram Bot first. Starting background tasks before
    # the Telegram application is initialized can cause host/startup crashes.
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    scheduler_tasks = [
        asyncio.create_task(run_daily_reset(application), name="daily_reset"),
        asyncio.create_task(run_auto_like(application), name="auto_like"),
    ]
    logger.info("Background scheduler tasks started: %s", [t.get_name() for t in scheduler_tasks])
    logger.info("Telegram Bot polling started.")

    # Render Port Binding Setup
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Bot is running successfully!"))
    app.router.add_post(BOHUDUR_SUCCESS_WEBHOOK_PATH, bohudur_webhook_success)
    app.router.add_post(BOHUDUR_CANCEL_WEBHOOK_PATH, bohudur_webhook_cancel)
    app.router.add_get(BOHUDUR_RETURN_PATH, bohudur_return)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Port binding web server started on port {port}")
    if BOHUDUR_API_KEY == "YOUR_BOHUDUR_API_KEY":
        logger.warning("BOHUDUR_API_KEY is not configured; Add Money payments are disabled.")
    if not PUBLIC_BASE_URL:
        logger.warning("PUBLIC_BASE_URL/RENDER_EXTERNAL_URL is missing; automatic Bohudur webhooks may not work.")

    # No startup catch-up: Auto Like is strictly 04:00 BD only.

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        logger.info("Shutting down AS LIKE BOT...")
        for task in scheduler_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*scheduler_tasks, return_exceptions=True)
        try:
            await application.updater.stop()
        except Exception:
            logger.exception("Error stopping Telegram updater")
        try:
            await application.stop()
        except Exception:
            logger.exception("Error stopping Telegram application")
        try:
            await application.shutdown()
        except Exception:
            logger.exception("Error shutting down Telegram application")
        global API_SESSION
        if API_SESSION is not None and not API_SESSION.closed:
            try:
                await API_SESSION.close()
            except Exception:
                logger.exception("Error closing API session")
            API_SESSION = None
        try:
            await runner.cleanup()
        except Exception:
            logger.exception("Error cleaning up web server")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing inside main.py.")

    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║           AS LIKE BOT VIP - Starting...                         ║
    ║           Free Fire Auto Like Bot                                ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
