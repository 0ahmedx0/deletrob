import asyncio
import os
import time
import random # << تعديل: استيراد مكتبة random

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from dotenv import load_dotenv

# تحميل إعدادات البيئة
load_dotenv()

# --- إعدادات تيليجرام والتشغيل ---

# استخدم هذا السطر إذا كنت تريد تحديد الجلسة مباشرة في الكود
# os.environ['SESSION'] = 'YourStringSessionHere'

API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('SESSION') 
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0))

# << تعديل: تحديد نطاق الرسائل >>
# ابدأ البحث من هذه الرسالة (الأقدم)
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))
# توقف عن البحث عند هذه الرسالة (الأحدث)، ضع 0 ليفحص حتى آخر رسالة
LAST_MSG_ID = int(os.getenv('LAST_MSG_ID', 0)) 

# << تعديل: تحديد نطاق التأخير العشوائي (بالثواني) >>
MIN_DELAY_SECONDS = 5
MAX_DELAY_SECONDS = 15

# إحصائيات وأداء (تعريف المتغيرات العامة)
total_reported_duplicates = 0
total_duplicate_messages = 0
processing_times = []
start_time = None

# ----------------- الدوال -----------------

async def collect_files(client, channel_id, first_msg_id, last_msg_id):
    global processing_times
    file_dict = {}
    start_collect = time.time()
    
    async def process_message(message):
        media = message.document or message.video or message.audio
        if media and hasattr(media, 'file_size'):
            file_size = media.file_size
            async with lock:
                if file_size in file_dict:
                    file_dict[file_size].append(message.id)
                else:
                    file_dict[file_size] = [message.id]
    
    tasks, lock = [], asyncio.Lock()
    print(f"جاري مسح الرسائل في القناة من الرسالة {first_msg_id} إلى {last_msg_id if last_msg_id > 0 else 'الأخيرة'}...")
    messages_scanned = 0
    
    # << تعديل: استخدام get_chat_history مع تحديد offset_id للبدء من نقطة معينة >>
    # إذا كان last_msg_id محدداً، نبدأ منه
    initial_offset_id = last_msg_id if last_msg_id > 0 else 0
    
    async for message in client.get_chat_history(chat_id=channel_id, offset_id=initial_offset_id):
        # نتوقف عندما نصل إلى الرسالة الأقدم المحددة أو نتجاوزها
        if message.id < first_msg_id: 
            break
        
        tasks.append(process_message(message))
        messages_scanned += 1
        if messages_scanned % 500 == 0:
            print(f"تم مسح {messages_scanned} رسالة حتى الآن...")
            await asyncio.gather(*tasks)
            tasks = []
    
    if tasks: await asyncio.gather(*tasks)
    
    processing_times.append(('collect_files', time.time() - start_collect))
    print(f"انتهى المسح. تم فحص {messages_scanned} رسالة.")
    return file_dict

