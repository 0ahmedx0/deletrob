# --- بداية الكود الرئيسي للبوت أو السكربت ---
import os
import asyncio
import time
from pyrogram import Client
from pyrogram.errors import FloodWait

# 1. إعدادات تيليجرام - قراءة المتغيرات مباشرة من البيئة
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN') # 🚨🚨🚨 قراءة توكن البوت 🚨🚨🚨

CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0))
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))
LAST_MSG_ID = int(os.getenv('LAST_MSG_ID', 0))

# للتحقق من أن المتغيرات الأساسية قد تم تحميلها
# تأكد أنك تتحقق من BOT_TOKEN وليس PYRO_SESSION_STRING
if not all([API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID, CHANNEL_ID_LOG, FIRST_MSG_ID, LAST_MSG_ID]):
    print("❌ خطأ: بعض المتغيرات البيئية الأساسية غير موجودة أو فارغة.")
    print(f"تحقق من API_ID={API_ID}, API_HASH={API_HASH}, BOT_TOKEN={BOT_TOKEN is not None}, CHANNEL_ID={CHANNEL_ID}, CHANNEL_ID_LOG={CHANNEL_ID_LOG}, FIRST_MSG_ID={FIRST_MSG_ID}, LAST_MSG_ID={LAST_MSG_ID}")
    exit(1)

# 2. إحصائيات وأداء
total_reported_duplicates = 0
total_duplicate_messages = 0
processing_times = []
start_time = None

# باقي الدوال (collect_files, send_duplicate_links_report, send_statistics, find_and_report_duplicates)
# لن تتغير من الكود الأخير الذي يعمل بـ Pyrogram، فقط ستعمل الآن مع بوت

async def collect_files(client, channel_id, first_msg_id, last_msg_id):
    """إصدار محسّن لجمع الملفات يعتمد على حجم الملف، ضمن نطاق IDs محدد."""
    global processing_times
    file_dict = {}
    
    start_collect = time.time()
    
    lock = asyncio.Lock()
    
    print(f"جاري مسح الرسائل في القناة ID: {channel_id} من الرسالة {first_msg_id} إلى {last_msg_id}...")
    messages_scanned = 0
    
    async for message in client.get_chat_history(chat_id=channel_id):
        if message.id < first_msg_id:
            break
        
        if message.id > last_msg_id:
            continue
        
        messages_scanned += 1
        
        file_size = 0
        if message.document and message.document.file_size:
            file_size = message.document.file_size
        elif message.photo and message.photo.file_size:
            file_size = message.photo.file_size
        elif message.video and message.video.file_size:
            file_size = message.video.file_size
        elif message.audio and message.audio.file_size:
            file_size = message.audio.file_size

        if file_size > 0:
            async with lock:
                if file_size in file_dict:
                    file_dict[file_size].append(message.id)
                else:
                    file_dict[file_size] = [message.id]
        
        if messages_scanned % 500 == 0:
            print(f"تم مسح {messages_scanned} رسالة (داخل النطاق). الرسالة الحالية ID: {message.id}")

    processing_time = time.time() - start_collect
    processing_times.append(('collect_files', processing_time))
    print(f"تم الانتهاء من مسح الرسائل. تم جمع {len(file_dict)} إدخال حجم ملف.")
    return file_dict

async def send_duplicate_links_report(client, source_chat_id, destination_chat_id, message_ids):
    global total_reported_duplicates, total_duplicate_messages
    
    if not message_ids or len(message_ids) < 2:
        return

    original_msg_id = message_ids[0]
    duplicate_msg_ids = message_ids[1:]

    if str(source_chat_id).startswith('-100'):
        clean_source_chat_id = str(source_chat_id)[4:]
    else:
        clean_source_chat_id = str(source_chat_id)

    total_reported_duplicates += 1
    total_duplicate_messages += len(duplicate_msg_ids)
    
    report_message = f"📌 **تم العثور على ملفات مكررة (حسب الحجم)!**\n\n"
    report_message += f"🔗 **الرسالة الأصلية:** `https://t.me/c/{clean_source_chat_id}/{original_msg_id}`\n\n"
    report_message += "**النسخ المكررة:**\n"

    for msg_id in duplicate_msg_ids:
        report_message += f"- `https://t.me/c/{clean_source_chat_id}/{msg_id}`\n"
    
    try:
        start_send = time.time()
        await client.send_message(chat_id=destination_chat_id, text=report_message)
        print(f"✅ تم إرسال تقرير عن {len(duplicate_msg_ids)} تكرار.")
    except FloodWait as e:
        print(f"⏳ (تقرير الروابط) انتظر {e.value} ثانية...")
        await asyncio.sleep(e.value + 1)
        try:
            await client.send_message(chat_id=destination_chat_id, text=report_message)
        except Exception as retry_e:
            print(f"⚠️ فشل إرسال تقرير الروابط بعد الانتظار: {retry_e}")
    except Exception as e:
        print(f"⚠️ خطأ أثناء إرسال تقرير الروابط: {e}")
    
    processing_times.append(('send_duplicate_links_report', time.time() - start_send))
    
    await asyncio.sleep(5)


