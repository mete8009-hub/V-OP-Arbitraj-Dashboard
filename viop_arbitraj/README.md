# VİOP Arbitraj Dashboard

BIST 30 hisseleri için spot vs VİOP arbitraj getirisini canlı gösteren web dashboard. Excel'deki orijinal dashboard'un canlı veri ile çalışan versiyonu.

## ⚡ Hızlı Başlangıç (5 dakika)

```bash
# 1. Projeyi indir
git clone <repo-url> viop_arbitraj
cd viop_arbitraj

# 2. Sanal ortam kur
python3 -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate

# 3. Paketleri yükle
pip install -r requirements.txt

# 4. Çalıştır
streamlit run app.py
```

Tarayıcıda `http://localhost:8501` açılır.

---

## 📋 Proje Yapısı

```
viop_arbitraj/
├── app.py                  # Streamlit ana uygulama (UI + grafikler)
├── requirements.txt        # Python bağımlılıkları
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml        # Tema (Excel görünümü)
└── src/
    ├── __init__.py
    ├── config.py          # Hisse listesi, VİOP kodları, vade tarihleri
    ├── data_fetcher.py    # İş Yatırım'dan fiyat çekme
    ├── arbitrage.py       # Arbitraj getirisi hesaplama
    └── dividends.py       # Temettü takvimi
```

---

## 🔧 Detaylı Kurulum

### Adım 1 — Python ortamını hazırla

Python 3.10+ gerekli. Kontrol et:
```bash
python3 --version
```

### Adım 2 — Sanal ortam oluştur

```bash
cd viop_arbitraj
python3 -m venv venv
source venv/bin/activate
```

> **Windows kullanıcısı isen:** `venv\Scripts\activate`

### Adım 3 — Paketleri kur

```bash
pip install -r requirements.txt
```

Yüklenen paketler:
- `streamlit` — web framework
- `plotly` — bar chart'lar (Excel görünümünü taklit eder)
- `pandas` — veri işleme
- `requests` — HTTP istekleri
- `pytz` — İstanbul saati

### Adım 4 — Çalıştır

```bash
streamlit run app.py
```

Tarayıcıda `http://localhost:8501` otomatik açılır.

---

## 🌐 Yöneticine Sunmak İçin: Streamlit Cloud'a Deploy

**Avantajı:** Tek link verirsin, herkes tarayıcıdan açar. Ücretsiz.

### Adım 1 — GitHub'a yükle

```bash
cd viop_arbitraj
git init
git add .
git commit -m "İlk versiyon"

# GitHub'da yeni repo oluştur, sonra:
git remote add origin https://github.com/KULLANICI_ADIN/viop-arbitraj.git
git branch -M main
git push -u origin main
```

### Adım 2 — Streamlit Cloud'da deploy

1. https://share.streamlit.io adresine git
2. GitHub ile giriş yap
3. **"New app"** tıkla
4. Repo'yu seç, ana dosya: `app.py`
5. **"Deploy"** tıkla

3-5 dakikada uygulaman canlıya çıkar. Link örneği:
```
https://kullanici-adin-viop-arbitraj.streamlit.app
```

Bu linki yöneticine gönderirsin, açar.

---

## ⚙️ Yapılandırma

### Hisse listesini değiştir

`src/config.py` içindeki `BIST30_STOCKS` listesini düzenle.

### Yenileme aralığını değiştir

`src/config.py`:
```python
REFRESH_INTERVAL_SEC = 15  # Saniye - default 15
```

### Komisyon oranlarını değiştir

`src/config.py`:
```python
SPOT_COMMISSION_RATE = 0.0002  # %0.02
VIOP_COMMISSION_RATE = 0.0003  # %0.03
```

### Temettü takvimini güncelle

`src/dividends.py` içindeki `DIVIDEND_CALENDAR_2026` sözlüğünü düzenle:
```python
DIVIDEND_CALENDAR_2026 = {
    "AKBNK": {"amount": 5.50, "ex_date": date(2026, 5, 15)},
    # ...
}
```

---

## 🔍 Veri Akışı Nasıl Çalışıyor?

```
Tarayıcı (kullanıcı)
    ↓
Streamlit (app.py)
    ↓
@st.cache_data(ttl=15) → Cache 15 saniye geçerli
    ↓
DataFetcher.fetch_all_spot_prices()  → İş Yatırım /MarketData
DataFetcher.fetch_all_viop_prices()  → İş Yatırım /ViopMarketData
    ↓
calculate_arbitrage() — her hisse + her vade için
    ↓
Plotly bar charts + sağ panel tabloları
    ↓
Tarayıcı her 15 saniyede otomatik yeniler
```

**Neden 15 saniye?**
- İş Yatırım public API'sinde rate limit var (saniyelik istek izinli değil)
- Arbitraj getirisi DTM/365 ile yıllıklandığı için saniyelik fiyat değişimleri gösterilen orana çok az etki eder
- Excel'deki refresh süresine yakın

---

## ⚠️ Bilinen Sınırlamalar

1. **Saniyelik tick yok**: Profesyonel data feed (Foreks, Matriks, Algolab) gerekir. Bu sürüm 15sn polling.
2. **VİOP gece seansı**: 18:00-23:00 arası işlem oluyorsa fiyatlar İş Yatırım sitesinde geç güncellenebilir.
3. **Temettüler manuel**: İlk versiyonda `dividends.py` içine elle giriliyor. Fintables MCP entegrasyonu sonraki sürümde.
4. **Endpoint değişimi**: İş Yatırım sitesini yenilerse data_fetcher.py'deki URL'leri güncellemek gerekebilir.

---

## 🔧 Sorun Giderme

### "Veri kaynaklarına erişilemiyor" hatası

İş Yatırım public endpoint'leri bazen 403/timeout dönebilir. Çözümler:

**1. Tarayıcı network sekmesinden gerçek endpoint'i bul:**
- https://www.isyatirim.com.tr aç → herhangi bir hisseye tıkla
- F12 → Network sekmesi → `data.aspx` veya `MarketData` filtresi
- Çalışan URL'yi `src/data_fetcher.py` içindeki sabite kopyala

**2. Fallback olarak Mynet'e geçir:**
`data_fetcher.py` içinde `FallbackFetcher` sınıfı zaten hazır.

**3. User-Agent header'ı yenile:**
`HEADERS` sözlüğündeki Chrome sürümünü güncelle.

### Streamlit cache temizleme

Eğer eski veri yapışıp kaldıysa:
- Sağ üstteki "..." menü → **"Clear cache"**
- Veya terminal'de `Ctrl+C` → tekrar `streamlit run app.py`

### Port 8501 kullanımda

```bash
streamlit run app.py --server.port 8502
```

---

## 🚀 İleri Geliştirmeler (Yol Haritası)

**v2 — Fintables MCP entegrasyonu**
- Temettü verileri otomatik çekilir
- KAP haberleri sağ panelde gösterilir

**v3 — Profesyonel data feed**
- Algolab/Matriks WebSocket → saniyelik tick
- FastAPI backend + React frontend
- Postgres'e tarihsel veri kaydı

**v4 — Otomatik trade sinyali**
- Belirli bir getiri eşiği aşıldığında Telegram/Slack bildirimi
- Webhook ile broker entegrasyonu

---

## 📞 Destek

Sorun yaşarsan `data_fetcher.py` içindeki test fonksiyonunu çalıştır:
```bash
python -c "from src.data_fetcher import DataFetcher; f = DataFetcher(); print(f.fetch_all_spot_prices())"
```

Boş sözlük dönerse İş Yatırım endpoint'i değişmiş demektir.