async def send_duplicate_links_report(client, source_chat_id, destination_chat_id, message_ids):
    global total_reported_duplicates, total_duplicate_messages
    if not message_ids: return
    message_ids.sort() # الأقدم هو الأصلي
    original_msg_id, duplicate_msg_ids = message_ids[0], message_ids[1:]
    if not duplicate_msg_ids: return

    total_reported_duplicates += 1
    total_duplicate_messages += len(duplicate_msg_ids)
    
    source_channel_id_for_link = str(source_chat_id).replace("-100", "")
    report_message = f"📌 **تم العثور على ملفات مكررة (حسب الحجم)!**\n\n"
    report_message += f"🔗 **الرسالة الأصلية:** `https://t.me/c/{source_channel_id_for_link}/{original_msg_id}`\n\n"
    report_message += "**النسخ المكررة:**\n"
    for msg_id in duplicate_msg_ids:
        report_message += f"- `https://t.me/c/{source_channel_id_for_link}/{msg_id}`\n"
    
    try:
        start_send = time.time()
        await client.send_message(destination_chat_id, report_message, parse_mode=ParseMode.MARKDOWN)
        print(f"✅ تم إرسال تقرير عن {len(duplicate_msg_ids)} تكرار للرسالة {original_msg_id}.")
        processing_times.append(('send_duplicate_links_report', time.time() - start_send))
    except FloodWait as e:
        print(f"⏳ (تقرير الروابط) انتظر {e.value} ثانية...")
        await asyncio.sleep(e.value + 1)
        await client.send_message(destination_chat_id, report_message, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"⚠️ خطأ أثناء إرسال تقرير الروابط: {e}")
    
    # << تعديل: استخدام تأخير عشوائي >>
    delay = random.randint(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
    print(f"   ... انتظار {delay} ثانية قبل التقرير التالي.")
    await asyncio.sleep(delay)


# ... (دالة send_statistics تبقى كما هي) ...
async def send_statistics(client):
    global total_reported_duplicates, total_duplicate_messages, start_time
    total_time = time.time() - start_time
    avg_time = sum(t[1] for t in processing_times) / len(processing_times) if processing_times else 0
    slowest_tasks = sorted(processing_times, key=lambda x: x[1], reverse=True)[:3]
    slowest_tasks_str = "\n    ".join([f"- {name}: {duration:.2f}s" for name, duration in slowest_tasks]) if slowest_tasks else "لا يوجد"
    report = f"""📊 **تقرير الأداء النهائي** 📊
----------------------------
• مجموعات التكرار التي تم الإبلاغ عنها: `{total_reported_duplicates}` 📝
• إجمالي الرسائل المكررة المكتشفة: `{total_duplicate_messages}` 🔎 (باستثناء الأصول)
• الوقت الكلي للعملية: `{total_time:.2f}` ثانية ⏱
• متوسط وقت المهمة: `{avg_time:.2f}` ثانية ⚡
• المهام الأبطأ: 
    {slowest_tasks_str}"""
    try:
        await client.send_message(CHANNEL_ID_LOG, report, parse_mode=ParseMode.MARKDOWN)
        print("✅ تم إرسال التقرير الإحصائي النهائي.")
    except Exception as e: print(f"⚠️ خطأ أثناء إرسال التقرير النهائي: {e}")


async def find_and_report_duplicates(client, channel_id, first_id, last_id):
    global start_time
    start_time = time.time()
    print("🔍 بدأ تحليل الملفات في القناة (اعتمادًا على حجم الملف فقط)...")
    file_dict = await collect_files(client, channel_id, first_id, last_id)
    
    print("⚡ بدأ إعداد تقارير الروابط للملفات المكررة...")
    # إنشاء المهام
    tasks = [
        send_duplicate_links_report(client, channel_id, CHANNEL_ID_LOG, msg_ids) 
        for _, msg_ids in file_dict.items() if len(msg_ids) > 1
    ]
    print(f"سيتم إرسال تقارير لـ {len(tasks)} مجموعة من التكرارات.")
    # تنفيذ المهام بالتتابع لضمان التأخير بين كل تقرير
    for task in tasks:
        await task
    
    await send_statistics(client)
    print(f"🏁 اكتملت العملية في {time.time()-start_time:.2f} ثانية.")

# ----------------- الدالة الرئيسية -----------------

async def main():
    if not SESSION:
        raise ValueError("خطأ: لم يتم توفير جلسة نصية (SESSION). يرجى تحديدها في ملف .env أو في الكود.")
    
    # << تعديل: استخدام StringSession بشكل حصري >>
    # سيتم إنشاء العميل في الذاكرة فقط، بدون إنشاء ملفات محلية
    async with Client("my_account", session_string=SESSION, api_id=API_ID, api_hash=API_HASH, in_memory=True) as client:
        print("🚀 اتصال ناجح بالتيليجرام عبر StringSession.")
        
        print("💡 جارٍ التحقق من الوصول إلى القنوات...")
        try:
            await client.get_chat(CHANNEL_ID)
            await client.get_chat(CHANNEL_ID_LOG)
            print("✅ تم التحقق من الوصول إلى القنوات بنجاح.")
        except Exception as e:
            print(f"❌ خطأ فادح: لا يمكن الوصول إلى إحدى القنوات. تأكد من أن الحساب عضو وأن المُعرّف صحيح.")
            print(f"تفاصيل الخطأ: {e}")
            return

        # << تعديل: تمرير معرفات البداية والنهاية >>
        await find_and_report_duplicates(client, CHANNEL_ID, FIRST_MSG_ID, LAST_MSG_ID)

if __name__ == '__main__':
    print("🔹 بدء التشغيل...")
    # التحقق من وجود المتغيرات الأساسية
    if not all([API_ID, API_HASH, CHANNEL_ID, CHANNEL_ID_LOG, FIRST_MSG_ID]):
        print("❌ خطأ في الإعدادات: يرجى التأكد من تعريف API_ID, API_HASH, CHANNEL_ID, CHANNEL_ID_LOG, FIRST_MSG_ID في ملف .env")
    else:
        asyncio.run(main())
