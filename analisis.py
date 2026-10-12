import glob
import os
import re
import warnings
 
warnings.filterwarnings("ignore", message="This pattern is interpreted as a regular expression")
 
import pandas as pd
 
# ====== PENGATURAN ======
FOLDER_DATA = "tweets-data"
POLA_FILE = "q*.csv"               # semua file hasil scraping: q1_..., q2_..., dst.
TANGGAL_MULAI = "2026-03-28"       # PP Tunas mulai berlaku
FOLDER_OUTPUT = "hasil_analisis"
 
# Tweet dianggap relevan kalau memuat salah satu istilah ini
POLA_RELEVAN = (
    r"komdigi|menkomdigi|kominfo|medsos|media sosial|sosmed|roblox|rablox"
    r"|pp tunas|pptunas|\btunas\b|pp 17|batas usia|igrs"
)
 
# Tweet dari media/akun resmi (bukan opini warga), diawali pola-pola ini
POLA_BERITA = (
    r"^(menteri komunikasi dan digital|menkomdigi|wamen|wakil menteri"
    r"|kementerian komunikasi|breaking|jakarta\s*[-–]|\[?berita|update:)"
)
 
# Kata kunci yang dihitung (jumlah TWEET yang menyebutnya)
KATA_KUNCI = {
    "roblox": r"\brob[l]?o?x\b|\brablox\b",
    "game": r"\bgame\b|\bgim\b|\bgaming\b",
    "youtube": r"\byoutube\b|\byt\b",
    "tiktok": r"\btiktok\b",
    "instagram": r"\binstagram\b|\big\b",
    "medsos": r"\bmedsos\b|\bsosmed\b|media sosial",
    "anak": r"\banak\b|\bbocil\b",
    "orang tua": r"orang ?tua|\bortu\b",
    "umur / usia": r"\bumur\b|\busia\b",
    "akun": r"\bakun\b",
    "blokir / banned": r"\bblokir\w*|\bdiblokir\b|\bban(ned)?\b|\bdibanned\b",
    "komdigi": r"\bkomdigi\b|\bmenkomdigi\b|\bkominfo\b",
    "pemerintah": r"\bpemerintah\b|\bmenteri\b",
    "judol / judi": r"\bjudol\b|\bjudi\b|\bjud0l\b",
    "korupsi": r"\bkorupsi\b|\bkorup\b",
    "hoax / bohong": r"\bhoa?x+s?\b|\bhoaks\b|\bbohong\b",
    "privasi / data": r"\bprivasi\b|\bdata pribadi\b",
    "setuju": r"\bsetuju\b",
    "tidak setuju": r"\b(tidak|tak|gak|ga|nggak|gk|ngga)\s?setuju\b|\bgasetuju\b",
}
 
STOPWORDS = set("""
yang dan di ke dari ini itu untuk dengan pada adalah juga atau karena tapi tp
kalau kalo jadi udah sudah belum masih aja saja sih dong deh kok lah ya yg dgn
gak ga nggak tidak tak bukan ada akan bisa mau lagi sama sm kan nya nih tuh
si para dalam oleh saya aku gue gw lu lo kita kami mereka dia kamu anda
harus lebih sangat banget bgt lebih semua setiap apa siapa kenapa gimana
https http co www rt amp com id
""".split())
 
 
def muat_data():
    files = sorted(glob.glob(os.path.join(FOLDER_DATA, POLA_FILE)))
    if not files:
        raise SystemExit(f"Tidak ada file {POLA_FILE} di folder '{FOLDER_DATA}'.")
    bagian = []
    for f in files:
        d = pd.read_csv(f, encoding="utf-8")
        d["sumber_query"] = os.path.basename(f)
        print(f"  {os.path.basename(f):30s} {len(d):5d} tweet")
        bagian.append(d)
    return pd.concat(bagian, ignore_index=True)
 
 
def bersihkan_teks(t):
    t = str(t).replace("\u2028", " ").replace("\u2029", " ")
    t = re.sub(r"https?://\S+", " ", t)      # buang link
    t = re.sub(r"@\w+", " ", t)              # buang mention (anonimisasi)
    return " ".join(t.split())
 
 
