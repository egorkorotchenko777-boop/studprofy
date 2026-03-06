import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
CHANNEL_ID = os.getenv("CHANNEL_ID", "@StudProfy")

BONUS_FOR_SUBSCRIBE = 50
BONUS_FOR_OWN_ORDER = 100
BONUS_FOR_REFERRAL = 150
BONUS_FOR_REFERRAL_ORDER = 300
MIN_BONUS_TO_SPEND = 100
GIFT_THRESHOLD = 1000
