import glob
import json
import os
import re
import time
import warnings
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
 
import pandas as pd
import requests
from bs4 import BeautifulSoup
 
warnings.filterwarnings("ignore", message="This pattern is interpreted as a regular expression")
 
# ====== PENGATURAN ======
FOLDER_TWEET = "tweets-data"
POLA_FILE = "q*.csv"
FOLDER_DATA = "berita-data"
FOLDER_HASIL = "hasil_analisis"
MAX_LINK_DICEK = 100      # maksimal link t.co yang diurai (diurutkan dari yang paling sering dibagikan)
MAX_ARTIKEL = 40          # maksimal artikel yang di-scrape
JEDA_DETIK = 2            # jeda antar permintaan supaya tidak membebani server

 
# Link ke situs ini dilewati 
DOMAIN_DILEWATI = (
    "x.com", "twitter.com", "t.co", "twimg.com", "youtube.com", "youtu.be",
    "instagram.com", "facebook.com", "fb.com", "tiktok.com", "threads.net",
    "discord.gg", "discord.com", "wa.me", "whatsapp.com", "t.me",
    "antaranews.com",
)
 
HEADERS_ARTIKEL = {
    "User-Agent": "Mozilla/5.0 (tugas kuliah Sosial Media UNM)",
    "Accept-Language": "id,en;q=0.8",
}
 
KATA_KUNCI = {
    "roblox": r"\brob[l]?o?x\b|\brablox\b",
    "game": r"\bgame\b|\bgim\b|\bgaming\b",
    "youtube": r"\byoutube\b",
    "tiktok": r"\btiktok\b",
    "instagram": r"\binstagram\b",
    "medsos": r"\bmedsos\b|\bsosmed\b|media sosial",
    "anak": r"\banak\b|\bbocil\b",
    "orang tua": r"orang ?tua|\bortu\b",
    "umur / usia": r"\bumur\b|\busia\b",
    "akun": r"\bakun\b",
    "blokir / banned": r"\bblokir\w*|\bdiblokir\b|\bban(ned)?\b",
    "komdigi": r"\bkomdigi\b|\bmenkomdigi\b|\bkemkomdigi\b|\bkominfo\b",
    "pemerintah": r"\bpemerintah\b|\bmenteri\b",
    "sanksi": r"\bsanksi\b|\bdenda\b",
    "platform": r"\bplatform\b",
    "privasi / data": r"\bprivasi\b|\bdata pribadi\b",
}
 
URL_RE = re.compile(r"https?://\S+")
 
 
# ---------- 1. Kumpulkan link dari tweet ----------
def kumpulkan_link_dari_tweet():
    files = sorted(glob.glob(os.path.join(FOLDER_TWEET, POLA_FILE)))
    if not files:
        raise SystemExit(f"Tidak ada file {POLA_FILE} di folder '{FOLDER_TWEET}'.")
    df = pd.concat([pd.read_csv(f, encoding="utf-8") for f in files], ignore_index=True)
    kunci = "id_str" if "id_str" in df.columns else "full_text"
    df = df.drop_duplicates(subset=kunci)       # satu tweet jangan dihitung dobel
    semua = []
    for teks in df["full_text"].dropna():
        semua += [u.rstrip(").,;\"'") for u in URL_RE.findall(str(teks))]
    hitung = pd.Series(semua).value_counts()
    print(f"Tweet dibaca: {len(df)} | link ditemukan: {len(semua)} | link unik: {len(hitung)}")
    return hitung.head(MAX_LINK_DICEK)
 
 
# ---------- 2. Urai link pendek ----------
def urai_link(url):
    """Ikuti link t.co sampai alamat aslinya."""
    try:
        r = requests.get(url, timeout=15, allow_redirects=False,
                         headers={"User-Agent": "python-requests"})
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            return r.headers["Location"]
        soup = BeautifulSoup(r.text, "html.parser")
        m = soup.find("meta", attrs={"http-equiv": re.compile("refresh", re.I)})
        if m and "url=" in m.get("content", "").lower():
            return re.split("url=", m["content"], flags=re.I)[1].strip(" '\"")
    except Exception:
        pass
    return None
 
 
def bersihkan_url(url):
    """Buang parameter pelacak (utm_*, fbclid) supaya link yang sama tidak terhitung dobel."""
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query)
         if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid", "ref", "source")]
    return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(q), ""))
 
 
def domain_dilewati(url):
    host = urlparse(url).netloc.lower().replace("www.", "")
    return any(host == d or host.endswith("." + d) for d in DOMAIN_DILEWATI)
 
 
