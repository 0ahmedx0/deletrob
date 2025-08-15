import os
import asyncio
from datetime import datetime
from collections import defaultdict
import logging

from pyrogram import Client
from pyrogram.errors import FloodWait

# --- إعدادات البيئة من Google Colab ---
# يفضل إبقاء هذه الطريقة كما هي في Colab

# معلومات المصادقة (اختر واحدة فقط وعلّق الأخرى)
# 1. للمصادقة كمستخدم (موصى به)
os.environ['API_ID'] = '27361100'
os.environ['API_HASH'] = '70f07944c80e1e52784f14cfe49f37fa'
os.environ['SESSION'] = 'BAGhf0wArwf6IT8U920coX5ZRamBo0_siOuRfy3r26gmxlZN-ysalq6araUZ5B9-h4XhkW3B1XRu6TrKx0zOEdGtp4orE5c0u9da4Rny-GHoRmUFOZ3imdsjzNW0KucaEwhoUYORSs7ZYDPLOS4C5bZlXFbaI8FAjUnkVS8P4nQdIFp6BUinShexzjgXPR4oRzRZb5kHhvdIvzfK9aDmYfqcUErOqcA0D_5cp-9lx6p2eA6OkdUA6Yed8TjcKEzfxHqri3g_XH0KwSjq4cePPaqLFK_6sVuPPmikbj9Fs6LwoBINaYyz41e_r6ABYwByXisDPthsE4hXSJCKnHPYANqe_gY_agAAAAHlNiU8AA'

# 2. للمصادقة كبوت (إذا كنت تفضل ذلك)
# تأكد من أن البوت مشرف في القناة
# os.environ['BOT_TOKEN'] = '8186829116:AAEAVKLdmg-BuZ5D4mhE4Ch1nLOWd0-LK3I'

# معلومات القناة والبحث
os.environ['CHANNEL_ID'] = "-1002603961050"
os.environ['CHANNEL_ID_LOG'] = "-1002603961050" # يمكن أن يكون رقمك الشخصي أو مجموعة أخرى
os.environ['FIRST_MSG_ID'] = '1'
os.environ['LAST_MSG_ID'] = '1000' # تم إضافة دعم لهذا المتغير


# --- الكود الرئيسي (لا تعدل ما بعد هذا الخط) ---

# إعداد تسجيل الأخطاء
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# قراءة المتغيرات
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_STRING = os.getenv("SESSION")

try:
    CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
    CHANNEL_ID_LOG = int(os.getenv("CHANNEL_ID_LOG"))
    FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID"))
    LAST_MSG_ID = int(os.getenv("LAST_MSG_ID", "0")) # اجعله 0 إذا لم يكن موجودًا
except (TypeError, ValueError) as e:
    logger.error(f"خطأ في قراءة المتغيرات الرقمية: {e}. تأكد من صحتها.")
    exit()

# اختيار طريقة المصادقة
if SESSION_STRING:
    logger.info("تم العثور على SESSION. سيتم تسجيل الدخول كـ (مستخدم).")
    app = Client("user_session", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH)
elif BOT_TOKEN:
    logger.info("تم العثور على BOT_TOKEN. سيتم تسجيل الدخول كـ (بوت).")
    app = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
else:
    logger.error("خطأ فادح: يجب توفير SESSION أو BOT_TOKEN للمصادقة.")
    exit()


