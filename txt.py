import asyncio
import os
import time
import math # لإضافة دالة format_size

from pyrogram import Client
from pyrogram.enums import ParseMode # قد لا تكون ضرورية لكن نتركها
from pyrogram.errors import FloodWait, RPCError # الرسائل غير الضرورية قد تكون مرتبطة بوظائف سابقة
from dotenv import load_dotenv

# تحميل إعدادات البيئة
load_dotenv()

# إعدادات تيليجرام
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')

# اسم ملف الجلسة الذي سيتم حفظه/تحميله منه
# إذا لم يتم تعيين SESSION في .env، فسيتم إنشاء ملف باسم "my_account_session"
SESSION_NAME = os.getenv('SESSION', "my_account_session")

CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0)) # القناة المصدر التي سيتم فحصها
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0)) # يبدأ البحث من هنا للرسائل الأحدث (أي الرسائل الأقدم من هذا ID سيتم تجاهلها)

# --- إعدادات المهمة الجديدة والمحدثة ---
SIZE_THRESHOLD_MB = 50  # حد الحجم بالميغابايت
SIZE_THRESHOLD_BYTES = SIZE_THRESHOLD_MB * 1024 * 1024 # تحويل الحجم إلى بايت
OUTPUT_FILE = "report.txt" # اسم ملف التقرير الناتج

# متغيرات لتتبع الإحصائيات (محدّثة لتناسب التقرير النصي)
start_time = None
total_messages_scanned = 0
total_large_files_found = 0

# ----------------- الدوال المساعدة -----------------

def format_size(size_bytes):
    """تحويل حجم الملف بالبايت إلى صيغة قابلة للقراءة (KB, MB, GB)."""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

# ----------------- الدالة الأساسية للمسح والتقرير -----------------

async def scan_and_report_large_files(client, channel_id, first_msg_id_limit):
    """
    تقوم بمسح القناة لتحديد الفيديوهات والمستندات ذات الحجم الكبير
    وتقوم بكتابة تقرير بذلك في ملف نصي.
    """
    global start_time, total_messages_scanned, total_large_files_found
    start_time = time.time()
    
    large_files_data = [] # لتخزين بيانات الملفات الكبيرة
    
    print(f"🔍 بدأ فحص القناة ID: {channel_id} للبحث عن الفيديوهات والمستندات الأكبر من {SIZE_THRESHOLD_MB} ميجابايت...")
    print(f"  (سيتوقف البحث عند الرسالة ID: {first_msg_id_limit} أو إذا وصل إلى بداية القناة إن لم يتم تعيينه.)")

    try:
        async for message in client.get_chat_history(channel_id):
            total_messages_scanned += 1
            
            # التوقف عند حد FIRST_MSG_ID_LIMIT إذا تم تعيينه
            if first_msg_id_limit and message.id <= first_msg_id_limit:
                print(f"تم الوصول إلى الرسالة ID: {message.id} (حد البحث)، توقف المسح.")
                break

            # لتجنب مسح قنوات ضخمة جداً إلى الأبد إذا لم يتم تحديد FIRST_MSG_ID
            # يمكنك تعديل هذا الشرط حسب الحاجة
            if not first_msg_id_limit and total_messages_scanned % 1000 == 0 and message.id < 50:
                print("⚠️ تم مسح أكثر من 1000 رسالة قديمة جدًا بدون حد `FIRST_MSG_ID`، توقف المسح لتجنب الإفراط.")
                break

            # طباعة التقدم كل 500 رسالة
            if total_messages_scanned % 500 == 0:
                print(f"تم مسح {total_messages_scanned} رسالة حتى الآن...")

            # التحقق مما إذا كانت الرسالة فيديو أو مستند
            media_object = None
            if message.video:
                media_object = message.video
            elif message.document:
                # يمكنك إضافة أنواع مستندات معينة هنا إذا أردت، مثل 'video/mp4' للمستندات التي هي في الأصل فيديوهات
                media_object = message.document

            # إذا كانت الرسالة تحتوي على وسائط لها حجم ملف
            if media_object and hasattr(media_object, 'file_size') and media_object.file_size is not None:
                if media_object.file_size > SIZE_THRESHOLD_BYTES:
                    # بناء رابط الرسالة للقناة العامة/الخاصة
                    # معرف القناة يتم تعديله ليتوافق مع رابط تليجرام الرسمي
                    chat_id_for_link = str(channel_id).replace("-100", "")
                    message_link = f"https://t.me/c/{chat_id_for_link}/{message.id}"
                    
                    file_size_formatted = format_size(media_object.file_size)
                    
                    large_files_data.append({
                        "link": message_link,
                        "size": file_size_formatted,
                        "raw_size_bytes": media_object.file_size,
                        "message_id": message.id
                    })
                    total_large_files_found += 1
                    print(f"✅ تم العثور على ملف كبير: {message_link} | الحجم: {file_size_formatted}")

            # إضافة تأخير بسيط لتجنب FloodWait إذا كانت هناك مشكلات، أو ليكون سلوك البوت أكثر طبيعية
            await asyncio.sleep(0.1) # 100 ميلي ثانية لكل رسالة

    except FloodWait as e:
        print(f"⏳ واجهت Pyrogram FloodWait. سأنتظر {e.value} ثانية قبل إعادة المحاولة. ثم سيستأنف البحث.")
        await asyncio.sleep(e.value + 5) # انتظر وقتاً إضافياً لضمان التعافي
        # بعد الانتظار، السكربت سيستأنف من حيث توقف thanks to async for
        await scan_and_report_large_files(client, channel_id, first_msg_id_limit) # قد يتسبب في تكرار بسيط، الأفضل أن تعالجه في نفس الدالة.
                                                                                # الخيار الحالي مع `async for` عادةً ما يتابع بشكل طبيعي بعد الانتظار.
    except RPCError as e:
        print(f"⚠️ خطأ RPC أثناء المسح: {e}. قد يكون هذا خطأ في الاتصال أو الصلاحيات.")
    except Exception as e:
        print(f"❌ حدث خطأ غير متوقع أثناء مسح القناة: {e}")

    # بعد الانتهاء من المسح، نكتب التقرير
    await write_report_to_file(large_files_data)
    
    total_time = time.time() - start_time
    print(f"\n🏁 اكتملت عملية البحث والتقرير!")
    print(f"   إجمالي الرسائل التي تم فحصها: {total_messages_scanned} رسالة.")
    print(f"   إجمالي الفيديوهات والمستندات الكبيرة التي تم العثور عليها: {total_large_files_found} ملف.")
    print(f"   تم حفظ التقرير في: {OUTPUT_FILE}")
    print(f"   الوقت الكلي المستغرق: {total_time:.2f} ثانية.")

