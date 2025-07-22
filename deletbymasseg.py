# متغير لتخزين آخر قيمة تأخير مستخدمة
prev_delay = None

import random
import asyncio
import os
import time

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, MessageDeleteForbidden, RPCError
from dotenv import load_dotenv

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
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0)) # قناة السجلات والوجهة للمكررات المنقولة
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))

# إحصائيات وأداء (تعريف المتغيرات العامة)
total_reported_duplicates = 0
total_duplicate_messages = 0
total_deleted_messages = 0 # عداد جديد للرسائل المحذوفة
total_moved_messages = 0   # عداد جديد للرسائل المنقولة
processing_times = []
start_time = None

# ----------------- الدوال -----------------

async def delete_message(client, chat_id, message_id):
    """تحذف رسالة من قناة مع معالجة الأخطاء."""
    global total_deleted_messages
    try:
        await client.delete_messages(chat_id, message_id)
        total_deleted_messages += 1
        print(f"🗑️ تم حذف الرسالة ID: {message_id} من {chat_id}.")
        return True
    except FloodWait as e:
        print(f"⏳ (حذف الرسائل) انتظر {e.value} ثانية قبل إعادة المحاولة...")
        await asyncio.sleep(e.value + 1)
        await client.delete_messages(chat_id, message_id) # محاولة أخرى بعد الانتظار
        total_deleted_messages += 1
        return True
    except MessageDeleteForbidden:
        print(f"🚫 لا يمكن حذف الرسالة ID: {message_id}. البوت لا يمتلك الصلاحيات الكافية.")
        return False
    except RPCError as e:
        print(f"⚠️ خطأ RPC أثناء حذف الرسالة ID: {message_id}: {e}")
        return False
    except Exception as e:
        print(f"⚠️ خطأ غير متوقع أثناء حذف الرسالة ID: {message_id}: {e}")
        return False

async def collect_files(client, channel_id, first_msg_id):
    global processing_times # التصريح باستخدام المتغير العام
    file_dict = {}
    start_collect = time.time()

    # تأمين الوصول إلى file_dict لتجنب مشاكل التزامن
    lock = asyncio.Lock()

    async def process_message(message):
        media = message.document or message.video or message.audio
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

