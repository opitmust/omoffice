"""Kurulum dosyasını üretir: python packaging/build.py [--tests]

Çıktı: dist/OmOffice-Setup-<sürüm>.exe ve yanında .sha256 dosyası.
--tests: testleri paketlenmiş ortamda çalışacak şekilde build/test-dist altına derler.
Gerekli: requirements-build.txt ve Inno Setup 6.
"""
import hashlib
import importlib.metadata as md
import os
import re
import shutil
import subprocess  # nosec B404 - yalnızca derleme araçlarını çalıştırır
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "packaging", "omoffice.spec")
# Qt for Python tekerlekleri yalnızca ticari lisans başvurusunu taşır; OmOffice Qt'yi LGPL-3.0 ile kullanır
QT_PACKAGES = {"PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6"}
PACKAGES = ["PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "python-docx", "lxml", "spylls",
            "typing_extensions", "pdfminer.six", "pyinstaller"]


def version():
    with open(os.path.join(ROOT, "omoffice", "__init__.py"), encoding="utf-8") as f:
        return re.search(r'__version__ = "([\d.]+)"', f.read()).group(1)


def pyinstaller(target, distpath):
    env = dict(os.environ, OMOFFICE_BUILD_TARGET=target, OMOFFICE_VERSION=version())
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",  # nosec
                    "--distpath", distpath, "--workpath", os.path.join(ROOT, "build", target), SPEC],
                   check=True, cwd=ROOT, env=env)


def copy_licenses(app_dir):
    """Dağıtılan her bileşenin lisans metni programla birlikte gider."""
    out = os.path.join(app_dir, "licenses")
    os.makedirs(out, exist_ok=True)
    shutil.copy(os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"), app_dir)
    shutil.copy(os.path.join(ROOT, "LICENSE"), os.path.join(app_dir, "LICENSE.txt"))
    shutil.copy(os.path.join(sys.base_prefix, "LICENSE.txt"), os.path.join(out, "Python-LICENSE.txt"))
    shutil.copytree(os.path.join(ROOT, "omoffice", "dicts", "licenses"), os.path.join(out, "sozlukler"),
                    dirs_exist_ok=True)
    for name in PACKAGES:
        if name in QT_PACKAGES:
            os.makedirs(os.path.join(out, name), exist_ok=True)
            shutil.copy(os.path.join(ROOT, "packaging", "licenses", "LGPL-3.0.txt"), os.path.join(out, name))
            shutil.copy(os.path.join(ROOT, "LICENSE"), os.path.join(out, name, "GPL-3.0.txt"))  # LGPL buna dayanır
            continue
        dist = md.distribution(name)
        files = [f for f in dist.files or [] if re.search(r"(^|/|\.)(LICEN[CS]E|COPYING|NOTICE)", str(f), re.I)
                 and ".dist-info" in str(f)]
        if not files:
            sys.exit(f"Lisans dosyası bulunamadı: {name}")
        for f in files:
            target = os.path.join(out, name, os.path.basename(str(f)))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy(dist.locate_file(f), target)


def find_iscc():
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        for sub in (os.path.join("Programs", "Inno Setup 6"), "Inno Setup 6"):
            path = os.path.join(base or "", sub, "ISCC.exe")
            if os.path.exists(path):
                return path
    sys.exit("Inno Setup 6 bulunamadı (winget install JRSoftware.InnoSetup)")


def main():
    if "--tests" in sys.argv:
        for target in ("selftest", "security_test"):
            pyinstaller(target, os.path.join(ROOT, "build", "test-dist"))
        return
    iscc = find_iscc()
    dist = os.path.join(ROOT, "dist")
    shutil.rmtree(dist, ignore_errors=True)
    pyinstaller("app", dist)
    copy_licenses(os.path.join(dist, "OmOffice"))
    ver = version()
    subprocess.run([iscc, "/Qp", f"/DAppVersion={ver}", os.path.join(ROOT, "packaging", "installer.iss")],  # nosec
                   check=True)
    setup = os.path.join(dist, f"OmOffice-Setup-{ver}.exe")
    digest = hashlib.sha256()
    with open(setup, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    with open(setup + ".sha256", "w", encoding="ascii", newline="\n") as f:
        f.write(f"{digest.hexdigest()}  {os.path.basename(setup)}\n")
    print(setup, f"{os.path.getsize(setup) / 1e6:.0f} MB", digest.hexdigest())


if __name__ == "__main__":
    main()