def main():
    os.makedirs(FOLDER_OUTPUT, exist_ok=True)
 
    print("Membaca file:")
    df = muat_data()
    n_awal = len(df)
 
    # Pastikan kolom penting ada
    for kol in ("full_text", "created_at"):
        if kol not in df.columns:
            raise SystemExit(f"Kolom '{kol}' tidak ada. Kolom tersedia: {list(df.columns)}")
 
    # Buang duplikat (satu tweet bisa muncul di beberapa query)
    kunci = "id_str" if "id_str" in df.columns else "full_text"
    df = df.drop_duplicates(subset=kunci)
    n_dedup = len(df)
 
    # Tanggal eksak, lalu filter sesudah PP Tunas berlaku
    df["tanggal"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True).dt.tz_localize(None)
    df = df[df["tanggal"] >= pd.to_datetime(TANGGAL_MULAI)]
    n_tanggal = len(df)
 
    # Bersihkan teks + anonimisasi
    df["komentar"] = df["full_text"].apply(bersihkan_teks)
    df = df[df["komentar"].str.len() >= 10]          # buang yang isinya cuma link/kosong
    n_panjang = len(df)
 
    # Tandai berita/akun resmi dan buang dari analisis opini
    df["is_berita"] = df["komentar"].str.contains(POLA_BERITA, case=False, regex=True)
    df = df[~df["is_berita"]]
    n_berita = len(df)
 
    # Hanya yang relevan dengan topik
    df = df[df["komentar"].str.contains(POLA_RELEVAN, case=False, regex=True)]
    n_relevan = len(df)
 
    df = df.reset_index(drop=True)
 
    # Simpan data bersih (username/identitas sengaja tidak ikut)
    kolom_simpan = ["tanggal", "komentar", "sumber_query"]
    if "favorite_count" in df.columns:
        kolom_simpan.insert(1, "favorite_count")
    df[kolom_simpan].to_csv(
        os.path.join(FOLDER_OUTPUT, "data_bersih.csv"),
        index=False, sep=";", encoding="utf-8-sig",
    )
 
    print("\nRingkasan pembersihan:")
    print(f"  Total gabungan awal        : {n_awal}")
    print(f"  Setelah buang duplikat     : {n_dedup}")
    print(f"  Setelah filter tanggal     : {n_tanggal}  (>= {TANGGAL_MULAI})")
    print(f"  Setelah buang teks pendek  : {n_panjang}")
    print(f"  Setelah buang berita/resmi : {n_berita}")
    print(f"  Setelah filter relevansi   : {n_relevan}  <- data akhir")
    if n_relevan == 0:
        raise SystemExit("Tidak ada data tersisa. Longgarkan filter di bagian PENGATURAN.")
    print(f"  Rentang tanggal            : {df['tanggal'].min().date()} s/d {df['tanggal'].max().date()}")
 
    # Frekuensi kata kunci (jumlah tweet yang menyebut)
    hasil = {}
    for nama, pola in KATA_KUNCI.items():
        hasil[nama] = int(df["komentar"].str.contains(pola, case=False, regex=True).sum())
    # "setuju" murni = menyebut setuju tapi bukan "tidak setuju"
    ada_tidak = df["komentar"].str.contains(KATA_KUNCI["tidak setuju"], case=False, regex=True)
    ada_setuju = df["komentar"].str.contains(KATA_KUNCI["setuju"], case=False, regex=True)
    hasil["setuju"] = int((ada_setuju & ~ada_tidak).sum())
 
    tabel = (pd.Series(hasil, name="jumlah_tweet")
             .sort_values(ascending=False).rename_axis("kata_kunci").reset_index())
    tabel["persen"] = (tabel["jumlah_tweet"] / len(df) * 100).round(1)
    tabel.to_csv(os.path.join(FOLDER_OUTPUT, "frekuensi_kata_kunci.csv"),
                 index=False, encoding="utf-8-sig")
    print("\nFrekuensi kata kunci (jumlah tweet):")
    print(tabel.to_string(index=False))
 
    # Kata paling sering muncul
    semua = " ".join(df["komentar"].str.lower())
    kata = re.findall(r"[a-z]{3,}", semua)
    kata = [k for k in kata if k not in STOPWORDS]
    top = pd.Series(kata).value_counts().head(30).rename_axis("kata").reset_index(name="frekuensi")
    top.to_csv(os.path.join(FOLDER_OUTPUT, "kata_terbanyak.csv"), index=False, encoding="utf-8-sig")
    print("\n15 kata terbanyak:")
    print(top.head(15).to_string(index=False))
 
    print(f"\nSelesai. Semua hasil ada di folder '{FOLDER_OUTPUT}/'.")
 
 
if __name__ == "__main__":
    main()