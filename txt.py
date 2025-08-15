import os
import asyncio
import math
import time
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from dotenv import load_dotenv

# -------------------
# تحميل المتغيرات
# -------------------
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID"))

# -------------------
# جلسات المستخدم والبوت
# -------------------
user_client = TelegramClient('user_session', API_ID, API_HASH)
bot_client = TelegramClient('bot_session', API_ID, API_HASH)

# -------------------
# حالة إلغاء الحذف وأحدث تقرير
# -------------------
cancel_delete = False
last_report = None

# -------------------
# تحويل حجم الملفات
# -------------------
def human_size(size_bytes):
    if size_bytes >= 1 << 30:
        return f"{size_bytes / (1<<30):.2f} GB"
    elif size_bytes >= 1 << 20:
        return f"{size_bytes / (1<<20):.2f} MB"
    elif size_bytes >= 1 << 10:
        return f"{size_bytes / (1<<10):.2f} KB"
    else:
        return f"{size_bytes} B"

# -------------------
# فحص القناة
# -------------------
async def scan_channel(channel_id: int, first_msg_id: int = 1, file_type: str = "all"):
    start_time = time.time()
    duplicates = {}
    total_scanned = 0

    try:
        async for msg in user_client.iter_messages(channel_id, min_id=first_msg_id - 1):
            total_scanned += 1
            if not msg.file or not msg.file.size:
                continue
            # فلترة حسب النوع
            if file_type != "all":
                if file_type == "document" and not msg.file.mime_type.startswith("application"):
                    continue
                elif file_type == "video" and not msg.file.mime_type.startswith("video"):
                    continue
                elif file_type == "audio" and not msg.file.mime_type.startswith("audio"):
                    continue
                elif file_type == "photo" and not msg.photo:
                    continue
            duplicates.setdefault(msg.file.size, []).append(msg)
    except FloodWaitError as e:
        await bot_client.send_message(MY_CHAT_ID, f"[!] انتظر {e.seconds} ثانية بسبب FloodWait")
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

    # إنشاء التقرير
    with open(report_name, "w", encoding="utf-8") as f:
        f.write("📄 تقرير الملفات المكررة في القناة\n")
        f.write("="*60 + "\n")
        f.write(f"📌 القناة: {channel_id}\n")
        f.write(f"📅 تاريخ التقرير: {datetime.now()}\n")
        f.write(f"⏱ الوقت المستغرق: {round(time.time() - start_time,2)} ثانية\n")
        f.write(f"🔍 الرسائل المفحوصة: {total_scanned}\n")
        f.write(f"📂 مجموعات التكرار: {len(duplicate_groups)}\n")
        f.write(f"📑 الرسائل المكررة: {sum(len(msgs)-1 for msgs in duplicate_groups.values())}\n")
        f.write(f"📦 أكبر ملف مكرر: {human_size(max_size)}\n")
        f.write(f"📦 أصغر ملف مكرر: {human_size(min_size)}\n")
        f.write("="*60 + "\n\n")

        for size, msgs in sorted(duplicate_groups.items(), key=lambda x:x[0], reverse=True):
            f.write(f"📦 الحجم: {human_size(size)}\n")
            f.write(f"🔗 الأصل: https://t.me/c/{str(channel_id)[4:]}/{msgs[0].id}\n")
            for dup in msgs[1:]:
                f.write(f"   ↳ مكرر: https://t.me/c/{str(channel_id)[4:]}/{dup.id}\n")
                delete_ids.append(dup.id)
            f.write("\n")

    return report_name, delete_ids, None

# -------------------
# حذف الرسائل بالدفعات مع نسبة التقدم
# -------------------
async def delete_messages_in_batches(channel_id, msg_ids, batch_size=100, delay=60):
    global cancel_delete
    total = len(msg_ids)
    deleted_count = 0
    start_time = time.time()

    for i in range(0, total, batch_size):
        if cancel_delete:
            await bot_client.send_message(MY_CHAT_ID, "❌ تم إلغاء عملية الحذف.")
            break
        batch = msg_ids[i:i+batch_size]
        try:
            await user_client.delete_messages(channel_id, batch)
            deleted_count += len(batch)
            percent = math.floor((deleted_count / total) * 100)
            await bot_client.send_message(MY_CHAT_ID, f"[{percent}%] تم حذف {deleted_count}/{total} رسالة.")
        except FloodWaitError as e:
            await bot_client.send_message(MY_CHAT_ID, f"[!] انتظر {e.seconds} ثانية بسبب FloodWait")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            await bot_client.send_message(MY_CHAT_ID, f"[!] خطأ في الحذف: {e}")
        await asyncio.sleep(delay)

    duration = round(time.time() - start_time,2)
    await bot_client.send_message(MY_CHAT_ID, f"✅ تم حذف {deleted_count} رسالة مكررة في {duration} ثانية.")
    return deleted_count, duration

