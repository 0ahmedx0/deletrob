import os
import asyncio
import math
import time
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

# جلسة حساب المستخدم
user_client = TelegramClient('user_session', API_ID, API_HASH)
# جلسة البوت
bot_client = TelegramClient('bot_session', API_ID, API_HASH)

async def scan_channel(channel_id: int, first_msg_id: int = 1):
    """فحص القناة وإرجاع اسم التقرير وقائمة IDs المكررة"""
    start_time = time.time()
    duplicates = {}
    total_scanned = 0

    try:
        async for msg in user_client.iter_messages(channel_id, min_id=first_msg_id - 1):
            total_scanned += 1
            if msg.file and msg.file.size:
                duplicates.setdefault(msg.file.size, []).append(msg)
    except FloodWaitError as e:
        print(f"[!] انتظر {e.seconds} ثانية بسبب FloodWait")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        return None, None, f"[!] خطأ أثناء الفحص: {e}"

    duplicate_groups = {size: msgs for size, msgs in duplicates.items() if len(msgs) > 1}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = f"duplicates_report_{timestamp}.txt"
    delete_ids = []

    if duplicate_groups:
        sizes = list(duplicate_groups.keys())
        max_size = max(sizes)
        min_size = min(sizes)
    else:
        max_size = min_size = 0

    with open(report_name, "w", encoding="utf-8") as f:
        f.write("📄 تقرير الملفات المكررة في القناة\n")
        f.write("="*50 + "\n")
        f.write(f"📌 القناة: {channel_id}\n")
        f.write(f"📅 تاريخ التقرير: {datetime.now()}\n")
        f.write(f"⏱ الوقت المستغرق: {round(time.time() - start_time, 2)} ثانية\n")
        f.write(f"🔍 الرسائل المفحوصة: {total_scanned}\n")
        f.write(f"📂 مجموعات التكرار: {len(duplicate_groups)}\n")
        f.write(f"📑 الملفات المكررة: {sum(len(msgs)-1 for msgs in duplicate_groups.values())}\n")
        f.write(f"📦 أكبر ملف مكرر: {max_size} بايت\n")
        f.write(f"📦 أصغر ملف مكرر: {min_size} بايت\n")
        f.write("="*50 + "\n\n")

        for size, msgs in sorted(duplicate_groups.items(), key=lambda x: x[0], reverse=True):
            f.write(f"📦 الحجم: {size} بايت\n")
            f.write(f"🔗 الأصل: https://t.me/c/{str(channel_id)[4:]}/{msgs[0].id}\n")
            for dup in msgs[1:]:
                f.write(f"   ↳ مكرر: https://t.me/c/{str(channel_id)[4:]}/{dup.id}\n")
                delete_ids.append(dup.id)
            f.write("\n")

    return report_name, delete_ids, None

async def delete_messages_in_batches(channel_id, msg_ids, batch_size=100, delay=60):
    """حذف الرسائل على دفعات مع إظهار النسبة"""
    total = len(msg_ids)
    deleted_count = 0
    start_time = time.time()

    for i in range(0, total, batch_size):
        batch = msg_ids[i:i+batch_size]
        try:
            await user_client.delete_messages(channel_id, batch)
            deleted_count += len(batch)
            percent = math.floor((deleted_count / total) * 100)
            print(f"[{percent}%] تم حذف {deleted_count}/{total} رسالة.")
        except FloodWaitError as e:
            print(f"[!] انتظر {e.seconds} ثانية بسبب FloodWait")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"[!] خطأ في الحذف: {e}")
        await asyncio.sleep(delay)

    duration = round(time.time() - start_time, 2)
    return deleted_count, duration

@bot_client.on(events.NewMessage(from_users=MY_CHAT_ID))
async def handler(event):
    """استقبال أوامر الفحص والحذف"""
    parts = event.raw_text.strip().split()
    if not parts:
        await event.reply("❌ أرسل: CHANNEL_ID [FIRST_MSG_ID] [delete]")
        return

    try:
        channel_id = int(parts[0])
        first_msg_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        do_delete = "delete" in parts
    except ValueError:
        await event.reply("❌ صيغة غير صحيحة.\n📌 مثال: `-1001234567890 5 delete`")
        return

    await event.reply(f"🚀 بدء فحص القناة {channel_id} من الرسالة {first_msg_id}...")
    report, delete_ids, error = await scan_channel(channel_id, first_msg_id)

    if error:
        await event.reply(error)
    else:
        await event.reply(file=report, message="✅ تم الانتهاء من الفحص")
        if do_delete and delete_ids:
            await event.reply(f"🗑 بدء حذف {len(delete_ids)} رسالة مكررة على دفعات...")
            deleted, duration = await delete_messages_in_batches(channel_id, delete_ids)
            await event.reply(f"✅ تم حذف {deleted} رسالة مكررة في {duration} ثانية.")

async def main():
    await user_client.start()
    await bot_client.start()
    print("[✓] البوت جاهز لاستقبال الأوامر.")
    await asyncio.Future()  # يبقى شغال للأبد

if __name__ == "__main__":
    user_client.loop.run_until_complete(main())
