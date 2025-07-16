from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from dotenv import load_dotenv
import asyncio
import os
import time

# تحميل إعدادات البيئة
load_dotenv()

# إعدادات تيليجرام
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('SESSION')  
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))  
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0))  
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))  

# إحصائيات وأداء
total_reported_duplicates = 0 # عدد مجموعات التكرارات التي تم الإبلاغ عنها
total_duplicate_messages = 0 # إجمالي عدد الرسائل المكررة التي تم العثور عليها (غير الأصلية)
processing_times = []  # لتتبع أداء المهام
start_time = None  # وقت بدء التشغيل

async def collect_files(client, channel_id, first_msg_id):
    """إصدار محسن لجمع الملفات مع تتبع الأداء"""
    global processing_times
    file_dict = {}
    
    start_collect = time.time()
    
    # معالجة غير متزامنة بمهام مجمعة
    async def process_message(message):
        if message.file and hasattr(message.file, 'size'):
            file_size = message.file.size
            # استخدام معرف الملف الفريد (file_id.unique_id) لضمان الدقة في التكرار
            # في حال وجود ملفات مختلفة بالحجم ولكن بمحتوى مختلف (نادر، لكن أكثر دقة)
            if message.file.size and message.file.md5_checksum: # استخدام md5_checksum أو file_id.unique_id
                file_unique_id = f"{message.file.size}_{message.file.md5_checksum}"
            elif message.file.id: # fallback if no checksum (e.g., photos without explicit checksum)
                file_unique_id = f"{message.file.size}_{message.file.id}"
            else: # last resort, use only size (less accurate for true duplicates)
                file_unique_id = str(message.file.size)

            async with lock:  # منع التنافس على الموارد
                if file_unique_id in file_dict:
                    file_dict[file_unique_id].append(message.id)
                else:
                    file_dict[file_unique_id] = [message.id]
    
    # إنشاء وتشغيل المهام بشكل متوازي
    tasks = []
    lock = asyncio.Lock()
    print("جاري مسح الرسائل في القناة...")
    async for message in client.iter_messages(channel_id, min_id=first_msg_id):
        tasks.append(process_message(message))
        if len(tasks) % 500 == 0:  # معالجة كل 500 رسالة دفعة واحدة
            print(f"تم مسح {len(tasks)} رسالة حتى الآن...")
            await asyncio.gather(*tasks)
            tasks = []
    
    if tasks:  # معالجة المتبقي
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

    original_msg_id = message_ids[0]
    duplicate_msg_ids = message_ids[1:] # الرسائل المكررة هي كل ما عدا الأولى

    # إذا لم يكن هناك تكرارات حقيقية (فقط الرسالة الأصلية)، فلا نرسل تقريراً
    if not duplicate_msg_ids:
        return

    total_reported_duplicates += 1
    total_duplicate_messages += len(duplicate_msg_ids)
    
    report_message = f"📌 **تم العثور على ملفات مكررة!**\n\n"
    report_message += f"🔗 **الرسالة الأصلية:** `https://t.me/c/{str(source_chat_id)[4:]}/{original_msg_id}`\n\n"
    report_message += "**النسخ المكررة:**\n"

    # بناء روابط النسخ المكررة
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
        await client.send_message(destination_chat_id, report_message)
    except Exception as e:
        print(f"⚠️ خطأ أثناء إرسال تقرير الروابط: {e}")
    
    processing_times.append(('send_duplicate_links_report', time.time() - start_send))
    
    # تأخير 5 ثواني بعد كل رسالة تقرير
    await asyncio.sleep(5)


async def send_statistics(client):
    """إرسال تقرير إحصائي مفصل"""
    global total_reported_duplicates, total_duplicate_messages, start_time
    
    total_time = time.time() - start_time
    # Avoid ZeroDivisionError if processing_times is empty
    avg_time = sum(t[1] for t in processing_times) / len(processing_times) if processing_times else 0
    
    report = f"""
    📊 **تقرير الأداء النهائي** 📊
    ----------------------------
    • مجموعات التكرار التي تم الإبلاغ عنها: {total_reported_duplicates} 📝
    • إجمالي الرسائل المكررة المكتشفة: {total_duplicate_messages} 🔎 (باستثناء الأصول)
    • الوقت الكلي للعملية: {total_time:.2f} ثانية ⏱
    • متوسط وقت المهمة: {avg_time:.2f} ثانية ⚡
    • المهام الأبطأ: 
    {sorted(processing_times, key=lambda x: x[1], reverse=True)[:3]}
    """
    
    try:
        await client.send_message(CHANNEL_ID_LOG, report)
        print("✅ تم إرسال التقرير الإحصائي النهائي.")
    except FloodWaitError as e:
        print(f"⏳ (تقرير نهائي) انتظر {e.seconds} ثانية...")
        await asyncio.sleep(e.seconds + 1)
        await client.send_message(CHANNEL_ID_LOG, report)
    except Exception as e:
        print(f"⚠️ خطأ أثناء إرسال التقرير النهائي: {e}")

async def find_and_report_duplicates(client, channel_id):
    global start_time
    start_time = time.time()
    
    print("🔍 بدأ تحليل الملفات في القناة...")
    file_dict = await collect_files(client, channel_id, FIRST_MSG_ID)
    
    print("⚡ بدأ إعداد تقارير الروابط للملفات المكررة...")
    
    # قائمة لتخزين المهام
    tasks = []
    
    for file_unique_id, msg_ids in file_dict.items():
        if len(msg_ids) > 1:  # إذا كان هناك أكثر من رسالة بنفس المعرف الفريد للملف (مكررة)
            # إضافة مهمة إرسال التقرير
            tasks.append(send_duplicate_links_report(client, channel_id, CHANNEL_ID_LOG, msg_ids))
    
    # تشغيل جميع مهام إرسال التقارير بالتتابع (بسبب الـ sleep داخل الدالة)
    # ملاحظة: asyncio.gather سيحاول تشغيلها بالتوازي، لكن الـ sleep داخل send_duplicate_links_report
    # سيؤخر العملية. إذا أردت التأكد من التتابع، يمكن استخدام for loop عادي
    # ولكن asyncio.gather لا يزال يحسن الأداء في بعض الجوانب.
    print(f"سيتم إرسال تقارير لـ {len(tasks)} مجموعة من التكرارات.")
    for task in tasks:
        await task # تشغيل المهام واحدة تلو الأخرى لضمان التأخير
    
    await send_statistics(client)
    print(f"🏁 اكتملت العملية في {time.time()-start_time:.2f} ثانية.")

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("🚀 اتصال ناجح بالتيليجرام.")
        await find_and_report_duplicates(client, CHANNEL_ID)

if __name__ == '__main__':
    print("🔹 بدء التشغيل...")
    asyncio.run(main())
