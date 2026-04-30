"""
Smoke test — Streamlit'i başlatmadan önce bunu çalıştır.

    python smoke_test.py

Bu script İş Yatırım endpoint'lerinin gerçekten çalışıp çalışmadığını test eder.
Eğer çalışmıyorsa, bana hatayı söyle, F12 ile gerçek URL'leri bulup düzeltirim.
"""
import sys
from src.data_fetcher import DataFetcher, DividendFetcher


def main():
    print("=" * 70)
    print("VİOP Arbitraj — Smoke Test")
    print("=" * 70)

    fetcher = DataFetcher()

    # Test 1: Spot fiyatlar
    print("\n[1/3] Spot fiyatlar test ediliyor...")
    spots = fetcher.fetch_all_spot_prices()
    print(f"     -> {len(spots)} hisse fiyatı çekildi.")
    if spots:
        for s in ["AKBNK", "GARAN", "THYAO"]:
            price = spots.get(s)
            if price:
                print(f"        {s}: {price:.2f} TL")
    else:
        print("     ❌ HATA: Spot fiyat çekilemedi!")
        print("     Bu, İş Yatırım'ın endpoint'inin değişmiş olabileceğini gösterir.")
        print("     Bir sonraki adıma geçemiyoruz, scripti durduruyorum.")
        sys.exit(1)

    # Test 2: VİOP fiyatları
    print("\n[2/3] VİOP fiyatları test ediliyor (örnek: AKBNK)...")
    viops = fetcher.fetch_viop_for_symbol("AKBNK")
    print(f"     -> {len(viops)} kontrat fiyatı çekildi.")
    for code, price in list(viops.items())[:5]:
        print(f"        {code}: {price:.2f} TL")
    if not viops:
        print("     ⚠️  UYARI: AKBNK için VİOP verisi gelmedi.")

    # Test 3: Temettü
    print("\n[3/3] Temettü scraping test ediliyor (örnek: AKBNK)...")
    div_fetcher = DividendFetcher()
    divs = div_fetcher.fetch_dividends("AKBNK")
    print(f"     -> {len(divs)} temettü kaydı bulundu.")
    if divs:
        for d in divs[:3]:
            print(f"        {d['ex_date']} -> {d['amount']:.4f} TL")
    else:
        print("     ⚠️  UYARI: AKBNK için temettü tablosu parse edilemedi.")
        print("        (Streamlit yine çalışır, sadece temettüler gözükmez.)")

    print("\n" + "=" * 70)
    print("✅ Smoke test tamamlandı.")
    print("Streamlit'i başlatmaya hazırsın:  streamlit run app.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
