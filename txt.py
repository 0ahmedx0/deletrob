import os
import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from dotenv import load_dotenv

# تحميل المتغيرات من ملف .env
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID"))

# إنشاء العميل
client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

async def send_notification(text: str):
    """إرسال إشعار إلى دردشة البوت نفسه"""
    try:
        await client.send_message('me', text)
    except Exception as e:
        print(f"[!] خطأ في إرسال الإشعار: {e}")

async def main():
    await send_notification("🚀 بدء فحص القناة لاكتشاف الملفات المكررة...")

    duplicates = {}  # {file_size: [(msg_id, link), ...]}

    try:
        async for msg in client.iter_messages(CHANNEL_ID, min_id=FIRST_MSG_ID-1):
            if msg.file and msg.file.size:
                file_size = msg.file.size
                link = f"https://t.me/c/{str(CHANNEL_ID)[4:]}/{msg.id}"
                duplicates.setdefault(file_size, []).append((msg.id, link))

    except FloodWaitError as e:
        print(f"[!] انتظر {e.seconds} ثانية بسبب FloodWait")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print(f"[!] خطأ أثناء الفحص: {e}")

    # تصفية التكرارات الحقيقية (أكثر من رسالة لنفس الحجم)
    duplicate_groups = {size: msgs for size, msgs in duplicates.items() if len(msgs) > 1}

    # إنشاء التقرير
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = f"duplicates_report_{timestamp}.txt"

    with open(report_name, "w", encoding="utf-8") as f:
        f.write("📄 تقرير الملفات المكررة في القناة\n")
        f.write(f"القناة: {CHANNEL_ID}\n")
        f.write(f"تاريخ التقرير: {datetime.now()}\n")
        f.write(f"إجمالي المجموعات المكررة: {len(duplicate_groups)}\n\n")

        for size, msgs in duplicate_groups.items():
            f.write(f"📦 حجم الملف: {size} بايت\n")
            f.write(f"🔗 الأصل: {msgs[0][1]}\n")
            for dup in msgs[1:]:
                f.write(f"   ↳ مكرر: {dup[1]}\n")
            f.write("\n")

    print(f"[✓] تم إنشاء التقرير: {report_name}")
    await send_notification(f"✅ تم الانتهاء من الفحص.\n📄 التقرير محفوظ باسم: {report_name}")

if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
