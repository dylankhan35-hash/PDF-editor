"""
PDF Editor - a free, offline PDF editor for Windows (works on Mac/Linux too).

Phase 1: app shell, tabbed viewer, thumbnails, and page tools
(rotate, delete, reorder, merge, extract, split, undo, save).

License: AGPL-3.0 (required because of PyMuPDF). Keep the source public.
"""
import bisect
import os
import sys
from collections import OrderedDict
from pathlib import Path

import pymupdf
from PySide6.QtCore import QItemSelectionModel, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QImage, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "PDF Editor"
GAP = 12                      # space between pages (px)
MIN_ZOOM, MAX_ZOOM = 0.1, 6.0
THUMB_W, THUMB_H = 100, 140
UNDO_LIMIT = 8
PDF_FILTER = "PDF files (*.pdf)"


# --------------------------------------------------------------------------
# Viewer: continuous-scroll page view that renders only what is visible
# --------------------------------------------------------------------------
class PageView(QAbstractScrollArea):
    pageChanged = Signal(int)
    zoomChanged = Signal(float)

    def __init__(self):
        super().__init__()
        self.doc = None
        self.zoom = 1.0
        self.current = 0
        self._cache = OrderedDict()
        self._tops = []
        self._sizes = []
        self._total = 0
        self._content_w = 0
        self.setFocusPolicy(Qt.StrongFocus)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.viewport().update())

    # -- document / layout -------------------------------------------------
    def set_document(self, doc):
        self.doc = doc
        self.current = 0
        self.refresh(keep_ratio=False)

    def refresh(self, keep_ratio=True):
        """Re-render everything (after zoom, rotation, page changes)."""
        self._cache.clear()
        vbar = self.verticalScrollBar()
        ratio = vbar.value() / vbar.maximum() if keep_ratio and vbar.maximum() > 0 else 0.0
        self._tops, self._sizes = [], []
        y = GAP
        if self.doc is not None:
            for page in self.doc:
                r = page.rect
                w, h = max(1, int(r.width * self.zoom)), max(1, int(r.height * self.zoom))
                self._tops.append(y)
                self._sizes.append((w, h))
                y += h + GAP
        self._total = y
        self._update_bars()
        vbar.setValue(int(ratio * vbar.maximum()))
        self.viewport().update()

    def _update_bars(self):
        vp = self.viewport().size()
        max_w = max((w for w, _ in self._sizes), default=0)
        self._content_w = max(vp.width(), max_w + 2 * GAP)
        vbar, hbar = self.verticalScrollBar(), self.horizontalScrollBar()
        vbar.setRange(0, max(0, self._total - vp.height()))
        vbar.setPageStep(vp.height())
        vbar.setSingleStep(60)
        hbar.setRange(0, max(0, self._content_w - vp.width()))
        hbar.setPageStep(vp.width())
        hbar.setSingleStep(60)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._update_bars()

    # -- zoom / navigation ---------------------------------------------------
    def set_zoom(self, z):
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        if abs(z - self.zoom) < 1e-4:
            return
        self.zoom = z
        self.refresh()
        self.zoomChanged.emit(z)

    def fit_width(self):
        if self.doc is None or len(self.doc) == 0:
            return
        widest = max(p.rect.width for p in self.doc)
        sb = self.verticalScrollBar().sizeHint().width()
        self.set_zoom((self.viewport().width() - 2 * GAP - sb) / widest)

    def goto(self, index):
        if not self._tops:
            return
        index = max(0, min(index, len(self._tops) - 1))
        self.verticalScrollBar().setValue(self._tops[index] - GAP)

    def _on_scroll(self, _):
        self.viewport().update()
        if not self._tops:
            return
        probe = self.verticalScrollBar().value() + self.viewport().height() // 3
        idx = max(0, min(bisect.bisect_right(self._tops, probe) - 1, len(self._tops) - 1))
        if idx != self.current:
            self.current = idx
            self.pageChanged.emit(idx)

    # -- input -------------------------------------------------------------------
    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.zoom * (1.1 ** (ev.angleDelta().y() / 120)))
            ev.accept()
        else:
            super().wheelEvent(ev)

    def keyPressEvent(self, ev):
        vbar = self.verticalScrollBar()
        k = ev.key()
        if k == Qt.Key_PageDown:
            vbar.setValue(vbar.value() + vbar.pageStep())
        elif k == Qt.Key_PageUp:
            vbar.setValue(vbar.value() - vbar.pageStep())
        elif k == Qt.Key_Down:
            vbar.setValue(vbar.value() + vbar.singleStep())
        elif k == Qt.Key_Up:
            vbar.setValue(vbar.value() - vbar.singleStep())
        elif k == Qt.Key_Home:
            vbar.setValue(0)
        elif k == Qt.Key_End:
            vbar.setValue(vbar.maximum())
        else:
            super().keyPressEvent(ev)

    # -- painting ------------------------------------------------------------------
    def _render(self, i):
        key = (i, round(self.zoom, 3))
        img = self._cache.get(key)
        if img is not None:
            self._cache.move_to_end(key)
            return img
        dpr = self.devicePixelRatioF()
        m = pymupdf.Matrix(self.zoom * dpr, self.zoom * dpr)
        pix = self.doc[i].get_pixmap(matrix=m, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        img.setDevicePixelRatio(dpr)
        self._cache[key] = img
        while len(self._cache) > 16:
            self._cache.popitem(last=False)
        return img

    def paintEvent(self, ev):
        p = QPainter(self.viewport())
        p.fillRect(ev.rect(), QColor("#585b61"))
        if self.doc is None:
            p.setPen(QColor("#d6d6d6"))
            p.drawText(self.viewport().rect(), Qt.AlignCenter, "Open a PDF (Ctrl+O) or drop one here")
            return
        y0 = self.verticalScrollBar().value()
        y1 = y0 + self.viewport().height()
        hx = self.horizontalScrollBar().value()
        first = max(0, bisect.bisect_right(self._tops, y0) - 1)
        for i in range(first, len(self._tops)):
            top = self._tops[i]
            if top > y1:
                break
            w, h = self._sizes[i]
            x = (self._content_w - w) // 2 - hx
            p.fillRect(x + 3, top - y0 + 3, w, h, QColor(0, 0, 0, 70))
            p.drawImage(x, top - y0, self._render(i))


# --------------------------------------------------------------------------
# One open document: thumbnails + viewer + edit operations
# --------------------------------------------------------------------------
class DocTab(QWidget):
    changed = Signal()

    def __init__(self, doc, path=None):
        super().__init__()
        self.doc = doc
        self.path = path
        self.modified = False
        self._undo = []
        self._thumb_gen = 0

        self.view = PageView()
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.IconMode)
        self.thumbs.setFlow(QListWidget.TopToBottom)
        self.thumbs.setWrapping(False)
        self.thumbs.setMovement(QListWidget.Static)
        self.thumbs.setResizeMode(QListWidget.Adjust)
        self.thumbs.setIconSize(QSize(THUMB_W, THUMB_H))
        self.thumbs.setSpacing(6)
        self.thumbs.setUniformItemSizes(True)
        self.thumbs.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.thumbs.itemClicked.connect(lambda it: self.view.goto(self.thumbs.row(it)))
        self.view.pageChanged.connect(self._follow_page)

        split = QSplitter()
        split.addWidget(self.thumbs)
        split.addWidget(self.view)
        split.setStretchFactor(1, 1)
        split.setSizes([150, 900])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(split)

        self.view.set_document(doc)
        self._rebuild_thumbs()

    # -- info ----------------------------------------------------------------------
    def title(self):
        name = Path(self.path).name if self.path else "Untitled"
        return name + ("*" if self.modified else "")

    def page_count(self):
        return len(self.doc)

    def selected_pages(self):
        rows = sorted({i.row() for i in self.thumbs.selectedIndexes()})
        return rows or [self.view.current]

    # -- thumbnails (rendered lazily in small batches) -----------------------------------
    def _rebuild_thumbs(self, select=()):
        self._thumb_gen += 1
        self.thumbs.clear()
        blank = QPixmap(THUMB_W, THUMB_H)
        blank.fill(QColor("#d9dbe0"))
        for i in range(len(self.doc)):
            it = QListWidgetItem(QIcon(blank), str(i + 1))
            it.setTextAlignment(Qt.AlignHCenter)
            self.thumbs.addItem(it)
        for r in select:
            if 0 <= r < self.thumbs.count():
                self.thumbs.item(r).setSelected(True)
        gen = self._thumb_gen
        QTimer.singleShot(0, lambda: self._thumb_step(gen, 0))

    def _thumb_step(self, gen, start):
        if gen != self._thumb_gen:
            return
        for i in range(start, min(start + 4, len(self.doc))):
            r = self.doc[i].rect
            s = min(THUMB_W / r.width, THUMB_H / r.height)
            pix = self.doc[i].get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            card = QPixmap(THUMB_W, THUMB_H)
            card.fill(QColor("#d9dbe0"))
            qp = QPainter(card)
            x, y = (THUMB_W - img.width()) // 2, (THUMB_H - img.height()) // 2
            qp.drawImage(x, y, img)
            qp.setPen(QColor("#8a8d94"))
            qp.drawRect(x, y, img.width() - 1, img.height() - 1)
            qp.end()
            self.thumbs.item(i).setIcon(QIcon(card))
        if start + 4 < len(self.doc):
            QTimer.singleShot(1, lambda: self._thumb_step(gen, start + 4))

    def _follow_page(self, i):
        if 0 <= i < self.thumbs.count():
            self.thumbs.setCurrentRow(i, QItemSelectionModel.NoUpdate)
            self.thumbs.scrollToItem(self.thumbs.item(i))

    # -- editing helpers -----------------------------------------------------------------
    def _after_edit(self, select=()):
        self.modified = True
        self.view.refresh()
        self._rebuild_thumbs(select)
        self.changed.emit()

    def _edit(self, fn, select=()):
        snapshot = self.doc.tobytes()
        try:
            fn()
        except Exception:
            self._restore(snapshot)
            raise
        self._undo.append(snapshot)
        del self._undo[:-UNDO_LIMIT]
        self._after_edit(select)

    def _restore(self, data):
        self.doc.close()
        self.doc = pymupdf.open(stream=data, filetype="pdf")
        self.view.doc = self.doc

    # -- page operations -----------------------------------------------------------------
    def can_undo(self):
        return bool(self._undo)

    def undo(self):
        if self._undo:
            self._restore(self._undo.pop())
            self._after_edit()

    def rotate(self, delta):
        pages = self.selected_pages()

        def run():
            for p in pages:
                pg = self.doc[p]
                pg.set_rotation((pg.rotation + delta) % 360)

        self._edit(run, select=pages)

    def delete_pages(self):
        pages = self.selected_pages()
        if len(pages) >= len(self.doc):
            raise ValueError("A PDF must keep at least one page.")
        self._edit(lambda: self.doc.delete_pages(pages))

    def move(self, direction):
        pages = self.selected_pages()
        sel = set(pages)
        n = len(self.doc)
        order = list(range(n))
        if direction < 0:
            for i in range(1, n):
                if order[i] in sel and order[i - 1] not in sel:
                    order[i], order[i - 1] = order[i - 1], order[i]
        else:
            for i in range(n - 2, -1, -1):
                if order[i] in sel and order[i + 1] not in sel:
                    order[i], order[i + 1] = order[i + 1], order[i]
        if order == list(range(n)):
            return
        self._edit(lambda: self.doc.select(order), select=[order.index(p) for p in pages])

    def append_document(self, other):
        start = len(self.doc)
        self._edit(lambda: self.doc.insert_pdf(other), select=range(start, start + len(other)))

    def extract(self, pages, out_path):
        new = pymupdf.open()
        for p in pages:
            new.insert_pdf(self.doc, from_page=p, to_page=p)
        new.save(out_path, garbage=3, deflate=True)
        new.close()

    def split_all(self, folder):
        stem = Path(self.path).stem if self.path else "document"
        width = max(3, len(str(len(self.doc))))
        for p in range(len(self.doc)):
            self.extract([p], str(Path(folder) / f"{stem}_page_{p + 1:0{width}d}.pdf"))
        return len(self.doc)

    # -- saving ------------------------------------------------------------------------------
    def save(self, path=None):
        path = path or self.path
        tmp = path + ".tmp"
        self.doc.save(tmp, garbage=3, deflate=True)
        os.replace(tmp, path)       # atomic: a crash never leaves a half-written PDF
        self.path = path
        self.modified = False
        self.changed.emit()

    def shutdown(self):
        self._thumb_gen += 1
        self.doc.close()


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(lambda _: self._sync_ui())
        self.setCentralWidget(self.tabs)

        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.valueChanged.connect(self._spin_changed)
        self.page_total = QLabel(" / 0 ")
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(48)
        self._syncing = False

        self._build_actions()
        self._sync_ui()

    # -- UI construction -------------------------------------------------------------------
    def _act(self, text, slot, shortcut=None):
        a = QAction(text, self)
        a.triggered.connect(lambda _=False: slot())
        if shortcut:
            a.setShortcut(QKeySequence(shortcut) if isinstance(shortcut, str) else shortcut)
        return a

    def _build_actions(self):
        A = self._act
        self.a_open = A("&Open...", self.open_dialog, QKeySequence.Open)
        self.a_save = A("&Save", self.save, QKeySequence.Save)
        self.a_save_as = A("Save &As...", self.save_as, QKeySequence.SaveAs)
        self.a_close = A("&Close tab", lambda: self.close_tab(self.tabs.currentIndex()), QKeySequence.Close)
        self.a_quit = A("E&xit", self.close, QKeySequence.Quit)
        self.a_undo = A("&Undo", self.undo, QKeySequence.Undo)
        self.a_rot_l = A("Rotate &left", lambda: self._page_op(lambda t: t.rotate(-90)), "Ctrl+Shift+L")
        self.a_rot_r = A("Rotate &right", lambda: self._page_op(lambda t: t.rotate(90)), "Ctrl+Shift+R")
        self.a_delete = A("&Delete page(s)", self.delete_pages, "Ctrl+Del")
        self.a_up = A("Move page(s) &up", lambda: self._page_op(lambda t: t.move(-1)), "Ctrl+Up")
        self.a_down = A("Move page(s) d&own", lambda: self._page_op(lambda t: t.move(1)), "Ctrl+Down")
        self.a_merge = A("&Merge / insert PDF...", self.merge, "Ctrl+M")
        self.a_extract = A("&Extract page(s) to new PDF...", self.extract, "Ctrl+E")
        self.a_split = A("&Split into single pages...", self.split_pages)
        self.a_zoom_in = A("Zoom &in", lambda: self._zoom(1.25), "Ctrl+=")
        self.a_zoom_out = A("Zoom &out", lambda: self._zoom(0.8), "Ctrl+-")
        self.a_fit = A("Fit &width", lambda: self._view_op(lambda v: v.fit_width()), "Ctrl+0")
        self.a_100 = A("&Actual size", lambda: self._view_op(lambda v: v.set_zoom(1.0)), "Ctrl+1")
        self.a_about = A("&About", self.about)

        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.a_open, self.a_save, self.a_save_as, self.a_close):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_quit)
        m = mb.addMenu("&Edit")
        for a in (self.a_undo, None, self.a_rot_l, self.a_rot_r, self.a_delete, self.a_up, self.a_down):
            m.addAction(a) if a else m.addSeparator()
        m = mb.addMenu("&Pages")
        for a in (self.a_merge, self.a_extract, self.a_split):
            m.addAction(a)
        m = mb.addMenu("&View")
        for a in (self.a_zoom_in, self.a_zoom_out, self.a_fit, self.a_100):
            m.addAction(a)
        mb.addMenu("&Help").addAction(self.a_about)

        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)
        for a in (self.a_open, self.a_save, None, self.a_undo, self.a_rot_l, self.a_rot_r, self.a_delete,
                  self.a_up, self.a_down, None, self.a_merge, self.a_extract, None,
                  self.a_zoom_out, self.a_zoom_in, self.a_fit):
            tb.addAction(a) if a else tb.addSeparator()
        tb.addSeparator()
        tb.addWidget(QLabel(" Page "))
        tb.addWidget(self.page_spin)
        tb.addWidget(self.page_total)
        tb.addSeparator()
        tb.addWidget(self.zoom_label)

        self._doc_actions = [
            self.a_save, self.a_save_as, self.a_close, self.a_rot_l, self.a_rot_r, self.a_delete,
            self.a_up, self.a_down, self.a_merge, self.a_extract, self.a_split,
            self.a_zoom_in, self.a_zoom_out, self.a_fit, self.a_100,
        ]

    # -- helpers ----------------------------------------------------------------------------------
    def tab(self):
        return self.tabs.currentWidget()

    def _error(self, msg):
        QMessageBox.warning(self, APP_NAME, msg)

    def _page_op(self, fn):
        t = self.tab()
        if t:
            try:
                fn(t)
            except Exception as e:
                self._error(str(e))

    def _view_op(self, fn):
        t = self.tab()
        if t:
            fn(t.view)

    def _zoom(self, factor):
        self._view_op(lambda v: v.set_zoom(v.zoom * factor))

    def _sync_ui(self):
        t = self.tab()
        for a in self._doc_actions:
            a.setEnabled(t is not None)
        self.a_undo.setEnabled(bool(t and t.can_undo()))
        self._syncing = True
        if t:
            self.page_spin.setMaximum(t.page_count())
            self.page_spin.setValue(t.view.current + 1)
            self.page_total.setText(f" / {t.page_count()} ")
            self.zoom_label.setText(f"{round(t.view.zoom * 100)}%")
            self.setWindowTitle(f"{t.title()} - {APP_NAME}")
        else:
            self.page_spin.setMaximum(1)
            self.page_total.setText(" / 0 ")
            self.zoom_label.setText("100%")
            self.setWindowTitle(APP_NAME)
        self._syncing = False

    def _spin_changed(self, v):
        t = self.tab()
        if t and not self._syncing:
            t.view.goto(v - 1)

    def _tab_changed(self, tab):
        i = self.tabs.indexOf(tab)
        if i >= 0:
            self.tabs.setTabText(i, tab.title())
            self.tabs.setTabToolTip(i, tab.path or "")
        if tab is self.tab():
            self._sync_ui()

    # -- opening ---------------------------------------------------------------------------------------
    def load_pdf(self, path):
        """Open a PDF from memory (so Windows never locks the file). Returns doc or None."""
        try:
            doc = pymupdf.open(stream=Path(path).read_bytes(), filetype="pdf")
        except Exception as e:
            self._error(f"Could not open:\n{path}\n\n{e}")
            return None
        while doc.needs_pass:
            pw, ok = QInputDialog.getText(
                self, "Password required", f"{Path(path).name} is encrypted.\nEnter password:",
                QLineEdit.Password)
            if not ok:
                doc.close()
                return None
            if not doc.authenticate(pw):
                self._error("Wrong password.")
        if len(doc) == 0:
            doc.close()
            self._error("This PDF has no pages.")
            return None
        return doc

    def open_paths(self, paths):
        for path in paths:
            path = os.path.abspath(path)
            existing = next((i for i in range(self.tabs.count()) if self.tabs.widget(i).path == path), None)
            if existing is not None:
                self.tabs.setCurrentIndex(existing)
                continue
            doc = self.load_pdf(path)
            if doc is None:
                continue
            tab = DocTab(doc, path)
            tab.changed.connect(lambda t=tab: self._tab_changed(t))
            tab.view.pageChanged.connect(lambda _, t=tab: t is self.tab() and self._sync_ui())
            tab.view.zoomChanged.connect(lambda _, t=tab: t is self.tab() and self._sync_ui())
            idx = self.tabs.addTab(tab, tab.title())
            self.tabs.setTabToolTip(idx, path)
            self.tabs.setCurrentIndex(idx)
            QTimer.singleShot(0, tab.view.fit_width)

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Open PDF", "", PDF_FILTER)
        self.open_paths(paths)

    # -- file actions ------------------------------------------------------------------------------------
    def save(self):
        t = self.tab()
        if not t:
            return
        if not t.path:
            return self.save_as()
        try:
            t.save()
        except Exception as e:
            self._error(f"Could not save:\n{e}")

    def save_as(self):
        t = self.tab()
        if not t:
            return False
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF as", t.path or "document.pdf", PDF_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            t.save(path)
        except Exception as e:
            self._error(f"Could not save:\n{e}")
            return False
        return True

    def _confirm_close(self, tab):
        if not tab.modified:
            return True
        r = QMessageBox.question(
            self, APP_NAME, f"Save changes to {Path(tab.path).name if tab.path else 'Untitled'}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            self.tabs.setCurrentWidget(tab)
            self.save()
            return not tab.modified
        return True

    def close_tab(self, index):
        tab = self.tabs.widget(index)
        if tab is None or not self._confirm_close(tab):
            return
        self.tabs.removeTab(index)
        tab.shutdown()
        tab.deleteLater()
        self._sync_ui()

    def closeEvent(self, ev):
        for i in range(self.tabs.count()):
            if not self._confirm_close(self.tabs.widget(i)):
                ev.ignore()
                return
        ev.accept()

    # -- edit / page actions ----------------------------------------------------------------------------------
    def undo(self):
        t = self.tab()
        if t:
            t.undo()
            self._sync_ui()

    def delete_pages(self):
        t = self.tab()
        if not t:
            return
        pages = t.selected_pages()
        label = f"page {pages[0] + 1}" if len(pages) == 1 else f"{len(pages)} pages"
        if QMessageBox.question(self, APP_NAME, f"Delete {label}? (You can undo with Ctrl+Z.)") != QMessageBox.Yes:
            return
        self._page_op(lambda tab: tab.delete_pages())

    def merge(self):
        t = self.tab()
        if not t:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose PDF(s) to add at the end", "", PDF_FILTER)
        for path in paths:
            other = self.load_pdf(path)
            if other is None:
                continue
            try:
                t.append_document(other)
            except Exception as e:
                self._error(f"Could not merge {Path(path).name}:\n{e}")
            finally:
                other.close()
        self._sync_ui()

    def extract(self):
        t = self.tab()
        if not t:
            return
        pages = t.selected_pages()
        path, _ = QFileDialog.getSaveFileName(self, "Save extracted pages as", "extracted.pdf", PDF_FILTER)
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            t.extract(pages, path)
            self.statusBar().showMessage(f"Saved {len(pages)} page(s) to {path}", 6000)
        except Exception as e:
            self._error(f"Could not extract:\n{e}")

    def split_pages(self):
        t = self.tab()
        if not t:
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for the single-page PDFs")
        if not folder:
            return
        try:
            n = t.split_all(folder)
            self.statusBar().showMessage(f"Wrote {n} files to {folder}", 6000)
        except Exception as e:
            self._error(f"Could not split:\n{e}")

    def about(self):
        QMessageBox.about(
            self, APP_NAME,
            f"<b>{APP_NAME}</b><br>Free, offline PDF editor. Your files never leave this computer."
            f"<br><br>Powered by PyMuPDF and Qt. Licensed AGPL-3.0.")

    # -- drag & drop -------------------------------------------------------------------------------------------
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.toLocalFile().lower().endswith(".pdf")]
        self.open_paths(paths)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    win.open_paths([a for a in sys.argv[1:] if a.lower().endswith(".pdf")])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
