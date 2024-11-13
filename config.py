from dotenv import load_dotenv
import os

load_dotenv()

# Jitsi configuration
JITSI_URL = os.getenv('JITSI_URL', 'logsimpl.com')
ROOM_NAME = os.getenv('ROOM_NAME', 'yo')
BOT_NAME = os.getenv('BOT_NAME', 'JitsiBot')
MEETING_URL = f"https://{JITSI_URL}/{ROOM_NAME}"