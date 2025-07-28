import asyncio
import os
import time

from pyrogram import Client
from dotenv import load_dotenv

# تحميل إعدادات البيئة
load_dotenv()

# إعدادات تيليجرام
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('SESSION') # سيتم استخدامه لإنشاء اسم ملف الجلسة
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))  # القناة المصدر التي سيتم فحصها
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))

# تحديد حجم الملف بالبايت (50 ميجابايت)
MIN_FILE_SIZE_BYTES = 50 * 1024 * 1024

# اسم ملف التقرير
REPORT_FILENAME = "report.txt"

# ----------------- الدوال -----------------

async def collect_large_files(client, channel_id, first_msg_id):
    """
    تقوم بمسح القناة وتجميع الرسائل التي تحتوي على فيديوهات أو مستندات
    أكبر من الحجم المحدد.
    """
    large_files_messages = []
    print("جاري مسح الرسائل في القناة للبحث عن الملفات الكبيرة...")
    messages_scanned = 0
    
    async for message in client.get_chat_history(channel_id):
        if message.id <= first_msg_id:
            break

        messages_scanned += 1
        if messages_scanned % 500 == 0:
            print(f"تم مسح {messages_scanned} رسالة حتى الآن...")

        media = message.video or message.document
        if media and hasattr(media, 'file_size') and media.file_size > MIN_FILE_SIZE_BYTES:
            large_files_messages.append(message)
            
    print(f"اكتمل المسح. تم العثور على {len(large_files_messages)} ملف بحجم أكبر من 50 ميجابايت.")
    return large_files_messages

async def generate_report_file(messages, source_chat_id):
    """
    تقوم بإنشاء ملف نصي يحتوي على روابط وأحجام الملفات الكبيرة.
    """
    if not messages:
        print("لم يتم العثور على ملفات تطابق الشروط. لن يتم إنشاء ملف تقرير.")
        return

    source_channel_id_for_link = str(source_chat_id).replace("-100", "")

    with open(REPORT_FILENAME, 'w', encoding='utf-8') as f:
        f.write(f"تقرير بالملفات التي يزيد حجمها عن {MIN_FILE_SIZE_BYTES / (1024*1024):.0f} ميجابايت\n")
        f.write("="*50 + "\n\n")

        # فرز الرسائل من الأقدم إلى الأحدث لعرضها بترتيب منطقي في التقرير
        sorted_messages = sorted(messages, key=lambda m: m.id)

        for message in sorted_messages:
            media = message.video or message.document
            file_size_mb = media.file_size / (1024 * 1024)
            link = f"https://t.me/c/{source_channel_id_for_link}/{message.id}"
            
            report_line = f"الرابط: {link}\nالحجم: {file_size_mb:.2f} MB\n"
            report_line += "-"*30 + "\n"
            
            f.write(report_line)

    print(f"✅ تم إنشاء التقرير بنجاح وحفظه في ملف: {REPORT_FILENAME}")

async def find_large_files_and_report(client, channel_id):
    """
    الوظيفة الرئيسية التي تنسق عملية البحث وإنشاء التقرير.
    """
    start_time = time.time()
    print("\n🔍 بدء عملية البحث عن الفيديوهات والمستندات التي يزيد حجمها عن 50 ميجابايت...")
    
    large_files = await collect_large_files(client, channel_id, FIRST_MSG_ID)
    
    await generate_report_file(large_files, channel_id)
    
    print(f"🏁 اكتملت العملية في {time.time() - start_time:.2f} ثانية.")

# ----------------- الدالة الرئيسية (مع التحقق المدمج) -----------------

async def main():
    # استخدام اسم جلسة مخصص لتجنب التعارض. Pyrogram سيُنشئ ملف 'scanner_session.session'
    async with Client("scanner_session", api_id=API_ID, api_hash=API_HASH) as client:
        print("🚀 اتصال ناجح بالتيليجرام عبر Pyrogram.")

        # --- بداية كتلة التحقق المطلوبة ---
        print("💡 جارٍ التحقق من الوصول إلى القناة المصدر...")
        try:
            # التحقق من أن الحساب يمكنه الوصول إلى القناة المطلوبة
            await client.get_chat(CHANNEL_ID)
            print("✅ تم التحقق من الوصول إلى القناة المصدر بنجاح.")
        except Exception as e:
            # في حالة الفشل، اطبع رسالة خطأ واضحة وتوقف عن التنفيذ
            print(f"❌ خطأ فادح: لا يمكن الوصول إلى القناة المصدر (CHANNEL_ID: {CHANNEL_ID}).")
            print(f"تفاصيل الخطأ: {e}")
            print("\nيرجى التأكد من أن: \n1. معرف القناة صحيح.\n2. الحساب المستخدم هو عضو في القناة الخاصة.")
            return # إيقاف السكربت
        # --- نهاية كتلة التحقق ---

        # إذا نجح التحقق، استمر في تنفيذ الوظيفة الرئيسية
        await find_large_files_and_report(client, CHANNEL_ID)

if __name__ == '__main__':
    print("🔹 بدء تشغيل أداة فحص الملفات الكبيرة...")
    asyncio.run(main())
