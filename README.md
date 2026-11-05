<p align="center"><img src="docs/logo.png" alt="OmOffice logosu" width="128"></p>

# OmOffice

Python ve PySide6 ile yazılmış, Türkçe arayüzlü, `.docx` odaklı masaüstü belge düzenleyici.
Windows için geliştirilir. Çevrimdışı çalışır, ağ bağlantısı kurmaz ve belgelerdeki makroları çalıştırmaz.

> Microsoft ile bir bağlantısı yoktur; "Word" ve "Office", Microsoft'un ticari markalarıdır.

## İndirme ve kurulum

1. [Releases](https://github.com/opitmust/omoffice/releases/latest) sayfasından `OmOffice-Setup-<sürüm>.exe` dosyasını indirin.
2. Çalıştırın. Python veya başka bir program gerekmez, yönetici izni istenmez.
3. Kurulum bitince OmOffice açılır.

Ücretsizdir. 64 bit Windows 10/11 içindir; yaklaşık 50 MB indirir, 185 MB yer kaplar.

**"Windows bilgisayarınızı korudu" uyarısı:** Kurulum dosyası henüz dijital olarak imzalanmadığı için çıkabilir.
**Ek bilgi › Yine de çalıştır** ile devam edebilirsiniz. Dosyanın değişmediğini doğrulamak için yanındaki `.sha256`
değerini karşılaştırın:

```
certutil -hashfile OmOffice-Setup-<sürüm>.exe SHA256
```

**Kaldırma:** Windows Ayarları › Uygulamalar › OmOffice › Kaldır. Kaydettiğiniz belgeler silinmez; ayarların ve
kurtarma kopyalarının da silinip silinmeyeceği sorulur.

OmOffice `.docx` dosyalarının varsayılan programını değiştirmez, yalnızca "Birlikte aç" listesine eklenir.

## Kaynak koddan çalıştırma

Geliştirme için [Python 3.12](https://www.python.org/downloads/) gerekir:

```
git clone https://github.com/opitmust/omoffice.git
cd omoffice
OmOffice.bat
```

İlk çalıştırmada `.venv` ortamı oluşturulur ve bağımlılıklar indirilir (yaklaşık 700 MB).

Kurulum dosyasını üretmek için [Inno Setup 6](https://jrsoftware.org/isinfo.php) ve `requirements-build.txt` gerekir:

```
python packaging\build.py
```

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

- Henüz yok: sütunlar, metin kutuları ve şekiller, denklemler, belge karşılaştırma, `.doc` ve `.rtf` içe aktarma, yorum yanıtları, otomatik güncelleme.
- Kurulum dosyası dijital olarak imzalı değildir.
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