async def write_report_to_file(files_list):
    """
    تنشئ أو تحدّث ملف نصي يحتوي على تقرير بالملفات الكبيرة التي تم العثور عليها.
    """
    print(f"\n📝 جاري كتابة التقرير في الملف: {OUTPUT_FILE}")
    
    # فرز الملفات حسب الحجم تنازلياً (من الأكبر للأصغر)
    sorted_files = sorted(files_list, key=lambda x: x['raw_size_bytes'], reverse=True)

    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(f"تقرير بالرسائل التي تحتوي على فيديوهات أو مستندات بحجم أكبر من {SIZE_THRESHOLD_MB} ميجابايت.\n")
            f.write(f"تاريخ التقرير: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 70 + "\n\n")
            
            if not sorted_files:
                f.write("لم يتم العثور على أي ملفات تطابق المعايير.\n")
                
            else:
                for idx, item in enumerate(sorted_files, 1):
                    f.write(f"[{idx}] الرابط: {item['link']}\n")
                    f.write(f"      الحجم: {item['size']}\n")
                    f.write(f"      معرف الرسالة: {item['message_id']}\n")
                    f.write("-" * 30 + "\n")
            
        print(f"✅ تم حفظ التقرير بنجاح في '{OUTPUT_FILE}'.")
    except Exception as e:
        print(f"❌ فشل في كتابة ملف التقرير '{OUTPUT_FILE}': {e}")


# ----------------- الدالة الرئيسية لتشغيل السكربت -----------------

async def main():
    # سيقوم Pyrogram بإنشاء/تحميل الجلسة تلقائياً بناءً على اسم الملف المحدد
    # اسم الملف سيتم أخذه من SESSION_NAME والذي يتم تعيينه من .env أو يستخدم الافتراضي "my_account_session"
    async with Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH) as client:
        # هذه الخطوة مهمة لكي يكتمل Pyrogram عملية إنشاء الجلسة لأول مرة (رقم الهاتف/رمز التحقق)
        try:
            user = await client.get_me()
            print(f"🚀 اتصال ناجح بالتيليجرام عبر Pyrogram كـ: {user.first_name}")
        except Exception as e:
            print(f"❌ خطأ فادح أثناء الاتصال بـ Telegram. ربما معلومات الجلسة غير صحيحة أو بحاجة للتحديث: {e}")
            print("الرجاء التأكد من صحة API_ID و API_HASH ومن إمكانية الوصول للشبكة.")
            return

        print("\n💡 جارٍ التحقق من الوصول إلى القناة المصدر...")
        try:
            # التحقق من أن CHANNEL_ID هو قناة مصدر صالحة
            if CHANNEL_ID == 0:
                raise ValueError("CHANNEL_ID لم يتم تعيينه بشكل صحيح في ملف .env. يجب أن يكون معرف قناة صالحًا (مثل -100xxxxxxxxxx).")
            
            chat_info = await client.get_chat(CHANNEL_ID)
            print(f"✅ تم التحقق من الوصول إلى القناة المصدر '{chat_info.title}' (ID: {CHANNEL_ID}) بنجاح.")

            # بدء عملية المسح والتقرير
            await scan_and_report_large_files(client, CHANNEL_ID, FIRST_MSG_ID)

        except FloodWait as e:
            print(f"⏳ واجهت Pyrogram FloodWait في مرحلة التحقق من القنوات. يرجى الانتظار {e.value} ثانية ثم إعادة المحاولة.")
            # هنا يفضل الانتظار يدوياً ثم إعادة التشغيل الكامل للسكربت
            await asyncio.sleep(e.value + 5)
        except Exception as e:
            print(f"❌ خطأ فادح: لا يمكن الوصول إلى القناة المحددة (CHANNEL_ID) أو حدث خطأ أثناء الاتصال.")
            print(f"تفاصيل الخطأ: {e}")
            print("الرجاء التحقق من معرف CHANNEL_ID، وتأكد من أن حسابك عضو في هذه القناة.")

if __name__ == '__main__':
    print("🔹 بدء تشغيل السكربت...")
    # التحقق من وجود المتغيرات الأساسية
    if not all([API_ID, API_HASH, CHANNEL_ID]):
        print("❌ خطأ: يرجى التأكد من تعيين كل من API_ID, API_HASH, CHANNEL_ID في ملف .env.")
        print("تأكد أن API_ID و API_HASH هي أرقام نصية (String) ومعرفات القنوات أرقام صحيحة.")
    else:
        asyncio.run(main())
