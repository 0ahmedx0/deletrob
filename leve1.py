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
total_deleted_count = 0
total_saved_space = 0  # إجمالي المساحة المحررة
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
            async with lock:  # منع التنافس على الموارد
                if file_size in file_dict:
                    file_dict[file_size].append((message.id, file_size))
                else:
                    file_dict[file_size] = [(message.id, file_size)]
    
    # إنشاء وتشغيل المهام بشكل متوازي
    tasks = []
    lock = asyncio.Lock()
    async for message in client.iter_messages(channel_id, min_id=first_msg_id):
        tasks.append(process_message(message))
        if len(tasks) % 100 == 0:  # معالجة كل 100 رسالة دفعة واحدة
            await asyncio.gather(*tasks)
            tasks = []
    
    if tasks:  # معالجة المتبقي
        await asyncio.gather(*tasks)
    
    processing_time = time.time() - start_collect
    processing_times.append(('collect_files', processing_time))
    return file_dict

async def forward_delete_and_send_original_link(client, source_chat, destination_chat, duplicate_msg_ids):
    """إصدار محسن مع تتبع الإحصائيات"""
    global total_deleted_count, total_saved_space
    chunk_size = 99
    
    original_msg_id, original_size = duplicate_msg_ids[0]
    duplicates = duplicate_msg_ids[1:]
    
    total_saved_space += original_size * len(duplicates)  # حساب المساحة المحررة
    
    # معالجة الدفعات بشكل متوازي
    tasks = []
    for i in range(0, len(duplicates), chunk_size):
        chunk = duplicates[i:i + chunk_size]
        tasks.append(process_chunk(client, source_chat, destination_chat, chunk, original_msg_id))
    
    await asyncio.gather(*tasks)

async def process_chunk(client, source_chat, dest_chat, chunk, original_id):
    """معالجة دفعة من الرسائل مع تتبع الوقت"""
    global total_deleted_count
    start_chunk = time.time()
    
    try:
        # نقل وحذف متوازي
        await asyncio.gather(
            client.forward_messages(dest_chat, [msg_id for msg_id, _ in chunk], from_peer=source_chat),
            client.delete_messages(source_chat, [msg_id for msg_id, _ in chunk])
        )
        
        total_deleted_count += len(chunk)
        print(f"✅ تم معالجة {len(chunk)} رسالة")
        
        # إرسال الرابط الأصلي
        original_link = f"https://t.me/c/{str(source_chat)[4:]}/{original_id}"
        await client.send_message(dest_chat, f"📌 الرسالة الأصلية: {original_link}")
        
    except FloodWaitError as e:
        print(f"⏳ انتظر {e.seconds} ثانية")
        await asyncio.sleep(e.seconds + 1)
    except Exception as e:
        print(f"⚠️ خطأ: {e}")
    
    processing_times.append(('process_chunk', time.time() - start_chunk))

async def send_statistics(client):
    """إرسال تقرير إحصائي مفصل"""
    global total_deleted_count, total_saved_space, start_time
    
    total_time = time.time() - start_time
    avg_time = sum(t[1] for t in processing_times) / len(processing_times) if processing_times else 0
    
    report = f"""
    📊 تقرير الأداء 📊
    --------------------
    • الرسائل المحذوفة: {total_deleted_count} 🗑
    • المساحة المحررة: {total_saved_space/1024/1024:.2f} ميجابايت 💾
    • الوقت الكلي: {total_time:.2f} ثانية ⏱
    • متوسط وقت المهمة: {avg_time:.2f} ثانية ⚡
    • المهام الأبطأ: 
    {sorted(processing_times, key=lambda x: x[1], reverse=True)[:3]}
    """
    
    await client.send_message(CHANNEL_ID_LOG, report)
    print("✅ تم إرسال التقرير الإحصائي")

async def delete_duplicates(client, channel_id):
    global start_time
    start_time = time.time()
    
    print("🔍 بدأ تحليل الملفات...")
    file_dict = await collect_files(client, channel_id, FIRST_MSG_ID)
    
    print("⚡ بدأ حذف المكررات...")
    tasks = []
    for file_size, msg_list in file_dict.items():
        if len(msg_list) > 1:
            tasks.append(forward_delete_and_send_original_link(
                client, channel_id, CHANNEL_ID_LOG, msg_list))
    
    await asyncio.gather(*tasks)
    
    await send_statistics(client)
    print(f"🏁 اكتملت العملية في {time.time()-start_time:.2f} ثانية")

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("🚀 اتصال ناجح بالتيليجرام")
        await delete_duplicates(client, CHANNEL_ID)

if __name__ == '__main__':
    print("🔹 بدء التشغيل...")
    asyncio.run(main())
