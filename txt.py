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
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID"))  # معرفك الرقمي (مثال: 123456789)

if not all([API_ID, API_HASH, BOT_TOKEN, MY_CHAT_ID]):
    raise SystemExit("❌ تأكد من إعداد المتغيرات API_ID, API_HASH, BOT_TOKEN, MY_CHAT_ID في ملف .env")

# -------------------
# جلسات المستخدم والبوت
# -------------------
user_client = TelegramClient('user_session', API_ID, API_HASH)
bot_client = TelegramClient('bot_session', API_ID, API_HASH)  # سنبدأه مع bot_token لاحقاً

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
    """
    يقبل:
      - "1234567890"  -> يحول إلى -1001234567890
      - "-1001234567890" -> يبقي كما هو
      - "1001234567890" -> يقبله (يصبح 1001234567890)
      - "-1234567890" -> يقبله
    """
    raw = raw.strip()
    # إزالة أية رموز غير رقمية باستثناء -
    # لكن نخلي المستخدم يكتب رقم نظيف عادة
    if raw.startswith("-100") or raw.startswith("-"):
        try:
            return int(raw)
        except:
            raise ValueError("Channel ID غير صالحة.")
    if raw.isdigit():
        # أضف -100 كبادئة
        return int(f"-100{raw}")
    # محاولة إزالة أي مسافات أو رموز
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
            # نتأكد أن الرسالة تحتوي ملف وحجم
            if not getattr(msg, "file", None) or not getattr(msg.file, "size", None):
                continue

            # فلترة حسب النوع
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
        # نُبلّغ المستخدم وننتظر
        await bot_client.send_message(MY_CHAT_ID, f"[!] FloodWait — انتظر {e.seconds} ثانية ثم أستكمل.")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        return None, None, f"[!] خطأ أثناء الفحص: {repr(e)}"

    # نختار المجموعات التي تحتوي أكثر من رسالة
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

    # كتابة التقرير المنسق
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

        # ترتيب حسب الحجم تنازلياً (أكبر أول)
        for size, msgs in sorted(duplicate_groups.items(), key=lambda x:x[0], reverse=True):
            f.write(f"📦 الحجم: {human_size(size)} ({size} B)\n")
            f.write(f"🔗 الأصل: https://t.me/c/{str(channel_id)[4:]}/{msgs[0].id}\n")
            for dup in msgs[1:]:
                f.write(f"   ↳ مكرر: https://t.me/c/{str(channel_id)[4:]}/{dup.id}\n")
                delete_ids.append(dup.id)
            f.write("\n")

    return report_name, delete_ids, None

# -------------------
# حذف بالدفعات مع تحديث رسالة تقدم واحدة
# -------------------
async def delete_messages_in_batches(channel_id, msg_ids, batch_size=100, delay=60):
    global cancel_delete
    total = len(msg_ids)
    deleted_count = 0
    start_time = time.time()

    # إرسال رسالة تقدم أولية قابلة للتعديل
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
            # نستمر بعد إبلاغ المستخدم
        await asyncio.sleep(delay)

    duration = round(time.time() - start_time, 2)
    await bot_client.edit_message(progress_msg, f"✅ انتهى الحذف. المحذوف الكلي: {deleted_count}/{total} رسالة في {duration} ثانية.")
    return deleted_count, duration

