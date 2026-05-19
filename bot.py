import telebot
from telebot import types
import sqlite3
import random
import re
import os
import time
import threading
import http.server
import socketserver

TOKEN = '8917939430:AAFjPYX4eZd_Cqf5ACreLL5JufZ3McfK1No'
bot = telebot.TeleBot(TOKEN)

# =====================================================================
# ⚙️ VIP VA TO'LOV SOZLAMALARI
# =====================================================================
ADMIN_ID = 6638229765  # 🔥 DIQQAT: Bu yerga o'zingizning raqamli ID'ingizni yozing!
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

import docx
import PyPDF2
import pandas as pd

def set_bot_menu():
    commands = [
        types.BotCommand("start", "Botni boshlash"),
        types.BotCommand("help", "Instruktsiya va fayl formati"),
        types.BotCommand("restart", "Tarixni tozalash"),
        types.BotCommand("finish", "Faol quizni yakunlash")
    ]
    bot.set_my_commands(commands)

set_bot_menu()

user_data = {}
poll_to_user = {}

def smart_truncate(text, max_length=100, suffix='...'):
    if len(text) <= max_length: return text
    truncated = text[:max_length - len(suffix)]
    last_space = truncated.rfind(' ')
    return (truncated[:last_space] + suffix) if last_space != -1 else (truncated + suffix)

# --- BAZA SOZLAMALARI VA FREEMIUM TIZIMI ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS history (user_id INTEGER, question_text TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS vip_users (user_id INTEGER PRIMARY KEY, is_vip INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS free_trials (user_id INTEGER PRIMARY KEY)''') # Yangi bepul urinish bazasi
    conn.commit()
    conn.close()

init_db()

