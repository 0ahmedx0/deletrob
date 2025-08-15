#!/usr/bin/env python3
# dup_bot.py
# Requires: telethon, python-dotenv
# pip install telethon python-dotenv

import os
import asyncio
import math
import time
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from dotenv import load_dotenv

# -------------------
# تحميل المتغيرات من .env
# -------------------
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID"))

if not all([API_ID, API_HASH, BOT_TOKEN, MY_CHAT_ID]):
    raise SystemExit("❌ تأكد من إعداد المتغيرات API_ID, API_HASH, BOT_TOKEN, MY_CHAT_ID في ملف .env")

# -------------------
# جلسات المستخدم والبوت
# -------------------
user_client = TelegramClient('user_session', API_ID, API_HASH)
bot_client = TelegramClient('bot_session', API_ID, API_HASH)

# -------------------
# حالة ومخزن تقارير
# -------------------
cancel_delete = False
last_report = None  # مسار آخر تقرير نصي

# -------------------
# دوال مساعدة
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

def normalize_channel_id(raw):
    raw = raw.strip()
    if raw.startswith("-100") or raw.startswith("-"):
        return int(raw)
    if raw.isdigit():
        return int(f"-100{raw}")
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if digits:
        return int(f"-100{digits}")
    raise ValueError("Channel ID غير صالحة.")

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
            if not getattr(msg, "file", None) or not getattr(msg.file, "size", None):
                continue

            mime = (getattr(msg.file, "mime_type", "") or "").lower()
            if file_type != "all":
                if file_type == "document" and not mime.startswith("application"):
                    continue
                if file_type == "video" and not (mime.startswith("video") or getattr(msg, "video", False)):
                    continue
                if file_type == "audio" and not mime.startswith("audio"):
                    continue
                if file_type == "photo" and not getattr(msg, "photo", None):
                    continue

            duplicates.setdefault(msg.file.size, []).append(msg)

    except FloodWaitError as e:
        await bot_client.send_message(MY_CHAT_ID, f"[!] FloodWait — انتظر {e.seconds} ثانية ثم أستكمل.")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        return None, None, f"[!] خطأ أثناء الفحص: {repr(e)}", None

    duplicate_groups = {size: msgs for size, msgs in duplicates.items() if len(msgs) > 1}
    delete_ids = []
    if duplicate_groups:
        sizes = list(duplicate_groups.keys())
        max_size = max(sizes)
        min_size = min(sizes)
    else:
        max_size = min_size = 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = f"duplicates_report_{timestamp}.txt"

    # كتابة التقرير
    with open(report_name, "w", encoding="utf-8") as f:
        f.write("📄 تقرير الملفات المكررة في القناة\n")
        f.write("="*60 + "\n")
        f.write(f"📌 القناة: {channel_id}\n")
        f.write(f"📅 تاريخ التقرير: {datetime.now()}\n")
        f.write(f"⏱ الوقت المستغرق: {round(time.time() - start_time,2)} ثانية\n")
        f.write(f"🔍 الرسائل المفحوصة: {total_scanned}\n")
        f.write(f"📂 مجموعات التكرار: {len(duplicate_groups)}\n")
        f.write(f"📑 الرسائل المكررة (ستُحذف إن اخترت الحذف): {sum(len(msgs)-1 for msgs in duplicate_groups.values())}\n")
        f.write(f"📦 أكبر ملف مكرر: {human_size(max_size)}\n")
        f.write(f"📦 أصغر ملف مكرر: {human_size(min_size)}\n")
        f.write("="*60 + "\n\n")

        for size, msgs in sorted(duplicate_groups.items(), key=lambda x:x[0], reverse=True):
            f.write(f"📦 الحجم: {human_size(size)} ({size} B)\n")
            f.write(f"🔗 الأصل: https://t.me/c/{str(channel_id)[4:]}/{msgs[0].id}\n")
            for dup in msgs[1:]:
                f.write(f"   ↳ مكرر: https://t.me/c/{str(channel_id)[4:]}/{dup.id}\n")
                delete_ids.append(dup.id)
            f.write("\n")

    stats = {
        "total_scanned": total_scanned,
        "duplicate_groups": duplicate_groups,
        "max_size": max_size,
        "min_size": min_size,
        "duration": round(time.time() - start_time,2)
    }

    return report_name, delete_ids, None, stats

