#!/usr/bin/env python3
# dup_bot_backup_delete.py
# Requires: telethon, python-dotenv
# pip install telethon python-dotenv

import os
import asyncio
import math
import time
from datetime import datetime
from telethon import TelegramClient, events
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
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID"))        # معرفك الرقمي
DEST_CHANNEL_ID = int(os.getenv("DEST_CHANNEL_ID"))  # قناة النسخ الاحتياطي

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

    # تصفية مجموعات التكرار
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
            # msgs مرتبة من الأحدث للأقدم، نحتفظ بالأقدم (آخر رسالة)
            original = msgs[-1]
            f.write(f"🔗 الأصل: https://t.me/c/{str(channel_id)[4:]}/{original.id}\n")
            for dup in msgs[:-1]:  # حذف الأحدث
                f.write(f"   ↳ مكرر: https://t.me/c/{str(channel_id)[4:]}/{dup.id}\n")
                delete_ids.append(dup.id)
            f.write("\n")

    return report_name, delete_ids, duplicate_groups, None

# -------------------
# نسخ الوسائط المكررة إلى قناة الوجهة (ألبومات من 10 صور/فيديو/صوتية فقط)
# -------------------
# -------------------
# نسخ الوسائط المكررة إلى قناة الوجهة (ألبومات من 10 صور/فيديو/صوتية فقط، حسب ترتيب الرسائل)
# -------------------
async def backup_duplicates(channel_id, delete_ids, dest_channel_id):
    batch_size = 10
    # ترتيب الرسائل حسب ID تصاعدياً
    sorted_ids = sorted(delete_ids)

    for i in range(0, len(sorted_ids), batch_size):
        batch_ids = sorted_ids[i:i+batch_size]
        messages_to_send = []
        for msg_id in batch_ids:
            msg = await user_client.get_messages(channel_id, ids=msg_id)
            # إضافة فقط الصور والفيديو والصوتيات
            if getattr(msg, "photo", None) or getattr(msg, "video", None):
                messages_to_send.append(msg)
        if messages_to_send:
            try:
                # إرسال الألبوم بالكامل دفعة واحدة
                await user_client.send_file(dest_channel_id, messages_to_send, silent=True)
                print(f"📦 تم إرسال ألبوم {i//batch_size + 1} يحتوي على {len(messages_to_send)} ملف/صورة/فيديو/صوتية")
            except Exception as e:
                print(f"[!] خطأ أثناء النسخ الاحتياطي: {repr(e)}")
        # تأخير 5 ثوانٍ قبل الألبوم التالي
        await asyncio.sleep(10)

# -------------------
# حذف بالدفعات مع تحديث تقدم
# -------------------
async def delete_messages_in_batches(channel_id, msg_ids, batch_size=100, delay=50):
    global cancel_delete
    total = len(msg_ids)
    deleted_count = 0
    start_time = time.time()
    progress_msg = await bot_client.send_message(MY_CHAT_ID, f"🗑 بدء حذف: 0/{total} رسالة (0%) ...")
    await asyncio.sleep(10)
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
# رسالة ترحيب وتعليمات
# -------------------
async def send_welcome(target_id):
    welcome_text = (
        "🤖 مرحباً بك في بوت إدارة الملفات المكررة!\n\n"
        "📌 الأوامر المتاحة:\n\n"
        "1) /scan <CHANNEL_ID> [FIRST_MSG_ID] [TYPE]\n"
        "   - فحص القناة فقط بدون حذف.\n"
        "2) /scan_delete <CHANNEL_ID> [FIRST_MSG_ID] [TYPE]\n"
        "   - فحص وحذف المكررات بعد النسخ الاحتياطي.\n"
        "3) أوصيغة سريعة (بدون /):\n"
        "   - 1234567890 5 delete\n"
        "   - 1234567890 delete\n"
        "   - 1234567890 5 photo\n"
        "4) /stats  -> إرسال آخر تقرير محفوظ (إذا وُجد)\n"
        "5) /cancel -> إلغاء عملية الحذف أثناء التنفيذ\n"
        "⚙️ TYPE: all | document | video | audio | photo\n"
        "ملاحظة: يمكنك إرسال رقم القناة بدون -100 وسيتم إضافتها تلقائياً."
    )
    await bot_client.send_message(target_id, "[✓] البوت جاهز لاستقبال الأوامر.")
    await bot_client.send_message(target_id, welcome_text)

