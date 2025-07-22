# --- بداية الكود الرئيسي للبوت أو السكربت ---
import os
import asyncio
import time
from pyrogram import Client
from pyrogram.errors import FloodWait # ملاحظة: تختلف هنا
# من Pyrogram لا نحتاج إلى StringSession، Client يتعامل مع الجلسات مباشرة

# 1. إعدادات تيليجرام - قراءة المتغيرات مباشرة من البيئة
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
PYRO_SESSION_STRING = os.getenv('PYRO_SESSION_STRING') # هذا هو متغير جلستك الصحيح الآن
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0))
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))
LAST_MSG_ID = int(os.getenv('LAST_MSG_ID', 0))

# للتحقق من أن المتغيرات الأساسية قد تم تحميلها
if not all([API_ID, API_HASH, PYRO_SESSION_STRING, CHANNEL_ID, CHANNEL_ID_LOG, FIRST_MSG_ID, LAST_MSG_ID]):
    print("❌ خطأ: بعض المتغيرات البيئية الأساسية غير موجودة أو فارغة.")
    print(f"تحقق من API_ID={API_ID}, API_HASH={API_HASH}, PYRO_SESSION_STRING={PYRO_SESSION_STRING is not None}, CHANNEL_ID={CHANNEL_ID}, CHANNEL_ID_LOG={CHANNEL_ID_LOG}, FIRST_MSG_ID={FIRST_MSG_ID}, LAST_MSG_ID={LAST_MSG_ID}")
    exit(1)

# 2. إحصائيات وأداء
total_reported_duplicates = 0
total_duplicate_messages = 0
processing_times = []
start_time = None

async def collect_files(client, channel_id, first_msg_id, last_msg_id):
    """إصدار محسّن لجمع الملفات يعتمد على حجم الملف، ضمن نطاق IDs محدد."""
    global processing_times
    file_dict = {}
    
    start_collect = time.time()
    
    lock = asyncio.Lock()
    
    print(f"جاري مسح الرسائل في القناة ID: {channel_id} من الرسالة {first_msg_id} إلى {last_msg_id}...")
    messages_scanned = 0
    
    # التغيير هنا: استخدام client.iter_messages() من Pyrogram
    # for message in client.iter_messages(chat_id=channel_id, offset_id=first_msg_id -1): # offset_id للبدء قبل رسالة معينة
    #     # هنا يجب أن نحدد توقفًا باستخدام `messages_scanned` و `last_msg_id`
    #     if message.id > last_msg_id:
    #         break

    # Pyrogram ليس لديها min_id و max_id مباشرين في iter_messages مثل Telethon
    # سنحتاج إلى تكرار كل الرسائل ومن ثم تطبيق الفلترة يدوياً
    
    # حل بديل لـ min_id و max_id في Pyrogram iter_messages
    # يمكن استخدام offset_id للبدء من رسالة معينة أو عدد محدد
    
    # لضمان الفحص ضمن النطاق بشكل فعال مع Pyrogram،
    # سنحتاج لضبط عدد الرسائل (limit) وتقليب الرسائل إذا لزم الأمر،
    # أو استخدام offset_id مع التحكم اليدوي.

    # النهج الأكثر موثوقية: التكرار للخلف حتى first_msg_id إذا كان كبيراً
    # أو التكرار للأمام وتطبيق الشرط يدويًا.

    # إذا كان النطاق صغيرًا (مثل 1 إلى 1000)، يمكننا تكرار الأحدث وتجاهل القديم
    # وإذا كان النطاق كبيراً (مثل 1000000 إلى 1001000)، نستخدم offset_id

    # لتبسيط الكود وحل المشكلة الحالية، سنستخدم طريقة أكثر عمومية:
    # التكرار عبر الرسائل بترتيب تنازلي (الأحدث أولاً) وتجاهل التي هي خارج النطاق.
    
    # لعدد الرسائل, limit: يمكن أن يكون رقمًا كبيرًا جداً، أو يمكننا التحكم في ذلك يدوياً
    # بما أننا نحدد First_Msg_ID و Last_Msg_ID، فالمفتاح هو معالجة الرسائل
    # التي تقع ضمن هذا النطاق فقط.

    # أفضل طريقة هي استخدام client.get_messages لجلب مجموعة من الرسائل أو التكرار العكسي إذا كان first_msg_id أصغر
    
    # هذا هو التغيير الرئيسي في منطق التكرار لـ Pyrogram
    async for message in client.iter_messages(chat_id=channel_id):
        if message.id > last_msg_id:
            # الرسالة أحدث من النطاق المحدد، ننتقل للتي قبلها
            continue
        elif message.id < first_msg_id:
            # الرسالة أقدم من النطاق المحدد، توقفنا عن البحث
            break
        
        messages_scanned += 1
        
        if message.document or message.photo or message.video or message.audio: # تأكد من التعامل مع أنواع الملفات المختلفة
            file_size = 0
            if message.document and message.document.file_size:
                file_size = message.document.file_size
            elif message.photo and message.photo.file_size:
                file_size = message.photo.file_size
            elif message.video and message.video.file_size:
                file_size = message.video.file_size
            elif message.audio and message.audio.file_size:
                file_size = message.audio.file_size

            if file_size > 0: # تأكد أن الملف له حجم فعلاً
                async with lock:
                    if file_size in file_dict:
                        file_dict[file_size].append(message.id)
                    else:
                        file_dict[file_size] = [message.id]
        
        if messages_scanned % 500 == 0:
            print(f"تم مسح {messages_scanned} رسالة (IDs من {first_msg_id} إلى {last_msg_id})...")

    processing_time = time.time() - start_collect
    processing_times.append(('collect_files', processing_time))
    print(f"تم الانتهاء من مسح الرسائل. تم جمع {len(file_dict)} إدخال حجم ملف.")
    return file_dict

