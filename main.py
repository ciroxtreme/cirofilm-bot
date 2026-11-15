import os
import itertools
import time
import threading
import sys
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import lk21_engine
import diag

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9155074189:AAF-D3xWr7r0Qsn3NGD8J-mFwvSjL_XNGug")
WORKER_URL = os.environ.get("WORKER_URL", "https://cirofilm-wake.captenciro.workers.dev")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

print("🤖 Cirofilm_bot is initializing (On-Demand GitHub Actions Edition)...")

# Cache memori untuk callback DrakorKita dengan atomic counter (anti-collision)
_dk_counter = itertools.count(1)
DK_CACHE = {}

# Idle timer management (1 jam = 3600 detik)
IDLE_TIMEOUT_SECONDS = 3600
last_activity_time = time.time()
is_shutting_down = False
last_user_chat_id = None

def update_activity(chat_id=None):
    global last_activity_time, last_user_chat_id
    last_activity_time = time.time()
    if chat_id:
        last_user_chat_id = chat_id

def restore_webhook():
    """Mengembalikan Telegram Webhook ke Cloudflare Worker saat bot mau tidur"""
    if not WORKER_URL:
        return
    try:
        print(f"🔄 Restoring webhook to Cloudflare Worker: {WORKER_URL}")
        bot.set_webhook(url=WORKER_URL, drop_pending_updates=True)
        print("✅ Webhook restored successfully!")
    except Exception as e:
        print(f"⚠️ Failed to restore webhook: {e}")

def shutdown_bot(reason="timeout"):
    global is_shutting_down
    if is_shutting_down:
        return
    is_shutting_down = True
    print(f"🛑 Shutting down Cirofilm Bot (Reason: {reason})...")

    if last_user_chat_id:
        try:
            if reason == "manual":
                bot.send_message(
                    last_user_chat_id,
                    "💤 <b>CiroFilm Bot telah dinonaktifkan (Manual Stop).</b>\n"
                    "Server GitHub Actions dimatikan untuk menghemat kuota.\n\n"
                    "<i>Ketik judul film apa saja kapan pun untuk membangunkan kembali!</i>"
                )
            else:
                bot.send_message(
                    last_user_chat_id,
                    "💤 <b>CiroFilm Bot otomatis tidur</b> karena tidak ada aktivitas selama 1 jam.\n"
                    "Server dimatikan dengan aman. Ketik judul film apa pun jika ingin nonton lagi!"
                )
        except Exception as e:
            print(f"⚠️ Failed to send shutdown message: {e}")

    try:
        bot.stop_polling()
    except Exception:
        pass

    restore_webhook()
    print("👋 Bye! Process exiting cleanly.")
    os._exit(0)

def idle_checker_thread():
    """Background monitor untuk auto-shutdown jika nganggur 1 jam"""
    while not is_shutting_down:
        time.sleep(15)
        idle_duration = time.time() - last_activity_time
        if idle_duration >= IDLE_TIMEOUT_SECONDS:
            print(f"⏰ Idle timeout reached ({int(idle_duration)}s >= {IDLE_TIMEOUT_SECONDS}s).")
            shutdown_bot(reason="timeout")
            break

def dk_cache_put(data):
    key = f"c_{next(_dk_counter)}"
    if len(DK_CACHE) > 1000:
        for k in list(DK_CACHE.keys())[:200]:
            DK_CACHE.pop(k, None)
    DK_CACHE[key] = data
    return key

@bot.message_handler(commands=["stop", "off"])
def handle_stop(message):
    update_activity(message.chat.id)
    bot.reply_to(message, "🛑 <i>Menerima perintah /stop. Menyiapkan proses tidur...</i>")
    threading.Thread(target=shutdown_bot, kwargs={"reason": "manual"}).start()

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    update_activity(message.chat.id)
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

