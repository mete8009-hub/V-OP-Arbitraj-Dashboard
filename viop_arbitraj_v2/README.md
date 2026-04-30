# VİOP Arbitraj Dashboard (v2)

BIST hisseleri için spot vs VİOP arbitraj getirisini canlı gösteren web dashboard.

**v2'de yeni:**
- ✅ Temettüler artık **otomatik** İş Yatırım'dan çekiliyor (manuel giriş yok)
- ✅ Streamlit Cloud "in the oven" sorunu çözüldü (`streamlit-autorefresh` kullanımı)
- ✅ `requirements.txt` flexible versiyonlar (Python 3.13 uyumlu)
- ✅ Smoke test scripti — ilk çalıştırmada her şeyin OK olduğunu görürsün

---

## ⚡ 5 Dakikada Aya Kaldır

### 1. Sanal ortam + paketler
```bash
cd viop_arbitraj_v2
python3 -m venv venv
source venv/bin/activate              # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. ÖNCE smoke test çalıştır (kritik!)
```bash
python smoke_test.py
```

Çıktı şuna benzemeli:
```
[1/3] Spot fiyatlar test ediliyor...
     -> 280 hisse fiyatı çekildi.
        AKBNK: 73.10 TL
        GARAN: 132.00 TL
        THYAO: 310.00 TL

[2/3] VİOP fiyatları test ediliyor (örnek: AKBNK)...
     -> 3 kontrat fiyatı çekildi.
        F_AKBNK0426: 73.45 TL
        F_AKBNK0526: 75.34 TL
        F_AKBNK0626: 76.80 TL

[3/3] Temettü scraping test ediliyor (örnek: AKBNK)...
     -> 12 temettü kaydı bulundu.

✅ Smoke test tamamlandı.
```

**Bu çalışıyorsa Streamlit %100 çalışır.** Çalışmıyorsa "Sorun Giderme" bölümüne bak.

### 3. Streamlit'i başlat
```bash
streamlit run app.py
```

Tarayıcıda `http://localhost:8501` otomatik açılır.

---

## 🌐 Streamlit Cloud Deploy (Yöneticine link vermek için)

### 1. GitHub'a yükle
```bash
cd viop_arbitraj_v2
git init
git add .
git commit -m "VİOP Arbitraj Dashboard v2"
git branch -M main
# GitHub'da yeni public/private repo aç, sonra:
git remote add origin https://github.com/KULLANICI_ADIN/viop-arbitraj.git
git push -u origin main
```

### 2. Streamlit Cloud'da deploy
1. https://share.streamlit.io/ → GitHub ile giriş
2. **"New app"**
3. Repo seç, branch: `main`, ana dosya: `app.py`
4. **Deploy** butonu

⏱️ İlk deploy ~2 dakika. **"In the oven" sorunu olmaz** çünkü `streamlit-autorefresh` kullanıyoruz, `meta refresh` değil.

3-5 dakika sonra link gelir:
```
https://kullanici-adin-viop-arbitraj.streamlit.app/
```

Bu linki yöneticinle paylaş.

---

## 📋 Proje Yapısı

```
viop_arbitraj_v2/
├── app.py                 # Streamlit ana dosya
├── smoke_test.py         # Endpoint sağlık kontrolü
├── requirements.txt      # Python paketleri
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml       # Tema
└── src/
    ├── __init__.py
    ├── config.py         # Hisse listesi, vade tarihleri
    ├── data_fetcher.py   # Spot + VİOP + Temettü scraping
    └── arbitrage.py      # Arbitraj formülü
```

---

## 🔧 Yapılandırma

### Hisse listesini değiştir
`src/config.py` → `DASHBOARD_STOCKS` listesi.

### Yenileme aralığı
`src/config.py` → `REFRESH_INTERVAL_SEC = 15`

### Temettü cache süresi
`src/config.py` → `DIVIDEND_CACHE_TTL_SEC = 3600` (1 saat — temettüler sürekli değişmez)

### Komisyon oranları
`src/config.py` → `SPOT_COMMISSION_RATE`, `VIOP_COMMISSION_RATE`

---

## 🐛 Sorun Giderme

### "Smoke test çalışmıyor" / "0 hisse fiyatı"

İş Yatırım endpoint'i bazen 403 dönebilir. Çözümler:

**1. User-Agent güncelle** (en yaygın çözüm):
`src/data_fetcher.py` → `DEFAULT_HEADERS` içindeki Chrome sürümünü Chrome'unun güncel sürümüne yükselt.

**2. Endpoint'i F12 ile yenile:**
- https://www.isyatirim.com.tr/tr-tr/Sayfalar/default.aspx → herhangi bir hisseye tıkla
- F12 → **Network** sekmesi → "Fetch/XHR" filtresi
- `data.aspx` veya `IndexHisseSenedi` aramasını yap
- Çalışan URL'yi `src/data_fetcher.py` içindeki sabite kopyala

**3. Bu hatayı bana söyle**, gerçek URL'leri 5 dakikada güncelleyebilirim.

### "Streamlit Cloud 'in the oven' takılıyor"

v2'de bu çözüldü. Ama yine olursa:
- GitHub repo branch'i `main` olmalı (`master` değil)
- `requirements.txt` exact versiyon (`==`) yerine `>=` kullanmalı (zaten öyle)
- Streamlit Cloud → **Manage app → Reboot**

### "Temettüler boş görünüyor"

Bu normal olabilir — yakın zamanda temettü ödenmemiş hisselere "No DIV" düşer. Smoke test'te AKBNK için temettü kaydı çıkıyorsa scraping çalışıyor demektir.

### Cache temizleme

Eski veri yapışıp kaldıysa:
- Streamlit sağ üst "**...**" → **Clear cache** → **Rerun**

---

## 📊 Veri Akışı

```
Tarayıcı (kullanıcı)
   ↓
Streamlit (15sn'de auto-refresh) ← streamlit-autorefresh
   ↓
@st.cache_data(ttl=15) → Spot + VİOP fiyatları
@st.cache_data(ttl=3600) → Temettü (1 saatte bir)
   ↓
İş Yatırım public ajax endpoint'leri
   ↓
calculate_arbitrage() → her hisse + her vade
   ↓
Plotly bar chart + sağ panel istatistikler
```

---

## ⚠️ Bilinen Sınırlamalar

1. **Saniyelik tick yok** — 15sn polling. Profesyonel data feed (Foreks/Matriks) gerekir gerçek tick için.
2. **VİOP gece seansı** (18:00-23:00) İş Yatırım sayfasında bazen geç güncellenebilir.
3. **Temettü tablosu HTML parsing** — İş Yatırım sayfa yapısını değiştirirse parser güncellenmeli.

---

## 🚀 İleri Geliştirmeler

- **v3**: Algolab/Matriks WebSocket → saniyelik tick + alarm sistemi
- **v4**: Belirli arbitraj eşiği aşılınca Telegram bildirimi
- **v5**: Postgres'e tarihsel kayıt + geriye dönük analiz

---

## ❓ Yardım

Smoke test çıktısını çalıştırıp bana paylaşırsan, herhangi bir endpoint sorununu 5 dakikada çözeriz.