async def send_duplicate_links_report(client, source_chat_id, destination_chat_id, message_ids):
    """
    يرسل تقريراً بروابط الرسائل المكررة إلى قناة السجل، مع تأخير زمني.
    Pyrogram لا يدعم روابط t.me/c/id/msg_id مباشرة بهذا التنسيق بدون User ID,
    ولكن هذا التنسيق هو لـ Desktop client أو web (Telegram WebK)
    والرابط هو `https://t.me/c/<channel_id_without_supergroup_prefix>/<message_id>`
    يجب حذف `-100` أو تحويلها من -100xxxxxxxxxx إلى xxxxxxxxxx
    """
    global total_reported_duplicates, total_duplicate_messages
    
    if not message_ids or len(message_ids) < 2:
        return

    original_msg_id = message_ids[0]
    duplicate_msg_ids = message_ids[1:]

    # تحويل CHANNEL_ID من -100 إلى ما يناسب الروابط (إزالة -100)
    # للحصول على ID القناة بدون prefix (هذا ما يتوقعه t.me/c/)
    # مثال: -1001234567890 تتحول إلى 1234567890
    if str(source_chat_id).startswith('-100'):
        clean_source_chat_id = str(source_chat_id)[4:]
    else:
        clean_source_chat_id = str(source_chat_id) # إذا كانت ID بوت أو يوزر

    total_reported_duplicates += 1
    total_duplicate_messages += len(duplicate_msg_ids)
    
    report_message = f"📌 **تم العثور على ملفات مكررة (حسب الحجم)!**\n\n"
    report_message += f"🔗 **الرسالة الأصلية:** `https://t.me/c/{clean_source_chat_id}/{original_msg_id}`\n\n"
    report_message += "**النسخ المكررة:**\n"

    for msg_id in duplicate_msg_ids:
        report_message += f"- `https://t.me/c/{clean_source_chat_id}/{msg_id}`\n"
    
    try:
        start_send = time.time()
        # client.send_message() في Pyrogram
        await client.send_message(chat_id=destination_chat_id, text=report_message)
        print(f"✅ تم إرسال تقرير عن {len(duplicate_msg_ids)} تكرار.")
    except FloodWait as e: # استخدام FloodWait من Pyrogram
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
        await client.send_message(chat_id=CHANNEL_ID_LOG, text=report) # استخدام chat_id و text
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
    # تهيئة عميل Pyrogram
    async with Client(
        name="my_pyrogram_session", # أي اسم للجلسة (سيُستخدم لإنشاء ملف .session)
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=PYRO_SESSION_STRING, # هنا نستخدم سلسلة الجلسة الخاصة بـ Pyrogram
        in_memory=True # هذا سيمنع Pyrogram من حفظ ملف الجلسة على القرص
    ) as client:
        print("🚀 اتصال ناجح بالتيليجرام باستخدام Pyrogram.")
        me = await client.get_me() # لاختبار الاتصال
        print(f"متصل كـ: {me.first_name} (@{me.username})")
        await find_and_report_duplicates(client, CHANNEL_ID)

if __name__ == '__main__':
    print("🔹 بدء التشغيل...")
    # لضمان عدم وجود حدث حلقه (event loop) سابق، خاصة في بيئات مثل Colab
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