# -------------------
# حذف بالدفعات
# -------------------
async def delete_messages_in_batches(channel_id, msg_ids, batch_size=100, delay=60):
    global cancel_delete
    total = len(msg_ids)
    deleted_count = 0
    start_time = time.time()

    progress_msg = await bot_client.send_message(MY_CHAT_ID, f"🗑 بدء حذف: 0/{total} رسالة (0%) ...")

    for i in range(0, total, batch_size):
        if cancel_delete:
            await bot_client.edit_message(progress_msg, f"❌ تم إلغاء عملية الحذف. المحذوف حتى الآن: {deleted_count}/{total}")
            cancel_delete = False
            return deleted_count, round(time.time() - start_time, 2)

        batch = msg_ids[i:i+batch_size]
        try:
            await user_client.delete_messages(channel_id, batch)
            deleted_count += len(batch)
            percent = math.floor((deleted_count / total) * 100)
            await bot_client.edit_message(progress_msg,
                                          f"🗑 حذف: {deleted_count}/{total} رسالة — {percent}%\nآخر دفعة: {len(batch)} رسالة.\n(انتظار {delay}s قبل الدفعة التالية)")
        except FloodWaitError as e:
            await bot_client.edit_message(progress_msg, f"[!] FloodWait — انتظار {e.seconds} ثانية ...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            await bot_client.edit_message(progress_msg, f"[!] خطأ أثناء الحذف: {repr(e)}")
        await asyncio.sleep(delay)

    duration = round(time.time() - start_time, 2)
    await bot_client.edit_message(progress_msg, f"✅ انتهى الحذف. المحذوف الكلي: {deleted_count}/{total} رسالة في {duration} ثانية.")
    return deleted_count, duration

# -------------------
# معالج أوامر البوت
# -------------------
@bot_client.on(events.NewMessage(from_users=MY_CHAT_ID))
async def handler(event):
    global cancel_delete, last_report
    raw_text = (event.raw_text or "").strip()
    if not raw_text:
        await event.reply("❌ لا يوجد نص. أرسل: /help")
        return

    text = raw_text.strip()
    parts = text.lower().split()
    do_delete = False
    first_msg = 1
    file_type = "all"

    # دعم أوامر /slash
    if parts[0].startswith("/"):
        cmd = parts[0]
        if cmd == "/cancel":
            cancel_delete = True
            await event.reply("❌ تم طلب إلغاء الحذف.")
            return
        if cmd == "/stats":
            if last_report and os.path.exists(last_report):
                await bot_client.send_file(MY_CHAT_ID, last_report, caption="📊 آخر تقرير:")
            else:
                await event.reply("❌ لا يوجد تقرير سابق.")
            return
        if cmd in ("/help", "/start"):
            await send_welcome(event.sender_id)
            return
        if cmd not in ("/scan", "/scan_delete"):
            await event.reply("❌ أمر غير معروف. استخدم /help لعرض الأوامر.")
            return
        try:
            channel_id = normalize_channel_id(parts[1])
            first_msg = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            file_type = parts[3] if len(parts) > 3 else "all"
            do_delete = (cmd == "/scan_delete")
        except:
            await event.reply("❌ صيغة غير صحيحة. مثال: /scan 1234567890 5 document")
            return
    else:
        # المدخل الحر
        try:
            channel_id = normalize_channel_id(parts[0])
            for token in parts[1:]:
                if token.isdigit() and first_msg == 1:
                    first_msg = int(token)
                    continue
                if token in ("delete", "del"):
                    do_delete = True
                    continue
                if token in ("all", "document", "video", "audio", "photo"):
                    file_type = token
                    continue
        except:
            await event.reply("❌ صيغة غير صحيحة. مثال: 1234567890 5 delete")
            return

    await bot_client.send_message(MY_CHAT_ID, f"🚀 بدء فحص القناة `{channel_id}` من الرسالة `{first_msg}` (نوع: `{file_type}`) — حذف: {do_delete}")

    report, delete_ids, error, stats = await scan_channel(channel_id, first_msg, file_type)
    if error:
        await bot_client.send_message(MY_CHAT_ID, error)
        return

    last_report = report
    await bot_client.send_file(MY_CHAT_ID, report, caption="✅ تم الانتهاء من الفحص — تقرير مفصل:")

    # إرسال ملخص الإحصائيات
    duplicate_groups = stats["duplicate_groups"]
    summary_text = (
        f"📌 القناة: {channel_id}\n"
        f"⏱ الوقت المستغرق: {stats['duration']} ثانية\n"
        f"🔍 الرسائل المفحوصة: {stats['total_scanned']}\n"
        f"📂 مجموعات التكرار: {len(duplicate_groups)}\n"
        f"📑 الرسائل المكررة: {sum(len(msgs)-1 for msgs in duplicate_groups.values())}\n"
        f"📦 أكبر ملف مكرر: {human_size(stats['max_size'])}\n"
        f"📦 أصغر ملف مكرر: {human_size(stats['min_size'])}"
    )
    await bot_client.send_message(MY_CHAT_ID, summary_text)

    # إذا مطلوب حذف
    if do_delete:
        if not delete_ids:
            await bot_client.send_message(MY_CHAT_ID, "ℹ️ لا توجد ملفات مكررة للحذف.")
            return
        await bot_client.send_message(MY_CHAT_ID, f"🗑 سيتم حذف {len(delete_ids)} رسالة مكررة على دفعات (كل دفعة 100 رسالة، تأخير 60s). لإلغاء أثناء التنفيذ أرسل /cancel .")
        deleted, duration = await delete_messages_in_batches(channel_id, delete_ids, batch_size=100, delay=60)
        await bot_client.send_message(MY_CHAT_ID, f"✅ انتهت عملية الحذف. المحذوف: {deleted} رسالة. المدة: {duration} ثانية.")
    else:
        await bot_client.send_message(MY_CHAT_ID, "ℹ️ تم الانتهاء من الفحص (لم يتم حذف أي رسالة).")

# -------------------
# رسالة ترحيب
# -------------------
async def send_welcome(target_id):
    welcome_text = (
        "🤖 مرحباً بك في بوت إدارة الملفات المكررة!\n\n"
        "📌 الأوامر المتاحة:\n\n"
        "1) /scan <CHANNEL_ID> [FIRST_MSG_ID] [TYPE]\n"
        "2) /scan_delete <CHANNEL_ID> [FIRST_MSG_ID] [TYPE]\n"
        "3) صيغة سريعة: 1234567890 5 delete\n"
        "4) /stats  -> إرسال آخر تقرير محفوظ\n"
        "5) /cancel -> إلغاء الحذف أثناء التنفيذ\n\n"
        "⚙️ TYPE: all | document | video | audio | photo\n"
        "ملاحظة: يمكنك إرسال رقم القناة بدون -100 وسيتم إضافته تلقائياً."
    )
    await bot_client.send_message(target_id, "[✓] البوت جاهز لاستقبال الأوامر.")
    await bot_client.send_message(target_id, welcome_text)

# -------------------
# بدء التشغيل
# -------------------
async def main():
    await user_client.start()
    await bot_client.start(bot_token=BOT_TOKEN)
    await send_welcome(MY_CHAT_ID)
    await asyncio.Future()

if __name__ == "__main__":
    user_client.loop.run_until_complete(main())