async def send_duplicate_links_report(client, source_chat_id, destination_chat_id, message_ids):
    global total_reported_duplicates, total_duplicate_messages, total_deleted_messages, total_moved_messages
    if not message_ids or len(message_ids) < 2:
        return # لا يوجد تكرار إذا كانت الرسائل أقل من 2

    message_ids.sort()
    original_msg_id = message_ids[0]
    duplicate_msg_ids = message_ids[1:] # جميع الرسائل ما عدا الأولى تعتبر مكررة

    total_reported_duplicates += 1
    total_duplicate_messages += len(duplicate_msg_ids) # العدد الكلي للرسائل المكررة التي سيتم التعامل معها

    source_channel_id_for_link = str(source_chat_id).replace("-100", "")

    # سنقوم بنقل أول رسالة مكررة (غير الأصلية)
    msg_id_to_move = duplicate_msg_ids[0] # الرسالة التي سيتم نقلها
    
    moved_successfully = False
    deleted_duplicates_count = 0
    
    # 1. نقل الرسالة المكررة المحددة إلى قناة الوجهة
    try:
        start_transfer = time.time()
        # جلب الرسالة للنقل
        message_to_repost = await client.get_messages(source_chat_id, msg_id_to_move)
        
        # إعادة توجيه الرسالة (أو إرسال نسخة منها) إلى قناة الوجهة
        # استخدام `copy_message` أفضل للحفاظ على التنسيق والكبشن وتغيير المحتوى إن لزم الأمر.
        # `forward_messages` تنقل الرسالة كما هي مع اسم المرسل الأصلي.
        
        # إذا كنت تريد "نسخ" الرسالة، بحيث تظهر وكأن البوت هو من أرسلها في الوجهة:
        await client.copy_message(
            chat_id=destination_chat_id,
            from_chat_id=source_chat_id,
            message_id=msg_id_to_move
        )
        print(f"✅ تم نقل الرسالة المكررة ID: {msg_id_to_move} إلى قناة السجل ({destination_chat_id}).")
        total_moved_messages += 1
        moved_successfully = True
        processing_times.append(('transfer_duplicate_message', time.time() - start_transfer))

    except FloodWait as e:
        print(f"⏳ (نقل الرسالة) انتظر {e.value} ثانية...")
        await asyncio.sleep(e.value + 1)
        try: # محاولة إعادة النقل بعد الانتظار
            message_to_repost = await client.get_messages(source_chat_id, msg_id_to_move)
            await client.copy_message(chat_id=destination_chat_id, from_chat_id=source_chat_id, message_id=msg_id_to_move)
            total_moved_messages += 1
            moved_successfully = True
        except Exception as retry_e:
            print(f"⚠️ فشل إعادة نقل الرسالة بعد FloodWait: {retry_e}")
    except Exception as e:
        print(f"⚠️ خطأ أثناء نقل الرسالة المكررة ID: {msg_id_to_move}: {e}")

    # 2. حذف الرسائل المكررة من القناة الأصلية (بما في ذلك الرسالة المنقولة)
    # لا تحذف الرسالة الأصلية (original_msg_id)
    messages_to_delete = [msg_id for msg_id in message_ids if msg_id != original_msg_id]

    print(f"🗑️ جاري حذف {len(messages_to_delete)} رسالة مكررة من القناة الأصلية...")
    for msg_id in messages_to_delete:
        if await delete_message(client, source_chat_id, msg_id):
            deleted_duplicates_count += 1
        # إضافة تأخير بسيط بين عمليات الحذف لتجنب FloodWait إضافية
        await asyncio.sleep(1)

    # 3. إعداد و إرسال التقرير
    report_message = f"📌 **تقرير الملفات المكررة والحذف والنقل!**\n\n"
    report_message += f"🔗 **الرسالة الأصلية (غير محذوفة):** https://t.me/c/{source_channel_id_for_link}/{original_msg_id}\n\n"

    if moved_successfully:
        report_message += f"✅ **تم نقل نسخة مكررة (ID: {msg_id_to_move}) إلى:** https://t.me/c/{str(destination_chat_id).replace('-100', '')}/{message_to_repost.id if 'message_to_repost' in locals() else '؟؟؟'} \n"
    else:
        report_message += f"❌ **فشل نقل الرسالة المكررة ID: {msg_id_to_move}.**\n"

    report_message += f"🗑️ **تم حذف {deleted_duplicates_count} رسالة مكررة من القناة الأصلية.**\n"
    if deleted_duplicates_count < len(messages_to_delete):
        report_message += f"⚠️ **فشل حذف {len(messages_to_delete) - deleted_duplicates_count} رسالة.**\n"
        
    if len(duplicate_msg_ids) > 1: # إذا كان هناك أكثر من نسخة مكررة واحدة (عدا التي نقلت)
        remaining_duplicates_for_report = [m_id for m_id in duplicate_msg_ids if m_id != msg_id_to_move]
        if remaining_duplicates_for_report:
            report_message += "\n**روابط النسخ المكررة الأخرى التي تم التعامل معها (والمحذوفة):**\n"
            for msg_id in remaining_duplicates_for_report:
                report_message += f"https://t.me/c/{source_channel_id_for_link}/{msg_id}\n"

    try:
        start_send = time.time()
        await client.send_message(destination_chat_id, report_message, parse_mode=ParseMode.MARKDOWN)
        print(f"✅ تم إرسال تقرير شامل.")
        processing_times.append(('send_detailed_report', time.time() - start_send))
    except FloodWait as e:
        print(f"⏳ (تقرير شامل) انتظر {e.value} ثانية...")
        await asyncio.sleep(e.value + 1)
        await client.send_message(destination_chat_id, report_message, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"⚠️ خطأ أثناء إرسال التقرير الشامل: {e}")

    # --- تطبيق التأخير العشوائي بعد إرسال التقرير ---
    delay = get_random_delay()
    print(f"😴 انتظار {delay:.2f} ثوانٍ قبل معالجة المجموعة التالية...")
    await asyncio.sleep(delay)
    # -------------------------------------------------


