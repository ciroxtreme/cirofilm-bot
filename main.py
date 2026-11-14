import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import lk21_engine
import diag

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9155074189:AAF-D3xWr7r0Qsn3NGD8J-mFwvSjL_XNGug")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

print("🤖 Cirofilm_bot is initializing...")

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    text = (
        "🎬 <b>Selamat Datang di CiroFilm Bot!</b>\n\n"
        "Bot download film & series tanpa iklan, ditenagai engine native Cloudflare Solver.\n\n"
        "📌 <b>Cara Pakai:</b>\n"
        "Cukup ketik judul film yang ingin kamu cari.\n"
        "Contoh: <code>Kung Fu Soccer</code> atau <code>Street Fighter</code>\n\n"
        "<i>Semua link download (Mega, Google Share, Direct) akan langsung diekstrak bersih!</i>"
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=["diag", "status"])
def send_diag(message):
    report = diag.run_diag()
    bot.reply_to(message, f"<pre>{report}</pre>")

@bot.message_handler(func=lambda message: True)
def handle_search(message):
    query = message.text.strip()
    if len(query) < 2:
        bot.reply_to(message, "⚠️ Masukkan judul film minimal 2 huruf ya!")
        return

    wait_msg = bot.reply_to(message, f"🔍 <b>Mencari film:</b> <i>{query}</i>\n<i>Sedang menembus Cloudflare LK21...</i>")

    try:
        movies = lk21_engine.search_movies(query)
        if not movies:
            err_detail = getattr(lk21_engine, "LAST_ERROR", "Tidak ada error tercatat")
            bot.edit_message_text(
                f"❌ Film dengan judul <b>{query}</b> tidak ditemukan di LK21.\n\n<code>Info Solver: {err_detail}</code>",
                chat_id=message.chat.id,
                message_id=wait_msg.message_id
            )
            return

        markup = InlineKeyboardMarkup()
        for m in movies:
            btn_text = f"🎬 {m['title']} ({m['year']}) ⭐ {m['rating']}"
            markup.add(InlineKeyboardButton(btn_text, callback_data=f"dl:{m['slug'][:40]}"))

        bot.edit_message_text(
            f"🍿 <b>Ditemukan {len(movies)} hasil untuk:</b> <i>{query}</i>\nSilakan pilih film di bawah ini:",
            chat_id=message.chat.id,
            message_id=wait_msg.message_id,
            reply_markup=markup
        )
    except Exception as e:
        bot.edit_message_text(f"⚠️ Terjadi kesalahan: {e}", chat_id=message.chat.id, message_id=wait_msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dl:"))
def handle_download_callback(call):
    slug = call.data.replace("dl:", "")
    bot.answer_callback_query(call.id, "Sedang memproses link download...")
    
    status_msg = bot.send_message(
        call.message.chat.id,
        "⏳ <i>Menembus gateway Turnstile & mengekstrak direct link... (butuh ~3-5 detik)</i>"
    )

    try:
        detail = lk21_engine.get_movie_detail(slug)
        if not detail:
            err_detail = getattr(lk21_engine, "LAST_ERROR", "Tidak ada error tercatat")
            bot.edit_message_text(
                f"❌ Gagal memuat detail film.\n\n<code>Info Solver: {err_detail}</code>",
                chat_id=call.message.chat.id,
                message_id=status_msg.message_id
            )
            return

        markup = InlineKeyboardMarkup()
        if detail["downloads"]:
            for dl in detail["downloads"]:
                label = f"📥 {dl['provider']} [{dl['quality']}]"
                markup.add(InlineKeyboardButton(label, url=dl["url"]))
        else:
            markup.add(InlineKeyboardButton("🌐 Tonton di Web LK21", url=f"https://tv12.lk21official.cc/{slug}"))

        caption = (
            f"🎬 <b>{detail['title']}</b>\n\n"
            f"📝 <b>Sinopsis:</b>\n<i>{detail['synopsis'][:350]}...</i>\n\n"
            f"⚡ <b>Pilih direct link download di bawah ini (Tanpa Iklan):</b>"
        )

        bot.delete_message(call.message.chat.id, status_msg.message_id)

        if detail["poster"]:
            bot.send_photo(
                call.message.chat.id,
                photo=detail["poster"],
                caption=caption,
                reply_markup=markup
            )
        else:
            bot.send_message(
                call.message.chat.id,
                text=caption,
                reply_markup=markup
            )

    except Exception as e:
        bot.edit_message_text(f"⚠️ Terjadi error: {e}", chat_id=call.message.chat.id, message_id=status_msg.message_id)

if __name__ == "__main__":
    print("🚀 Bot started polling...")
    bot.infinity_polling(skip_pending=True)
