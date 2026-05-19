import os
import sqlite3
from telebot import TeleBot, types

# --- ASOSIY SOZLAMALAR ---
TOKEN = "YOUR_BOT_TOKEN_HERE"  # Bu yerga botingiz tokenini qo'ying
ADMIN_ID = 6638229765          # Sizning Admin ID raqamingiz

bot = TeleBot(TOKEN)

# Foydalanuvchilarning joriy test seanslarini saqlash uchun lug'at
user_data = {}

# --- MA'LUMOTLAR BAZASI BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Foydalanuvchilar jadvali
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        remaining_limit INTEGER DEFAULT 20,
        is_vip INTEGER DEFAULT 0
    )
    ''')
    
    # Dinamik kanallar jadvali
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS channels (
        channel_id TEXT PRIMARY KEY,
        channel_title TEXT,
        channel_invite_link TEXT
    )
    ''')
    conn.commit()
    conn.close()

# Bazani ishga tushiramiz
init_db()

# --- MAJBURIY OBUNANI TEKSHIRISH MANTIG'I ---
def check_all_subscriptions(user_id):
    """Foydalanuvchi bazadagi barcha majburiy kanallarga a'zomi yoki yo'qligini tekshiradi"""
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
            # Bot kanalda admin bo'lmasa yoki kanal topilmasa ham ro'yxatga oladi
            not_subscribed.append((ch_title, ch_link))

    return not_subscribed

# --- FOYDALANUVChI BUYRUQLARI (START & REYTING) ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    
    # Avval bazada foydalanuvchi borligini tekshiramiz/qo'shamiz
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (chat_id,))
    conn.commit()
    
    # Foydalanuvchi holatini tekshiramiz
    cursor.execute("SELECT remaining_limit, is_vip FROM users WHERE user_id = ?", (chat_id,))
    res = cursor.fetchone()
    db_limit, is_vip = res[0], res[1]
    conn.close()

    # Kanallarga obunani tekshiramiz
    unsubscribed = check_all_subscriptions(chat_id)
    
    if unsubscribed is not True and len(unsubscribed) > 0:
        markup = types.InlineKeyboardMarkup(row_width=1)
        text = "🛑 **Botdan foydalanish uchun quyidagi rasmiy kanallarimizga a'zo bo'lishingiz shart:**\n\n"
        
        for idx, (ch_title, ch_link) in enumerate(unsubscribed, 1):
            text += f"{idx}. {ch_title}\n"
            markup.add(types.InlineKeyboardButton(f"📣 {ch_title}ga o'tish", url=ch_link))
            
        markup.add(types.InlineKeyboardButton("✅ A'zo bo'ldim", callback_data="check_subs"))
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        return

    # Agar VIP bo'lsa
    if is_vip == 1 or chat_id == ADMIN_ID:
        text = (
            "👑 **Assalomu alaykum, VIP profilga xush kelibsiz!**\n\n"
            "Siz botdan umrbod va cheksiz foydalanish huquqiga egasiz. "
            "Test boshlash uchun shunchaki fayl yuboring."
        )
    else:
        text = (
            "👋 **Assalomu alaykum! Quiz Botga xush kelibsiz!**\n\n"
            "Bu bot orqali o'z test fayllaringizni (.txt, .docx, .pdf, .xlsx) yuklab, "
            "qulay taymerli quiz shaklida yechishingiz mumkin.\n\n"
             f"🎁 Sizda qolgan bepul urinishlar: **{db_limit} ta**\n\n"
            "Test boshlash uchun pastdagi tugmani bosing yoki fayl yuklang:"
        )
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("🚀 Test faylini yuklash va boshlash"))
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "check_subs")
def callback_check_subs(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    
    unsubscribed = check_all_subscriptions(chat_id)
    if unsubscribed is not True and len(unsubscribed) > 0:
        bot.send_message(chat_id, "❌ Siz hali barcha kanallarga a'zo bo'lmadingiz. Iltimos, tekshirib qaytadan urinib ko'ring.")
    else:
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, "🎉 Rahmat! Obuna tasdiqlandi. Botdan foydalanish uchun /start ni bosing.")

# --- FINISH: CHALA QOLGAN TESTLARNI QAYTARISH MANTIG'I ---