# ---------- 3. robots.txt ----------
def boleh_diambil(url, cache={}):
    p = urlparse(url)
    dasar = f"{p.scheme}://{p.netloc}"
    if dasar not in cache:
        rp = RobotFileParser()
        rp.set_url(dasar + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        cache[dasar] = rp
    rp = cache[dasar]
    return True if rp is None else rp.can_fetch(HEADERS_ARTIKEL["User-Agent"], url)
 
 
# ---------- 4. Ambil isi artikel (BeautifulSoup) ----------
def ambil_judul(soup):
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    h1 = soup.find("h1")
    return h1.get_text(" ", strip=True) if h1 else ""
 
 
def ambil_tanggal(soup):
    for atribut in ({"property": "article:published_time"}, {"name": "pubdate"},
                    {"itemprop": "datePublished"}, {"name": "publishdate"}):
        m = soup.find("meta", attrs=atribut)
        if m and m.get("content"):
            return m["content"].strip()
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if isinstance(item, dict) and item.get("datePublished"):
                return str(item["datePublished"])
    t = soup.find("time")
    if t:
        return (t.get("datetime") or t.get_text(strip=True)).strip()
    return ""
 
 
def ambil_isi(soup):
    wadah = soup.find("article") or soup
    paragraf = []
    for p in wadah.find_all("p"):
        teks = p.get_text(" ", strip=True)
        if len(teks) < 40:
            continue
        if re.match(r"^(baca juga|baca selengkapnya|simak|advertisement|iklan)", teks, re.I):
            continue
        paragraf.append(teks)
    return " ".join(paragraf)
 
 
def ambil_artikel(url):
    r = requests.get(url, headers=HEADERS_ARTIKEL, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    return {
        "url": r.url,
        "sumber": urlparse(r.url).netloc.replace("www.", ""),
        "judul": ambil_judul(soup),
        "tanggal": ambil_tanggal(soup),
        "isi": ambil_isi(soup),
    }
 
 
# ---------- 5. Hitung kata kunci ----------
def hitung_kata_kunci(df, kolom):
    hasil = {k: int(df[kolom].str.contains(p, case=False, regex=True).sum())
             for k, p in KATA_KUNCI.items()}
    t = pd.Series(hasil, name="jumlah_artikel").rename_axis("kata_kunci").reset_index()
    t["persen"] = (t["jumlah_artikel"] / len(df) * 100).round(1)
    return t.sort_values("jumlah_artikel", ascending=False)
 
 
def main():
    os.makedirs(FOLDER_DATA, exist_ok=True)
    os.makedirs(FOLDER_HASIL, exist_ok=True)
 
    # 1-2. link dari tweet -> alamat asli
    link_tweet = kumpulkan_link_dari_tweet()
    asli = {}   # alamat asli -> berapa kali dibagikan di tweet
    print(f"\nMengurai {len(link_tweet)} link t.co ...")
    for u, n in link_tweet.items():
        tujuan = urai_link(u)
        time.sleep(0.5)
        if not tujuan or domain_dilewati(tujuan):
            continue
        tujuan = bersihkan_url(tujuan)
        asli[tujuan] = asli.get(tujuan, 0) + int(n)
    print(f"Link ke situs berita/web (bukan medsos): {len(asli)}")
    if not asli:
        raise SystemExit("Tidak ada link artikel di tweet. Coba perbesar MAX_LINK_DICEK.")
 
    urutan = sorted(asli.items(), key=lambda x: x[1], reverse=True)[:MAX_ARTIKEL]
 
    # 3-4. scrape artikel
    baris = []
    for url, n in urutan:
        if not boleh_diambil(url):
            print(f"[dilewati, dilarang robots.txt] {url}")
            continue
        try:
            a = ambil_artikel(url)
            a["dibagikan_di_tweet"] = n
            print(f"[ok] {a['sumber']:24s} {len(a['isi']):6d} karakter | {a['judul'][:55]}")
            baris.append(a)
        except Exception as e:
            print(f"[gagal] {url}\n        {e}")
        time.sleep(JEDA_DETIK)
 
    if not baris:
        raise SystemExit("Tidak ada artikel yang berhasil diambil.")
    df = pd.DataFrame(baris)
    df = df[df["isi"].str.len() > 200].reset_index(drop=True)
    if df.empty:
        raise SystemExit("Isi artikel kosong semua (kemungkinan situsnya memblokir atau butuh JavaScript).")
 
    df["gabungan"] = df["judul"] + ". " + df["isi"]
    df.drop(columns="gabungan").to_csv(os.path.join(FOLDER_DATA, "berita_dari_tweet.csv"),
                                       index=False, sep=";", encoding="utf-8-sig")
 
    # 5. kata kunci + perbandingan dengan tweet
    tabel = hitung_kata_kunci(df, "gabungan")
    tabel.to_csv(os.path.join(FOLDER_HASIL, "frekuensi_berita.csv"), index=False, encoding="utf-8-sig")
    print(f"\nArtikel berhasil diambil: {len(df)}")
    print("\nFrekuensi kata kunci di berita (jumlah artikel):")
    print(tabel.to_string(index=False))
 
    f_tweet = os.path.join(FOLDER_HASIL, "frekuensi_kata_kunci.csv")
    if os.path.exists(f_tweet):
        tw = pd.read_csv(f_tweet)[["kata_kunci", "persen"]].rename(columns={"persen": "persen_tweet"})
        bd = tabel[["kata_kunci", "persen"]].rename(columns={"persen": "persen_berita"})
        banding = bd.merge(tw, on="kata_kunci", how="inner")
        banding["selisih"] = (banding["persen_berita"] - banding["persen_tweet"]).round(1)
        banding.to_csv(os.path.join(FOLDER_HASIL, "perbandingan_berita_tweet.csv"),
                       index=False, encoding="utf-8-sig")
        print("\nPerbandingan % kemunculan (berita vs tweet):")
        print(banding.sort_values("selisih", ascending=False).to_string(index=False))
 
 
if __name__ == "__main__":
    main()