# -------------------
# معالج رسائل البوت: يقبل أوامر /slash وكذلك المدخل الحر (مثال: 1234567890 5 delete)
# -------------------
@bot_client.on(events.NewMessage(from_users=MY_CHAT_ID))
async def handler(event):
    global cancel_delete, last_report
    raw_text = (event.raw_text or "").strip()
    if not raw_text:
        await event.reply("❌ لا يوجد نص. أرسل: /help أو مثال: `1234567890 5 delete`")
        return

    text = raw_text.strip()
    lower = text.lower().strip()
    parts = lower.split()

    # دعم أوامر الشرط المسبق
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
        if cmd not in ("/scan", "/scan_delete"):
            await event.reply("❌ أمر غير معروف. استخدم /help لعرض الأوامر.")
            return

        # /scan or /scan_delete parsing
        try:
            channel_raw = parts[1]
            channel_id = normalize_channel_id(channel_raw)
            first_msg = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            file_type = parts[3] if len(parts) > 3 else "all"
        except Exception as e:
            await event.reply("❌ صيغة غير صحيحة.\nمثال: /scan 1234567890 5 document\nTYPE: all|document|video|audio|photo")
            return

        do_delete = (cmd == "/scan_delete")
    else:
        # صيغة المدخل الحر: يمكن أن تكون "1234567890 5 delete" أو "1234567890 delete" أو "1234567890 5 photo"
        try:
            # اجعلنا مرنين: الأول معرف القناة
            channel_raw = parts[0]
            channel_id = normalize_channel_id(channel_raw)
            # الآن نبحث عن first_msg_id و/أو كلمة delete أو file_type
            first_msg = 1
            file_type = "all"
            do_delete = False

            # تفحص الباقي
            for token in parts[1:]:
                if token.isdigit():
                    # يأخذ أول رقم يجده كـ FIRST_MSG_ID
                    if first_msg == 1:
                        first_msg = int(token)
                        continue
                if token in ("delete", "del"):
                    do_delete = True
                    continue
                if token in ("all", "document", "video", "audio", "photo"):
                    file_type = token
                    continue
                # تجاهل أي كلمات أخرى
        except Exception as e:
            await event.reply("❌ صيغة غير صحيحة. مثال: `1234567890 5 delete` أو `/scan 1234567890 5 document`")
            return

    # نعرف الآن: channel_id, first_msg, file_type, do_delete
    # إبلاغ المستخدم بالبدء
    await bot_client.send_message(MY_CHAT_ID, f"🚀 بدء فحص القناة `{channel_id}` من الرسالة `{first_msg}` (نوع: `{file_type}`) — حذف: {do_delete}")

    report, delete_ids, error = await scan_channel(channel_id, first_msg, file_type)
    if error:
        await bot_client.send_message(MY_CHAT_ID, error)
        return

    # حفظ آخر تقرير وإرساله
    last_report = report
    await bot_client.send_file(MY_CHAT_ID, report, caption="✅ تم الانتهاء من الفحص — تقرير مفصل:")
    # -------------------
    # إرسال ملخص الإحصائيات بعد التقرير
    # -------------------
    total_scanned = sum(len(msgs) for msgs in duplicate_groups.values()) + (total_scanned - sum(len(msgs) for msgs in duplicate_groups.values()))
    summary_text = (
        f"📌 القناة: {channel_id}\n"
        f"⏱ الوقت المستغرق: {round(time.time() - start_time,2)} ثانية\n"
        f"🔍 الرسائل المفحوصة: {total_scanned}\n"
        f"📂 مجموعات التكرار: {len(duplicate_groups)}\n"
        f"📑 الرسائل المكررة: {sum(len(msgs)-1 for msgs in duplicate_groups.values())}\n"
        f"📦 أكبر ملف مكرر: {human_size(max_size)}\n"
        f"📦 أصغر ملف مكرر: {human_size(min_size)}"
    )
    await bot_client.send_message(MY_CHAT_ID, summary_text)

    # إذا مطلوب حذف ونوجد عناصر للحذف
    if do_delete:
        if not delete_ids:
            await bot_client.send_message(MY_CHAT_ID, "ℹ️ لا توجد ملفات مكررة للحذف.")
            return

        # تأكيد قصير قبل البدء (يمكن حذفه أو تعديله)
        await bot_client.send_message(MY_CHAT_ID, f"🗑 سيتم حذف {len(delete_ids)} رسالة مكررة على دفعات (كل دفعة {100} رسالة، تأخير 60s). لإلغاء أثناء التنفيذ أرسل /cancel .")
        # بدء الحذف
        deleted, duration = await delete_messages_in_batches(channel_id, delete_ids, batch_size=100, delay=60)
        await bot_client.send_message(MY_CHAT_ID, f"✅ انتهت عملية الحذف. المحذوف: {deleted} رسالة. المدة: {duration} ثانية.")
    else:
        # لا حذف — انتهينا
        await bot_client.send_message(MY_CHAT_ID, "ℹ️ تم الانتهاء من الفحص (لم يتم حذف أي رسالة).")

# -------------------
# رسالة ترحيب مع تعليمات الأوامر (تُرسل عند التشغيل و/أو بطلب /help)
# -------------------
async def send_welcome(target_id):
    welcome_text = (
        "🤖 مرحباً بك في بوت إدارة الملفات المكررة!\n\n"
        "📌 الأوامر المتاحة:\n\n"
        "1) /scan <CHANNEL_ID> [FIRST_MSG_ID] [TYPE]\n"
        "   - فحص القناة فقط بدون حذف.\n"
        "   - مثال: /scan 1234567890 5 document\n\n"
        "2) /scan_delete <CHANNEL_ID> [FIRST_MSG_ID] [TYPE]\n"
        "   - فحص وحذف المكررات على دفعات.\n"
        "   - مثال: /scan_delete 1234567890 5 photo\n\n"
        "3) أوصيغة سريعة (بدون /):\n"
        "   - 1234567890 5 delete\n"
        "   - 1234567890 delete\n"
        "   - 1234567890 5 photo\n\n"
        "4) /stats  -> إرسال آخر تقرير محفوظ (إذا وُجد)\n"
        "5) /cancel -> إلغاء عملية الحذف أثناء التنفيذ\n\n"
        "⚙️ TYPE يمكن أن يكون: all | document | video | audio | photo\n\n"
        "ملاحظة: يمكنك إرسال رقم القناة بدون بادئة -100 (مثلاً: 1234567890) وسيتم إضافة -100 تلقائياً."
    )
    await bot_client.send_message(target_id, "[✓] البوت جاهز لاستقبال الأوامر.")
    await bot_client.send_message(target_id, welcome_text)

# -------------------
# بدء التشغيل
# -------------------
async def main():
    # بدء جلسة المستخدم (لتصفح/حذف الرسائل)
    await user_client.start()
    # بدء جلسة البوت باستخدام Bot Token
    await bot_client.start(bot_token=BOT_TOKEN)
    # إرسال رسالة ترحيب في المحادثة
    await send_welcome(MY_CHAT_ID)
    # لا نغلق الحدث — يبقى شغال
    await asyncio.Future()

if __name__ == "__main__":
    # تشغيل ضمن نفس الـ event loop الخاص بـ Telethon
    user_client.loop.run_until_complete(main())
