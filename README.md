# Pazar Sepeti Analizi

Gökhan Kartal · 2645007017 · SEED **7017**

Kod deposu: https://github.com/gkhankartal/veri-madenciligi-pazar-sepeti

Online Retail II üzerinde Apriori, FP-Growth ve ECLAT ile sık ürün kümeleri ve
ilişki kuralları çıkarılır. Ayrı bir ürün varlığı tahmin görevinde CART ile
çoğunluk sınıfı baseline modeli karşılaştırılır.

## Ara rapor

[PDF](report/ara_rapor.pdf) · [LaTeX](report/ara_rapor.tex) ·
[Markdown](report/ara_rapor.md)

Rapor resmi IEEEtran konferans sınıfını kullanır. İçeriği dört, kaynakçası bir
sayfadır; özet 88 kelimedir. Veri, yöntemler, altı EDA görseli, ilk bulgular ve
beş hakemli kaynak raporda yer alır.

## Kurulum

Python 3.12 ve Windows için:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m unittest discover -p "test*.py" -v
```

## Yeniden üretim

```powershell
.venv/Scripts/python run_all.py --input "data/online_retail_II.xlsx" --tectonic "C:/path/tectonic.exe"
```

Girdi belirtilmezse resmi UCI arşivi `data/` dizinine indirilir. Tectonic 0.17,
resmi IEEEtran PDF'sinin derlenmesi içindir; ilk çalıştırmada TeX paketlerini ve
fontları indirebilir. Tectonic olmadan sayısal deneyler ve düzenlenebilir rapor
kaynakları üretilebilir; PDF'nin derleme durumu doğrulama çıktısında belirtilir.
Ara sonuçlar `results/`, yerel veri önbelleği `work/` altında tutulur. Ham veri,
önbellek ve sanal ortam Git deposuna dahil edilmez.

## Veri ve örnekleme

Veri: Chen, D. (2012), Online Retail II, UCI 502.
DOI: https://doi.org/10.24432/C5CG6D . Lisans: CC BY 4.0.
Kaynak: https://archive.ics.uci.edu/dataset/502/online+retail+ii

Ham verideki 53.628 benzersiz fatura kimliğinden `SEED=7017` ile yerine koymadan
50.000 seçilir. Seçilen faturaların bütün satırları korunur; ayrıca %80 örnekleme
yapılmaz. Seçimden sonra sayfalar arası örtüşme, iade/iptal kayıtları, pozitif
olmayan miktar/fiyatlar ve belirlenmiş işlem kodları ayıklanır. Sonuç 36.824
sepettir. Eksik müşteri kimliği, fatura bazlı görevde silme nedeni değildir.

## Deney tasarımı

- Bir fatura bir sepettir; ürün varlığı 0/1 kodlanır.
- Tarih sırasıyla 22.066 eğitim, 7.345 doğrulama ve 7.413 test faturası ayrılır.
  Tam takvim günleri ve faturalar farklı bölümlere parçalanmaz.
- Ürün sözlüğü, CART hedefi ve özellikler yalnızca eğitim verisinden belirlenir.
  Hedef ürün 85123A, tahmin girdilerinden çıkarılır.
- Ana madencilikte destek %2/%3/%5, maksimum küme uzunluğu 3'tür. Güven
  %20/%40/%60 ve lift >1/>2/>3 eşiğinde kural sayısı karşılaştırılır.
- Her destek ve algoritma için üç süre tekrarı yapılır. Aynı veri/eşiklerde
  ürün kümelerinin ve tam destek sayılarının eşitliği denetlenir.
- CART'ın 24 parametre birleşimi doğrulama F1 ile seçilir. Test dönemi daha
  önce incelendiğinden sonuçlar yeni kör dış doğrulama olarak sunulmaz.
- Ek analizler küme uzunluğu, sepet çıkarma duyarlılığı, aylık kural kararlılığı,
  gereksiz kuralların elenmesi ve bootstrap belirsizlik aralıklarını kapsar.
  Kategori etiketleri açıklamadan türetilmiş sezgisel etiketlerdir.

Ana politikada destek ≥%2, güven ≥%40 ve lift >1 ile 61 kural bulunur. CART
modelinin test F1 değeri yaklaşık 0,353; çoğunluk baseline F1 değeri sıfırdır.
Yüksek lift, nedensel satış artışı kanıtı olarak yorumlanmaz.

## Sonuç dosyaları

- `results/data_audit.json`: seçim, temizleme bilançosu ve tarih sınırları.
- `results/mining.json`, `association_rules.csv`: kurallar ve dönem metrikleri.
- `results/runtime_comparison.csv`, `threshold_sweep.csv`: süre ve eşik deneyleri.
- `results/cart.json`, `cart_metrics.csv`: CART ve baseline değerlendirmesi.
- `results/extended.json`: duyarlılık ve zaman kararlılığı deneyleri.
- `results/figures/`: PNG ve JPEG grafikler.
- `results/verification.json`: otomatik kontrol sonuçları.
- `literature.json`, `REFERENCES.bib`: makaleler ve veri kaynağı.
- `category_map.json`: açıklamaya dayalı kategori sözlüğü.

## Parametre denemesi

```powershell
.venv/Scripts/python demo.py --support 0.02
.venv/Scripts/python demo.py --support 0.03
```

Bu komutlar yalnızca eğitimi kullanır ve ana sonuç dosyalarını değiştirmez.
Mevcut örneklemde sırasıyla 61 ve 9 kural verir. `--confidence`, `--lift`,
`--max-len` ve `--cache` seçenekleri kullanılabilir.

## Kaynaklar

Algoritma ve kütüphane bağlantıları `SOURCES.md` dosyasındadır. IEEEtran sınıfının
özgün lisans başlığı korunmuştur. Ham veri atfı ve makale kaynakları raporda
ve BibTeX dosyasında verilmiştir.
