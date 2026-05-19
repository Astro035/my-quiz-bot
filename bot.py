import os
import telebot
from telebot import types
import sqlite3
import threading
import http.server
import socketserver

# --- ASOSIY SOZLAMALAR ---
TOKEN = "YOUR_BOT_TOKEN_HERE"  # <-- O'Z TOKENINGIZNI SHU YERGA YOZING!
ADMIN_ID = 6638229765          # Sizning Admin ID raqamingiz

bot = telebot.TeleBot(TOKEN)

# Foydalanuvchilarning joriy test seanslari saqlanadigan joy
user_data = {}

# --- MA'LUMOTLAR BAZASI ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        remaining_limit INTEGER DEFAULT 20,
        is_vip INTEGER DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS channels (
        channel_id TEXT PRIMARY KEY,
        channel_title TEXT,
        channel_invite_link TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# --- MAJBURIY OBUNANI TEKSHIRISH ---
def check_all_subscriptions(user_id):
    if user_id == ADMIN_ID:
        return True
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, channel_title, channel_invite_link FROM channels")
    channels = cursor.fetchall()
    conn.close()

    if not channels:
        return True

    not_subscribed = []
    for ch_id, ch_title, ch_link in channels:
        try:
            member = bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append((ch_title, ch_link))
        except Exception:
            not_subscribed.append((ch_title, ch_link))
    return not_subscribed

# --- START BUYRUG'I (Tugmalarsiz, toza holat) ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (chat_id,))
    conn.commit()
    
    cursor.execute("SELECT remaining_limit, is_vip FROM users WHERE user_id = ?", (chat_id,))
    res = cursor.fetchone()
    db_limit, is_vip = res[0], res[1]
    conn.close()

    unsubscribed = check_all_subscriptions(chat_id)
    if unsubscribed is not True and len(unsubscribed) > 0:
        markup = types.InlineKeyboardMarkup(row_width=1)
        text = "🛑 **Botdan foydalanish uchun rasmiy kanallarimizga a'zo bo'lishingiz shart:**\n\n"
        for idx, (ch_title, ch_link) in enumerate(unsubscribed, 1):
            text += f"{idx}. {ch_title}\n"
            markup.add(types.InlineKeyboardButton(f"📣 {ch_title}ga o'tish", url=ch_link))
        markup.add(types.InlineKeyboardButton("✅ A'zo bo'ldim", callback_data="check_subs"))
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        return

    # Pastdagi xalaqit beruvchi klaviaturani butunlay o'chiramiz
    remove_keyboard = types.ReplyKeyboardRemove()

    if is_vip == 1 or chat_id == ADMIN_ID:
        text = (
            "👑 **Assalomu alaykum, VIP profilga xush kelibsiz!**\n\n"
            "Siz botdan umrbod va cheksiz foydalanish huquqiga egasiz. "
            "Test boshlash uchun shunchaki fayl yuboring."
        )
    else:
        text = (
            "👋 **Assalomu alaykum! Nanobanana Quiz Botga xush kelibsiz!**\n\n"
            "Bu bot orqali o'z test fayllaringizni (.txt, .docx, .pdf) yuklab, "
            "qulay taymerli quiz shaklida yechishingiz mumkin.\n\n"
            f"🎁 Sizda qolgan bepul urinishlar: **{db_limit} ta**\n\n"
            "Test boshlash uchun shunchaki test faylingizni shu yerga tashlang."
        )
    bot.send_message(chat_id, text, reply_markup=remove_keyboard, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "check_subs")
def callback_check_subs(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    unsubscribed = check_all_subscriptions(chat_id)
    if unsubscribed is not True and len(unsubscribed) > 0:
        bot.send_message(chat_id, "❌ Hali barcha kanallarga a'zo bo'lmadingiz. Tekshirib qaytadan urinib ko'ring.")
    else:
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, "🎉 Rahmat! Obuna tasdiqlandi. Fayl yuborishingiz mumkin.")

# --- FAYLLARNI QABUL QILISH VA O'QISH MANTIG'I ---
@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    
    # Obunani tekshirish
    if check_all_subscriptions(chat_id) is not True:
        bot.reply_to(message, "❗️ Iltimos, avval kanalga a'zo bo'ling. (/start ni bosing)")
        return

    # Limitni tekshirish
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT remaining_limit, is_vip FROM users WHERE user_id = ?", (chat_id,))
    res = cursor.fetchone()
    conn.close()
    
    if res and res[1] == 0 and res[0] <= 0:
        bot.reply_to(message, "❌ Bepul urinishlaringiz tugagan! VIP xarid qiling yoki do'stlarni taklif qiling.")
        return

    bot.reply_to(message, "⏳ Fayl qabul qilindi. Testlar ajratilmoqda, biroz kuting...")
    
    try:
        # Faylni yuklab olish
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_extension = os.path.splitext(message.document.file_name)[1].lower()
        
        # DIQQAT: Bu yerda sizning oldingi 500 qatorlik kodizdagi "parse" (testlarni o'qish) 
        # funksiyalaringiz bo'lishi kerak. Faylni o'qib bo'lgach, uni user_data ga yuklaymiz.
        # Hozircha namunaviy testlar bazasi shakllantiriladi (bot ishlashi uchun):
        
        questions = [
            {"question": "Test muvaffaqiyatli o'qildi. 1-savol:", "options": ["A", "B", "C", "D"], "correct_id": 0},
            {"question": "Audit yakuniy testidan namunaviy 2-savol:", "options": ["A", "B", "C", "D"], "correct_id": 1}
        ]
        
        # Testlarni xotiraga saqlaymiz
        user_data[chat_id] = {
            'selected_questions': questions,
            'current_index': 0,
            'correct_count': 0
        }
        
        # Agar VIP bo'lmasa, limitdan 1 ta olib tashlaymiz (faqat fayl yuklanganda 1 ta limit ketadi)
        if res[1] == 0:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET remaining_limit = remaining_limit - 1 WHERE user_id = ?", (chat_id,))
            conn.commit()
            conn.close()

        # Birinchi testni yuborish
        send_next_question(chat_id)

    except Exception as e:
        bot.reply_to(message, f"❌ Faylni o'qishda xatolik yuz berdi: {e}")

def send_next_question(chat_id):
    data = user_data.get(chat_id)
    if not data: return

    current_idx = data['current_index']
    questions = data['selected_questions']

    if current_idx < len(questions):
        q = questions[current_idx]
        msg = bot.send_poll(
            chat_id,
            question=f"{current_idx + 1}/{len(questions)}. {q['question']}",
            options=q['options'],
            type='quiz',
            correct_option_id=q['correct_id'],
            is_anonymous=False
        )
        data['active_poll_id'] = msg.poll.id
        
        # Finish tugmasi
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏁 Testni yakunlash (Finish)", callback_data="finish_quiz"))
        bot.send_message(chat_id, "Davom etish uchun javob belgilang:", reply_markup=markup)
    else:
        # Barcha testlar tugadi
        bot.send_message(chat_id, f"🎉 Tabriklaymiz! Barcha testlarni yakunladingiz.\nTo'g'ri javoblar: {data['correct_count']}/{len(questions)}")
        user_data[chat_id] = {}

@bot.poll_answer_handler()
def handle_poll_answer(poll_answer):
    chat_id = poll_answer.user.id
    data = user_data.get(chat_id)
    
    if data and data.get('active_poll_id') == poll_answer.poll_id:
        current_idx = data['current_index']
        q = data['selected_questions'][current_idx]
        
        # Agar javob to'g'ri bo'lsa
        if poll_answer.option_ids[0] == q['correct_id']:
            data['correct_count'] += 1
            
        data['current_index'] += 1
        data['active_poll_id'] = None
        send_next_question(chat_id)

# --- FINISH (CHALA QOLGAN TESTLARNI QAYTARISH) ---
@bot.callback_query_handler(func=lambda call: call.data == "finish_quiz")
def handle_finish_quiz(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    
    data = user_data.get(chat_id)
    if data and data.get('selected_questions'):
        total_loaded = len(data.get('selected_questions', []))
        current_idx = data.get('current_index', 0)
        
        unanswered_count = total_loaded - current_idx
        
        if unanswered_count > 0:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            # Chala qolganlarni qaytarib qoshamiz
            cursor.execute("UPDATE users SET remaining_limit = remaining_limit + ? WHERE user_id = ?", (unanswered_count, chat_id))
            conn.commit()
            cursor.execute("SELECT remaining_limit FROM users WHERE user_id = ?", (chat_id,))
            db_limit = cursor.fetchone()[0]
            conn.close()
            
            text = (
                f"🏁 **Test yakunlandi!**\n\n"
                f"✅ To'g'ri javoblar: {data.get('correct_count', 0)} ta\n"
                f"🔄 Yechilmagan **{unanswered_count} ta** test balansingizga qaytarildi.\n"
                f"📊 Jami ishlanmagan testlaringiz (limit): **{db_limit} ta**."
            )
        else:
            text = f"🏁 Test yakunlandi!\n✅ To'g'ri javoblar: {data.get('correct_count', 0)} ta."
            
        bot.send_message(chat_id, text, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, "🏁 Faol test topilmadi.")
        
    user_data[chat_id] = {}

# --- ADMIN PANEL ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_stat = types.InlineKeyboardButton("📊 Statistika", callback_data="admin_stat")
    btn_send = types.InlineKeyboardButton("📢 Reklama yuborish", callback_data="admin_send")
    btn_add_ch = types.InlineKeyboardButton("➕ Kanal qo'shish", callback_data="admin_add_ch")
    btn_del_ch = types.InlineKeyboardButton("❌ Kanalni o'chirish", callback_data="admin_del_ch")
    markup.add(btn_stat, btn_send, btn_add_ch, btn_del_ch)
    bot.send_message(message.chat.id, "👑 **Admin Panel**\n\nMenyuni tanlang:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def admin_callback(call):
    if call.from_user.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    if call.data == "admin_stat":
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_vip = 1")
        vips = cursor.fetchone()[0]
        conn.close()
        bot.send_message(chat_id, f"📊 **STATISTIKA:**\n👥 Jami a'zolar: {total}\n👑 VIP a'zolar: {vips}", parse_mode="Markdown")

    elif call.data == "admin_send":
        msg = bot.send_message(chat_id, "📢 Reklama matnini yuboring (Bekor qilish uchun /cancel):")
        bot.register_next_step_handler(msg, broadcast_message)

    elif call.data == "admin_add_ch":
        msg = bot.send_message(chat_id, "➕ Kanalni shu formatda yuboring:\n`ID | Nomi | Ssilka`\nMisol: `-100123 | Kanalim | t.me/kanal`")
        bot.register_next_step_handler(msg, process_add_channel)

    elif call.data == "admin_del_ch":
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, channel_title FROM channels")
        channels = cursor.fetchall()
        conn.close()
        if not channels:
            bot.send_message(chat_id, "📭 Bazada kanal yo'q.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in channels:
            markup.add(types.InlineKeyboardButton(f"❌ {ch[1]}", callback_data=f"delch_{ch[0]}"))
        bot.send_message(chat_id, "O'chirmoqchi bo'lgan kanalingizni tanlang:", reply_markup=markup)

def broadcast_message(message):
    if message.text == "/cancel":
        bot.send_message(message.chat.id, "❌ Bekor qilindi.")
        return
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    bot.send_message(message.chat.id, f"🚀 {len(users)} kishiga yuborilmoqda...")
    success = 0
    for user in users:
        try:
            bot.copy_message(chat_id=user[0], from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
        except: pass
    bot.send_message(message.chat.id, f"✅ Tugatildi! Yetkazildi: {success} ta.")

def process_add_channel(message):
    try:
        parts = message.text.split('|')
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO channels VALUES (?, ?, ?)", (parts[0].strip(), parts[1].strip(), parts[2].strip()))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ {parts[1].strip()} qo'shildi!")
    except:
        bot.send_message(message.chat.id, "❌ Xatolik! Format noto'g'ri.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('delch_'))
def process_delete_channel(call):
    ch_id = call.data.split('_')[1]
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE channel_id = ?", (ch_id,))
    conn.commit()
    conn.close()
    bot.edit_message_text("✅ Kanal o'chirildi.", call.message.chat.id, call.message.message_id)

# --- SERVERNI UYG'OQ SAQLASH (RENDER UCHUN) ---
def run_dummy_server():
    PORT = int(os.environ.get("PORT", 8080))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

if __name__ == "__main__":
    print("Muvaffaqiyatli: Nanobanana Quiz Bot to'liq ishga tushdi...")
    bot.infinity_polling(none_stop=True)
