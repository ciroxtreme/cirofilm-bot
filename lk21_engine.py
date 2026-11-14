import subprocess
import os
import shutil
import tempfile
import urllib.parse
import json
import re
from bs4 import BeautifulSoup
from curl_cffi import requests

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CHALLENGE_BIN = os.path.join(CURRENT_DIR, "bin", "challenge")
PROFILE_JSON = os.path.join(CURRENT_DIR, "profiles", "safari-26-ios.json")

# Pastikan permission executable
if os.path.exists(CHALLENGE_BIN):
    try:
        os.chmod(CHALLENGE_BIN, 0o755)
    except Exception:
        pass

if not os.path.exists(CHALLENGE_BIN):
    CHALLENGE_BIN = "/home/container/files/cfsolve-repo/target/release/challenge"
if not os.path.exists(PROFILE_JSON):
    PROFILE_JSON = "/home/container/files/cfsolve-repo/profiles/safari-26-ios.json"

BASE_LK21 = "https://tv12.lk21official.cc"
BASE_SERIES = "https://tv.nontondrama.vip"
DEFAULT_SITEKEY = "0x4AAAAAAD1B9GOEfUpOVP4w"

LAST_ERROR = ""

def fetch_with_cfsolve(target_url: str) -> str:
    """Tembus Cloudflare Challenge halaman menggunakan cfsolve"""
    global LAST_ERROR
    out_dir = tempfile.mkdtemp(prefix="cfsolve_page_")
    try:
        cmd = [
            CHALLENGE_BIN,
            "--page", target_url,
            out_dir,
            "--solve",
            "--fingerprint", PROFILE_JSON
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=65)
        if res.returncode != 0:
            LAST_ERROR = f"Exit code {res.returncode}: {res.stderr[:200]}"
            print(f"[cfsolve returncode != 0] {res.stderr}")
            
        cleared_file = os.path.join(out_dir, "cleared.html")
        if os.path.exists(cleared_file):
            with open(cleared_file, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        else:
            if not LAST_ERROR:
                LAST_ERROR = f"cleared.html not found. stderr: {res.stderr[:200]}"
        return ""
    except Exception as e:
        LAST_ERROR = f"Exception: {e}"
        print(f"[cfsolve error] {e}")
        return ""
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)

def solve_turnstile_token(page_url: str, sitekey: str = DEFAULT_SITEKEY) -> str:
    """Selesaikan Turnstile widget untuk mendapatkan validasi token"""
    global LAST_ERROR
    out_dir = tempfile.mkdtemp(prefix="cfsolve_widget_")
    try:
        cmd = [
            CHALLENGE_BIN,
            "--page", page_url,
            out_dir,
            "--sitekey", sitekey,
            "--blank-page",
            "--solve",
            "--fingerprint", PROFILE_JSON
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=50)
        lines = res.stdout.strip().split("\n")
        if lines:
            token = lines[-1].strip()
            if len(token) > 100:
                return token
        LAST_ERROR = f"Widget solve failed. stderr: {res.stderr[:200]}"
        return ""
    except Exception as e:
        LAST_ERROR = f"Widget Exception: {e}"
        print(f"[turnstile error] {e}")
        return ""
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)

def search_movies(query: str):
    """Cari film & series via backend LK21 (gudangvape.com API)"""
    search_url = f"https://gudangvape.com/search.php?s={urllib.parse.quote(query)}&page=1"
    raw_json = fetch_with_cfsolve(search_url)
    if not raw_json:
        return []
    
    try:
        data = json.loads(raw_json)
        items = data.get("data", [])
        results = []
        for it in items[:8]:
            mtype = it.get("type", "movie")
            results.append({
                "title": it.get("title", ""),
                "slug": it.get("slug", ""),
                "rating": it.get("rating", "-"),
                "year": it.get("year", "-"),
                "type": mtype,
                "episodes_count": it.get("episode", 0),
                "poster": f"https://poster.assetsy.de/wp-content/uploads/{it.get('poster', '')}" if it.get("poster") else ""
            })
        return results
    except Exception as e:
        print(f"[parse search error] {e}")
        return []

