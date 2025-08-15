import os
import asyncio
from datetime import datetime
from collections import defaultdict
import logging

from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.errors import FloodWait

# إعداد تسجيل الأخطاء في الطرفية
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# تحميل المتغيرات من ملف .env
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

try:
    CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
    CHANNEL_ID_LOG = int(os.getenv("CHANNEL_ID_LOG"))
    FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID"))
except (TypeError, ValueError):
    logger.error("خطأ: تأكد من أن CHANNEL_ID, CHANNEL_ID_LOG, FIRST_MSG_ID أرقام صحيحة في ملف .env")
    exit()

# إنشاء عميل Pyrogram باستخدام توكن البوت
# "duplicate_finder_bot" هو اسم ملف الجلسة الذي سيتم إنشاؤه
app = Client(
    "duplicate_finder_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

async def find_duplicates():
    """
    الوظيفة الرئيسية لفحص القناة، تحديد الملفات المكررة، وتوليد التقرير.
    """
    files_by_size = defaultdict(list)
    messages_scanned = 0
    files_found = 0
    start_time = datetime.now()

    async with app:
        try:
            logger.info("تم تسجيل دخول البوت بنجاح.")
            await app.send_message(CHANNEL_ID_LOG, "⏳ جارٍ بدء عملية فحص الملفات المكررة...")

            # الحصول على معلومات القناة
            chat = await app.get_chat(CHANNEL_ID)
            logger.info(f"بدء الفحص في القناة: '{chat.title}'")

            # الدوران على كل الرسائل في القناة
            async for message in app.get_chat_history(CHANNEL_ID):
                # التوقف عند الوصول إلى رسالة أقدم من الرسالة المحددة
                if message.id < FIRST_MSG_ID:
                    logger.info(f"تم الوصول إلى الرسالة المحددة FIRST_MSG_ID ({FIRST_MSG_ID}). إيقاف الفحص.")
                    break
                
                messages_scanned += 1
                if messages_scanned % 100 == 0:
                    logger.info(f"تم فحص {messages_scanned} رسالة...")

                # استخراج الملف وحجمه (يدعم أنواع متعددة)
                file_info = None
                if message.document:
                    file_info = message.document
                elif message.video:
                    file_info = message.video
                elif message.audio:
                    file_info = message.audio
                elif message.photo:
                    file_info = message.photo # يأخذ أكبر حجم للصورة

                if file_info and hasattr(file_info, 'file_size'):
                    files_found += 1
                    file_size = file_info.file_size
                    # تخزين رابط الرسالة ورقمها للفرز لاحقًا
                    files_by_size[file_size].append((message.id, message.link))

        except FloodWait as e:
            logger.warning(f"تم تقييد الطلبات (FloodWait). الانتظار لمدة {e.value} ثانية...")
            await asyncio.sleep(e.value)
        except Exception as e:
            error_message = f"حدث خطأ فادح أثناء الفحص: {e}"
            logger.error(error_message)
            await app.send_message(CHANNEL_ID_LOG, f"❌ حدث خطأ وتوقفت العملية:\n`{e}`")
            return # إيقاف التنفيذ عند حدوث خطأ فادح

    logger.info("انتهى الفحص. جارٍ توليد التقرير...")

    # --- توليد التقرير ---
    
    # فلترة النتائج للحصول فقط على الملفات التي لها تكرارات
    duplicate_groups = {size: messages for size, messages in files_by_size.items() if len(messages) > 1}
    
    # إنشاء اسم ملف التقرير مع طابع زمني
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_filename = f"report_duplicates_{timestamp}.txt"
    
    total_duplicate_files = sum(len(messages) - 1 for messages in duplicate_groups.values())
    
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write("تقرير الملفات المكررة في قناة تليجرام\n")
        f.write("="*40 + "\n\n")
        
        # قسم الإحصائيات العامة
        f.write("📊 إحصائيات عامة:\n")
        f.write("-" * 20 + "\n")
        f.write(f"تاريخ إنشاء التقرير: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"مدة الفحص: {datetime.now() - start_time}\n")
        f.write(f"إجمالي الرسائل التي تم فحصها: {messages_scanned}\n")
        f.write(f"إجمالي الملفات التي تم العثور عليها: {files_found}\n")
        f.write(f"عدد مجموعات الملفات المكررة: {len(duplicate_groups)}\n")
        f.write(f"إجمالي عدد النسخ المكررة: {total_duplicate_files}\n\n")
        
        f.write("="*40 + "\n\n")
        
        if not duplicate_groups:
            f.write("🎉 لم يتم العثور على أي ملفات مكررة بناءً على حجم الملف.\n")
        else:
            f.write("🔍 تفاصيل المجموعات المكررة:\n\n")
            # فرز المجموعات حسب حجم الملف (من الأكبر للأصغر)
            sorted_groups = sorted(duplicate_groups.items(), key=lambda item: item[0], reverse=True)

            for i, (size, messages) in enumerate(sorted_groups, 1):
                # فرز الرسائل داخل كل مجموعة حسب رقم الرسالة (الأقدم أولاً)
                messages.sort(key=lambda x: x[0])
                
                original_msg_id, original_link = messages[0]
                duplicate_links = [link for msg_id, link in messages[1:]]
                
                f.write(f"--- المجموعة رقم {i} (حجم الملف: {size / 1024 / 1024:.2f} MB) ---\n")
                f.write(f"الرسالة الأصلية (الأقدم): {original_link}\n")
                f.write(f"النسخ المكررة ({len(duplicate_links)}):\n")
                for dup_link in duplicate_links:
                    f.write(f"  - {dup_link}\n")
                f.write("\n")
    
    logger.info(f"تم حفظ التقرير بنجاح في الملف: {report_filename}")
    
    # إرسال إشعار الانتهاء
    try:
        await app.start()
        completion_message = (
            f"✅ اكتملت عملية الفحص بنجاح!\n\n"
            f"📄 تم حفظ التقرير محلياً باسم:\n`{report_filename}`\n\n"
            f"** ملخص النتائج:**\n"
            f"- الرسائل المفحوصة: {messages_scanned}\n"
            f"- مجموعات مكررة: {len(duplicate_groups)}\n"
            f"- إجمالي التكرارات: {total_duplicate_files}"
        )
        await app.send_message(CHANNEL_ID_LOG, completion_message)
        # يمكنك إرسال التقرير نفسه إذا كان حجمه صغيراً
        if os.path.getsize(report_filename) < 50 * 1024 * 1024: # 50 MB
             await app.send_document(CHANNEL_ID_LOG, report_filename, caption="📄 مرفق تقرير التفاصيل")
        await app.stop()
    except Exception as e:
        logger.error(f"حدث خطأ أثناء إرسال إشعار الانتهاء: {e}")


# هذا هو الجزء الجديد والمُحسّن
async def main():
    """
    الدالة الرئيسية التي تبدأ وتوقف العميل بشكل آمن.
    """
    logger.info("بدء تشغيل سكربت البحث عن التكرارات...")
    try:
        await app.start()
        await find_duplicates()
    except Exception as e:
        logger.error(f"حدث خطأ غير متوقع في المستوى الأعلى: {e}")
    finally:
        if app.is_connected:
            await app.stop()
        logger.info("انتهى تنفيذ السكربت.")

if __name__ == "__main__":
    # استخدام asyncio.run لتشغيل الدالة الرئيسية غير المتزامنة
    asyncio.run(main())
