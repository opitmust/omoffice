# Üçüncü taraf bileşenler

## Depoda bulunanlar

| Bileşen | Dosyalar | Kaynak | Lisans |
| --- | --- | --- | --- |
| Türkçe Hunspell sözlüğü | `omoffice/dicts/tr_TR.aff`, `tr_TR.dic` | [tdd-ai/hunspell-tr](https://github.com/tdd-ai/hunspell-tr) (değiştirilmedi) | MPL-2.0: [`licenses/tr_TR_MPL-2.0.txt`](omoffice/dicts/licenses/tr_TR_MPL-2.0.txt) |
| İngilizce Hunspell sözlüğü | `omoffice/dicts/en_US.aff`, `en_US.dic` | [LibreOffice/dictionaries](https://github.com/LibreOffice/dictionaries/tree/master/en) (değiştirilmedi) | SCOWL tabanlı: [`licenses/en_US_README.txt`](omoffice/dicts/licenses/en_US_README.txt) |

## Kurulum paketine dahil olanlar (depoda bulunmaz)

Kaynak koddan çalıştırırken `pip` ile kurulurlar. Lisans metinleri kurulu programın `licenses` klasöründedir.

| Paket | Lisans |
| --- | --- |
| [Python](https://www.python.org/) | PSF License |
| [PySide6](https://pypi.org/project/PySide6/) (Qt for Python) | LGPL-3.0 |
| [python-docx](https://pypi.org/project/python-docx/) | MIT |
| [lxml](https://pypi.org/project/lxml/) | BSD-3-Clause |
| [spylls](https://pypi.org/project/spylls/) | MPL-2.0 |
| [typing_extensions](https://pypi.org/project/typing-extensions/) | PSF License |
| [pdfminer.six](https://pypi.org/project/pdfminer.six/) | MIT |

Qt kitaplıkları ayrı DLL dosyaları olarak dağıtılır; LGPL kapsamında kurulu klasördeki Qt ve PySide6 dosyaları
uyumlu bir sürümle değiştirilebilir. PySide6 ve Qt'nin kaynak kodu: <https://code.qt.io/>
LGPL-3.0 metni kurulu programın `licenses/PySide6` klasöründedir. Qt'nin içinde kullandığı üçüncü taraf
kitaplıkların (FreeType, HarfBuzz, zlib, libpng vb.) lisansları: <https://doc.qt.io/qt-6/licenses-used-in-qt.html>

Kurulum paketi [PyInstaller](https://pyinstaller.org/) (önyükleyicisi GPL istisnasıyla) ve
[Inno Setup](https://jrsoftware.org/isinfo.php) ile üretilir.
