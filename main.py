import os
import re
from datetime import datetime
from html.parser import HTMLParser
from html import unescape
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OUTPUT_DIR = "output"
BASE_URL = "https://www.tjk.org/TR/YarisSever/Info/Page/GunlukYarisSonuclari"


class VisibleTextExtractor(HTMLParser):
    """HTML içinden script/style hariç görünür metni toplar."""

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self.parts.append(text)


def tarih_dogrula(tarih_text):
    try:
        datetime.strptime(tarih_text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Tarih formatı YYYY-MM-DD olmalı.") from exc


def sehir_norm(sehir):
    temiz = sehir.strip()
    if not temiz:
        raise ValueError("Şehir boş olamaz.")
    return temiz


def url_olustur(tarih, sehir):
    """TJK sonuç sayfası için olası query parametreleri."""
    tarih_tr = datetime.strptime(tarih, "%Y-%m-%d").strftime("%d.%m.%Y")

    query_sets = [
        {"QueryParameter_Tarih": tarih_tr, "QueryParameter_Sehir": sehir},
        {"QueryParameter_Tarih": tarih_tr, "QueryParameter_SehirAdi": sehir},
        {"Tarih": tarih_tr, "Sehir": sehir},
    ]

    return [f"{BASE_URL}?{urlencode(params)}" for params in query_sets]


def sayfa_indir(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def satir_temizle(line):
    line = unescape(line)
    line = re.sub(r"\s+", " ", line).strip()
    if not line:
        return ""

    gereksiz_kelimeler = [
        "ANA SAYFA",
        "YARIŞSEVER",
        "KURUMSAL",
        "İLETİŞİM",
        "KVKK",
        "ÇEREZ",
        "REKLAM",
        "YASAL UYARI",
    ]
    upper_line = line.upper()
    if any(kelime in upper_line for kelime in gereksiz_kelimeler):
        return ""
    return line


def html_parse_ile_sonuclar(html):
    """Öncelikli yöntem: sonuç metnini HTML bloklarından ayıklama."""
    patterns = [
        re.compile(r"<(div|section)[^>]*(?:result|sonuc|sonuclar|race)[^>]*>(.*?)</\\1>", re.I | re.S),
        re.compile(r"<(table)[^>]*(?:result|sonuc|sonuclar|race)[^>]*>(.*?)</\\1>", re.I | re.S),
    ]

    bloklar = []
    for pattern in patterns:
        for eslesme in pattern.finditer(html):
            ham = re.sub(r"<[^>]+>", "\n", eslesme.group(2))
            satirlar = [satir_temizle(s) for s in ham.splitlines()]
            temiz = [s for s in satirlar if s]
            if len(temiz) >= 8:
                bloklar.extend(temiz)

    if not bloklar:
        return []

    return satirlardan_kosulari_ayir(bloklar)


def fallback_gorunur_metin(html):
    """Fallback: tüm görünür metni alıp filtreleme."""
    parser = VisibleTextExtractor()
    parser.feed(html)

    satirlar = [satir_temizle(s) for s in parser.parts]
    satirlar = [s for s in satirlar if s]

    anahtarlar = ("Koşu", "KOŞU", "AGF", "GANYAN", "Sıra", "Fark")
    odak = [s for s in satirlar if any(a in s for a in anahtarlar)]

    hedef = odak if len(odak) >= 8 else satirlar
    return satirlardan_kosulari_ayir(hedef)


def satirlardan_kosulari_ayir(satirlar):
    """Koşu başlıklarına göre bölümlendirir."""
    kosu_re = re.compile(r"^(\d{1,2})\s*[\.|\-|)]?\s*Koşu", re.I)

    kosular = []
    aktif_baslik = "Genel"
    aktif_satirlar = []

    for satir in satirlar:
        eslesme = kosu_re.search(satir)
        if eslesme:
            if aktif_satirlar:
                kosular.append((aktif_baslik, aktif_satirlar))
            aktif_baslik = f"{eslesme.group(1)}. Koşu"
            aktif_satirlar = [satir]
        else:
            aktif_satirlar.append(satir)

    if aktif_satirlar:
        kosular.append((aktif_baslik, aktif_satirlar))

    return kosular


def markdown_uret(tarih, sehir, kosular, kaynak_url):
    lines = [f"# {tarih} - {sehir} Yarış Sonuçları", "", f"Kaynak: {kaynak_url}", ""]

    for baslik, satirlar in kosular:
        lines.append(f"## {baslik}")
        lines.append("")
        for satir in satirlar:
            lines.append(f"- {satir}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def dosya_adi_olustur(tarih, sehir):
    sehir_guvenli = re.sub(r"[^A-Za-z0-9çğıöşüÇĞİÖŞÜ]+", "", sehir.title())
    return f"{tarih}_{sehir_guvenli}_sonuclar.md"


def main():
    print("TJK Yarış Sonuçları Markdown Çıkarıcı")

    tarih = input("Tarih (YYYY-MM-DD): ").strip()
    sehir = input("Şehir: ").strip()

    try:
        tarih_dogrula(tarih)
        sehir = sehir_norm(sehir)
    except ValueError as err:
        print(f"Hata: {err}")
        return

    urls = url_olustur(tarih, sehir)

    html = ""
    secilen_url = ""
    for url in urls:
        try:
            html = sayfa_indir(url)
            if "Koşu" in html or "SONUÇ" in html.upper():
                secilen_url = url
                break
        except Exception:
            continue

    if not html:
        print("Sonuç sayfası indirilemedi.")
        return

    kosular = html_parse_ile_sonuclar(html)
    if not kosular:
        kosular = fallback_gorunur_metin(html)

    if not kosular:
        print("Sayfadan sonuç metni çıkarılamadı.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, dosya_adi_olustur(tarih, sehir))

    icerik = markdown_uret(tarih, sehir, kosular, secilen_url or urls[0])
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(icerik)

    print(f"Tamamlandı: {out_path}")


if __name__ == "__main__":
    main()