@bot.callback_query_handler(func=lambda call: call.data == "finish_quiz")
def handle_finish_quiz(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    
    data = user_data.get(chat_id)
    if data and data.get('selected_questions'):
        total_loaded = len(data.get('selected_questions', []))
        current_idx = data.get('current_index', 0)
        
        # Ishlanmay qolib ketgan testlar soni
        unanswered_count = total_loaded - current_idx
        
        if unanswered_count > 0:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            # Chala testlarni balansga qaytaramiz
            cursor.execute("UPDATE users SET remaining_limit = remaining_limit + ? WHERE user_id = ?", (unanswered_count, chat_id))
            conn.commit()
            
            cursor.execute("SELECT remaining_limit FROM users WHERE user_id = ?", (chat_id,))
            db_limit = cursor.fetchone()[0]
            conn.close()
            
            text = (
                f"🏁 **Test yakunlandi!**\n\n"
                f"📝 Siz {total_loaded} ta testdan {current_idx} tasini yechdingiz.\n"
                f"🔄 Ishlanmagan **{unanswered_count} ta** test balansingizga qaytarildi.\n"
                f"📊 Jami ishlanmagan testlaringiz: **{db_limit} ta**."
            )
        else:
            text = "🏁 Barcha testlarni to'liq yechib tugatdingiz!"
            
        bot.send_message(chat_id, text, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, "🏁 Faol test seansi topilmadi.")
        
    # Seansni tozalaymiz
    user_data[chat_id] = {}

# --- CROWN ADMIN PANEL VA FUNKSIYALARI ---

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
    
    bot.send_message(
        message.chat.id, 
        "👑 **Nanobanana Quiz Bot — Admin Panel**\n\nBoshqarish uchun menyuni tanlang:", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def admin_callback(call):
    if call.from_user.id != ADMIN_ID:
        return

    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    if call.data == "admin_stat":
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_vip = 1")
        total_vips = cursor.fetchone()[0]
        conn.close()
        
        text = (
            "📊 **BOT STATISTIKASI:**\n\n"
            f"👤 Jami foydalanuvchilar: **{total_users} ta**\n"
            f"👑 VIP foydalanuvchilar: **{total_vips} ta**"
        )
        bot.send_message(chat_id, text, parse_mode="Markdown")

    elif call.data == "admin_send":
        msg = bot.send_message(chat_id, "📢 **Reklama matni yoki rasmini yuboring:**\n\nBekor qilish uchun /cancel deb yozing.")
        bot.register_next_step_handler(msg, broadcast_message)

    elif call.data == "admin_add_ch":
        msg = bot.send_message(
            chat_id, 
            "➕ **Kanal qo'shish uchun ma'lumotni shunday formatda yuboring:**\n\n"
            "`Kanal_ID | Kanal_Nomi | Taklif_Ssilkasi`\n\n"
            "**Misol:**\n"
            "`-1003501768656 | Mening Kanalim | https://t.me/+abcde`"
        )
        bot.register_next_step_handler(msg, process_add_channel)

    elif call.data == "admin_del_ch":
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, channel_title FROM channels")
        channels = cursor.fetchall()
        conn.close()
        
        if not channels:
            bot.send_message(chat_id, "📭 Bazada hech qanday kanal yo't.")
            return
            
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in channels:
            markup.add(types.InlineKeyboardButton(f"❌ {ch[1]} ({ch[0]})", callback_data=f"delch_{ch[0]}"))
            
        bot.send_message(chat_id, "O'chirmoqchi bo'lgan kanalingizni tanlang:", reply_markup=markup)

# Reklamani tarqatish
def broadcast_message(message):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text == "/cancel":
        bot.send_message(message.chat.id, "❌ Reklama yuborish bekor qilindi.")
        return

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    bot.send_message(message.chat.id, f"🚀 **{len(users)} ta** foydalanuvchiga reklama tarqatilmoqda...")
    success, failed = 0, 0
    
    for user in users:
        try:
            bot.copy_message(chat_id=user[0], from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
        except Exception:
            failed += 1

    bot.send_message(message.chat.id, f"✅ **Tugatildi!**\n\n🟢 Yetkazildi: {success} ta\n🔴 Bloklaganlar: {failed} ta")

# Kanalni bazaga qo'shish
def process_add_channel(message):
    if message.from_user.id != ADMIN_ID:
        return
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
        
        bot.send_message(message.chat.id, f"✅ **{ch_title}** kanali majburiy obunalarga muvaffaqiyatli qo'shildi!")
    except Exception:
        bot.send_message(message.chat.id, "❌ Xatolik! Format noto'g'ri. Iltimos, qaytadan urinib ko'ring.")

# Kanalni bazadan o'chirish callback
@bot.callback_query_handler(func=lambda call: call.data.startswith('delch_'))
def process_delete_channel(call):
    if call.from_user.id != ADMIN_ID:
        return
    ch_id = call.data.split('_')[1]
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE channel_id = ?", (ch_id,))
    conn.commit()
    conn.close()
    
    bot.answer_callback_query(call.id, "Kanal o'chirildi!")
    bot.edit_message_text("✅ Kanal ro'yxatdan muvaffaqiyatli olib tashlandi.", call.message.chat.id, call.message.message_id)

# --- VIP BERISH VA O'CHIRISH BUYRUQLARI ---
@bot.message_handler(commands=['addvip'])
def add_vip(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.split()[1])
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_vip = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"👑 Foydalanuvchi {target_id} muvaffaqiyatli VIP qilindi!")
    except Exception:
        bot.send_message(message.chat.id, "Xato! Format: /addvip USER_ID")

@bot.message_handler(commands=['delvip'])
def del_vip(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.split()[1])
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_vip = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"❌ Foydalanuvchi {target_id} VIP statusidan mahrum qilindi.")
    except Exception:
        bot.send_message(message.chat.id, "Xato! Format: /delvip USER_ID")

# --- BOTNI ISHGA TUSHIRISH (DUMMY SERVER BILAN) ---
# Render bepul servisda portni tinglab turish majburiy bo'lgani uchun dummy server qismi:
import threading
import http.server
import socketserver

def run_dummy_server():
    PORT = int(os.environ.get("PORT", 8080))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Dummy server {PORT}-portda ishlamoqda...")
        httpd.serve_forever()

# Serverni alohida oqimda yoqamiz
threading.Thread(target=run_dummy_server, daemon=True).start()

if __name__ == "__main__":
    print("Muvaffaqiyatli: Nanobanana Quiz Bot ishga tushdi...")
    bot.infinity_polling(none_stop=True)
