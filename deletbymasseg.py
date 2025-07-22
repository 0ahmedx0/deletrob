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
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0))
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))

# إحصائيات وأداء (تعريف المتغيرات العامة)
total_reported_duplicates = 0
total_duplicate_messages = 0
processing_times = []
start_time = None

# ----------------- الدوال -----------------

async def collect_files(client, channel_id, first_msg_id):
    global processing_times # التصريح باستخدام المتغير العام
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
    print("جاري مسح الرسائل في القناة...")
    messages_scanned = 0
    async for message in client.get_chat_history(channel_id):
        if message.id <= first_msg_id: break
        tasks.append(process_message(message))
        messages_scanned += 1
        if messages_scanned % 500 == 0:
            print(f"تم مسح {messages_scanned} رسالة حتى الآن...")
            await asyncio.gather(*tasks)
            tasks = []
    if tasks: await asyncio.gather(*tasks)
    
    processing_times.append(('collect_files', time.time() - start_collect))
    return file_dict

async def send_duplicate_links_report(client, source_chat_id, destination_chat_id, message_ids):
    global total_reported_duplicates, total_duplicate_messages # استخدام المتغيرات العامة
    if not message_ids: return
    message_ids.sort()
    original_msg_id, duplicate_msg_ids = message_ids[0], message_ids[1:]
    if not duplicate_msg_ids: return

    total_reported_duplicates += 1
    total_duplicate_messages += len(duplicate_msg_ids)
    
    source_channel_id_for_link = str(source_chat_id).replace("-100", "")
    
    report_message = f"📌 **تم العثور على ملفات مكررة (حسب الحجم)!**\n\n"
    report_message += f"🔗 **الرسالة الأصلية:** https://t.me/c/{source_channel_id_for_link}/{original_msg_id}\n\n"
    report_message += "**النسخ المكررة:**\n"
    for msg_id in duplicate_msg_ids:
        report_message += f"https://t.me/c/{source_channel_id_for_link}/{msg_id}\n"
    
    try:
        start_send = time.time()
        await client.send_message(destination_chat_id, report_message, parse_mode=ParseMode.MARKDOWN)
        print(f"✅ تم إرسال تقرير عن {len(duplicate_msg_ids)} تكرار.")
        processing_times.append(('send_duplicate_links_report', time.time() - start_send))
    except FloodWait as e:
        print(f"⏳ (تقرير الروابط) انتظر {e.value} ثانية...")
        await asyncio.sleep(e.value + 1)
        await client.send_message(destination_chat_id, report_message, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"⚠️ خطأ أثناء إرسال تقرير الروابط: {e}")
    
    await asyncio.sleep(5)

async def send_statistics(client):
    global total_reported_duplicates, total_duplicate_messages, start_time # استخدام المتغيرات العامة
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

async def find_and_report_duplicates(client, channel_id):
    global start_time # استخدام المتغير العام
    start_time = time.time()
    print("🔍 بدأ تحليل الملفات في القناة (اعتمادًا على حجم الملف فقط)...")
    file_dict = await collect_files(client, channel_id, FIRST_MSG_ID)
    print("⚡ بدأ إعداد تقارير الروابط للملفات المكررة...")
    tasks = [send_duplicate_links_report(client, channel_id, CHANNEL_ID_LOG, msg_ids) for file_size, msg_ids in file_dict.items() if len(msg_ids) > 1]
    print(f"سيتم إرسال تقارير لـ {len(tasks)} مجموعة من التكرارات.")
    for task in tasks: await task
    await send_statistics(client)
    print(f"🏁 اكتملت العملية في {time.time()-start_time:.2f} ثانية.")

# ----------------- الدالة الرئيسية -----------------

async def main():
    # اسم الجلسة يجب أن يكون هو نفسه الذي سجلت به الدخول سابقًا
    async with Client("new_pyrogram_session", api_id=API_ID, api_hash=API_HASH) as client:
        print("🚀 اتصال ناجح بالتيليجرام عبر Pyrogram.")
        
        # لا حاجة لتسخين الذاكرة المؤقتة في كل مرة إذا كانت الجلسة موجودة
        # ولكن إبقاؤها لا يضر
        print("💡 جارٍ التحقق من الوصول إلى القنوات...")
        try:
            await client.get_chat(CHANNEL_ID)
            await client.get_chat(CHANNEL_ID_LOG)
            print("✅ تم التحقق من الوصول إلى القنوات بنجاح.")
        except Exception as e:
            print(f"❌ خطأ فادح: لا يمكن الوصول إلى إحدى القنوات.")
            print(f"تفاصيل الخطأ: {e}")
            return

        await find_and_report_duplicates(client, CHANNEL_ID)

if __name__ == '__main__':
    print("🔹 بدء التشغيل...")
    asyncio.run(main())