async def find_duplicates():
    files_by_size = defaultdict(list)
    messages_scanned = 0
    files_found = 0
    start_time = datetime.now()

    try:
        await app.send_message(CHANNEL_ID_LOG, "⏳ جارٍ بدء عملية فحص الملفات المكررة...")

        # تحديد نطاق الرسائل
        message_ids = range(FIRST_MSG_ID, LAST_MSG_ID + 1)
        total_messages_to_scan = len(message_ids)
        logger.info(f"سيتم فحص {total_messages_to_scan} رسالة من ID {FIRST_MSG_ID} إلى {LAST_MSG_ID}.")

        # جلب الرسائل في دفعات (أكثر كفاءة)
        for i in range(0, total_messages_to_scan, 200): # دفعة من 200 رسالة
            chunk_ids = message_ids[i:i + 200]
            try:
                messages = await app.get_messages(chat_id=CHANNEL_ID, message_ids=chunk_ids)

                for message in messages:
                    if not message: # إذا كانت الرسالة محذوفة أو غير موجودة
                        continue
                        
                    messages_scanned += 1
                    
                    file_info = None
                    if message.document: file_info = message.document
                    elif message.video: file_info = message.video
                    elif message.audio: file_info = message.audio
                    elif message.photo: file_info = message.photo

                    if file_info and hasattr(file_info, 'file_size'):
                        files_found += 1
                        files_by_size[file_info.file_size].append((message.id, message.link))
                
                logger.info(f"التقدم: تم فحص {messages_scanned}/{total_messages_to_scan} رسالة...")

            except FloodWait as e:
                logger.warning(f"تم تقييد الطلبات. الانتظار لمدة {e.value} ثانية...")
                await asyncio.sleep(e.value + 2) # الانتظار + ثانيتين إضافيتين
            except Exception as e:
                logger.error(f"حدث خطأ أثناء جلب دفعة من الرسائل: {e}")
                continue # استمر مع الدفعة التالية

    except Exception as e:
        error_message = f"حدث خطأ فادح أثناء الفحص: {e}"
        logger.error(error_message, exc_info=True) # طباعة تفاصيل الخطأ الكاملة
        await app.send_message(CHANNEL_ID_LOG, f"❌ حدث خطأ وتوقفت العملية:\n`{e}`")
        return

    logger.info("انتهى الفحص. جارٍ توليد التقرير...")
    
    # --- توليد التقرير (نفس الكود السابق) ---
    duplicate_groups = {size: messages for size, messages in files_by_size.items() if len(messages) > 1}
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_filename = f"report_duplicates_{timestamp}.txt"
    total_duplicate_files = sum(len(messages) - 1 for messages in duplicate_groups.values())
    
    with open(report_filename, "w", encoding="utf-8") as f:
        # ... (محتوى التقرير لم يتغير، وهو صحيح)
        f.write("تقرير الملفات المكررة في قناة تليجرام\n")
        f.write("="*40 + "\n\n")
        f.write("📊 إحصائيات عامة:\n")
        f.write("-" * 20 + "\n")
        f.write(f"تاريخ إنشاء التقرير: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"مدة الفحص: {datetime.now() - start_time}\n")
        f.write(f"نطاق الرسائل المفحوصة: من {FIRST_MSG_ID} إلى {LAST_MSG_ID}\n")
        f.write(f"إجمالي الملفات التي تم العثور عليها: {files_found}\n")
        f.write(f"عدد مجموعات الملفات المكررة: {len(duplicate_groups)}\n")
        f.write(f"إجمالي عدد النسخ المكررة: {total_duplicate_files}\n\n")
        f.write("="*40 + "\n\n")
        
        if not duplicate_groups:
            f.write("🎉 لم يتم العثور على أي ملفات مكررة بناءً على حجم الملف.\n")
        else:
            f.write("🔍 تفاصيل المجموعات المكررة:\n\n")
            sorted_groups = sorted(duplicate_groups.items(), key=lambda item: item[0], reverse=True)
            for i, (size, messages) in enumerate(sorted_groups, 1):
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

    completion_message = (
        f"✅ اكتملت عملية الفحص بنجاح!\n\n"
        f"📄 تم حفظ التقرير محلياً باسم:\n`{report_filename}`\n\n"
        f"** ملخص النتائج:**\n"
        f"- الرسائل المفحوصة: {messages_scanned}\n"
        f"- مجموعات مكررة: {len(duplicate_groups)}\n"
        f"- إجمالي التكرارات: {total_duplicate_files}"
    )
    await app.send_message(CHANNEL_ID_LOG, completion_message)
    if os.path.getsize(report_filename) < 50 * 1024 * 1024:
        await app.send_document(CHANNEL_ID_LOG, report_filename, caption="📄 مرفق تقرير التفاصيل")


async def main():
    logger.info("بدء تشغيل السكربت...")
    try:
        await app.start()
        await find_duplicates()
    except Exception as e:
        logger.error(f"حدث خطأ غير متوقع في المستوى الأعلى: {e}", exc_info=True)
    finally:
        if app.is_connected:
            await app.stop()
        logger.info("انتهى تنفيذ السكربت.")

# تشغيل الكود
asyncio.run(main())