# -------------------
# معالج رسائل البوت
# -------------------
@bot_client.on(events.NewMessage(from_users=MY_CHAT_ID))
async def handler(event):
    global cancel_delete, last_report
    raw_text = (event.raw_text or "").strip()
    if not raw_text:
        await event.reply("❌ لا يوجد نص. أرسل /help أو مثال: `1234567890 5 delete`")
        return

    text = raw_text.strip()
    lower = text.lower().strip()
    parts = lower.split()
    # دعم أوامر /slash
    if parts[0].startswith("/"):
        cmd = parts[0]
        if cmd == "/cancel":
            cancel_delete = True
            await event.reply("❌ تم طلب إلغاء الحذف. سيتم الإيقاف في أقرب نقطة آمنة.")
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
        # /scan or /scan_delete parsing
        try:
            channel_raw = parts[1]
            channel_id = normalize_channel_id(channel_raw)
            first_msg = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            file_type = parts[3] if len(parts) > 3 else "all"
        except:
            await event.reply("❌ صيغة غير صحيحة.\nمثال: /scan 1234567890 5 document")
            return
        do_delete = (cmd == "/scan_delete")
    else:
        # صيغة المدخل الحر: "1234567890 5 delete"
        try:
            channel_raw = parts[0]
            channel_id = normalize_channel_id(channel_raw)
            first_msg = 1
            file_type = "all"
            do_delete = False
            for token in parts[1:]:
                if token.isdigit() and first_msg == 1:
                    first_msg = int(token)
                    continue
                if token in ("delete", "del"):
                    do_delete = True
                    continue
                if token in ("all", "document", "video", "audio", "photo"):
                    file_type = token
        except:
            await event.reply("❌ صيغة غير صحيحة. مثال: `1234567890 5 delete`")
            return

    # إبلاغ المستخدم بالبدء
    await bot_client.send_message(MY_CHAT_ID, f"🚀 بدء فحص القناة `{channel_id}` من الرسالة `{first_msg}` (نوع: `{file_type}`) — حذف: {do_delete}")

    report, delete_ids, duplicate_groups, error = await scan_channel(channel_id, first_msg, file_type)
    if error:
        await bot_client.send_message(MY_CHAT_ID, error)
        return

    last_report = report
    await bot_client.send_file(MY_CHAT_ID, report, caption="✅ تم الانتهاء من الفحص — تقرير مفصل:")

    # إرسال ملخص الإحصائيات بعد التقرير
    total_scanned = sum(len(msgs) for msgs in duplicate_groups.values()) + (first_msg-1)
    summary_text = (
        f"📌 القناة: {channel_id}\n"
        f"⏱ الوقت المستغرق: {round(time.time() - time.time(),2)} ثانية\n"
        f"🔍 الرسائل المفحوصة: {total_scanned}\n"
        f"📂 مجموعات التكرار: {len(duplicate_groups)}\n"
        f"📑 الرسائل المكررة: {sum(len(msgs)-1 for msgs in duplicate_groups.values())}\n"
        f"📦 أكبر ملف مكرر: {human_size(max(duplicate_groups) if duplicate_groups else 0)}\n"
        f"📦 أصغر ملف مكرر: {human_size(min(duplicate_groups) if duplicate_groups else 0)}"
    )
    await bot_client.send_message(MY_CHAT_ID, summary_text)

    # إذا مطلوب حذف ونوجد عناصر للحذف
    if do_delete and delete_ids:
        await bot_client.send_message(MY_CHAT_ID, f"💾 نسخ الملفات المكررة إلى قناة الوجهة قبل الحذف ...")
        await backup_duplicates(channel_id, delete_ids, DEST_CHANNEL_ID)
        await bot_client.send_message(MY_CHAT_ID, f"🗑 بدء الحذف بعد النسخ ...")
        deleted, duration = await delete_messages_in_batches(channel_id, delete_ids, batch_size=100, delay=50)
        await bot_client.send_message(MY_CHAT_ID, f"✅ انتهت عملية الحذف. المحذوف: {deleted} رسالة. المدة: {duration} ثانية.")
    elif do_delete:
        await bot_client.send_message(MY_CHAT_ID, "ℹ️ لا توجد ملفات مكررة للحذف.")
    else:
        await bot_client.send_message(MY_CHAT_ID, "ℹ️ تم الانتهاء من الفحص (لم يتم حذف أي رسالة).")

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
