
# الخطوة 2: استيراد المكتبات وإعداد المتغيرات
import os
import asyncio
from datetime import datetime
from collections import defaultdict
import logging

# إعداد المتغيرات مباشرة (استبدل بالقيم الجديدة والآمنة)
# 🚨🚨 لا تشارك هذه القيم مع أحد 🚨🚨
os.environ['API_ID'] = ""  # استبدل بالـ API_ID الجديد
os.environ['API_HASH'] = "" # استبدل بالـ API_HASH الجديد
os.environ['BOT_TOKEN'] = "" # ⬅️⬅️ ضع توكن البوت الجديد هنا

# معلومات القناة (تأكد أن البوت عضو ومشرف هنا)
os.environ['CHANNEL_ID'] = "" 
os.environ['CHANNEL_ID_LOG'] = "" 

# نطاق الرسائل
os.environ['FIRST_MSG_ID'] = '1'
os.environ['LAST_MSG_ID'] = '1000' # يمكنك وضع رقم كبير جداً لفحص كل شيء


# --- بداية الكود الرئيسي ---

# إعداد تسجيل الأخطاء
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# قراءة المتغيرات من البيئة
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

try:
    # Pyrogram يمكنه التعامل مع أسماء المستخدمين (@username) كـ string
    # لذا سنحاول تحويلها إلى int، وإذا فشل، نستخدمها كما هي
    try:
        CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
    except ValueError:
        CHANNEL_ID = os.getenv("CHANNEL_ID")

    try:
        CHANNEL_ID_LOG = int(os.getenv("CHANNEL_ID_LOG"))
    except ValueError:
        CHANNEL_ID_LOG = os.getenv("CHANNEL_ID_LOG")
        
    FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID"))
    # تمت إضافة LAST_MSG_ID
    LAST_MSG_ID = int(os.getenv("LAST_MSG_ID", "0")) # قيمة افتراضية 0 إذا لم يتم تحديده
    if LAST_MSG_ID == 0:
        logger.warning("المتغير LAST_MSG_ID غير محدد، سيتم فحص كل الرسائل.")
        LAST_MSG_ID = float('inf') # رقم لا نهائي لفحص كل شيء

except (TypeError, ValueError) as e:
    logger.error(f"خطأ في قراءة المتغيرات: {e}")
    exit()

# إنشاء عميل Pyrogram
app = Client(
    "duplicate_finder_colab",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True # استخدام الذاكرة بدلاً من ملف جلسة في Colab
)

async def find_duplicates():
    files_by_size = defaultdict(list)
    messages_scanned = 0
    files_found = 0
    start_time = datetime.now()

    try:
        await app.send_message(CHANNEL_ID_LOG, "⏳ جارٍ بدء عملية فحص الملفات المكررة...")
        
        chat = await app.get_chat(CHANNEL_ID)
        logger.info(f"بدء الفحص في القناة: '{chat.title}'")

        async for message in app.get_chat_history(CHANNEL_ID):
            # تجاوز الرسائل الأحدث من LAST_MSG_ID
            if message.id > LAST_MSG_ID:
                continue

            # التوقف عند الوصول إلى رسالة أقدم من FIRST_MSG_ID
            if message.id < FIRST_MSG_ID:
                logger.info(f"تم الوصول إلى الرسالة المحددة FIRST_MSG_ID ({FIRST_MSG_ID}). إيقاف الفحص.")
                break
            
            messages_scanned += 1
            if messages_scanned % 100 == 0:
                logger.info(f"تم فحص {messages_scanned} رسالة...")

            file_info = None
            if message.document: file_info = message.document
            elif message.video: file_info = message.video
            elif message.audio: file_info = message.audio
            elif message.photo: file_info = message.photo

            if file_info and hasattr(file_info, 'file_size') and file_info.file_size:
                files_found += 1
                files_by_size[file_info.file_size].append((message.id, message.link))

    except Exception as e:
        error_message = f"حدث خطأ فادح أثناء الفحص: {e}"
        logger.error(error_message, exc_info=True)
        await app.send_message(CHANNEL_ID_LOG, f"❌ حدث خطأ وتوقفت العملية:\n`{e}`")
        return # إيقاف التنفيذ

    logger.info("انتهى الفحص. جارٍ توليد التقرير...")

    duplicate_groups = {size: messages for size, messages in files_by_size.items() if len(messages) > 1}
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_filename = f"report_duplicates_{timestamp}.txt"
    total_duplicate_files = sum(len(messages) - 1 for messages in duplicate_groups.values())
    
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(f"تقرير الملفات المكررة - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*40 + "\n\n")
        f.write(f"📊 إحصائيات عامة:\n")
        f.write(f" - نطاق الفحص: من رسالة {FIRST_MSG_ID} إلى {LAST_MSG_ID}\n")
        f.write(f" - الرسائل المفحوصة: {messages_scanned}\n")
        f.write(f" - الملفات التي تم العثور عليها: {files_found}\n")
        f.write(f" - مجموعات مكررة: {len(duplicate_groups)}\n")
        f.write(f" - إجمالي التكرارات: {total_duplicate_files}\n\n")
        f.write("="*40 + "\n\n")
        
        if not duplicate_groups:
            f.write("🎉 لم يتم العثور على أي ملفات مكررة.\n")
        else:
            sorted_groups = sorted(duplicate_groups.items(), key=lambda item: item[0], reverse=True)
            for i, (size, messages) in enumerate(sorted_groups, 1):
                messages.sort(key=lambda x: x[0])
                original_msg_id, original_link = messages[0]
                duplicate_links = [link for msg_id, link in messages[1:]]
                f.write(f"--- المجموعة {i} (الحجم: {size / 1024 / 1024:.2f} MB) ---\n")
                f.write(f"الأصلية: {original_link}\n")
                f.write(f"التكرارات ({len(duplicate_links)}):\n")
                for dup_link in duplicate_links:
                    f.write(f"  - {dup_link}\n")
                f.write("\n")
    
    logger.info(f"تم حفظ التقرير: {report_filename}")
    
    completion_message = (
        f"✅ اكتملت عملية الفحص بنجاح!\n\n"
        f"📄 التقرير `{report_filename}` جاهز.\n"
        f"📊 **النتائج:** {len(duplicate_groups)} مجموعة مكررة."
    )
    await app.send_document(CHANNEL_ID_LOG, report_filename, caption=completion_message)
    # في Colab، يمكنك عرض الملف مباشرة
    from google.colab import files
    files.download(report_filename)


async def main():
    logger.info("بدء تشغيل السكربت...")
    try:
        await app.start()
        await find_duplicates()
    except Exception as e:
        logger.error(f"حدث خطأ غير متوقع: {e}", exc_info=True)
    finally:
        if app.is_connected:
            await app.stop()
        logger.info("انتهى التنفيذ.")

# تشغيل الكود
if BOT_TOKEN != "YOUR_NEW_REVOKED_BOT_TOKEN":
    asyncio.run(main())
else:
    logger.error("خطأ: يرجى وضع توكن البوت الجديد في المتغير BOT_TOKEN قبل التشغيل.")
