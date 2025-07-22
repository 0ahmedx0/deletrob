# --- بداية الكود الرئيسي للبوت أو السكربت ---
import os
import asyncio
import time
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

# لا نستخدم load_dotenv() هنا، لأننا سنقوم بتعيين المتغيرات مباشرة في بيئة Colab.

# 1. إعدادات تيليجرام - قراءة المتغيرات مباشرة من البيئة
# استخدم int() للتحويل إلى أعداد صحيحة إذا كانت المتغيرات تمثل IDs رقمية.
# استخدم os.getenv() بدلاً من os.environ[] لتجنب الأخطاء إذا كان المتغير غير موجود.
API_ID = int(os.getenv('API_ID', 0)) # قيمة افتراضية 0 إذا لم يتم العثور
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('TELETHON_SESSION_STRING') # غيّرت الاسم ليكون أكثر وضوحًا
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0))
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))
LAST_MSG_ID = int(os.getenv('LAST_MSG_ID', 0))

# للتحقق من أن المتغيرات الأساسية قد تم تحميلها
if not all([API_ID, API_HASH, SESSION, CHANNEL_ID, CHANNEL_ID_LOG, FIRST_MSG_ID, LAST_MSG_ID]):
    print("❌ خطأ: بعض المتغيرات البيئية الأساسية غير موجودة أو فارغة.")
    print(f"تحقق من API_ID={API_ID}, API_HASH={API_HASH}, SESSION={SESSION is not None}, CHANNEL_ID={CHANNEL_ID}, CHANNEL_ID_LOG={CHANNEL_ID_LOG}, FIRST_MSG_ID={FIRST_MSG_ID}, LAST_MSG_ID={LAST_MSG_ID}")
    exit(1) # إنهاء السكربت إذا كانت المتغيرات ناقصة

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
    
    # استخدام asyncio.Lock لمنع شروط التنافس إذا تم توسيع معالجة الرسائل لاحقًا
    lock = asyncio.Lock()
    
    print(f"جاري مسح الرسائل في القناة ID: {channel_id} من الرسالة {first_msg_id} إلى {last_msg_id}...")
    messages_scanned = 0
    
    # `max_id` يستبعد الرسالة ذات المعرف `max_id` نفسها، لذا نضيف 1 لتضمينها.
    async for message in client.iter_messages(channel_id, min_id=first_msg_id, max_id=last_msg_id + 1):
        messages_scanned += 1
        
        # التأكد من أن الرسالة تحتوي على ملف وأن له حجم
        if message.file and hasattr(message.file, 'size'):
            file_size = message.file.size
            async with lock:
                if file_size in file_dict:
                    file_dict[file_size].append(message.id)
                else:
                    file_dict[file_size] = [message.id]
        
        if messages_scanned % 500 == 0:
            print(f"تم مسح {messages_scanned} رسالة حتى الآن...")

    processing_time = time.time() - start_collect
    processing_times.append(('collect_files', processing_time))
    print(f"تم الانتهاء من مسح الرسائل. تم جمع {len(file_dict)} إدخال حجم ملف.")
    return file_dict