def get_series_detail(slug: str):
    """Ambil detail series/drakor & daftar episode dari tv.nontondrama.vip"""
    series_url = f"{BASE_SERIES}/{slug}"
    html = fetch_with_cfsolve(series_url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.text.strip() if title_tag else slug

    synopsis = ""
    syn_tag = soup.find(class_="synopsis") or soup.find("blockquote")
    if syn_tag:
        synopsis = syn_tag.text.strip()
    else:
        for p in soup.find_all("p"):
            txt = p.text.strip()
            if len(txt) > 50 and "GANTI PLAYER" not in txt:
                synopsis = txt
                break

    poster = ""
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and "poster.assetsy.de" in src:
            poster = src
            break

    # Ekstrak daftar episode lengkap dari JSON #season-data
    episodes = []
    season_el = soup.find(id="season-data")
    if season_el:
        try:
            season_json = json.loads(season_el.string or season_el.text)
            for s_num, ep_list in season_json.items():
                s_int = int(s_num)
                for ep_item in ep_list:
                    ep_no = int(ep_item.get("episode_no", 0))
                    ep_slug = ep_item.get("slug", "")
                    if ep_slug:
                        episodes.append({
                            "season": s_int,
                            "episode": ep_no,
                            "label": f"S{s_int} Ep {ep_no}",
                            "slug": ep_slug
                        })
        except Exception as e:
            print(f"[season-data parse error] {e}")

    # Fallback jika season-data tidak ada
    if not episodes:
        seen_slugs = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if re.search(r"episode-[0-9]+", href, re.I):
                ep_slug = href.strip("/").split("/")[-1]
                if ep_slug not in seen_slugs and ep_slug != slug:
                    seen_slugs.add(ep_slug)
                    ep_match = re.search(r"episode-([0-9]+)", ep_slug, re.I)
                    ep_num = ep_match.group(1) if ep_match else str(len(episodes) + 1)
                    season_match = re.search(r"season-([0-9]+)", ep_slug, re.I)
                    season_num = season_match.group(1) if season_match else "1"
                    
                    episodes.append({
                        "season": int(season_num),
                        "episode": int(ep_num),
                        "label": f"S{season_num} Ep {ep_num}",
                        "slug": ep_slug
                    })

    # Urutkan episode dari awal ke akhir
    episodes.sort(key=lambda x: (x["season"], x["episode"]))

    return {
        "title": title,
        "poster": poster,
        "synopsis": synopsis,
        "type": "series",
        "episodes": episodes
    }

def get_download_links_from_gateway(dl_gateway: str):
    """Ambil direct download link dari gateway dadadidi.de"""
    parts = dl_gateway.strip("/").split("/")
    gw_slug = parts[-1]

    downloads = []
    turnstile_token = solve_turnstile_token(f"https://dadadidi.de/get/{gw_slug}", DEFAULT_SITEKEY)
    if turnstile_token:
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
            "Referer": f"https://dadadidi.de/get/{gw_slug}",
            "Origin": "https://dadadidi.de",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        data = {"slug": gw_slug, "cf-turnstile-response": turnstile_token}
        try:
            r = requests.post(
                f"https://dadadidi.de/verifying.php?slug={gw_slug}",
                headers=headers,
                data=data,
                impersonate="chrome124",
                timeout=15
            )
            if r.status_code == 200 and "table" in r.text:
                table_soup = BeautifulSoup(r.text, "html.parser")
                for tr in table_soup.find_all("tr"):
                    cols = tr.find_all("td")
                    if len(cols) >= 2:
                        prov = cols[0].text.strip()
                        a_tag = cols[1].find("a")
                        if a_tag:
                            downloads.append({
                                "provider": prov,
                                "quality": a_tag.text.strip(),
                                "url": a_tag.get("href")
                            })
        except Exception as e:
            print(f"[verifying.php error] {e}")
            
    return downloads

def get_episode_download(ep_slug: str):
    """Ambil link download untuk satu episode spesifik langsung via gateway dadadidi.de"""
    # Shortcut langsung: gateway dadadidi.de menggunakan format https://dadadidi.de/{ep_slug}
    direct_gw = f"https://dadadidi.de/{ep_slug}"
    print(f"[direct gateway] Mengambil link langsung dari {direct_gw}...")
    downloads = get_download_links_from_gateway(direct_gw)
    
    # Jika shortcut gagal, baru fallback buka halaman webnya
    if not downloads:
        ep_url = f"{BASE_SERIES}/{ep_slug}"
        html = fetch_with_cfsolve(ep_url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                if "dadadidi.de" in a["href"]:
                    downloads = get_download_links_from_gateway(a["href"])
                    break

    return {
        "title": ep_slug.replace("-", " ").title(),
        "downloads": downloads
    }

def get_movie_detail(slug: str):
    """Ambil detail film & direct download link"""
    movie_url = f"{BASE_LK21}/{slug}"
    html = fetch_with_cfsolve(movie_url)
    if not html:
        return None
        
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.text.strip() if title_tag else slug
    
    synopsis = ""
    syn_tag = soup.find(class_="synopsis") or soup.find("blockquote")
    if syn_tag:
        synopsis = syn_tag.text.strip()
    else:
        for p in soup.find_all("p"):
            txt = p.text.strip()
            if len(txt) > 60 and "GANTI PLAYER" not in txt:
                synopsis = txt
                break
                
    poster = ""
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and "poster.assetsy.de" in src:
            poster = src
            break

    # Cari link gateway download (dadadidi.de)
    dl_gateway = None
    for a in soup.find_all("a", href=True):
        if "dadadidi.de" in a["href"]:
            dl_gateway = a["href"]
            break
            
    downloads = []
    if dl_gateway:
        downloads = get_download_links_from_gateway(dl_gateway)

    return {
        "title": title,
        "poster": poster,
        "synopsis": synopsis,
        "type": "movie",
        "downloads": downloads
    }


def search_drakorkita(query: str):
    """Cari drama di drakor.kita.mobi"""
    url = f"https://drakor.kita.mobi/all?q={urllib.parse.quote(query)}"
    html = fetch_with_cfsolve(url)
    if not html:
        return []
        
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/detail/" in href and href not in seen:
            seen.add(href)
            # Bersihkan judul teks
            title_text = a.text.strip()
            # Pisahkan teks durasi & tahun jika ada
            lines = [l.strip() for l in title_text.splitlines() if l.strip()]
            main_title = lines[1] if len(lines) > 1 else (lines[0] if lines else href)
            # Ambil slug
            slug = href.strip("/").split("/")[-1]
            img = a.find("img")
            poster = img.get("src") or img.get("data-src") if img else ""
            
            results.append({
                "source": "drakorkita",
                "title": main_title,
                "slug": slug,
                "detail_url": f"https://drakor.kita.mobi{href}",
                "poster": poster
            })
            if len(results) >= 6:
                break
    return results
