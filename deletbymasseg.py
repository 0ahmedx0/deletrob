import asyncio
import os
import time

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from dotenv import load_dotenv

# تحميل إعدادات البيئة
load_dotenv()

# إعدادات تيليجرام
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('SESSION')
# في pyrogram، يفضل أن يكون معرف القناة رقمًا صحيحًا (integer)، مثال: -100123456789
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0))
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))

# إحصائيات وأداء
total_reported_duplicates = 0  # عدد مجموعات التكرارات التي تم الإبلاغ عنها
total_duplicate_messages = 0   # إجمالي عدد الرسائل المكررة التي تم العثور عليها (غير الأصلية)
processing_times = []          # لتتبع أداء المهام
start_time = None              # وقت بدء التشغيل

async def collect_files(client, channel_id, first_msg_id):
    """إصدار محسن لجمع الملفات مع تتبع الأداء، يعتمد على حجم الملف فقط (لـ Pyrogram)"""
    global processing_times
    file_dict = {}
    
    start_collect = time.time()
    
    async def process_message(message):
        # في Pyrogram، لا يوجد 'message.file'، لذا يجب التحقق من أنواع الوسائط
        media = message.document or message.video or message.audio
        if media and hasattr(media, 'file_size'):
            file_size = media.file_size
            async with lock:  # منع التنافس على الموارد
                if file_size in file_dict:
                    file_dict[file_size].append(message.id)
                else:
                    file_dict[file_size] = [message.id]
    
    # إنشاء وتشغيل المهام بشكل متوازي
    tasks = []
    lock = asyncio.Lock()
    print("جاري مسح الرسائل في القناة...")
    messages_scanned = 0
    # client.get_chat_history يجلب الرسائل من الأحدث للأقدم
    async for message in client.get_chat_history(channel_id):
        # نتوقف عندما نصل إلى الرسالة المحددة كنقطة بداية (أو أقدم)
        if message.id <= first_msg_id:
            break
        
        tasks.append(process_message(message))
        messages_scanned += 1
        if messages_scanned % 500 == 0:  # طباعة التقدم كل 500 رسالة
            print(f"تم مسح {messages_scanned} رسالة حتى الآن...")
            await asyncio.gather(*tasks) # تنفيذ المهام المتراكمة
            tasks = [] # إعادة تعيين قائمة المهام

    # معالجة أي مهام متبقية بعد انتهاء الحلقة
    if tasks:
        await asyncio.gather(*tasks)
    
    processing_time = time.time() - start_collect
    processing_times.append(('collect_files', processing_time))
    return file_dict

async def send_duplicate_links_report(client, source_chat_id, destination_chat_id, message_ids):
    """
    يرسل تقريراً بروابط الرسائل المكررة إلى قناة السجل، مع تأخير زمني.
    """
    global total_reported_duplicates, total_duplicate_messages
    
    if not message_ids:
        return

    # نفرز المعرفات للتأكد من أن الأقدم هو الأصلي
    message_ids.sort()
    original_msg_id = message_ids[0]
    duplicate_msg_ids = message_ids[1:] # الرسائل المكررة هي كل ما عدا الأولى

    # إذا لم يكن هناك تكرارات حقيقية (فقط الرسالة الأصلية)، فلا نرسل تقريراً
    if not duplicate_msg_ids:
        return

    total_reported_duplicates += 1
    total_duplicate_messages += len(duplicate_msg_ids)
    
    # صيغة الرابط تعمل مع القنوات الخاصة (ID يبدأ بـ -100)
    source_channel_id_for_link = str(source_chat_id).replace("-100", "")
    
    report_message = f"📌 **تم العثور على ملفات مكررة (حسب الحجم)!**\n\n"
    report_message += f"🔗 **الرسالة الأصلية:** `https://t.me/c/{source_channel_id_for_link}/{original_msg_id}`\n\n"
    report_message += "**النسخ المكررة:**\n"

    # بناء روابط النسخ المكررة
    for msg_id in duplicate_msg_ids:
        report_message += f"- `https://t.me/c/{source_channel_id_for_link}/{msg_id}`\n"
    
    try:
        start_send = time.time()
        # استخدام parse_mode لتفعيل تنسيق Markdown
        await client.send_message(destination_chat_id, report_message, parse_mode=ParseMode.MARKDOWN)
        print(f"✅ تم إرسال تقرير عن {len(duplicate_msg_ids)} تكرار.")
    except FloodWait as e:
        # في Pyrogram، مدة الانتظار تكون في e.value أو e.x
        wait_time = e.value
        print(f"⏳ (تقرير الروابط) انتظر {wait_time} ثانية...")
        await asyncio.sleep(wait_time + 1)
        # محاولة الإرسال مرة أخرى بعد الانتظار
        await client.send_message(destination_chat_id, report_message, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"⚠️ خطأ أثناء إرسال تقرير الروابط: {e}")
    
    processing_times.append(('send_duplicate_links_report', time.time() - start_send))
    
    # تأخير 5 ثواني بعد كل رسالة تقرير
    await asyncio.sleep(5)