async def send_statistics(client):
    """إرسال تقرير إحصائي مفصل"""
    global total_reported_duplicates, total_duplicate_messages, start_time
    
    total_time = time.time() - start_time
    avg_time = sum(t[1] for t in processing_times) / len(processing_times) if processing_times else 0
    
    slowest_tasks_str = ""
    if processing_times:
        sorted_times = sorted(processing_times, key=lambda x: x[1], reverse=True)
        for name, duration in sorted_times[:3]:
            slowest_tasks_str += f"- {name}: {duration:.2f} ثانية\n"
    else:
        slowest_tasks_str = "لا توجد مهام مسجلة."

    report = f"""
    📊 **تقرير الأداء النهائي** 📊
    ----------------------------
    • مجموعات التكرار التي تم الإبلاغ عنها: {total_reported_duplicates} 📝
    • إجمالي الرسائل المكررة المكتشفة: {total_duplicate_messages} 🔎 (باستثناء الأصول)
    • الوقت الكلي للعملية: {total_time:.2f} ثانية ⏱
    • متوسط وقت المهمة: {avg_time:.2f} ثانية ⚡
    • المهام الأبطأ: 
    {slowest_tasks_str}
    """
    
    try:
        await client.send_message(chat_id=CHANNEL_ID_LOG, text=report)
        print("✅ تم إرسال التقرير الإحصائي النهائي.")
    except FloodWait as e:
        print(f"⏳ (تقرير نهائي) انتظر {e.value} ثانية...")
        await asyncio.sleep(e.value + 1)
        try:
            await client.send_message(chat_id=CHANNEL_ID_LOG, text=report)
        except Exception as retry_e:
            print(f"⚠️ فشل إرسال التقرير النهائي بعد الانتظار: {retry_e}")
    except Exception as e:
        print(f"⚠️ خطأ أثناء إرسال التقرير النهائي: {e}")

async def find_and_report_duplicates(client, channel_id):
    global start_time
    start_time = time.time()
    
    print("🔍 بدأ تحليل الملفات في القناة (اعتمادًا على حجم الملف فقط)...")
    file_dict = await collect_files(client, channel_id, FIRST_MSG_ID, LAST_MSG_ID)
    
    print(f"⚡ بدأ إعداد تقارير الروابط للملفات المكررة. تم العثور على {len(file_dict)} ملفًا فريدًا حسب الحجم.")
    
    report_tasks = []
    
    for file_size, msg_ids in file_dict.items():
        if len(msg_ids) > 1:
            report_tasks.append(send_duplicate_links_report(client, channel_id, CHANNEL_ID_LOG, msg_ids))
    
    print(f"سيتم إرسال تقارير لـ {len(report_tasks)} مجموعة من التكرارات.")
    
    for task in report_tasks:
        await task
    
    await send_statistics(client)
    print(f"🏁 اكتملت العملية في {time.time()-start_time:.2f} ثانية.")

async def main():
    # 🚨🚨🚨 هذا هو التغيير الرئيسي في تهيئة العميل 🚨🚨🚨
    async with Client(
        name="my_duplicate_finder_bot", # اسم الجلسة للبوت
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN # تمرير توكن البوت
    ) as client:
        print("🚀 اتصال ناجح بالتيليجرام باستخدام Pyrogram.")
        me = await client.get_me() # ستُرجع معلومات عن البوت نفسه
        print(f"متصل كـ: {me.first_name} (@{me.username})")
        await find_and_report_duplicates(client, CHANNEL_ID)

if __name__ == '__main__':
    print("🔹 بدء التشغيل...")
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        print("💡 تم اكتشاف حلقة أحداث قائمة، تشغيل main كـ asyncio.create_task.")
        asyncio.create_task(main())
    else:
        asyncio.run(main())
# --- نهاية الكود الرئيسي للبوت أو السكربت ---