def check_vip_status(user_id):
    if user_id == ADMIN_ID: return True
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_vip FROM vip_users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def is_trial_used(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM free_trials WHERE user_id=?", (user_id,))
    used = cursor.fetchone()
    conn.close()
    return used is not None

def mark_trial_used(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO free_trials (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def send_payment_msg(chat_id):
    pay_text = (
        "🔒 <b>Bepul urinishingiz tugadi!</b>\n\n"
        "Botga test fayllarini yuklash va telegramda cheksiz yechish <b>umrbod faqat 5 000 so'm</b>.\n\n"
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

# --- MENYU VA BUYRUQLAR ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    text = (
        "👋 **Assalomu alaykum! Quiz Botga xush kelibsiz!**\n\n"
        "Bu bot orqali siz turli formatdagi (.txt, .docx, .pdf, .xlsx) test fayllarini yuklab, "
        "ularni qulay taymerli quiz shaklida yechishingiz mumkin.\n\n"
        "🎁 *Sizda birinchi test (30 yoki 50 talik) mutlaqo BEPUL!*\n\n"
        "Qani, tayyor bo'lsangiz bilimingizni sinab ko'ramizmi?"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🚀 Test faylini yuklash va boshlash", callback_data="upload_prompt"),
        types.InlineKeyboardButton("💎 VIP xarid qilish (Cheksiz)", callback_data="buy_vip")
    )
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['addvip'])
def cmd_addvip(message):
    if message.chat.id != ADMIN_ID: return
    try:
        target_id = int(message.text.split()[1])
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO vip_users (user_id, is_vip) VALUES (?, 1)", (target_id,))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"✅ Foydalanuvchi `{target_id}` VIP tizimiga qo'shildi!", parse_mode="Markdown")
        bot.send_message(target_id, "🎉 **Ajoyib xushxabar!**\n\nTo'lovingiz tasdiqlandi. Botdan umrbod cheksiz foydalanish huquqiga ega bo'ldingiz! 🚀")
    except Exception:
        bot.send_message(ADMIN_ID, "❌ Xatolik! Format: `/addvip USER_ID`", parse_mode="Markdown")

@bot.message_handler(commands=['delvip'])
def cmd_delvip(message):
    if message.chat.id != ADMIN_ID: return
    try:
        target_id = int(message.text.split()[1])
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO vip_users (user_id, is_vip) VALUES (?, 0)", (target_id,))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"❌ Foydalanuvchi `{target_id}` VIP tizimidan o'chirildi!", parse_mode="Markdown")
        bot.send_message(target_id, "⚠️ **Ogohlantirish!**\nSizning VIP maqomingiz to'xtatildi. Botdan foydalanish uchun qayta to'lov qilishingiz kerak.")
    except Exception:
        bot.send_message(ADMIN_ID, "❌ Xatolik! Format: `/delvip USER_ID`", parse_mode="Markdown")

@bot.message_handler(commands=['help'])
def cmd_help(message):
    bot.send_message(message.chat.id, "📖 **Fayl formati:**\n\n`1. Savol matni`\n`+ To'g'ri javob`\n`- Noto'g'ri javob`", parse_mode='Markdown')

@bot.message_handler(commands=['restart'])
def cmd_restart(message):
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
    if data and 'selected_questions' in data:
        correct = data.get('correct_count', 0)
        total = len(data['selected_questions'])
        percentage = int((correct / total) * 100) if total > 0 else 0
        bot.send_message(chat_id, f"🛑 **Test yakunlandi!**\n📊 Natijangiz: **{correct}/{total}** ({percentage}%)", parse_mode="Markdown")
        data['last_batch'] = data['selected_questions']
        check_remaining_and_ask(chat_id)
    else:
        bot.send_message(chat_id, "ℹ️ Faol test yo'q.")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    
    # VIP bo'lmasa va bepul urinish ishlatilgan bo'lsa, fayl yuklashni to'sib qo'yamiz
    if not check_vip_status(chat_id):
        if is_trial_used(chat_id):
            send_payment_msg(chat_id)
            return

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
        bot.send_message(chat_id, "❌ Fayldan test topilmadi.")
        return

    user_data[chat_id] = {'all_questions': questions}
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("30 ta", callback_data="count_30"), types.InlineKeyboardButton("50 ta", callback_data="count_50"))
    bot.send_message(chat_id, f"✅ Jami **{len(questions)}** ta test topildi.\nNechta test yechasiz?", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    
    if call.data == "upload_prompt":
        bot.send_message(chat_id, "📂 **Iltimos, menga test savollari bor faylni yuboring!**\n(.txt, .docx, .pdf yoki .xlsx formatlarida)", parse_mode="Markdown")
        bot.answer_callback_query(call.id)
        return
        
    elif call.data == "buy_vip":
        send_payment_msg(chat_id)
        bot.answer_callback_query(call.id)
        return

    elif call.data.startswith("count_") or call.data == "retry_last":
        # 🛡️ FREEMIUM TEKSHIRUVI: Test boshlanishidan oldin to'siq
        if not check_vip_status(chat_id):
            if is_trial_used(chat_id):
                bot.delete_message(chat_id, call.message.message_id)
                send_payment_msg(chat_id)
                return
            else:
                # Agar trial ishlatilmagan bo'lsa, uni ishlatildi deb belgilaymiz
                mark_trial_used(chat_id)
                bot.send_message(chat_id, "🎁 **Diqqat! Siz 1 martalik bepul urinishingizdan foydalanmoqdasiz.** Omadingizni bersin!")

        bot.delete_message(chat_id, call.message.message_id)
        
        if call.data.startswith("count_"):
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
        user_data[chat_id]['time'] = int(call.data.split("_")[1])
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, "🚀 Test boshlanmoqda...")
        prepare_quiz(chat_id)

def prepare_quiz(chat_id):
    data = user_data.get(chat_id)
    if not data: return
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT question_text FROM history WHERE user_id=?", (chat_id,))
    history = [row[0] for row in cursor.fetchall()]

    new_questions = [q for q in data['all_questions'] if q['text'] not in history]
    if not new_questions:
        bot.send_message(chat_id, "🎉 Barcha testlarni yechib bo'lgansiz! Tarixni tozalash: /restart")
        conn.close()
        return

    selected = random.sample(new_questions, min(data['count'], len(new_questions)))
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
    
    idx = data['current_index']
    questions = data['selected_questions']
    
    if idx >= len(questions):
        correct = data.get('correct_count', 0)
        total = len(questions)
        percentage = int((correct / total) * 100) if total > 0 else 0
        data['last_batch'] = questions 
        
        bot.send_message(chat_id, f"🏁 **Test yakunlandi!**\n📊 Natijangiz: **{correct}/{total}** ({percentage}%)\n", parse_mode="Markdown")
        check_remaining_and_ask(chat_id)
        return

    q = questions[idx]
    options = [smart_truncate(opt) for opt in q['options'][:10]]
    correct_ans = smart_truncate(q['correct']) if q['correct'] else ""
    random.shuffle(options)
    correct_id = options.index(correct_ans) if correct_ans in options else 0
    data['current_correct_id'] = correct_id

    try:
        msg = bot.send_poll(chat_id, q['text'][:300], options, type='quiz', correct_option_id=correct_id, is_anonymous=False, open_period=data['time'])
        data['active_poll_id'] = msg.poll.id
        poll_to_user[msg.poll.id] = chat_id
        threading.Timer(data['time'] + 1.5, auto_force_next, args=[chat_id, idx, msg.poll.id]).start()
    except Exception:
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
        data['active_poll_id'] = None
        data['current_index'] += 1
        send_next_question(chat_id)

bot.polling(none_stop=True)
