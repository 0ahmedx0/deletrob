# متغير لتخزين آخر قيمة تأخير مستخدمة (لم تعد تستخدم ولكن أبقيها لتكون مرجعاً)
prev_delay = None

import random
import asyncio
import os
import time

from pyrogram import Client
from pyrogram.enums import ParseMode # قد لا نحتاجها الآن ولكن أبقيها
from pyrogram.errors import FloodWait, MessageDeleteForbidden, RPCError # لم تعد تستخدم ولكن أبقيها
from dotenv import load_dotenv

# هذه الدالة لم تعد تستخدم لأننا لن نرسل تقارير فورية بعد الآن
def get_random_delay(min_delay=5, max_delay=30, min_diff=5):
    """
    تُولد قيمة تأخير عشوائية بين min_delay و max_delay.
    إذا كانت القيمة الجديدة قريبة جدًا (فرق أقل من min_diff) من القيمة السابقة،
    يتم إعادة التوليد.
    """
    global prev_delay
    delay = random.randint(min_delay, max_delay)
    # حلقة While loop لضمان أن التأخير الجديد ليس قريبًا جدًا من السابق
    while prev_delay is not None and abs(delay - prev_delay) < min_diff:
        delay = random.randint(min_delay, max_delay)
    prev_delay = delay
    return delay

# تحميل إعدادات البيئة
load_dotenv()

# إعدادات تيليجرام
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('SESSION')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0)) # القناة الأصلية (المصدر)
# CHANNEL_ID_LOG لم تعد تستخدم لإرسال التقارير، لكن قد تظل مفيدة لرسائل البدء/النهاية
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0)) 
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))

# إحصائيات وأداء (تعريف المتغيرات العامة)
total_reported_duplicates = 0 # هذا سيعد مجموعات التكرار المكتشفة
total_duplicate_messages_found = 0 # هذا سيعد إجمالي الرسائل المكررة المكتشفة
processing_times = []
start_time = None

# متغير عالمي لتخزين التقرير النهائي
final_report_content = []

# ----------------- الدوال -----------------

# دالة delete_message لم تعد تستخدم
# async def delete_message(client, chat_id, message_id):
#     """تحذف رسالة من قناة مع معالجة الأخطاء."""
#     # ... (كود حذف الرسالة الأصلي) ...

async def collect_files(client, channel_id, first_msg_id):
    global processing_times # التصريح باستخدام المتغير العام
    file_dict = {}
    start_collect = time.time()

    # تأمين الوصول إلى file_dict لتجنب مشاكل التزامن
    lock = asyncio.Lock()

    async def process_message(message):
        # التحقق من أن الرسالة ليست مجموعة ألبومات
        if message.media_group_id:
            return # نتجاهل رسائل الألبومات لتجنب التكرار في الفحص

        media = message.document or message.video or message.audio or message.photo # أضفنا message.photo
        if media and hasattr(media, 'file_size'):
            file_size = media.file_size
            async with lock: # استخدام القفل هنا
                if file_size in file_dict:
                    file_dict[file_size].append(message.id)
                else:
                    file_dict[file_size] = [message.id]

    tasks = []
    print("جاري مسح الرسائل في القناة...")
    messages_scanned = 0
    # استخدام `await client.get_chat_history` للحصول على كائن مكرر
    async for message in client.get_chat_history(channel_id):
        if message.id <= first_msg_id: break
        tasks.append(process_message(message))
        messages_scanned += 1
        # معالجة المهام على دفعات لتجنب استهلاك الذاكرة بشكل مفرط
        if messages_scanned % 500 == 0:
            print(f"تم مسح {messages_scanned} رسالة حتى الآن...")
            await asyncio.gather(*tasks)
            tasks = [] # إعادة تعيين قائمة المهام
    if tasks:
        await asyncio.gather(*tasks) # معالجة أي مهام متبقية

    processing_times.append(('collect_files', time.time() - start_collect))
    return file_dict

