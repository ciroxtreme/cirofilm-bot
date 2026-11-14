import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import lk21_engine
import diag

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9155074189:AAF-D3xWr7r0Qsn3NGD8J-mFwvSjL_XNGug")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

print("🤖 Cirofilm_bot is initializing (Movies & TV Series Edition)...")

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    text = (
        "🎬 <b>Selamat Datang di CiroFilm Bot!</b>\n\n"
        "Bot download <b>Film & Drama Korea / TV Series</b> tanpa iklan, ditenagai engine native Cloudflare Solver.\n\n"
        "📌 <b>Cara Pakai:</b>\n"
        "Cukup ketik judul film atau drakor/series yang ingin kamu tonton.\n"
        "Contoh:\n"
        "• Film: <code>Oppenheimer</code> atau <code>Kung Fu Soccer</code>\n"
        "• Series / Drakor: <code>Vincenzo</code> atau <code>Chicago PD</code>\n\n"
        "<i>Semua link download (Google Share, Mega, Cast, Telegram) langsung diekstrak bersih per episode!</i>"
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
        bot.reply_to(message, "⚠️ Masukkan judul minimal 2 huruf ya!")
        return

    wait_msg = bot.reply_to(message, f"🔍 <b>Mencari:</b> <i>{query}</i>\n<i>Sedang menembus Cloudflare database...</i>")

    try:
        results = lk21_engine.search_movies(query)
        if not results:
            err_detail = getattr(lk21_engine, "LAST_ERROR", "Tidak ada error tercatat")
            bot.edit_message_text(
                f"❌ Judul <b>{query}</b> tidak ditemukan di database LK21 / NontonDrama.\n\n<code>Info Solver: {err_detail}</code>",
                chat_id=message.chat.id,
                message_id=wait_msg.message_id
            )
            return

        markup = InlineKeyboardMarkup()
        for it in results:
            is_series = it["type"] == "series"
            icon = "📺" if is_series else "🎬"
            ep_tag = f" [{it['episodes_count']} Eps]" if is_series and it.get("episodes_count") else ""
            btn_text = f"{icon} {it['title']} ({it['year']}){ep_tag} ⭐ {it['rating']}"
            cb_data = f"ser:{it['slug'][:40]}" if is_series else f"dl:{it['slug'][:40]}"
            markup.add(InlineKeyboardButton(btn_text, callback_data=cb_data))

        bot.edit_message_text(
            f"🍿 <b>Ditemukan {len(results)} hasil untuk:</b> <i>{query}</i>\nSilakan pilih tontonan di bawah ini:",
            chat_id=message.chat.id,
            message_id=wait_msg.message_id,
            reply_markup=markup
        )
    except Exception as e:
        bot.edit_message_text(f"⚠️ Terjadi kesalahan: {e}", chat_id=message.chat.id, message_id=wait_msg.message_id)

# Handler khusus Series / Drakor (Menampilkan daftar episode)
@bot.callback_query_handler(func=lambda call: call.data.startswith("ser:"))
def handle_series_callback(call):
    slug = call.data.replace("ser:", "")
    bot.answer_callback_query(call.id, "Memuat daftar episode series...")

    status_msg = bot.send_message(
        call.message.chat.id,
        "⏳ <i>Menghubungkan ke tv.nontondrama.vip & memuat daftar episode...</i>"
    )

    try:
        detail = lk21_engine.get_series_detail(slug)
        if not detail:
            err_detail = getattr(lk21_engine, "LAST_ERROR", "Tidak ada error tercatat")
            bot.edit_message_text(
                f"❌ Gagal memuat episode series.\n\n<code>Info Solver: {err_detail}</code>",
                chat_id=call.message.chat.id,
                message_id=status_msg.message_id
            )
            return

        markup = InlineKeyboardMarkup()
        episodes = detail.get("episodes", [])
        
        # Susun tombol 3-4 kolom per baris agar rapi
        row = []
        for ep in episodes:
            btn = InlineKeyboardButton(ep["label"], callback_data=f"ep:{ep['slug'][:40]}")
            row.append(btn)
            if len(row) == 3:
                markup.row(*row)
                row = []
        if row:
            markup.row(*row)

        caption = (
            f"📺 <b>{detail['title']}</b>\n\n"
            f"📝 <b>Sinopsis:</b>\n<i>{detail['synopsis'][:350]}...</i>\n\n"
            f"⚡ <b>Pilih Episode di bawah ini untuk melihat link download:</b>"
        )

        bot.delete_message(call.message.chat.id, status_msg.message_id)

        if detail.get("poster"):
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

# Handler per Episode Series
@bot.callback_query_handler(func=lambda call: call.data.startswith("ep:"))
def handle_episode_callback(call):
    ep_slug = call.data.replace("ep:", "")
    bot.answer_callback_query(call.id, f"Mengekstrak download {ep_slug}...")

    status_msg = bot.send_message(
        call.message.chat.id,
        f"⏳ <i>Mengekstrak link download untuk: <b>{ep_slug}</b>...</i>"
    )

    try:
        data = lk21_engine.get_episode_download(ep_slug)
        downloads = data.get("downloads", [])

        markup = InlineKeyboardMarkup()
        if downloads:
            for dl in downloads:
                label = f"📥 {dl['provider']} [{dl['quality']}]"
                markup.add(InlineKeyboardButton(label, url=dl["url"]))
        else:
            markup.add(InlineKeyboardButton("🌐 Tonton di Web NontonDrama", url=f"https://tv.nontondrama.vip/{ep_slug}"))

        text = (
            f"🎬 <b>{data.get('title', ep_slug)}</b>\n\n"
            f"⚡ <b>Pilih direct link download (Tanpa Iklan):</b>"
        )

        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=markup
        )
    except Exception as e:
        bot.edit_message_text(f"⚠️ Terjadi error: {e}", chat_id=call.message.chat.id, message_id=status_msg.message_id)

# Handler Movie Lepas
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
    print("🚀 Bot started polling (Movies & Series Support)...")
    bot.infinity_polling(skip_pending=True)
