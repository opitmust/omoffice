<p align="center"><img src="docs/logo.png" alt="OmOffice logosu" width="128"></p>

# OmOffice

<p align="center"><b><a href="https://github.com/opitmust/omoffice/releases/latest">⬇ OmOffice'i indir (Windows kurulum dosyası)</a></b><br>
<sub>Açılan sayfada <b>Assets</b> bölümündeki <code>OmOffice-Setup-…exe</code> dosyasını indirin.</sub></p>

Python ve PySide6 ile yazılmış, Türkçe arayüzlü, `.docx` odaklı masaüstü belge düzenleyici.
Windows için geliştirilir. Çevrimdışı çalışır, belgelerdeki makroları çalıştırmaz; izin verdiğiniz isteğe bağlı
güncelleme denetimi dışında ağ bağlantısı kurmaz.

> Microsoft ile bir bağlantısı yoktur; "Word" ve "Office", Microsoft'un ticari markalarıdır.

## İndirme ve kurulum

1. [Releases](https://github.com/opitmust/omoffice/releases/latest) sayfasında **Assets** bölümünden
   `OmOffice-Setup-<sürüm>.exe` dosyasını indirin. ("Source code (zip)" kaynak koddur, kurulum dosyası değildir.)
2. Çalıştırın. Python veya başka bir program gerekmez, yönetici izni istenmez.
3. Kurulum bitince OmOffice açılır.

Ücretsizdir. 64 bit Windows 10 (1809) ve 11 içindir; yaklaşık 60 MB indirir, 210 MB yer kaplar.

> **Yalnızca bu sayfadan indirin.** OmOffice'in resmî tek kaynağı bu deponun
> [Releases](https://github.com/opitmust/omoffice/releases) sayfasıdır. Başka sitelerdeki kopyalar değiştirilmiş
> olabilir.

**Dosyayı doğrulama:** Her kurulum dosyasının yanında bir `.sha256` dosyası vardır. İndirdiğiniz dosyanın
değiştirilmediğini görmek için, dosyanın bulunduğu klasörde komut istemine şunu yazın ve çıkan değeri `.sha256`
dosyasındaki değerle karşılaştırın; tek bir karakter bile farklıysa dosyayı çalıştırmayın:

```
certutil -hashfile OmOffice-Setup-<sürüm>.exe SHA256
```

**"Windows bilgisayarınızı korudu" uyarısı:** Kurulum dosyası henüz dijital olarak imzalanmadığı için çıkabilir.
Dosyayı doğruladıysanız **Ek bilgi › Yine de çalıştır** ile devam edebilirsiniz.

**Antivirüs uyarısı:** Python ile paketlenmiş programlar bazı antivirüslerce yanlışlıkla şüpheli işaretlenebilir.
Emin olmak için dosyayı [VirusTotal](https://www.virustotal.com/)'e yükleyip sonucuna bakabilirsiniz.

**Güncelleme:** Eski sürümü kaldırmanız gerekmez. Yeni sürümün kurulum dosyasını indirip çalıştırın; mevcut
kurulumun üzerine kurulur, ayarlarınız ve belgeleriniz korunur. Program açıksa kurulum kapatmayı önerir.


**Yeni sürüm bildirimi (1.1.0 ve sonrası):** OmOffice ilk açılışta yeni sürümlerden haberdar edilmek isteyip
istemediğinizi sorar. İzin verirseniz yeni sürüm çıktığında durum çubuğunda **Yeni sürüm** düğmesi belirir;
tıklayınca indirme sayfası açılır. Program kendiliğinden hiçbir şey indirmez veya kurmaz. Elle denetlemek ya da
ayarı değiştirmek için: **Dosya › Güncellemeleri Denetle** ve **Dosya › Açılışta Güncellemeleri Denetle**.
GitHub'da **Watch › Custom › Releases** seçeneğiyle de yeni sürümlerden haberdar olabilirsiniz.

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

## Güvenlik ve gizlilik

**Gizlilik**

- OmOffice veri toplamaz, kullanım istatistiği göndermez, hesap istemez.
- Tek ağ bağlantısı isteğe bağlı güncelleme denetimidir ve yalnızca siz izin verirseniz yapılır: günde en fazla
  bir kez GitHub'dan (`api.github.com`) en son sürümün numarası sorulur. İstekte belge, ad, sürüm ya da başka
  kişisel bilgi gönderilmez. İzin vermezseniz OmOffice hiç ağa çıkmaz.
- Belgeleriniz yalnızca sizin seçtiğiniz yere kaydedilir. Kurtarma dosyaları ve hata günlüğü (`omoffice.log`)
  yalnızca bu bilgisayarda, `%APPDATA%\OmOffice` içinde durur.
- Belgelerdeki uzak resimler ve ağ yolları yüklenmez; böylece bir belgeyi açtığınız dışarıya haber verilmez.

**Bilgisayarınızın güvenliği**

- Yönetici izni istemez; yalnızca sizin kullanıcı klasörünüze kurulur, sistem ayarlarını değiştirmez.
- Belgelerdeki makroları, betikleri ve gömülü programları çalıştırmaz.
- Kötü niyetli dosyalara karşı denetimler vardır: bilgisayardaki dosyaları okumaya çalışan belgeler (XXE),
  programı kilitlemeye çalışan dosya bombaları (zip bombası, "milyar kahkaha"), bozuk ve sahte dosyalar,
  zararlı bağlantılar. Bunlar her sürümde `tests\security_test.py` ile sınanır.
- Kaynak kodu açıktır; programın ne yaptığını herkes inceleyebilir.

**Belgelerinizin güvenliği**

- Kayıt önce geçici dosyaya yazılır ve doğrulanır; asıl dosya ancak kayıt tamamlanınca değişir.
- Değişiklikler düzenli aralıklarla kurtarma kopyasına yazılır, beklenmedik kapanıştan sonra geri getirilir.
- "Kaydetme" denilen belgelerin kopyası 7 gün saklanır.

**Güvenlik açığı bildirme:** Bir güvenlik açığı bulursanız lütfen herkese açık Issues yerine bu deponun
**Security › Report a vulnerability** bölümünden gizli olarak bildirin.

## Bilinen sınırlar

- Henüz yok: sütunlar, metin kutuları ve şekiller, denklemler, belge karşılaştırma, `.doc` ve `.rtf` içe aktarma, yorum yanıtları, güncellemeyi kendiliğinden indirip kurma (yeni sürüm yalnızca bildirilir).
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

Copyright (C) 2026 Ömer Faruk

OmOffice özgür yazılımdır: [GNU Genel Kamu Lisansı sürüm 3](LICENSE) ya da (isteğinize bağlı olarak)
sonraki herhangi bir sürümü koşullarıyla kullanabilir, değiştirebilir ve dağıtabilirsiniz. Değiştirilmiş
sürümleri dağıtanlar kaynak kodunu da aynı lisansla açmalıdır. Program hiçbir garanti olmaksızın sunulur.

Üçüncü taraf bileşenler için [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) dosyasına bakın.
