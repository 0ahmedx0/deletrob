import os
import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from dotenv import load_dotenv

# تحميل المتغيرات من .env
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID"))  # معرفك من @userinfobot

# جلسة حساب المستخدم (للوصول للقنوات)
user_client = TelegramClient('user_session', API_ID, API_HASH)

# جلسة البوت (للأوامر والإشعارات)
bot_client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

async def scan_channel(channel_id: int, first_msg_id: int = 1):
    """فحص القناة وإرجاع اسم التقرير"""
    duplicates = {}
    try:
        async for msg in user_client.iter_messages(channel_id, min_id=first_msg_id - 1):
            if msg.file and msg.file.size:
                file_size = msg.file.size
                link = f"https://t.me/c/{str(channel_id)[4:]}/{msg.id}"
                duplicates.setdefault(file_size, []).append((msg.id, link))
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        return None, f"[!] خطأ أثناء الفحص: {e}"

    duplicate_groups = {size: msgs for size, msgs in duplicates.items() if len(msgs) > 1}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = f"duplicates_report_{timestamp}.txt"
    with open(report_name, "w", encoding="utf-8") as f:
        f.write("📄 تقرير الملفات المكررة في القناة\n")
        f.write(f"القناة: {channel_id}\n")
        f.write(f"تاريخ التقرير: {datetime.now()}\n")
        f.write(f"إجمالي المجموعات المكررة: {len(duplicate_groups)}\n\n")
        for size, msgs in duplicate_groups.items():
            f.write(f"📦 حجم الملف: {size} بايت\n")
            f.write(f"🔗 الأصل: {msgs[0][1]}\n")
            for dup in msgs[1:]:
                f.write(f"   ↳ مكرر: {dup[1]}\n")
            f.write("\n")
    return report_name, None

@bot_client.on(events.NewMessage(from_users=MY_CHAT_ID))
async def handler(event):
    """استقبال الأوامر من صاحب البوت"""
    text = event.raw_text.strip()
    parts = text.split()

    if len(parts) == 0:
        await event.reply("❌ أرسل: CHANNEL_ID [FIRST_MSG_ID]")
        return

    try:
        channel_id = int(parts[0])
        first_msg_id = int(parts[1]) if len(parts) > 1 else 1
    except ValueError:
        await event.reply("❌ صيغة غير صحيحة.\n📌 مثال: `-1001234567890 5`")
        return

    await event.reply(f"🚀 بدء فحص القناة {channel_id} من الرسالة {first_msg_id}...")
    report, error = await scan_channel(channel_id, first_msg_id)

    if error:
        await event.reply(error)
    else:
        await event.reply(file=report, message="✅ تم الانتهاء من الفحص")

async def main():
    await user_client.start()
    print("[✓] البوت جاهز لاستقبال الأوامر.")
    await bot_client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
