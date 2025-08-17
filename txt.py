#!/usr/bin/env python3
# dup_bot_backup_delete.py
# Requires: telethon, python-dotenv
# pip install telethon python-dotenv

import os
import asyncio
import math
import time
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError
from telethon.tl.types import InputMediaDocument
from dotenv import load_dotenv

# -------------------
# تحميل المتغيرات من .env
# -------------------
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID"))
DEST_CHANNEL_ID = int(os.getenv("DEST_CHANNEL_ID"))

if not all([API_ID, API_HASH, BOT_TOKEN, MY_CHAT_ID, DEST_CHANNEL_ID]):
    raise SystemExit("❌ تأكد من إعداد المتغيرات API_ID, API_HASH, BOT_TOKEN, MY_CHAT_ID, DEST_CHANNEL_ID في ملف .env")

# -------------------
# جلسات المستخدم والبوت
# -------------------
user_client = TelegramClient('user_session', API_ID, API_HASH)
bot_client = TelegramClient('bot_session', API_ID, API_HASH)

# -------------------
# حالة ومخزن تقارير
# -------------------
cancel_delete = False
last_report = None

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
        try:
            return int(raw)
        except:
            raise ValueError("Channel ID غير صالحة.")
    if raw.isdigit():
        return int(f"-100{raw}")
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if digits:
        return int(f"-100{digits}")
    raise ValueError("Channel ID غير صالحة.")

# -------------------
# تقسيم وإرسال التقرير كنصوص (ذكي)
# -------------------
async def send_report_as_text_chunks(report_path: str, target_id: int):
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()

        limit = 4096
        parts = []
        current = ""

        for line in content.splitlines(keepends=True):
            if len(current) + len(line) > limit:
                parts.append(current)
                current = ""
            current += line
        if current:
            parts.append(current)

        for i, part in enumerate(parts, 1):
            await bot_client.send_message(
                target_id,
                f"📑 جزء {i}/{len(parts)} من التقرير:\n\n{part}"
            )
    except Exception as e:
        await bot_client.send_message(target_id, f"[!] خطأ أثناء إرسال نص التقرير: {repr(e)}")

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
        return None, None, None, f"[!] خطأ أثناء الفحص: {repr(e)}"

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
            original = msgs[-1]  # الاحتفاظ بالأقدم
            f.write(f"🔗 الأصل: https://t.me/c/{str(channel_id)[4:]}/{original.id}\n")
            for dup in msgs[:-1]:
                f.write(f"   ↳ مكرر: https://t.me/c/{str(channel_id)[4:]}/{dup.id}\n")
                delete_ids.append(dup.id)
            f.write("\n")

    # إرسال التقرير كملف
    await bot_client.send_file(MY_CHAT_ID, report_name, caption="✅ تم الانتهاء من الفحص — تقرير مفصل:")

    # عرض أزرار نعم / لا لإرسال نسخة النصوص
    buttons = [
        [Button.inline("نعم ✅", b"send_text_yes"), Button.inline("لا ❌", b"send_text_no")]
    ]
    await bot_client.send_message(
        MY_CHAT_ID,
        "📌 هل ترغب بإرسال نسخة التقرير مقسمة بالنصوص أيضًا؟",
        buttons=buttons
    )

    return report_name, delete_ids, duplicate_groups, None

# -------------------
# بقية الدوال: backup_duplicates, delete_messages_in_batches, send_welcome
# -------------------
async def backup_duplicates(channel_id, delete_ids, dest_channel_id):
    batch_size = 10
    sorted_ids = sorted(delete_ids)

    for i in range(0, len(sorted_ids), batch_size):
        batch_ids = sorted_ids[i:i+batch_size]
        messages_to_send = []
        for msg_id in batch_ids:
            msg = await user_client.get_messages(channel_id, ids=msg_id)
            if getattr(msg, "photo", None) or getattr(msg, "video", None):
                messages_to_send.append(msg)
        if messages_to_send:
            try:
                await user_client.send_file(dest_channel_id, messages_to_send, silent=True)
            except Exception as e:
                print(f"[!] خطأ أثناء النسخ الاحتياطي: {repr(e)}")
        await asyncio.sleep(5)

async def delete_messages_in_batches(channel_id, msg_ids, batch_size=100, delay=50):
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

async def send_welcome(target_id):
    welcome_text = (
        "🤖 مرحباً بك في بوت إدارة الملفات المكررة!\n\n"
        "📌 الأوامر المتاحة:\n"
        "1) /scan <CHANNEL_ID> [FIRST_MSG_ID] [TYPE]\n"
        "2) /scan_delete <CHANNEL_ID> [FIRST_MSG_ID] [TYPE]\n"
        "3) /stats -> إرسال آخر تقرير محفوظ\n"
        "4) /cancel -> إلغاء عملية الحذف أثناء التنفيذ\n"
        "⚙️ TYPE: all | document | video | audio | photo"
    )
    await bot_client.send_message(target_id, "[✓] البوت جاهز لاستقبال الأوامر.")
    await bot_client.send_message(target_id, welcome_text)

# -------------------
# معالج ضغط أزرار نعم / لا
# -------------------
@bot_client.on(events.CallbackQuery)
async def callback_handler(event):
    global last_report
    if not last_report or not os.path.exists(last_report):
        await event.answer("❌ لا يوجد تقرير لإرسال نسخة النصوص منه.")
        return

    if event.data == b"send_text_yes":
        await event.edit("📌 جاري إرسال نسخة التقرير كنصوص مقسمة...")
        await send_report_as_text_chunks(last_report, MY_CHAT_ID)
    elif event.data == b"send_text_no":
        await event.edit("❌ تم تجاهل نسخة النصوص.")
    else:
        await event.answer()

# -------------------
# معالج رسائل البوت
# -------------------
@bot_client.on(events.NewMessage(from_users=MY_CHAT_ID))
async def handler(event):
    global cancel_delete, last_report
    cmd = event.text.strip()
    if cmd.startswith("/start"):
        await send_welcome(MY_CHAT_ID)
    elif cmd.startswith("/cancel"):
        cancel_delete = True
    elif cmd.startswith("/scan"):
        args = cmd.split()
        if len(args) < 2:
            await bot_client.send_message(MY_CHAT_ID, "❌ استخدم: /scan <CHANNEL_ID> [FIRST_MSG_ID] [TYPE]")
            return
        channel_id = normalize_channel_id(args[1])
        first_msg = int(args[2]) if len(args) > 2 else 1
        ftype = args[3] if len(args) > 3 else "all"
        report_name, delete_ids, groups, err = await scan_channel(channel_id, first_msg, ftype)
        if err:
            await bot_client.send_message(MY_CHAT_ID, err)
        else:
            last_report = report_name

# -------------------
# Main
# -------------------
async def main():
    await user_client.start()
    await bot_client.start(bot_token=BOT_TOKEN)
    print("🤖 البوت جاهز للعمل.")
    await bot_client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
