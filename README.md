
# AYÇA Nöbet — Grup Simülasyonu

Bu proje, AYÇA Nöbet algoritmasının grup, mesafe, minimum nöbet aralığı ve geçmiş yük mantığını interaktif bir şehir haritası üzerinde göstermek için hazırlanmış Streamlit demosudur.

## Özellikler

- 104 sentetik eczane ve 16 alt grup
- 8 günlük grup kombinasyonu
- Gün bazlı aktif grup gösterimi
- Bir gruptan eczane seçildiğinde diğer gruplardaki uygun adayların yeniden hesaplanması
- Minimum mesafe kuralı
- Minimum nöbet aralığı kuralı
- Geçmiş yük, hafta sonu ve bayram yüküne göre karar skoru
- Otomatik günlük seçim
- PyDeck tabanlı interaktif şehir haritası

## Yerelde çalıştırma

```bash
pip install -r requirements.txt
streamlit run app.py
```

## GitHub + Streamlit Community Cloud

1. Bu klasördeki dosyaları yeni bir GitHub repository'sine yükleyin.
2. Streamlit Community Cloud üzerinde `New app` seçin.
3. Repository'yi ve `app.py` dosyasını seçin.
4. Deploy edin.

## Önemli not

Bu sürüm demo amacıyla sentetik koordinatlar kullanır. Gerçek kurulumda `pharmacies.csv` dosyası oda tarafından sağlanan eczane, grup ve koordinat verileriyle değiştirilir.
