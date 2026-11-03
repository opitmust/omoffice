import logging
import logging.handlers
import os
import sys
import traceback


def _setup_log():
    """Konsolsuz (pythonw) çalışırken hatalar kaybolmasın. Günlük yalnızca bu bilgisayarda kalır."""
    base = os.environ.get("OMOFFICE_TEST_DATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "OmOffice")
    path = os.path.join(folder, "omoffice.log")
    try:
        os.makedirs(folder, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    except OSError:
        return path
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("omoffice")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return path


def _report_fatal(log_path):
    """Qt yüklenememiş olabilir; bu yüzden pencereyi doğrudan Windows'a açtırır."""
    logging.getLogger("omoffice").critical("Program başlatılamadı\n%s", traceback.format_exc())
    text = f"OmOffice başlatılamadı.\n\n{traceback.format_exc(limit=1)}\nAyrıntılar: {log_path}"
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "OmOffice", 0x10)
    except (ImportError, AttributeError, OSError):
        print(text, file=sys.stderr)


def main():
    log_path = _setup_log()
    try:
        from PySide6.QtGui import QFont, QImageReader
        from PySide6.QtWidgets import QApplication

        from .common import APP_NAME, APP_ORG
        from .mainwindow import MainWindow, glyph

        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setOrganizationName(APP_ORG)
        app.setStyle("Fusion")
        app.setFont(QFont("Segoe UI", 9))
        QImageReader.setAllocationLimit(256)  # MB; dev boyutlu kötü niyetli resimlere karşı
        app.setWindowIcon(glyph("", color="#2F5DA8", size=64, scale=0.7))
        win = MainWindow(sys.argv[1] if len(sys.argv) > 1 else None)
    except Exception:
        _report_fatal(log_path)
        return 1
    # Beklenmeyen hata programı kapatmasın; belge kurtarma kopyasına yazılsın
    sys.excepthook = win.on_crash
    # Windows oturumu kapanırken de kurtarma kopyası al
    app.commitDataRequest.connect(lambda _m: win._autosave(force=True))
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