async def send_statistics(client):
    global total_reported_duplicates, total_duplicate_messages, total_deleted_messages, total_moved_messages, start_time
    total_time = time.time() - start_time
    avg_time = sum(t[1] for t in processing_times) / len(processing_times) if processing_times else 0
    slowest_tasks = sorted(processing_times, key=lambda x: x[1], reverse=True)[:3]
    slowest_tasks_str = "\n    ".join([f"- {name}: {duration:.2f}s" for name, duration in slowest_tasks]) if slowest_tasks else "لا يوجد"
    report = f"""📊 **تقرير الأداء النهائي** 📊
----------------------------
• مجموعات التكرار التي تم الإبلاغ عنها: `{total_reported_duplicates}` 📝
• إجمالي الرسائل المكررة التي تم تحديدها: `{total_duplicate_messages}` 🔎 (باستثناء الأصول)
• الرسائل المنقولة إلى قناة الوجهة: `{total_moved_messages}` ➡️
• إجمالي الرسائل المحذوفة من القناة الأصلية: `{total_deleted_messages}` 🗑️
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
    print("⚡ بدأ إعداد تقارير الروابط للملفات المكررة وحذفها ونقلها...")

    duplicate_groups_to_report = [(file_size, msg_ids) for file_size, msg_ids in file_dict.items() if len(msg_ids) > 1]
    print(f"سيتم معالجة {len(duplicate_groups_to_report)} مجموعة من التكرارات (نقل/حذف/تقرير).")

    for file_size, msg_ids in duplicate_groups_to_report:
        await send_duplicate_links_report(client, channel_id, CHANNEL_ID_LOG, msg_ids)
    
    await send_statistics(client)
    print(f"🏁 اكتملت العملية في {time.time()-start_time:.2f} ثانية.")

# ----------------- الدالة الرئيسية -----------------

async def main():
    async with Client("new_pyrogram_session", api_id=API_ID, api_hash=API_HASH) as client:
        print("🚀 اتصال ناجح بالتيليجرام عبر Pyrogram.")

        print("💡 جارٍ التحقق من الوصول إلى القنوات...")
        try:
            # التحقق من أن CHANNEL_ID_LOG هو قناة وجهة صالحة
            if CHANNEL_ID_LOG == 0:
                raise ValueError("CHANNEL_ID_LOG لم يتم تعيينه بشكل صحيح. يجب أن يكون معرف قناة صالحًا.")

            await client.get_chat(CHANNEL_ID)
            await client.get_chat(CHANNEL_ID_LOG)
            print("✅ تم التحقق من الوصول إلى القنوات بنجاح.")
        except Exception as e:
            print(f"❌ خطأ فادح: لا يمكن الوصول إلى إحدى القنوات أو لم يتم تعيينها بشكل صحيح.")
            print(f"تفاصيل الخطأ: {e}")
            try:
                if CHANNEL_ID_LOG != 0: # حاول إرسال الخطأ فقط إذا كان ID القناة الوجهة معرفاً بشكل صحيح
                    await client.send_message(CHANNEL_ID_LOG, f"❌ **فشل في بدء عملية فحص التكرار!**\n\nسبب الخطأ: `{e}`\n\nيرجى التحقق من معرفات القنوات والإذن.", parse_mode=ParseMode.MARKDOWN)
            except Exception as send_e:
                print(f"⚠️ فشل في إرسال رسالة الخطأ إلى قناة السجلات: {send_e}")
            return

        # --- رسالة بداية المعالجة ---
        start_message = "✨ **بدء عملية فحص التكرار والنقل والحذف والتبليغ!**\n\n`جاري تحليل الملفات في القناة والبحث عن المكررات، نقلها، حذفها، وتقديم التقارير.`"
        try:
            await client.send_message(CHANNEL_ID_LOG, start_message, parse_mode=ParseMode.MARKDOWN)
            print("✅ تم إرسال رسالة بداية المعالجة.")
        except Exception as e:
            print(f"⚠️ فشل في إرسال رسالة البداية إلى قناة السجلات: {e}")
        # ---------------------------

        await find_and_report_duplicates(client, CHANNEL_ID)

        # --- رسالة نهاية المعالجة ---
        end_message = "🎉 **اكتملت عملية فحص التكرار والنقل والحذف والتبليغ!**\n\n`تم فحص جميع الملفات المطلوبة وإرسال التقارير، ونقل النسخ المحددة وحذف المكررات.`"
        try:
            await client.send_message(CHANNEL_ID_LOG, end_message, parse_mode=ParseMode.MARKDOWN)
            print("✅ تم إرسال رسالة نهاية المعالجة.")
        except Exception as e:
            print(f"⚠️ فشل في إرسال رسالة النهاية إلى قناة السجلات: {e}")
        # ---------------------------

if __name__ == '__main__':
    print("🔹 بدء التشغيل...")
    asyncio.run(main())
