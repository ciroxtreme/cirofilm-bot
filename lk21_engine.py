import subprocess
import os
import shutil
import tempfile
import urllib.parse
import json
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
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
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
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
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
    """Cari film via backend LK21 (gudangvape.com API)"""
    search_url = f"https://gudangvape.com/search.php?s={urllib.parse.quote(query)}&page=1"
    raw_json = fetch_with_cfsolve(search_url)
    if not raw_json:
        return []
    
    try:
        data = json.loads(raw_json)
        items = data.get("data", [])
        movies = []
        for it in items[:8]:
            movies.append({
                "title": it.get("title", ""),
                "slug": it.get("slug", ""),
                "rating": it.get("rating", "-"),
                "year": it.get("year", "-"),
                "type": it.get("type", "movie"),
                "poster": f"https://poster.assetsy.de/wp-content/uploads/{it.get('poster', '')}" if it.get("poster") else ""
            })
        return movies
    except Exception as e:
        print(f"[parse search error] {e}")
        return []

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
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if "dadadidi.de" in href:
            dl_gateway = href
            break
            
    downloads = []
    if dl_gateway:
        parts = dl_gateway.strip("/").split("/")
        gw_slug = parts[-1]
        
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

    return {
        "title": title,
        "poster": poster,
        "synopsis": synopsis,
        "downloads": downloads
    }