async def send_statistics(client):
    """إرسال تقرير إحصائي مفصل"""
    global total_reported_duplicates, total_duplicate_messages, start_time
    
    total_time = time.time() - start_time
    # تجنب القسمة على صفر
    avg_time = sum(t[1] for t in processing_times) / len(processing_times) if processing_times else 0
    
    # فرز المهام الأبطأ للعرض
    slowest_tasks = sorted(processing_times, key=lambda x: x[1], reverse=True)[:3]
    slowest_tasks_str = "\n    ".join([f"- {name}: {duration:.2f}s" for name, duration in slowest_tasks]) if slowest_tasks else "لا يوجد"
    
    report = f"""
📊 **تقرير الأداء النهائي** 📊
----------------------------
• مجموعات التكرار التي تم الإبلاغ عنها: `{total_reported_duplicates}` 📝
• إجمالي الرسائل المكررة المكتشفة: `{total_duplicate_messages}` 🔎 (باستثناء الأصول)
• الوقت الكلي للعملية: `{total_time:.2f}` ثانية ⏱
• متوسط وقت المهمة: `{avg_time:.2f}` ثانية ⚡
• المهام الأبطأ: 
    {slowest_tasks_str}
"""
    
    try:
        await client.send_message(CHANNEL_ID_LOG, report, parse_mode=ParseMode.MARKDOWN)
        print("✅ تم إرسال التقرير الإحصائي النهائي.")
    except FloodWait as e:
        wait_time = e.value
        print(f"⏳ (تقرير نهائي) انتظر {wait_time} ثانية...")
        await asyncio.sleep(wait_time + 1)
        await client.send_message(CHANNEL_ID_LOG, report, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"⚠️ خطأ أثناء إرسال التقرير النهائي: {e}")

async def find_and_report_duplicates(client, channel_id):
    global start_time
    start_time = time.time()
    
    print("🔍 بدأ تحليل الملفات في القناة (اعتمادًا على حجم الملف فقط)...")
    file_dict = await collect_files(client, channel_id, FIRST_MSG_ID)
    
    print("⚡ بدأ إعداد تقارير الروابط للملفات المكررة...")
    
    tasks = []
    
    for file_size, msg_ids in file_dict.items():
        if len(msg_ids) > 1:  # إذا كان هناك أكثر من رسالة بنفس الحجم
            tasks.append(send_duplicate_links_report(client, channel_id, CHANNEL_ID_LOG, msg_ids))
    
    print(f"سيتم إرسال تقارير لـ {len(tasks)} مجموعة من التكرارات.")
    # تشغيل المهام واحدة تلو الأخرى لضمان احترام التأخير الزمني بين كل تقرير
    for task in tasks:
        await task
    
    await send_statistics(client)
    print(f"🏁 اكتملت العملية في {time.time()-start_time:.2f} ثانية.")

async def main():
    # طريقة تعريف العميل في Pyrogram
    # الاسم "duplicate_finder_bot" يُستخدم لحفظ ملف .session إذا لم يتم توفير SESSION
    async with Client("duplicate_finder_bot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION) as client:
        print("🚀 اتصال ناجح بالتيليجرام عبر Pyrogram.")
        await find_and_report_duplicates(client, CHANNEL_ID)

if __name__ == '__main__':
    print("🔹 بدء التشغيل...")
    asyncio.run(main())
