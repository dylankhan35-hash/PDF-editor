"""Quick check used by the cloud build: the app starts and can open a PDF."""
import os, sys, tempfile
import pymupdf
from PySide6.QtWidgets import QApplication
import app as A

path = os.path.join(tempfile.mkdtemp(), "t.pdf")
d = pymupdf.open(); d.new_page(); d.new_page(); d.save(path); d.close()
qa = QApplication([])
w = A.MainWindow(); w.show(); w.open_paths([path])
assert w.tab() is not None and w.tab().page_count() == 2
w.tab().rotate(90); w.tab().undo()
print("smoke test OK"); sys.exit(0)