# هذه الدالة تم تعديلها لتجهيز التقرير للملف بدلاً من إرساله لتيليجرام
async def prepare_duplicate_report_entry(source_chat_id, message_ids):
    global total_reported_duplicates, total_duplicate_messages_found, final_report_content
    if not message_ids or len(message_ids) < 2:
        return # لا يوجد تكرار إذا كانت الرسائل أقل من 2

    message_ids.sort()
    original_msg_id = message_ids[0]
    duplicate_msg_ids = message_ids[1:] # جميع الرسائل ما عدا الأولى تعتبر مكررة

    total_reported_duplicates += 1
    total_duplicate_messages_found += len(duplicate_msg_ids)

    source_channel_id_for_link = str(source_chat_id).replace("-100", "")

    # بناء جزء التقرير لهذه المجموعة من التكرارات
    report_entry = f"--- مجموعة تكرار # {total_reported_duplicates} ---\n"
    report_entry += f"الرسالة الأصلية (غير مكررة): https://t.me/c/{source_channel_id_for_link}/{original_msg_id}\n"
    report_entry += "الرسائل المكررة:\n"
    for msg_id in duplicate_msg_ids:
        report_entry += f"  - https://t.me/c/{source_channel_id_for_link}/{msg_id}\n"
    report_entry += "\n" # سطر فارغ للفصل بين المجموعات

    final_report_content.append(report_entry)
    print(f"تم إضافة تقرير عن مجموعة تكرار ({len(message_ids)} رسالة) إلى المحتوى النهائي.")


async def send_statistics(client):
    global total_reported_duplicates, total_duplicate_messages_found, start_time, final_report_content
    total_time = time.time() - start_time
    avg_time = sum(t[1] for t in processing_times) / len(processing_times) if processing_times else 0
    slowest_tasks = sorted(processing_times, key=lambda x: x[1], reverse=True)[:3]
    slowest_tasks_str = "\n    ".join([f"- {name}: {duration:.2f}s" for name, duration in slowest_tasks]) if slowest_tasks else "لا يوجد"
    
    # بناء التقرير الإحصائي الذي سيضاف إلى الملف النصي
    stats_report = f"""📊 تقرير الأداء النهائي 📊
----------------------------
• مجموعات التكرار التي تم اكتشافها: {total_reported_duplicates}
• إجمالي الرسائل المكررة التي تم تحديدها: {total_duplicate_messages_found} (باستثناء الأصول)
• الوقت الكلي للعملية: {total_time:.2f} ثانية
• متوسط وقت المهمة: {avg_time:.2f} ثانية
• المهام الأبطأ:
    {slowest_tasks_str}
----------------------------
"""
    final_report_content.insert(0, stats_report) # أضف التقرير الإحصائي في بداية الملف

    # كتابة التقرير بالكامل إلى ملف نصي
    report_filename = f"duplicate_files_report_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write("".join(final_report_content))
        print(f"✅ تم حفظ التقرير الشامل في الملف: {report_filename}")
    except Exception as e:
        print(f"⚠️ خطأ أثناء حفظ التقرير في الملف: {e}")

    # (اختياري) يمكنك إرسال إحصائيات موجزة إلى قناة السجلات إذا أردت
    # try:
    #     if CHANNEL_ID_LOG != 0:
    #         await client.send_message(CHANNEL_ID_LOG, stats_report, parse_mode=ParseMode.MARKDOWN)
    #         print("✅ تم إرسال التقرير الإحصائي الموجز إلى قناة السجلات.")
    # except Exception as e:
    #     print(f"⚠️ خطأ أثناء إرسال التقرير الإحصائي الموجز إلى قناة السجلات: {e}")


