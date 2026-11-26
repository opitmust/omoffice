# PyInstaller tanımı. Doğrudan değil, packaging/build.py üzerinden çalıştırın.
# OMOFFICE_BUILD_TARGET: app (varsayılan) ya da donmuş ortamda çalışacak bir test betiğinin adı.
import os
import sys

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

ROOT = os.path.dirname(SPECPATH)
sys.path.insert(0, ROOT)
TARGET = os.environ.get("OMOFFICE_BUILD_TARGET", "app")
IS_APP = TARGET == "app"
VERSION = os.environ["OMOFFICE_VERSION"]
ICON = os.path.join(ROOT, "omoffice", "omoffice.ico")

parts = tuple(int(x) for x in VERSION.split(".")) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=parts, prodvers=parts),
    kids=[
        StringFileInfo([StringTable("041F04B0", [
            StringStruct("CompanyName", "OmOffice"),
            StringStruct("FileDescription", "OmOffice belge düzenleyici"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", "OmOffice"),
            StringStruct("OriginalFilename", "OmOffice.exe"),
            StringStruct("ProductName", "OmOffice"),
            StringStruct("ProductVersion", VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x041F, 0x04B0])]),
    ],
)

entry = os.path.join(ROOT, "packaging", "entry.py") if IS_APP else os.path.join(ROOT, "tests", TARGET + ".py")
name = "OmOffice" if IS_APP else TARGET

a = Analysis(
    [entry],
    pathex=[ROOT],
    datas=[
        (os.path.join(ROOT, "omoffice", "dicts"), os.path.join("omoffice", "dicts")),
        (ICON, "omoffice"),
        (os.path.join(ROOT, "omoffice", "omoffice.png"), "omoffice"),
    ] + collect_data_files("docx") + collect_data_files("pdfminer"),  # pdfminer: CMap tabloları
    hiddenimports=["PySide6.QtPdf"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick"],
)
# Qt'nin TLS eklentileri kullanılmaz (güncelleme denetimi Python'un kendi ssl modülünü kullanır). Pakette
# kalırlarsa PyInstaller, OpenSSL'i derleme bilgisayarının PATH'inden (ör. Git for Windows) toplar; sürümü
# denetlenmeyen başka bir programın DLL'leri dağıtılmış olur.
_NO_QT_TLS = ("libssl-3-x64.dll", "libcrypto-3-x64.dll")
a.binaries = [b for b in a.binaries
              if not b[0].replace("\\", "/").lower().startswith("pyside6/plugins/tls/")
              and os.path.basename(b[0]).lower() not in _NO_QT_TLS]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=name,
    icon=ICON,
    version=version_info,
    console=not IS_APP,  # testler sonucu konsola yazar
    upx=False,           # UPX antivirüslerde yanlış alarma yol açar
)
coll = COLLECT(exe, a.binaries, a.datas, name=name, upx=False)
