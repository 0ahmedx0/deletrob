import asyncio
import os
import time
from datetime import datetime

from pyrogram import Client
from pyrogram.enums import ParseMode
from dotenv import load_dotenv

# تحميل إعدادات البيئة
load_dotenv()

# --- إعدادات أساسية ---
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('SESSION')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))       # القناة التي سيتم فحصها (المصدر)
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))   # أول رسالة يتوقف عندها الفحص

# --- إعدادات مخصصة للمهمة الجديدة ---
SIZE_LIMIT_MB = 50  # حد الحجم بالميجابايت
SIZE_LIMIT_BYTES = SIZE_LIMIT_MB * 1024 * 1024  # تحويل الحجم إلى بايت

# --- متغيرات لتتبع الأداء والنتائج ---
start_time = None
found_videos_count = 0
report_lines = []  # قائمة لتخزين نتائج البحث في الذاكرة

# ----------------- الدوال -----------------

def write_report_to_file():
    """
    يكتب التقرير النهائي الذي تم تجميعه في ملف نصي.
    """
    global found_videos_count, start_time, report_lines
    
    if not report_lines:
        print("ℹ️ لم يتم العثور على أي فيديوهات تطابق المعايير، لذا لن يتم إنشاء ملف تقرير.")
        return

    total_time = time.time() - start_time
    
    # إنشاء اسم ملف فريد باستخدام التاريخ والوقت الحالي
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"report_large_videos_{timestamp}.txt"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            # كتابة رأس التقرير (الملخص)
            f.write("📊 تقرير الفيديوهات ذات الحجم الكبير 📊\n")
            f.write("=======================================\n")
            f.write(f"• القناة التي تم فحصها: {CHANNEL_ID}\n")
            f.write(f"• معيار البحث: فيديوهات أكبر من {SIZE_LIMIT_MB} ميجابايت\n")
            f.write(f"• إجمالي الفيديوهات التي تم العثور عليها: {found_videos_count}\n")
            f.write(f"• مدة الفحص: {total_time:.2f} ثانية\n")
            f.write("=======================================\n\n")
            
            # كتابة قائمة الفيديوهات التي تم العثور عليها
            f.write("قائمة الفيديوهات:\n\n")
            for line in report_lines:
                f.write(line + "\n")

        print(f"\n✅ نجاح! تم حفظ التقرير بالكامل في الملف: {filename}")
        
    except Exception as e:
        print(f"\n❌ خطأ فادح أثناء كتابة ملف التقرير: {e}")

async def scan_for_large_videos(client, source_channel_id):
    """
    يفحص القناة بحثًا عن الفيديوهات والمستندات الفيديو التي يتجاوز حجمها المحدد
    ويقوم بتخزين النتائج في الذاكرة.
    """
    global start_time, found_videos_count, report_lines
    start_time = time.time()
    
    print(f"🔍 بدأ فحص القناة {source_channel_id} عن الفيديوهات الأكبر من {SIZE_LIMIT_MB} ميجابايت...")
    
    messages_scanned = 0
    source_channel_link_prefix = str(source_channel_id).replace("-100", "")

    async for message in client.get_chat_history(source_channel_id):
        # التوقف عند الوصول إلى أقدم رسالة محددة
        if message.id <= FIRST_MSG_ID:
            print("⏹️ تم الوصول إلى أقدم رسالة محددة (FIRST_MSG_ID). إيقاف الفحص.")
            break

        messages_scanned += 1
        if messages_scanned % 500 == 0:
            print(f"⏳ تم فحص {messages_scanned} رسالة حتى الآن...")

        media = message.video or message.document
        
        if not media:
            continue

        is_valid_video_document = (
            message.document and 
            message.document.mime_type and 
            message.document.mime_type.startswith("video/")
        )

        if message.video or is_valid_video_document:
            file_size = media.file_size
            
            if file_size > SIZE_LIMIT_BYTES:
                found_videos_count += 1
                
                link = f"https://t.me/c/{source_channel_link_prefix}/{message.id}"
                size_in_mb = file_size / (1024 * 1024)
                
                # إنشاء نص التقرير للرسالة الحالية
                report_line = (
                    f"🔗 الرابط: {link}\n"
                    f"💾 الحجم: {size_in_mb:.2f} ميجابايت\n"
                    f"--------------------------------"
                )
                
                # إضافة السطر إلى قائمة التقارير في الذاكرة
                report_lines.append(report_line)
                
                # طباعة إشعار في الطرفية للمتابعة المباشرة
                print(f"   [تم العثور على] {link} - الحجم: {size_in_mb:.2f} MB")

    print(f"\n🏁 اكتملت عملية الفحص في {time.time() - start_time:.2f} ثانية.")

# ----------------- الدالة الرئيسية -----------------

async def main():
    async with Client("video_finder_session", api_id=API_ID, api_hash=API_HASH) as client:
        print("🚀 تم الاتصال بنجاح بحساب تيليجرام.")

        print("💡 جارٍ التحقق من صلاحية الوصول إلى القناة المصدر...")
        try:
            await client.get_chat(CHANNEL_ID)
            print("✅ تم التحقق من الوصول إلى القناة بنجاح.")
        except Exception as e:
            print(f"❌ خطأ فادح: لا يمكن الوصول إلى القناة {CHANNEL_ID}. تأكد من صحة المعرف وأن الحساب عضو فيها.")
            print(f"   تفاصيل الخطأ: {e}")
            return

        # --- بدء المهمة الرئيسية ---
        await scan_for_large_videos(client, CHANNEL_ID)
        
        # --- كتابة التقرير المجمع في ملف نصي ---
        write_report_to_file()

if __name__ == '__main__':
    print("🔹 بدء تشغيل السكربت...")
    asyncio.run(main())
