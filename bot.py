import telebot
from telebot import types
import sqlite3
import random
import re
import os
import threading
import http.server
import socketserver
import docx
import PyPDF2
import pandas as pd
from datetime import datetime

# O'ZINGIZNING ENG OXIRGI YANGI TOKENINGIZNI SHU YERGA QO'YING:
TOKEN = '8917939430:AAGfZtgH6TEB1lq4Nvq-vPxw4wQDBQBavvM' 
bot = telebot.TeleBot(TOKEN)
bot_info = bot.get_me()

# =====================================================================
# ⚙️ ASOSIY SOZLAMALAR
# =====================================================================
ADMIN_ID = 6638229765  
CARD_NUMBER = '9860 1201 5457 0036'  
BANK_NAME = 'Muzaffar Abdumalikov'
ADMIN_USERNAME = '@Abdumal1koff_Muzaffar'
# =====================================================================

# =====================================================================
# 🌐 RENDER PLATFORMASI UCHUN VEB-PORT TIZIMI
# =====================================================================
def run_dummy_server():
    PORT = int(os.environ.get("PORT", 8080))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()
# =====================================================================

# --- MENYUNI SOZLASH ---
def set_bot_menu():
    public_commands = [
        types.BotCommand("start", "Botni ishga tushirish"),
        types.BotCommand("top", "🏆 Eng kuchli bilimdonlar reytingi"),
        types.BotCommand("help", "Fayl formati qoidalari"),
        types.BotCommand("restart", "Yechilgan testlar tarixini tozalash"),
        types.BotCommand("finish", "Faol quizni yakunlash")
    ]
    bot.set_my_commands(public_commands)
    
    admin_commands = public_commands.copy()
    admin_commands.append(types.BotCommand("stat", "👑 Admin Panel"))
    try:
        bot.set_my_commands(admin_commands, scope=types.BotCommandScopeChat(ADMIN_ID))
    except Exception:
        pass

set_bot_menu()

user_data = {}
poll_to_user = {}

def smart_truncate(text, max_length=100, suffix='...'):
    if len(text) <= max_length: return text
    truncated = text[:max_length - len(suffix)]
    last_space = truncated.rfind(' ')
    return (truncated[:last_space] + suffix) if last_space != -1 else (truncated + suffix)

