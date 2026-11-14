import os
import itertools
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import lk21_engine
import diag

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9155074189:AAF-D3xWr7r0Qsn3NGD8J-mFwvSjL_XNGug")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

print("🤖 Cirofilm_bot is initializing (Movies & TV Series Edition)...")

# Cache memori untuk callback DrakorKita dengan atomic counter (anti-collision)
_dk_counter = itertools.count(1)
DK_CACHE = {}

def dk_cache_put(data):
    key = f"c_{next(_dk_counter)}"
    if len(DK_CACHE) > 1000:
        for k in list(DK_CACHE.keys())[:200]:
            DK_CACHE.pop(k, None)
    DK_CACHE[key] = data
    return key

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

    wait_msg = bot.reply_to(message, f"🔍 <b>Mencari:</b> <i>{query}</i>\n<i>Sedang menembus database LK21 & DrakorKita...</i>")

    try:
        # 1. Cari di LK21 / NontonDrama
        results_lk21 = lk21_engine.search_movies(query)
        
        # 2. Cari di DrakorKita
        results_dk = lk21_engine.search_drakorkita(query)

        if not results_lk21 and not results_dk:
            err_detail = getattr(lk21_engine, "LAST_ERROR", "Tidak ada error tercatat")
            bot.edit_message_text(
                f"❌ Judul <b>{query}</b> tidak ditemukan di LK21 maupun DrakorKita.\n\n<code>Info Solver: {err_detail}</code>",
                chat_id=message.chat.id,
                message_id=wait_msg.message_id
            )
            return

        markup = InlineKeyboardMarkup()

        # Opsi Sumber 1: LK21 / NontonDrama
        if results_lk21:
            markup.add(InlineKeyboardButton("➖➖ 🌐 LK21 / NONTONDRAMA ➖➖", callback_data="noop"))
            for it in results_lk21[:5]:
                is_series = it["type"] == "series"
                icon = "📺" if is_series else "🎬"
                ep_tag = f" [{it['episodes_count']} Eps]" if is_series and it.get("episodes_count") else ""
                btn_text = f"{icon} {it['title']} ({it['year']}){ep_tag} ⭐ {it['rating']}"
                cb_data = f"ser:{it['slug']}" if is_series else f"dl:{it['slug']}"
                markup.add(InlineKeyboardButton(btn_text, callback_data=cb_data))

        # Opsi Sumber 2: Drakor.Kita.Mobi
        if results_dk:
            markup.add(InlineKeyboardButton("➖➖ 🇰🇷 DRAKOR.KITA.MOBI ➖➖", callback_data="noop"))
            for dk in results_dk[:5]:
                btn_text = f"🇰🇷 {dk['title']}"
                cid = dk_cache_put(dk["slug"])
                markup.add(InlineKeyboardButton(btn_text, callback_data=f"dk:{cid}"))

        total_found = len(results_lk21) + len(results_dk)
        bot.edit_message_text(
            f"🍿 <b>Ditemukan {total_found} hasil untuk:</b> <i>{query}</i>\nSilakan pilih server sumber di bawah ini:",
            chat_id=message.chat.id,
            message_id=wait_msg.message_id,
            reply_markup=markup
        )
    except Exception as e:
        bot.edit_message_text(f"⚠️ Terjadi kesalahan: {e}", chat_id=message.chat.id, message_id=wait_msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "noop")
def handle_noop(call):
    bot.answer_callback_query(call.id)

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
            btn = InlineKeyboardButton(ep["label"], callback_data=f"ep:{ep['slug']}")
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

# ==================== DRAKORKITA HANDLERS ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith("dk:"))
def handle_drakorkita_episodes(call):
    cid = call.data.replace("dk:", "")
    slug = DK_CACHE.get(cid, cid)
    bot.answer_callback_query(call.id, "Memuat episode DrakorKita...")

    status_msg = bot.send_message(
        call.message.chat.id,
        "⏳ <i>Menghubungkan ke drakor.kita.mobi & mengekstrak semua episode...</i>"
    )

    try:
        detail = lk21_engine.get_drakorkita_episodes(slug)
        if not detail or not detail.get("episodes"):
            err_detail = getattr(lk21_engine, "LAST_ERROR", "Tidak ada error tercatat")
            bot.edit_message_text(
                f"❌ Gagal memuat episode drama.\n\n<code>Info Solver: {err_detail}</code>",
                chat_id=call.message.chat.id,
                message_id=status_msg.message_id
            )
            return

        markup = InlineKeyboardMarkup()
        episodes = detail.get("episodes", [])
        
        # Susun tombol 2 kolom per baris
        row = []
        for ep in episodes:
            ep_cid = dk_cache_put({
                "ep_name": ep["name"],
                "qualities": ep["qualities"],
                "title": detail["title"]
            })
            clean_name = ep["name"].replace("Download ", "")
            btn = InlineKeyboardButton(f"📺 {clean_name}", callback_data=f"dep:{ep_cid}")
            row.append(btn)
            if len(row) == 2:
                markup.row(*row)
                row = []
        if row:
            markup.row(*row)

        caption = (
            f"🇰🇷 <b>{detail['title']}</b>\n\n"
            f"📝 <b>Sinopsis:</b>\n<i>{detail['synopsis'][:350]}...</i>\n\n"
            f"📑 <b>Total Episode:</b> {len(episodes)}\n"
            f"👉 <i>Silakan pilih episode yang ingin kamu unduh:</i>"
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

@bot.callback_query_handler(func=lambda call: call.data.startswith("dep:"))
def handle_drakorkita_download(call):
    ep_cid = call.data.replace("dep:", "")
    ep_data = DK_CACHE.get(ep_cid)
    if not ep_data:
        bot.answer_callback_query(call.id, "⚠️ Sesi kedaluwarsa. Silakan cari ulang ya.")
        return

    bot.answer_callback_query(call.id, "Mengekstrak direct download link...")
    status_msg = bot.send_message(
        call.message.chat.id,
        f"⏳ <i>Mengekstrak file download untuk <b>{ep_data['ep_name']}</b>...</i>"
    )

    try:
        markup = InlineKeyboardMarkup()
        for q in ep_data["qualities"]:
            direct_url = lk21_engine.get_drakorkita_download_link(q["dl_id"])
            if direct_url:
                markup.add(InlineKeyboardButton(f"📥 {q['label']}", url=direct_url))
            else:
                markup.add(InlineKeyboardButton(f"🌐 Web: {q['label']}", url=f"https://drakor.kita.mobi/download/{q['dl_id']}"))

        text = (
            f"🎬 <b>{ep_data['title']}</b>\n"
            f"📌 <b>{ep_data['ep_name']}</b>\n\n"
            f"⚡ <b>Pilih resolusi link download langsung (Direct Video File):</b>"
        )

        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=markup
        )
    except Exception as e:
        bot.edit_message_text(f"⚠️ Terjadi error: {e}", chat_id=call.message.chat.id, message_id=status_msg.message_id)

if __name__ == "__main__":
    print("🚀 Bot started polling (Movies & Series Support)...")
    bot.infinity_polling(skip_pending=True)
