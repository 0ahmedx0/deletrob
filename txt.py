import asyncio
import os
import time
import math

from pyrogram import Client
from pyrogram.errors import FloodWait
from dotenv import load_dotenv

# تحميل إعدادات البيئة
load_dotenv()

# إعدادات تيليجرام
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('SESSION')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0)) # القناة المصدر التي سيتم فحصها
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))

# --- إعدادات المهمة الجديدة ---
SIZE_THRESHOLD_MB = 50  # حد الحجم بالميغابايت
SIZE_THRESHOLD_BYTES = SIZE_THRESHOLD_MB * 1024 * 1024 # تحويل الحجم إلى بايت
OUTPUT_FILE = "report.txt" # اسم ملف التقرير الناتج

# متغيرات لتتبع الأداء
start_time = None
total_files_found = 0

# ----------------- الدوال -----------------

def format_size(size_bytes):
    """تحويل حجم الملف بالبايت إلى صيغة قابلة للقراءة (KB, MB, GB)."""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    # استخدام math.log للعثور على المؤشر الصحيح لاسم الحجم
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

async def find_large_files(client, channel_id, first_msg_id):
    """
    تبحث في القناة عن الفيديوهات والمستندات التي يتجاوز حجمها الحد المحدد.
    """
    global total_files_found
    large_files = []
    print(f"🔍 جاري البحث عن الفيديوهات والمستندات الأكبر من {SIZE_THRESHOLD_MB} ميجابايت...")
    
    messages_scanned = 0
    try:
        # استخدام `await client.get_chat_history` للحصول على الرسائل
        async for message in client.get_chat_history(channel_id):
            # التوقف إذا وصلنا إلى أقدم رسالة محددة
            if message.id <= first_msg_id:
                break

            messages_scanned += 1
            if messages_scanned % 500 == 0:
                print(f"تم مسح {messages_scanned} رسالة حتى الآن...")
            
            # التحقق مما إذا كانت الرسالة تحتوي على فيديو أو مستند
            media = message.video or message.document
            
            if media and hasattr(media, 'file_size') and media.file_size is not None:
                # التحقق مما إذا كان حجم الملف أكبر من الحد المحدد
                if media.file_size > SIZE_THRESHOLD_BYTES:
                    # بناء رابط الرسالة
                    # يتم إزالة '-100' من معرف القناة لإنشاء رابط صحيح
                    link = f"https://t.me/c/{str(channel_id).replace('-100', '')}/{message.id}"
                    
                    # تخزين الرابط وحجم الملف
                    large_files.append({
                        "link": link,
                        "size": media.file_size
                    })
                    total_files_found += 1
                    print(f"✅ تم العثور على ملف كبير: {link} | الحجم: {format_size(media.file_size)}")
    
    except FloodWait as e:
        print(f"⏳ واجهنا خطأ FloodWait. سننتظر لمدة {e.value} ثانية ونكمل.")
        await asyncio.sleep(e.value + 5)
        # يمكنك استدعاء الدالة مرة أخرى هنا أو معالجة الأمر بشكل أكثر تعقيدًا إذا لزم الأمر
        
    except Exception as e:
        print(f"⚠️ حدث خطأ غير متوقع أثناء مسح الرسائل: {e}")

    return large_files

def generate_report_file(files_list):
    """
    تنشئ ملف نصي يحتوي على تقرير بالملفات التي تم العثور عليها.
    """
    print(f"\n📝 جاري كتابة التقرير في الملف: {OUTPUT_FILE}")
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(f"تقرير بالملفات التي يتجاوز حجمها {SIZE_THRESHOLD_MB} ميجابايت\n")
            f.write("=" * 50 + "\n\n")
            
            if not files_list:
                f.write("لم يتم العثور على أي ملفات تطابق المعايير.\n")
                return

            for item in files_list:
                file_link = item['link']
                file_size_formatted = format_size(item['size'])
                f.write(f"الرابط: {file_link}\n")
                f.write(f"الحجم: {file_size_formatted}\n")
                f.write("-" * 30 + "\n")
        
        print(f"✅ تم حفظ التقرير بنجاح في '{OUTPUT_FILE}'.")
    except Exception as e:
        print(f"❌ فشل في كتابة ملف التقرير: {e}")

async def process_channel(client, channel_id):
    """
    الدالة الرئيسية التي تدير عملية البحث وإنشاء التقرير.
    """
    global start_time
    start_time = time.time()
    
    # 1. البحث عن الملفات الكبيرة
    large_files = await find_large_files(client, channel_id, FIRST_MSG_ID)
    
    # 2. إنشاء ملف التقرير
    if large_files:
        generate_report_file(large_files)
    else:
        print("\nℹ️ لم يتم العثور على أي ملفات تتجاوز الحجم المحدد.")
        # ننشئ ملف تقرير فارغ للتأكيد
        generate_report_file([])

    total_time = time.time() - start_time
    print(f"\n🏁 اكتملت العملية بنجاح!")
    print(f"🔍 إجمالي الملفات التي تم العثور عليها: {total_files_found}")
    print(f"⏱️ الوقت الكلي المستغرق: {total_time:.2f} ثانية.")

# ----------------- الدالة الرئيسية -----------------

async def main():
    # استخدام `with Client(...)` يضمن إغلاق الجلسة بشكل آمن
    async with Client("my_account_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION) as client:
        user = await client.get_me()
        print(f"🚀 تم تسجيل الدخول بنجاح كـ: {user.first_name}")

        print("\n💡 جارٍ التحقق من الوصول إلى القناة المصدر...")
        try:
            # التحقق من أن CHANNEL_ID هو قناة صالحة يمكن الوصول إليها
            await client.get_chat(CHANNEL_ID)
            print(f"✅ تم التحقق من الوصول إلى القناة ({CHANNEL_ID}) بنجاح.")
        except Exception as e:
            print(f"❌ خطأ فادح: لا يمكن الوصول إلى القناة المحددة في `CHANNEL_ID`.")
            print(f"تفاصيل الخطأ: {e}")
            return

        await process_channel(client, CHANNEL_ID)

if __name__ == '__main__':
    # التأكد من وجود المتغيرات الأساسية
    if not all([API_ID, API_HASH, SESSION, CHANNEL_ID]):
        print("❌ خطأ: يرجى التأكد من تعيين كل من API_ID, API_HASH, SESSION, CHANNEL_ID في ملف .env")
    else:
        print("🔹 بدء تشغيل السكربت...")
        asyncio.run(main())