# --- BAZA SOZLAMALARI ---
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS history (user_id INTEGER, question_text TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS vip_users (user_id INTEGER PRIMARY KEY, is_vip INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_stats (
                        user_id INTEGER PRIMARY KEY, 
                        first_name TEXT,
                        trials_left INTEGER DEFAULT 1, 
                        total_correct INTEGER DEFAULT 0,
                        referrals_count INTEGER DEFAULT 0,
                        join_date DATE DEFAULT CURRENT_DATE
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS channels (
                        channel_id TEXT PRIMARY KEY,
                        channel_title TEXT,
                        channel_invite_link TEXT
                    )''')
    conn.commit()
    conn.close()

init_db()

# --- FOYDALANUVCHI VA OBUNA FUNKSIYALARI ---
def check_vip_status(user_id):
    if user_id == ADMIN_ID: return True
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_vip FROM vip_users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def check_all_subscriptions(user_id):
    if user_id == ADMIN_ID: return True
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, channel_title, channel_invite_link FROM channels")
    channels = cursor.fetchall()
    conn.close()

    if not channels: return True

    not_subscribed = []
    for ch_id, ch_title, ch_link in channels:
        try:
            member = bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append((ch_title, ch_link))
        except Exception:
            not_subscribed.append((ch_title, ch_link))
    return not_subscribed

def require_subscription(message):
    chat_id = message.chat.id
    unsubscribed = check_all_subscriptions(chat_id)
    
    if unsubscribed is not True and len(unsubscribed) > 0:
        markup = types.InlineKeyboardMarkup(row_width=1)
        text = "🛑 **Diqqat!**\n\nBotdan foydalanish uchun quyidagi rasmiy kanallarimizga a'zo bo'lishingiz shart:\n\n"
        for idx, (ch_title, ch_link) in enumerate(unsubscribed, 1):
            text += f"{idx}. {ch_title}\n"
            markup.add(types.InlineKeyboardButton(f"📢 {ch_title} ga o'tish", url=ch_link))
        markup.add(types.InlineKeyboardButton("✅ A'zo bo'ldim", callback_data="check_sub_btn"))
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        return True 
    return False 

def get_or_create_user(user_id, first_name, referrer_id=None):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT trials_left FROM user_stats WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.execute("INSERT INTO user_stats (user_id, first_name) VALUES (?, ?)", (user_id, first_name))
        conn.commit()
        if referrer_id and referrer_id != user_id:
            cursor.execute("UPDATE user_stats SET referrals_count = referrals_count + 1 WHERE user_id=?", (referrer_id,))
            conn.commit()
            cursor.execute("SELECT referrals_count FROM user_stats WHERE user_id=?", (referrer_id,))
            ref_count = cursor.fetchone()[0]
            if ref_count % 3 == 0:
                cursor.execute("UPDATE user_stats SET trials_left = trials_left + 1 WHERE user_id=?", (referrer_id,))
                conn.commit()
                bot.send_message(referrer_id, "🎉 **Tabriklaymiz!** Siz 3 ta do'stingizni taklif qildingiz va yana **+1 ta BEPUL fayl yuklash** urinishini qo'lga kiritdingiz!", parse_mode="Markdown")
    conn.close()

def get_trials_left(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT trials_left FROM user_stats WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def use_trial(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE user_stats SET trials_left = trials_left - 1 WHERE user_id=? AND trials_left > 0", (user_id,))
    conn.commit()
    conn.close()

def add_correct_answer(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE user_stats SET total_correct = total_correct + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def send_payment_msg(chat_id):
    pay_text = (
        "🔒 <b>Urinishlaringiz tugadi!</b>\n\n"
        "Botga o'z test fayllaringizni yuklash va telegramda cheksiz yechish <b>umrbod faqat 5 000 so'm</b>.\n\n"
        f"💳 <b>Karta:</b> <code>{CARD_NUMBER}</code>\n"
        f"🏦 <b>Ega:</b> {BANK_NAME}\n\n"
        f"📌 To'lov qilib chekni {ADMIN_USERNAME} ga yuboring va pasdagi ID'ingizni qo'shib yozing.\n\n"
        f"🆔 Sizning ID raqamingiz: <code>{chat_id}</code>"
    )
    bot.send_message(chat_id, pay_text, parse_mode='HTML')

# --- FAYL O'QISH ---
def extract_text_from_file(file_path, file_ext):
    text = ""
    try:
        if file_ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f: text = f.read()
        elif file_ext == '.docx':
            doc = docx.Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
        elif file_ext == '.pdf':
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages: text += page.extract_text() + "\n"
        elif file_ext == '.xlsx':
            df = pd.read_excel(file_path)
            text = "\n".join(df.iloc[:, 0].dropna().astype(str).tolist())
    except Exception as e:
        print(f"Xatolik: {e}")
    return text

def parse_questions(text):
    questions = []
    current_q = None
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        if re.match(r'^\d+\s*\.', line):
            if current_q and len(current_q['options']) >= 2: questions.append(current_q)
            current_q = {'text': line, 'options': [], 'correct': None}
        elif line.startswith('+') and current_q:
            ans = line[1:].strip()
            current_q['options'].append(ans)
            current_q['correct'] = ans
        elif line.startswith('-') and current_q:
            current_q['options'].append(line[1:].strip())
    if current_q and len(current_q['options']) >= 2: questions.append(current_q)
    return questions

# --- BUYRUQLAR VA MENYULAR ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if require_subscription(message): return 
    
    chat_id = message.chat.id
    first_name = message.from_user.first_name if message.from_user.first_name else "Do'stim"
    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    
    get_or_create_user(chat_id, first_name, referrer_id)
    is_vip = check_vip_status(chat_id)
    
    if is_vip:
        text = f"👑 **Assalomu alaykum, {first_name}! VIP profilga xush kelibsiz!**\n\nSiz botdan umrbod va cheksiz foydalanish huquqiga egasiz. Test boshlash uchun shunchaki fayl yuboring."
        bot.send_message(chat_id, text, parse_mode='Markdown')
    else:
        trials = get_trials_left(chat_id)
        ref_link = f"https://t.me/{bot_info.username}?start={chat_id}"
        text = (
            f"👋 **Assalomu alaykum, {first_name}! Quiz Botga xush kelibsiz!**\n\n"
            "Bu bot orqali o'z test fayllaringizni (.txt, .docx, .pdf, .xlsx) yuklab, qulay taymerli quiz shaklida yechishingiz mumkin.\n\n"
            f"🎁 **Sizda qolgan bepul urinishlar:** {trials} ta\n\n"
            f"🤝 **Do'stlarni taklif qiling!** Ushbu ssilka orqali 3 ta do'stingiz botga kirsa, yana 1 ta BEPUL urinish olasiz:\n`{ref_link}`"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        if trials > 0:
            markup.add(types.InlineKeyboardButton("🚀 Test faylini yuklash va boshlash", callback_data="upload_prompt"))
        markup.add(types.InlineKeyboardButton("💎 VIP xarid qilish (Cheksiz)", callback_data="buy_vip"))
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['top'])
def cmd_top(message):
    if require_subscription(message): return
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, total_correct FROM user_stats ORDER BY total_correct DESC LIMIT 10")
    top_users = cursor.fetchall()
    conn.close()
    
    if not top_users:
        bot.send_message(message.chat.id, "Hozircha reyting bo'sh.")
        return
        
    text = "🏆 **ENG KUCHLI BILIMDONLAR TOP-10 REYTINGI:**\n\n"
    medals = ['🥇', '🥈', '🥉']
    for i, user in enumerate(top_users):
        medal = medals[i] if i < 3 else "🔸"
        text += f"{medal} {user[0]} - {user[1]} ta to'g'ri javob\n"
        
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['stat'])
def cmd_stat(message):
    if message.chat.id != ADMIN_ID: return
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_stats")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM user_stats WHERE join_date = CURRENT_DATE")
    today_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM vip_users WHERE is_vip = 1")
    vip_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM channels")
    total_channels = cursor.fetchone()[0]
    conn.close()
    
    text = (
        "👑 **BOSHQARUV PANELIGA XUSH KELIBSIZ!**\n\n"
        "📊 **BOT STATISTIKASI:**\n"
        f"👥 Jami foydalanuvchilar: **{total_users} ta**\n"
        f"🆕 Bugun qo'shilganlar: **{today_users} ta**\n"
        f"💎 VIP mijozlar: **{vip_users} ta**\n"
        f"📢 Majburiy kanallar: **{total_channels} ta**\n\n"
        "Quyidagi tugmalar orqali botni boshqarishingiz mumkin:"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📢 Xabar tarqatish", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("🔄 Panelni yangilash", callback_data="admin_refresh")
    )
    markup.add(
        types.InlineKeyboardButton("➕ Kanal qo'shish", callback_data="admin_add_ch"),
        types.InlineKeyboardButton("❌ Kanalni o'chirish", callback_data="admin_del_ch")
    )
    bot.send_message(ADMIN_ID, text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['addvip'])
def cmd_addvip(message):
    if message.chat.id != ADMIN_ID: return
    
    # 1. ID formatini alohida tekshiramiz
    try:
        target_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        bot.send_message(ADMIN_ID, "❌ Xatolik! Format: `/addvip USER_ID`\nID faqat raqamlardan iborat bo'lishi kerak.", parse_mode="Markdown")
        return

    # 2. Bazaga yozish (Bu aniq ishlaydi)
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO vip_users (user_id, is_vip) VALUES (?, 1)", (target_id,))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"✅ Foydalanuvchi `{target_id}` VIP tizimiga muvaffaqiyatli qo'shildi!", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Baza xatoligi yuz berdi: {e}")
        return

    # 3. Foydalanuvchiga xabar yuborish (Agar bloklagan bo'lsa, xato bermaydi)
    try:
        bot.send_message(target_id, "🎉 **Ajoyib xushxabar!**\n\nTo'lovingiz tasdiqlandi. Botdan umrbod cheksiz foydalanish huquqiga ega bo'ldingiz! 🚀", parse_mode="Markdown")
    except Exception:
        bot.send_message(ADMIN_ID, "⚠️ *Diqqat: Mijozga VIP berildi, lekin unga xabar bormadi. Chunki u botni bloklagan yoki umuman start bosmagan.*", parse_mode="Markdown")

@bot.message_handler(commands=['delvip'])
def cmd_delvip(message):
    if message.chat.id != ADMIN_ID: return
    
    try:
        target_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        bot.send_message(ADMIN_ID, "❌ Xatolik! Format: `/delvip USER_ID`", parse_mode="Markdown")
        return

    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO vip_users (user_id, is_vip) VALUES (?, 0)", (target_id,))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"❌ Foydalanuvchi `{target_id}` VIP tizimidan o'chirildi!", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Baza xatoligi: {e}")
        return

    try:
        bot.send_message(target_id, "⚠️ **Ogohlantirish!**\nSizning VIP maqomingiz to'xtatildi. Botdan foydalanish uchun qayta to'lov qilishingiz kerak.", parse_mode="Markdown")
    except Exception:
        pass # Bloklagan bo'lsa, indamaymiz

@bot.message_handler(commands=['help'])
def cmd_help(message):
    if require_subscription(message): return
    bot.send_message(message.chat.id, "📖 **Fayl formati:**\n\n`1. Savol matni`\n`+ To'g'ri javob`\n`- Noto'g'ri javob`", parse_mode='Markdown')

@bot.message_handler(commands=['restart'])
def cmd_restart(message):
    if require_subscription(message): return
    chat_id = message.chat.id
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history WHERE user_id=?", (chat_id,))
    conn.commit()
    conn.close()
    if chat_id in user_data: del user_data[chat_id]
    bot.send_message(chat_id, "🔄 **Tarix tozalandi!**\nBarcha savollar boshidan beriladi.")

@bot.message_handler(commands=['finish'])
def cmd_finish(message):
    chat_id = message.chat.id
    data = user_data.get(chat_id)
    if data and data.get('selected_questions'):
        correct = data.get('correct_count', 0)
        total = len(data['selected_questions'])
        current_idx = data.get('current_index', 0)
        percentage = int((correct / total) * 100) if total > 0 else 0
        
        unanswered_questions = data['selected_questions'][current_idx:]
        if unanswered_questions:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            for q in unanswered_questions:
                cursor.execute("DELETE FROM history WHERE user_id=? AND question_text=?", (chat_id, q['text']))
            conn.commit()
            conn.close()
            
        data['active_poll_id'] = None 
        data['last_batch'] = data['selected_questions'][:current_idx] 
        data['selected_questions'] = [] 
        bot.send_message(chat_id, f"🛑 **Test muddatidan oldin yakunlandi!**\n📊 Natijangiz: **{correct}/{current_idx}** ({percentage}%)\n⚠️ Yechishga ulgurmagan testlaringiz umumiy balansga muvaffaqiyatli qaytarildi.", parse_mode="Markdown")
        check_remaining_and_ask(chat_id)
    else:
        bot.send_message(chat_id, "ℹ️ Hozirda hech qanday faol test yo'q.")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if require_subscription(message): return 
    
    chat_id = message.chat.id
    if not check_vip_status(chat_id):
        trials = get_trials_left(chat_id)
        if trials <= 0:
            send_payment_msg(chat_id)
            return
        use_trial(chat_id)

    file_info = bot.get_file(message.document.file_id)
    file_ext = os.path.splitext(message.document.file_name)[1].lower()
    if file_ext not in ['.txt', '.docx', '.pdf', '.xlsx']:
        bot.send_message(chat_id, "❌ Faqat .txt, .docx, .pdf yoki .xlsx fayllarni yuboring.")
        return

    msg = bot.send_message(chat_id, "⏳ Fayl o'qilmoqda...")
    downloaded_file = bot.download_file(file_info.file_path)
    file_path = f"temp_{chat_id}{file_ext}"
    with open(file_path, 'wb') as f: f.write(downloaded_file)

    text = extract_text_from_file(file_path, file_ext)
    os.remove(file_path)
    questions = parse_questions(text)
    bot.delete_message(chat_id, msg.message_id)
    
    if not questions:
        bot.send_message(chat_id, "❌ Fayldan test topilmadi. Format to'g'riligiga ishonch hosil qiling.")
        return

    # BO'SH O'ZGARUVCHILARDAN HIMOYALANGAN ZIRH
    user_data[chat_id] = {
        'all_questions': questions,
        'count': 30, # Default qotib qolmasligi uchun
        'time': 15   # Default qotib qolmasligi uchun
    }
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("30 ta", callback_data="count_30"), types.InlineKeyboardButton("50 ta", callback_data="count_50"))
    bot.send_message(chat_id, f"✅ Jami **{len(questions)}** ta test topildi.\nNechta test yechasiz?", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    
    if call.data == "check_sub_btn":
        unsubscribed = check_all_subscriptions(call.from_user.id)
        if unsubscribed is True or len(unsubscribed) == 0:
            try: bot.delete_message(chat_id, call.message.message_id)
            except: pass
            bot.send_message(chat_id, "✅ Rahmat! Barcha kanallarga a'zo bo'ldingiz.\nEndi botdan bemalol foydalanishingiz mumkin. Boshlash uchun /start ni bosing.")
        else:
            bot.answer_callback_query(call.id, "❌ Hali barcha kanallarga a'zo bo'lmadingiz! Iltimos, tekshirib qaytadan urinib ko'ring.", show_alert=True)
        return
    
    if call.data == "upload_prompt":
        bot.send_message(chat_id, "📂 **Iltimos, menga test savollari bor faylni yuboring!**\n(.txt, .docx, .pdf yoki .xlsx formatlarida)", parse_mode="Markdown")
        bot.answer_callback_query(call.id)
        return
        
    elif call.data == "buy_vip":
        send_payment_msg(chat_id)
        bot.answer_callback_query(call.id)
        return

    elif call.data == "admin_broadcast":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "📢 **Reklama xabarini yuboring.**\n\nSiz yuborgan xabar (matn, rasm yoki video) botning barcha foydalanuvchilariga yuboriladi. Bekor qilish uchun /cancel deb yozing.")
        bot.register_next_step_handler(msg, process_admin_broadcast)
        return

    elif call.data == "admin_refresh":
        bot.answer_callback_query(call.id, "🔄 Yangilanmoqda...")
        bot.delete_message(chat_id, call.message.message_id)
        cmd_stat(call.message)
        return

    elif call.data == "admin_add_ch":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "➕ **Kanal qo'shish uchun ma'lumotni shu formatda yuboring:**\n\n`ID | Nomi | Ssilka`\n\nMisol:\n`-100123456789 | Mening Kanalim | https://t.me/+abcde`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_add_channel)
        return

    elif call.data == "admin_del_ch":
        bot.answer_callback_query(call.id)
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, channel_title FROM channels")
        channels = cursor.fetchall()
        conn.close()
        if not channels:
            bot.send_message(chat_id, "📭 Bazada hech qanday kanal yo'q.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in channels:
            markup.add(types.InlineKeyboardButton(f"❌ {ch[1]}", callback_data=f"delch_{ch[0]}"))
        bot.send_message(chat_id, "O'chirmoqchi bo'lgan kanalingizni tanlang:", reply_markup=markup)
        return

    elif call.data.startswith("delch_"):
        ch_id = call.data.split('_')[1]
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM channels WHERE channel_id = ?", (ch_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text("✅ Kanal ro'yxatdan muvaffaqiyatli o'chirildi.", chat_id, call.message.message_id)
        return

    elif call.data.startswith("count_") or call.data == "retry_last":
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        
        if call.data.startswith("count_"):
            if chat_id not in user_data: return
            user_data[chat_id]['count'] = int(call.data.split("_")[1])
            markup = types.InlineKeyboardMarkup(row_width=3)
            markup.add(*[types.InlineKeyboardButton(f"{t} s", callback_data=f"time_{t}") for t in [5, 10, 15, 20, 25, 30]])
            bot.send_message(chat_id, "⏱ Taymer qancha bo'lsin?", reply_markup=markup)
            
        elif call.data == "retry_last":
            if 'last_batch' in user_data.get(chat_id, {}):
                user_data[chat_id]['selected_questions'] = user_data[chat_id]['last_batch']
                user_data[chat_id]['current_index'] = 0
                user_data[chat_id]['correct_count'] = 0
                user_data[chat_id]['active_poll_id'] = None
                bot.send_message(chat_id, "🚀 **Xatolar ustida ishlash:** Test qayta boshlanmoqda...", parse_mode="Markdown")
                send_next_question(chat_id)
            else:
                bot.send_message(chat_id, "❌ Qayta ishlash uchun test topilmadi.")

    elif call.data.startswith("time_"):
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        if chat_id not in user_data: return
        user_data[chat_id]['time'] = int(call.data.split("_")[1])
        bot.send_message(chat_id, "🚀 Test boshlanmoqda...")
        prepare_quiz(chat_id)

def process_add_channel(message):
    if message.chat.id != ADMIN_ID: return
    try:
        parts = message.text.split('|')
        ch_id = parts[0].strip()
        ch_title = parts[1].strip()
        ch_link = parts[2].strip()
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO channels (channel_id, channel_title, channel_invite_link) VALUES (?, ?, ?)", (ch_id, ch_title, ch_link))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ **{ch_title}** kanali bazaga muvaffaqiyatli qo'shildi!", parse_mode="Markdown")
    except Exception:
        bot.send_message(message.chat.id, "❌ Xatolik! Format noto'g'ri yuborildi.", parse_mode="Markdown")

def process_admin_broadcast(message):
    if message.chat.id != ADMIN_ID: return
    if message.text == '/cancel':
        bot.send_message(ADMIN_ID, "❌ Reklama yuborish bekor qilindi.")
        return
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM user_stats")
    all_users = cursor.fetchall()
    conn.close()
    bot.send_message(ADMIN_ID, f"🚀 **{len(all_users)} ta** foydalanuvchiga reklama yuborish boshlandi...")
    success, failed = 0, 0
    for user in all_users:
        try:
            bot.copy_message(chat_id=user[0], from_chat_id=ADMIN_ID, message_id=message.message_id)
            success += 1
        except Exception: failed += 1
    bot.send_message(ADMIN_ID, f"✅ **Yuborish yakunlandi!**\n🟢 Muvaffaqiyatli: {success} ta\n🔴 Yetkazilmadi: {failed} ta")

def prepare_quiz(chat_id):
    data = user_data.get(chat_id)
    if not data: return
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT question_text FROM history WHERE user_id=?", (chat_id,))
    history = [row[0] for row in cursor.fetchall()]

    new_questions = [q for q in data.get('all_questions', []) if q['text'] not in history]
    if not new_questions:
        bot.send_message(chat_id, "🎉 Barcha testlarni yechib bo'lgansiz! Tarixni tozalash: /restart")
        conn.close()
        return

    count = data.get('count', 30)
    selected = random.sample(new_questions, min(count, len(new_questions)))
    for q in selected: cursor.execute("INSERT INTO history (user_id, question_text) VALUES (?, ?)", (chat_id, q['text']))
    conn.commit()
    conn.close()

    data['selected_questions'] = selected
    data['current_index'] = 0
    data['correct_count'] = 0
    data['active_poll_id'] = None
    send_next_question(chat_id)

def send_next_question(chat_id):
    data = user_data.get(chat_id)
    if not data: return
    
    idx = data.get('current_index', 0)
    questions = data.get('selected_questions', [])
    
    if idx >= len(questions):
        correct = data.get('correct_count', 0)
        total = len(questions)
        percentage = int((correct / total) * 100) if total > 0 else 0
        data['last_batch'] = questions 
        bot.send_message(chat_id, f"🏁 **Test yakunlandi!**\n📊 Natijangiz: **{correct}/{total}** ({percentage}%)\n", parse_mode="Markdown")
        check_remaining_and_ask(chat_id)
        return

    q = questions[idx]
    
    # 🛑 JAVOBLAR BIR XIL BO'LIB QOLISHIDAN (CRASH) HIMOYA 
    raw_options = []
    for opt in q['options']:
        safe_opt = smart_truncate(opt)
        if safe_opt not in raw_options:  # Faqat takrorlanmaganlarini olamiz
            raw_options.append(safe_opt)
            
    if len(raw_options) < 2:  # Agar javob qolmasa o'tkazib yuboramiz
        data['current_index'] += 1
        send_next_question(chat_id)
        return

    options = raw_options[:10]
    correct_ans = smart_truncate(q['correct']) if q['correct'] else ""
    random.shuffle(options)
    correct_id = options.index(correct_ans) if correct_ans in options else 0
    data['current_correct_id'] = correct_id

    try:
        time_limit = data.get('time', 15)
        msg = bot.send_poll(chat_id, q['text'][:300], options, type='quiz', correct_option_id=correct_id, is_anonymous=False, open_period=time_limit)
        data['active_poll_id'] = msg.poll.id
        poll_to_user[msg.poll.id] = chat_id
        threading.Timer(time_limit + 1.5, auto_force_next, args=[chat_id, idx, msg.poll.id]).start()
    except Exception as e:
        # Telegram API bu savolni yoqtirmasa, bot jim qotmaydi, keyingisiga o'tadi
        data['current_index'] += 1
        send_next_question(chat_id)

def check_remaining_and_ask(chat_id):
    data = user_data.get(chat_id)
    if not data or 'all_questions' not in data: return
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT question_text FROM history WHERE user_id=?", (chat_id,))
    history = [row[0] for row in cursor.fetchall()]
    conn.close()

    remaining = [q for q in data['all_questions'] if q['text'] not in history]
    markup = types.InlineKeyboardMarkup()
    btn_retry = types.InlineKeyboardButton("🔄 Hozirgisini qayta ishlash", callback_data="retry_last")

    if remaining:
        markup.row(types.InlineKeyboardButton("30 ta yangi", callback_data="count_30"), types.InlineKeyboardButton("50 ta yangi", callback_data="count_50"))
        markup.row(btn_retry)
        bot.send_message(chat_id, f"💡 Faylda yana **{len(remaining)}** ta yechilmagan test qoldi.\nDavom ettiramizmi?", reply_markup=markup, parse_mode="Markdown")
        data['selected_questions'] = []
    else:
        markup.row(btn_retry)
        bot.send_message(chat_id, "🎉 Tabriklaymiz! Ushbu fayldagi barcha testlarni yechib tugatdingiz.", reply_markup=markup)

def auto_force_next(chat_id, expected_idx, poll_id):
    data = user_data.get(chat_id)
    if data and data.get('current_index') == expected_idx and data.get('active_poll_id') == poll_id:
        try:
            current_q = data['selected_questions'][expected_idx]
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("DELETE FROM history WHERE user_id=? AND question_text=?", (chat_id, current_q['text']))
            conn.commit()
            conn.close()
        except Exception: pass
        data['active_poll_id'] = None
        data['current_index'] += 1
        send_next_question(chat_id)

@bot.poll_answer_handler()
def handle_poll_answer(poll_answer):
    chat_id = poll_to_user.get(poll_answer.poll_id)
    if not chat_id: return
    data = user_data.get(chat_id)
    if data and data.get('active_poll_id') == poll_answer.poll_id:
        if poll_answer.option_ids[0] == data.get('current_correct_id'):
            data['correct_count'] = data.get('correct_count', 0) + 1
            add_correct_answer(chat_id)
        data['active_poll_id'] = None
        data['current_index'] += 1
        send_next_question(chat_id)

if __name__ == "__main__":
    bot.infinity_polling(none_stop=True)