# -------------------
# أوامر البوت
# -------------------
@bot_client.on(events.NewMessage(from_users=MY_CHAT_ID))
async def handler(event):
    global cancel_delete, last_report
    text = event.raw_text.strip().lower()
    parts = text.split()

    if not parts:
        await event.reply("❌ أرسل: <CHANNEL_ID> [FIRST_MSG_ID] [TYPE] أو delete")
        return

    if parts[0] == "/cancel":
        cancel_delete = True
        await event.reply("❌ تم إلغاء عملية الحذف.")
        return

    if parts[0] == "/stats":
        if last_report:
            await event.reply(file=last_report, message="📊 آخر تقرير:")
        else:
            await event.reply("❌ لا يوجد تقرير سابق.")
        return

    # صيغة جديدة: CHANNEL_ID FIRST_MSG_ID TYPE أو delete
    try:
        raw_id = parts[0]
        channel_id = int(raw_id)
        if channel_id > 0:
            channel_id = -1000000000000 + channel_id  # إضافة -100 تلقائياً
        first_msg_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        type_or_delete = parts[2] if len(parts) > 2 else "all"
        do_delete = type_or_delete in ["delete", "del"]
        file_type = type_or_delete if type_or_delete not in ["delete", "del"] else "all"
    except:
        await event.reply("❌ صيغة غير صحيحة.\n📌 مثال: `1234567890 5 document` أو `1234567890 5 delete`")
        return

    cancel_delete = False
    await bot_client.send_message(MY_CHAT_ID, f"🚀 بدء فحص القناة {channel_id} من الرسالة {first_msg_id} (نوع: {file_type})...")
    report, delete_ids, error = await scan_channel(channel_id, first_msg_id, file_type)

    if error:
        await bot_client.send_message(MY_CHAT_ID, error)
        return

    last_report = report
    await bot_client.send_message(MY_CHAT_ID, "✅ تم الانتهاء من الفحص", file=report)

    if do_delete and delete_ids:
        await bot_client.send_message(MY_CHAT_ID, f"🗑 بدء حذف {len(delete_ids)} رسالة مكررة على دفعات...")
        await delete_messages_in_batches(channel_id, delete_ids)

# -------------------
# تشغيل البوت
# -------------------
async def main():
    await user_client.start()
    await bot_client.start(bot_token=BOT_TOKEN)

    # رسالة ترحيب مع قائمة الأوامر
    welcome_text = """🤖 مرحباً بك في بوت إدارة الملفات المكررة!

📌 الصيغ المتاحة:

1️⃣ <CHANNEL_ID> [FIRST_MSG_ID] [TYPE]
   🔹 فحص فقط بدون حذف
   🔹 مثال: 1234567890 5 document

2️⃣ <CHANNEL_ID> [FIRST_MSG_ID] delete
   🔹 فحص وحذف الرسائل المكررة
   🔹 مثال: 1234567890
2️⃣ <CHANNEL_ID> [FIRST_MSG_ID] delete
   🔹 فحص وحذف الرسائل المكررة
   🔹 مثال: 1234567890 5 delete

3️⃣ /stats
   🔹 عرض آخر تقرير تم إنشاؤه

4️⃣ /cancel
   🔹 إلغاء عملية الحذف إذا كانت قيد التنفيذ

⚙️ TYPE يمكن أن يكون: all | document | video | audio | photo

📌 كل الإشعارات، التقدم، والتقارير تُرسل هنا في هذه المحادثة
"""
    await bot_client.send_message(MY_CHAT_ID, "[✓] البوت جاهز لاستقبال الأوامر.")
    await bot_client.send_message(MY_CHAT_ID, welcome_text)

    await asyncio.Future()  # يبقى البوت شغال للأبد

# -------------------
# نقطة الدخول
# -------------------
if __name__ == "__main__":
    # تشغيل البوت مع جلسة المستخدم
    try:
        user_client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("✅ تم إيقاف البوت يدوياً")
