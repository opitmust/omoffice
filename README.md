# OmOffice

Python ve PySide6 ile yazılmış, Türkçe arayüzlü, `.docx` odaklı masaüstü belge düzenleyici.
Windows için geliştirilir. Çevrimdışı çalışır, ağ bağlantısı kurmaz ve belgelerdeki makroları çalıştırmaz.

> Microsoft ile bir bağlantısı yoktur; "Word" ve "Office", Microsoft'un ticari markalarıdır.

## Kurulum ve çalıştırma

1. [Python 3.12](https://www.python.org/downloads/) kurun ("Add python.exe to PATH" seçeneğini işaretleyin).
2. Depoyu indirin:
   ```
   git clone https://github.com/opitmust/omoffice.git
   ```
3. `OmOffice.bat` dosyasına çift tıklayın.

İlk çalıştırmada proje klasöründe `.venv` ortamı oluşturulur ve bağımlılıklar indirilir (yaklaşık 700 MB).
Sonraki açılışlarda bu adım atlanır; `requirements.txt` değişirse otomatik yenilenir.

Bir belgeyle açmak için: `OmOffice.bat belge.docx`

## Özellikler

- **Dosya:** `.docx` ve `.odt` açma ve kaydetme; `.html`, `.md`, `.txt` desteği; PDF'e aktarma ve yazdırma
- **Biçimlendirme:** stiller, listeler, tablolar, resimler, sayfa düzeni, filigran, sayfa rengi ve kenarlığı
- **Sayfa öğeleri:** sayfaya özel üst ve alt bilgi, dipnotlar, içindekiler, satır numaraları
- **Gözden geçirme:** değişiklik izleme, açıklamalar, Türkçe ve İngilizce yazım denetimi, sesli okuma
- **Akademik yazım:** tez, makale, rapor, dilekçe gibi türler için şablonlar ve bölüm rehberi; APA, IEEE ve MLA kaynakça biçimleri
- **Arayüz:** açık ve koyu tema, odak modu, komut paleti (`Alt+Q`)

## Veri güvenliği

- Kayıt önce geçici dosyaya yazılır ve doğrulanır; asıl dosya ancak kayıt tamamlanınca değişir.
- Değişiklikler düzenli aralıklarla kurtarma kopyasına yazılır, beklenmedik kapanıştan sonra geri getirilir.
- "Kaydetme" denilen belgelerin kopyası 7 gün saklanır.
- Kötü niyetli dosyalara karşı zip bombası, XXE, makro ve zararlı bağlantı denetimleri vardır.
- Kurtarma dosyaları ve hata günlüğü (`omoffice.log`) yalnızca bu bilgisayarda, `%APPDATA%\OmOffice` içinde durur.

## Bilinen sınırlar

- Henüz yok: sütunlar, metin kutuları ve şekiller, denklemler, belge karşılaştırma, `.doc` ve `.rtf` içe aktarma, yorum yanıtları, `.exe` paketi.
- Word yazı genişliklerini biraz farklı hesaplayabildiğinden uzun metinlerde satırlar farklı yerden kırılabilir.

Önemli belgelerde yedek tutmanız önerilir.

## Testler

Testler kendi geçici klasörlerinde çalışır; kullanıcının ayarlarına ve kurtarma dosyalarına dokunmaz.

```
.venv\Scripts\python tests\selftest.py
.venv\Scripts\python tests\security_test.py
```

Şu iki test için Microsoft Word kurulu olmalıdır:

```
.venv\Scripts\python tests\hf_test.py
.venv\Scripts\python tests\fidelity_test.py <çıktı_klasörü>
```

Test edilen ortam: Windows 11, Python 3.12.

## Lisans

Üçüncü taraf bileşenler için [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) dosyasına bakın.