def ask_search_target(chat_id: int, query: str):
    """Langkah 1: Tanyakan ke user mau cari di LK21 (Barat/Global) atau DrakorKita (Asian/Korea)"""
    update_activity(chat_id)
    cid = dk_cache_put({"q": query, "page": 1})
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🌐 LK21 (Film Barat / Hollywood)", callback_data=f"src:lk:{cid}"),
        InlineKeyboardButton("🇰🇷 DrakorKita (Drama Korea / Asia)", callback_data=f"src:dk:{cid}")
    )
    markup.add(InlineKeyboardButton("🍿 Cari di Keduanya (Semua Server)", callback_data=f"src:all:{cid}"))

    text = (
        f"🎬 <b>Pencarian:</b> <i>{query}</i>\n\n"
        f"Pilih sumber server yang ingin kamu jelajahi:"
    )
    bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("src:"))
def handle_source_selection(call):
    update_activity(call.message.chat.id)
    _, target_src, cid = call.data.split(":")
    cached = DK_CACHE.get(cid)
    if not cached:
        bot.answer_callback_query(call.id, "Sesi pencarian kedaluwarsa, silakan ketik ulang.")
        return

    cached["src"] = target_src
    query = cached["q"]

    # Jika memilih LK21 atau All, tanyakan mau Movie atau Series
    if target_src in ["lk", "all"]:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🎬 Movie (Film Bioskop)", callback_data=f"fmt:movie:{cid}"),
            InlineKeyboardButton("📺 Series / Serial TV", callback_data=f"fmt:series:{cid}")
        )
        markup.add(InlineKeyboardButton("🍿 Tampilkan Semua Format", callback_data=f"fmt:all:{cid}"))
        
        bot.edit_message_text(
            f"🎬 <b>Pencarian:</b> <i>{query}</i>\n"
            f"📍 <b>Server:</b> {'LK21' if target_src == 'lk' else 'Semua Server'}\n\n"
            f"Mau format apa Tuan Ciro?",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
    else:
        # DrakorKita langsung jalankan pencarian
        cached["fmt"] = "all"
        execute_paged_search(call.message.chat.id, call.message.message_id, cid)

@bot.callback_query_handler(func=lambda call: call.data.startswith("fmt:"))
def handle_format_selection(call):
    update_activity(call.message.chat.id)
    _, fmt, cid = call.data.split(":")
    cached = DK_CACHE.get(cid)
    if not cached:
        bot.answer_callback_query(call.id, "Sesi pencarian kedaluwarsa.")
        return

    cached["fmt"] = fmt
    execute_paged_search(call.message.chat.id, call.message.message_id, cid)

def execute_paged_search(chat_id: int, message_id: int, cid: str):
    cached = DK_CACHE.get(cid)
    if not cached:
        return

    query = cached["q"]
    page = cached.get("page", 1)
    target_src = cached.get("src", "all")
    target_fmt = cached.get("fmt", "all")

    bot.edit_message_text(
        f"🔍 <b>Mencari:</b> <i>{query}</i> (Halaman {page})\n<i>Sedang menghubungkan ke server...</i>",
        chat_id=chat_id,
        message_id=message_id
    )

    try:
        results_lk21 = []
        total_pages_lk = 1
        results_dk = []
        total_pages_dk = 1

        # 1. Cari LK21 jika diminta
        if target_src in ["lk", "all"]:
            lk_res = lk21_engine.search_movies(query, page=page)
            raw_lk = lk_res.get("data", [])
            total_pages_lk = lk_res.get("total_pages", 1)
            
            # Filter format jika dipilih spesifik
            if target_fmt == "movie":
                results_lk21 = [x for x in raw_lk if x.get("type") == "movie"]
            elif target_fmt == "series":
                results_lk21 = [x for x in raw_lk if x.get("type") == "series"]
            else:
                results_lk21 = raw_lk

        # 2. Cari DrakorKita jika diminta
        if target_src in ["dk", "all"]:
            dk_res = lk21_engine.search_drakorkita(query, page=page)
            results_dk = dk_res.get("data", [])
            total_pages_dk = dk_res.get("total_pages", 1)

        total_pages = max(total_pages_lk, total_pages_dk)

        if not results_lk21 and not results_dk:
            bot.edit_message_text(
                f"❌ Tidak ditemukan hasil untuk <b>{query}</b> pada halaman {page}.\n\n"
                f"<i>Tips: Periksa ejaan judul atau coba gunakan kata kunci yang lebih singkat.</i>",
                chat_id=chat_id,
                message_id=message_id
            )
            return

        markup = InlineKeyboardMarkup()

        if results_lk21:
            markup.add(InlineKeyboardButton("➖➖ 🌐 LK21 / NONTONDRAMA ➖➖", callback_data="noop"))
            for it in results_lk21[:6]:
                is_series = it["type"] == "series"
                icon = "📺" if is_series else "🎬"
                ep_tag = f" [{it['episodes_count']} Eps]" if is_series and it.get("episodes_count") else ""
                btn_text = f"{icon} {it['title']} ({it['year']}){ep_tag} ⭐ {it['rating']}"
                item_cid = dk_cache_put(it["slug"])
                cb_data = f"ser:{item_cid}" if is_series else f"dl:{item_cid}"
                markup.add(InlineKeyboardButton(btn_text, callback_data=cb_data))

        if results_dk:
            markup.add(InlineKeyboardButton("➖➖ 🇰🇷 DRAKOR.KITA.MOBI ➖➖", callback_data="noop"))
            for dk in results_dk[:6]:
                btn_text = f"🎬 {dk['title']}"
                item_cid = dk_cache_put(dk["slug"])
                markup.add(InlineKeyboardButton(btn_text, callback_data=f"dk:{item_cid}"))

        # Tombol Navigasi Pagination
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"pg:{page-1}:{cid}"))
        nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"pg:{page+1}:{cid}"))

        if len(nav_buttons) > 1:
            markup.row(*nav_buttons)

        bot.edit_message_text(
            f"🍿 <b>Hasil Pencarian:</b> <i>{query}</i>\n"
            f"📑 <b>Halaman:</b> {page} dari {total_pages}\n\n"
            f"Silakan pilih judul di bawah ini:",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=markup
        )
    except Exception as e:
        bot.edit_message_text(f"⚠️ Terjadi kesalahan: {e}", chat_id=chat_id, message_id=message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pg:"))
def handle_pagination(call):
    update_activity(call.message.chat.id)
    _, p_str, cid = call.data.split(":")
    cached = DK_CACHE.get(cid)
    if not cached:
        bot.answer_callback_query(call.id, "Sesi telah kedaluwarsa.")
        return

    cached["page"] = int(p_str)
    execute_paged_search(call.message.chat.id, call.message.message_id, cid)

def process_search_query(chat_id: int, query: str):
    """Titik masuk awal pencarian"""
    ask_search_target(chat_id, query)

@bot.message_handler(func=lambda message: True)
def handle_search(message):
    update_activity(message.chat.id)
    query = message.text.strip()
    if len(query) < 2:
        bot.reply_to(message, "⚠️ Masukkan judul minimal 2 huruf ya!")
        return
    ask_search_target(message.chat.id, query)

@bot.callback_query_handler(func=lambda call: call.data == "noop")
def handle_noop(call):
    update_activity(call.message.chat.id)
    bot.answer_callback_query(call.id)

# Handler khusus Series / Drakor (Menampilkan daftar episode)
@bot.callback_query_handler(func=lambda call: call.data.startswith("ser:"))
def handle_series_callback(call):
    update_activity(call.message.chat.id)
    raw_val = call.data.replace("ser:", "")
    slug = DK_CACHE.get(raw_val, raw_val)
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
            ep_cid = dk_cache_put(ep["slug"])
            btn = InlineKeyboardButton(ep["label"], callback_data=f"ep:{ep_cid}")
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
    raw_val = call.data.replace("ep:", "")
    ep_slug = DK_CACHE.get(raw_val, raw_val)
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
    raw_val = call.data.replace("dl:", "")
    slug = DK_CACHE.get(raw_val, raw_val)
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
        is_single_movie = (len(episodes) == 1 and "unnamed" in episodes[0]["name"].lower())
        
        for ep in episodes:
            ep_cid = dk_cache_put({
                "ep_name": ep["name"],
                "qualities": ep["qualities"],
                "title": detail["title"]
            })
            raw_name = ep["name"].replace("Download ", "").strip()
            if "unnamed" in raw_name.lower():
                clean_name = "Download Full Movie"
                btn_icon = "📥"
            else:
                clean_name = raw_name
                btn_icon = "📺"

            btn = InlineKeyboardButton(f"{btn_icon} {clean_name}", callback_data=f"dep:{ep_cid}")
            row.append(btn)
            if len(row) == 2 or is_single_movie:
                markup.row(*row)
                row = []
        if row:
            markup.row(*row)

        category_icon = "🎬" if is_single_movie else "📺"
        category_label = "Movie / Film" if is_single_movie else "Series / Drama"
        total_info = f"📑 <b>Tipe:</b> {category_label}\n" if is_single_movie else f"📑 <b>Total Episode:</b> {len(episodes)}\n"
        guide_text = "👉 <i>Klik tombol di bawah untuk memilih kualitas download:</i>" if is_single_movie else "👉 <i>Silakan pilih episode yang ingin kamu unduh:</i>"

        caption = (
            f"{category_icon} <b>{detail['title']}</b>\n\n"
            f"📝 <b>Sinopsis:</b>\n<i>{detail['synopsis'][:350]}...</i>\n\n"
            f"{total_info}"
            f"{guide_text}"
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
    print("🚀 Initializing Cirofilm Bot On-Demand Runner...")
    
    # Lepas webhook dulu agar polling bisa jalan
    try:
        print("🔓 Removing Telegram webhook for polling mode...")
        bot.remove_webhook()
    except Exception as e:
        print(f"⚠️ remove_webhook error: {e}")

    # Nyalakan thread pemantau idle 1 jam
    idle_monitor = threading.Thread(target=idle_checker_thread, daemon=True)
    idle_monitor.start()
    print(f"⏱️ Idle shutdown monitor active (Timeout: {IDLE_TIMEOUT_SECONDS}s / 1 hour).")

    # Cek apakah bot dibangunkan dengan query awal (Wake query flow)
    wake_chat_id = os.environ.get("WAKE_CHAT_ID", "").strip()
    wake_query = os.environ.get("WAKE_QUERY", "").strip()
    wake_msg_id = os.environ.get("WAKE_MSG_ID", "").strip()

    def handle_initial_wake():
        if not wake_chat_id or not wake_query:
            return
        try:
            cid = int(wake_chat_id)
            print(f"⚡ Handling initial wake query: '{wake_query}' for chat {cid} (Wake Msg ID: {wake_msg_id})")

            # 1. Hapus pesan "Membangunkan mesin Ciro..."
            if wake_msg_id and wake_msg_id != "0":
                try:
                    bot.delete_message(cid, int(wake_msg_id))
                    print("🗑️ Deleted wake message")
                except Exception as e:
                    print(f"⚠️ Failed to delete wake message: {e}")

            # 2. Kirim pesan "Bot Ciro ON"
            on_msg = bot.send_message(cid, "🟢 <b>Bot Ciro ON</b>", parse_mode="HTML")
            time.sleep(1.5)

            # 3. Hapus pesan "Bot Ciro ON"
            try:
                bot.delete_message(cid, on_msg.message_id)
                print("🗑️ Deleted 'Bot Ciro ON' message")
            except Exception as e:
                print(f"⚠️ Failed to delete ON message: {e}")

            # 4. Jika query bukan /stop, jalankan pencarian
            if wake_query not in ["/stop", "/off", "/start"]:
                process_search_query(cid, wake_query)
            elif wake_query in ["/stop", "/off"]:
                shutdown_bot(reason="manual")
        except Exception as e:
            print(f"⚠️ Error handling initial wake: {e}")

    # Jalankan initial wake di thread terpisah agar polling langsung aktif
    threading.Thread(target=handle_initial_wake, daemon=True).start()

    print("🚀 Bot started polling (Interactive Movies & Series Mode)...")
    try:
        bot.infinity_polling(skip_pending=True)
    except Exception as e:
        print(f"⚠️ Bot polling exception: {e}")
    finally:
        restore_webhook()
