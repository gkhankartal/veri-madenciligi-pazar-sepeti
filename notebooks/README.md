# Notebook çalışması

Notebook'ları Python 3.12 ile aşağıdaki sırada, hücreleri baştan sona çalıştırarak kullanın:

1. `01_veri_ve_eda.ipynb`: ham faturaların örneklenmesi, temizlik, zaman bölümleri ve EDA.
2. `02_birliktelik_kurallari.ipynb`: Apriori, FP-Growth, ECLAT, eşik taraması ve dönem karşılaştırması.
3. `03_cart.ipynb`: ürün varlığı tahmini, doğrulama ile model seçimi ve çoğunluk temel modeli.
4. `04_ek_deneyler.ipynb`: sepet çıkarma, uzunluk duyarlılığı ve zamansal kararlılık.

Proje kökünde `python -m pip install -r requirements-notebooks.txt` komutuyla bağımlılıkları kurun. VS Code'da notebook dosyasını açıp bu Python ortamını kernel olarak seçebilirsiniz.

Online Retail II çalışma kitabını `data/online_retail_II.xlsx` konumuna yerleştirin. Resmî veri indirme komutu proje kökünde `python download_data.py --help` ile görülebilir. Farklı bir dosya yolu için `RETAIL_DATA_PATH` ortam değişkenini kullanın.

İlk notebook, SEED=7017 ile temizlikten önce 50.000 farklı faturayı seçer. Ayrıca %80 örnekleme yapılmaz. Temiz sepetler ve hesaplanan sonuçlar yerel `work/notebooks` dizinine yazılır; JPEG grafikler bunun `figures` alt dizinindedir. Bu dizin ve ham veri Git tarafından dışlanır. İstenirse `RETAIL_NOTEBOOK_WORK` ile başka bir çalışma dizini seçilebilir.

Her notebook ayrı bir kernel ile çalışabilir. İkinci notebook birincinin önbelleğine, dördüncü notebook ilk ikisinin çıktılarına ihtiyaç duyar. Rastgelelik SEED ile sabitlenir; çalışma süreleri bilgisayara göre değişir.

Mevcut Python betikleri, `results` dizini ve ara rapor korunmuştur. Notebook çalıştırmak bu dosyaların üzerine yazmaz. Yöntemler eşit parametrelerde aynı sık öğe kümelerini üretir; CART ayrı bir tahmin deneyidir. Test dönemi daha önce incelendiği için sonraki karşılaştırmalar keşifsel olarak değerlendirilir.