async def send_duplicate_links_report(client, source_chat_id, destination_chat_id, message_ids):
    """
    يرسل تقريراً بروابط الرسائل المكررة إلى قناة السجل، مع تأخير زمني.
    """
    global total_reported_duplicates, total_duplicate_messages
    
    if not message_ids or len(message_ids) < 2: # تأكد أن هناك رسالة أصلية وتكرار واحد على الأقل
        return

    original_msg_id = message_ids[0]
    duplicate_msg_ids = message_ids[1:]

    total_reported_duplicates += 1
    total_duplicate_messages += len(duplicate_msg_ids)
    
    report_message = f"📌 **تم العثور على ملفات مكررة (حسب الحجم)!**\n\n"
    report_message += f"🔗 **الرسالة الأصلية:** `https://t.me/c/{str(source_chat_id)[4:]}/{original_msg_id}`\n\n"
    report_message += "**النسخ المكررة:**\n"

    for msg_id in duplicate_msg_ids:
        report_message += f"- `https://t.me/c/{str(source_chat_id)[4:]}/{msg_id}`\n"
    
    try:
        start_send = time.time()
        await client.send_message(destination_chat_id, report_message)
        print(f"✅ تم إرسال تقرير عن {len(duplicate_msg_ids)} تكرار.")
    except FloodWaitError as e:
        print(f"⏳ (تقرير الروابط) انتظر {e.seconds} ثانية...")
        await asyncio.sleep(e.seconds + 1)
        # محاولة الإرسال مرة أخرى بعد الانتظار
        try:
            await client.send_message(destination_chat_id, report_message)
        except Exception as retry_e:
            print(f"⚠️ فشل إرسال تقرير الروابط بعد الانتظار: {retry_e}")
    except Exception as e:
        print(f"⚠️ خطأ أثناء إرسال تقرير الروابط: {e}")
    
    processing_times.append(('send_duplicate_links_report', time.time() - start_send))
    
    # تأخير 5 ثواني بعد كل رسالة تقرير
    await asyncio.sleep(5)


async def send_statistics(client):
    """إرسال تقرير إحصائي مفصل"""
    global total_reported_duplicates, total_duplicate_messages, start_time
    
    total_time = time.time() - start_time
    # تجنب الخطأ في حالة القسمة على صفر
    avg_time = sum(t[1] for t in processing_times) / len(processing_times) if processing_times else 0
    
    # تنسيق أفضل لعرض أبطأ المهام
    slowest_tasks_str = ""
    if processing_times:
        # ترتيب المهام حسب وقت المعالجة تنازليًا
        sorted_times = sorted(processing_times, key=lambda x: x[1], reverse=True)
        # أخذ أول 3 مهام (أو أقل إذا كانت المهام الكلية أقل)
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
        await client.send_message(CHANNEL_ID_LOG, report)
        print("✅ تم إرسال التقرير الإحصائي النهائي.")
    except FloodWaitError as e:
        print(f"⏳ (تقرير نهائي) انتظر {e.seconds} ثانية...")
        await asyncio.sleep(e.seconds + 1)
        try:
            await client.send_message(CHANNEL_ID_LOG, report)
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
    
    # قائمة بمهام إرسال التقارير
    report_tasks = []
    
    for file_size, msg_ids in file_dict.items():
        if len(msg_ids) > 1:  # إذا كان هناك أكثر من رسالة بنفس الحجم
            report_tasks.append(send_duplicate_links_report(client, channel_id, CHANNEL_ID_LOG, msg_ids))
    
    print(f"سيتم إرسال تقارير لـ {len(report_tasks)} مجموعة من التكرارات.")
    
    # تنفيذ المهام بترتيب تسلسلي مع التأخير بينها (للسيطرة على FloodWait)
    for task in report_tasks:
        await task # تنتظر اكتمال كل مهمة قبل بدء التالية
    
    await send_statistics(client)
    print(f"🏁 اكتملت العملية في {time.time()-start_time:.2f} ثانية.")

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("🚀 اتصال ناجح بالتيليجرام.")
        await client.get_me() # لاختبار الاتصال
        await find_and_report_duplicates(client, CHANNEL_ID)

if __name__ == '__main__':
    print("🔹 بدء التشغيل...")
    # لضمان عدم وجود حدث حلقه (event loop) سابق، خاصة في بيئات مثل Colab
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        # إذا كان هناك حدث حلقه بالفعل، قم بتشغيل المهمة في الخلفية
        print("💡 تم اكتشاف حلقة أحداث قائمة، تشغيل main كـ asyncio.create_task.")
        asyncio.create_task(main())
    else:
        # إذا لم يكن هناك حدث حلقه، قم بتشغيله كالمعتاد
        asyncio.run(main())

# --- نهاية الكود الرئيسي للبوت أو السكربت ---