async def find_and_report_duplicates(client, channel_id):
    global start_time # استخدام المتغير العام
    start_time = time.time()
    print("🔍 بدأ تحليل الملفات في القناة (اعتمادًا على حجم الملف فقط)...")
    file_dict = await collect_files(client, channel_id, FIRST_MSG_ID)
    print("⚡ بدأ إعداد تقارير الروابط للملفات المكررة...")

    duplicate_groups_to_report = [(file_size, msg_ids) for file_size, msg_ids in file_dict.items() if len(msg_ids) > 1]
    print(f"سيتم معالجة {len(duplicate_groups_to_report)} مجموعة من التكرارات.")

    for file_size, msg_ids in duplicate_groups_to_report:
        await prepare_duplicate_report_entry(channel_id, msg_ids)
    
    await send_statistics(client) # هذه الدالة الآن تقوم بحفظ التقرير إلى ملف

    print(f"🏁 اكتملت العملية في {time.time()-start_time:.2f} ثانية.")

# ----------------- الدالة الرئيسية -----------------

async def main():
    # استخدام توكن البوت بدلاً من سلسلة الجلسة
    async with Client(
        "my_bot_session", # هذا الاسم يستخدم لتخزين معلومات الكاش، ليس الجلسة
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN # <--- هذا هو التغيير الرئيسي هنا
    ) as client:
        print("🚀 اتصال ناجح بالتيليجرام عبر Pyrogram.")

        print("💡 جارٍ التحقق من الوصول إلى القنوات (فقط للتحقق من المعرفات)...")
        try:
            # التحقق من أن CHANNEL_ID_LOG هو معرف صالح (وإن لم نعد نستخدمه لإرسال التقارير الرئيسية)
            if CHANNEL_ID_LOG == 0:
                print("⚠️ تنبيه: CHANNEL_ID_LOG غير محدد. لن يتم إرسال رسائل بدء/نهاية المعالجة إلى Telegram.")
            else:
                await client.get_chat(CHANNEL_ID_LOG) # تحقق فقط من صلاحيته

            await client.get_chat(CHANNEL_ID)
            print("✅ تم التحقق من الوصول إلى القنوات بنجاح.")
        except Exception as e:
            print(f"❌ خطأ فادح: لا يمكن الوصول إلى إحدى القنوات أو لم يتم تعيينها بشكل صحيح.")
            print(f"تفاصيل الخطأ: {e}")
            # لم نعد نرسل رسالة خطأ إلى قناة السجلات لمنع حدوث مشاكل في حال كان CHANNEL_ID_LOG هو المشكلة
            return

        # --- رسالة بداية المعالجة (اختيارية، يمكن إرسالها إلى قناة السجلات إذا كانت موجودة) ---
        if CHANNEL_ID_LOG != 0:
            start_message = "✨ **بدء عملية فحص التكرار!**\n\n`جاري تحليل الملفات في القناة والبحث عن المكررات، وسيتم حفظ التقرير في ملف نصي محلي.`"
            try:
                await client.send_message(CHANNEL_ID_LOG, start_message, parse_mode=ParseMode.MARKDOWN)
                print("✅ تم إرسال رسالة بداية المعالجة.")
            except Exception as e:
                print(f"⚠️ فشل في إرسال رسالة البداية إلى قناة السجلات: {e}")
        # ----------------------------------------------------------------------------------

        await find_and_report_duplicates(client, CHANNEL_ID)

        # --- رسالة نهاية المعالجة (اختيارية، يمكن إرسالها إلى قناة السجلات) ---
        if CHANNEL_ID_LOG != 0:
            end_message = "🎉 **اكتملت عملية فحص التكرار!**\n\n`تم فحص جميع الملفات المطلوبة وحفظ التقرير في ملف نصي محلي.`"
            try:
                await client.send_message(CHANNEL_ID_LOG, end_message, parse_mode=ParseMode.MARKDOWN)
                print("✅ تم إرسال رسالة نهاية المعالجة.")
            except Exception as e:
                print(f"⚠️ فشل في إرسال رسالة النهاية إلى قناة السجلات: {e}")
        # --------------------------------------------------------------------

if __name__ == '__main__':
    print("🔹 بدء التشغيل...")
    asyncio.run(main())
