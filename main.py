import sys
from pathlib import Path
from PySide6.QtCore import Qt, QPoint, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QPixmap, QFont, QFontDatabase, QTransform, QColor
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QMessageBox
from PySide6.QtMultimedia import QSoundEffect
from pynput.mouse import Listener as MouseListener, Button as PynputButton

ASSETS_DIR = Path(__file__).parent / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
SOUNDS_DIR = ASSETS_DIR / "sounds"
FONTS_DIR = ASSETS_DIR / "fonts"

HIT_RESET_MS = 150
SCALE_STEP = 0.05
SCALE_MIN = 0.2
SCALE_MAX = 3.0


class Main(QWidget):
    global_mouse_click = Signal(str, int, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Main")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        try:
            self.orig_idle = QPixmap(str(IMAGES_DIR / "cat_idle.png"))
            self.orig_left = QPixmap(str(IMAGES_DIR / "cat_left.png"))
            self.orig_right = QPixmap(str(IMAGES_DIR / "cat_right.png"))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить картинки: {e}")
            raise

        if self.orig_idle.isNull():
            QMessageBox.critical(self, "Ошибка", "Нет cat_idle.png в assets/images")
            sys.exit(1)

        self.state = "idle"
        self.rotation = 0
        self.scale = 1.0
        self.locked = False
        self.dragging = False
        self.offset = QPoint(0, 0)

        self.cat_label = QLabel(self)
        self.cat_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        font = QFont("Arial", 20, QFont.Bold)
        font_file = FONTS_DIR / "Pixel.otf"
        if font_file.exists():
            font_id = QFontDatabase.addApplicationFont(str(font_file))
            fams = QFontDatabase.applicationFontFamilies(font_id)
            if fams:
                font = QFont(fams[0], 20)

        self.counter_label = QLabel(self)
        self.counter_label.setFont(font)

        self.counter_color = "white"

        self.clicks = 0
        self.update_counter_label()

        self.snd_left = QSoundEffect()
        self.snd_right = QSoundEffect()
        try:
            left_path = SOUNDS_DIR / "click.wav"
            right_path = SOUNDS_DIR / "click.wav"
            if left_path.exists():
                self.snd_left.setSource(QUrl.fromLocalFile(str(left_path)))
            if right_path.exists():
                self.snd_right.setSource(QUrl.fromLocalFile(str(right_path)))
            for s in (self.snd_left, self.snd_right):
                s.setLoopCount(1)
                s.setVolume(0.9)
        except Exception:
            pass

        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self._set_idle_state)

        self._update_image()

        self.global_mouse_click.connect(self._on_global_mouse_click)
        self._start_global_mouse_listener()

    def update_counter_label(self):
        self.counter_label.setText(f"{self.clicks}")
        self.counter_label.adjustSize()
        self.counter_label.move(8, 6)
        self.counter_label.setStyleSheet(
            f"color: {self.counter_color}; background: transparent;"
        )

    def _get_current_orig(self):
        if self.state == "idle":
            return self.orig_idle
        elif self.state == "left":
            return self.orig_left
        return self.orig_right

    def _update_image(self):
        orig = self._get_current_orig()
        if orig.isNull():
            return

        new_w = max(1, int(orig.width() * self.scale))
        new_h = max(1, int(orig.height() * self.scale))
        scaled = orig.scaled(new_w, new_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        transform = QTransform().rotate(self.rotation)
        rotated = scaled.transformed(transform, Qt.SmoothTransformation)

        self.cat_label.setPixmap(rotated)
        self.cat_label.resize(rotated.size())
        self.resize(rotated.size())
        self.counter_label.raise_()

    def _set_idle_state(self):
        self.state = "idle"
        self._update_image()

    def hit(self, side: str):
        if side not in ("left", "right"):
            return
        self.clicks += 1
        self.update_counter_label()

        self.state = side
        self._update_image()

        try:
            if side == "left":
                self.snd_left.play()
            else:
                self.snd_right.play()
        except Exception:
            pass

        self.reset_timer.start(HIT_RESET_MS)

    def _start_global_mouse_listener(self):
        def _mouse_on_click(x, y, button, pressed):
            if not pressed:
                return
            side = "left" if button == PynputButton.left else "right" if button == PynputButton.right else "middle"
            try:
                self.global_mouse_click.emit(side, int(x), int(y))
            except RuntimeError:
                pass

        self._mouse_listener = MouseListener(on_click=_mouse_on_click)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

    @Slot(str, int, int)
    def _on_global_mouse_click(self, side: str, screen_x: int, screen_y: int):
        rect = self.frameGeometry()
        pt = QPoint(screen_x, screen_y)
        if rect.contains(pt):
            local = pt - rect.topLeft()
            if self._is_pixel_opaque(local):
                return

        if side == "left":
            self.hit("left")
        elif side == "right":
            self.hit("right")
            if not self.locked:
                self.rotation = (self.rotation + 90) % 360
                self._update_image()

    def _is_pixel_opaque(self, local_point: QPoint) -> bool:
        pm = self.cat_label.pixmap()
        if pm is None or pm.isNull():
            return False
        img = pm.toImage()
        x, y = int(local_point.x()), int(local_point.y())
        if x < 0 or y < 0 or x >= img.width() or y >= img.height():
            return False
        rgba = QColor(img.pixel(x, y))
        return rgba.alpha() > 10

    def mousePressEvent(self, event):
        pos_local = event.position().toPoint()
        if not self._is_pixel_opaque(pos_local):
            return

        if event.button() == Qt.LeftButton:
            mods = event.modifiers()
            if (mods & Qt.ControlModifier) and (mods & Qt.ShiftModifier):
                self.locked = False
            elif (mods & Qt.ControlModifier):
                self.locked = True
            else:
                if not self.locked:
                    self.dragging = True
                    self.offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.hit("left")

        elif event.button() == Qt.RightButton:
            self.hit("right")
            if not self.locked:
                self.rotation = (self.rotation + 90) % 360
                self._update_image()

    def mouseMoveEvent(self, event):
        if self.dragging and not self.locked:
            new_top_left = event.globalPosition().toPoint() - self.offset
            self.move(new_top_left)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False

    def wheelEvent(self, event):
        if self.locked:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        steps = delta / 120.0
        self.scale = max(SCALE_MIN, min(SCALE_MAX, self.scale + steps * SCALE_STEP))
        self._update_image()

    def keyPressEvent(self, event):
        if self.dragging and not self.locked:
            if event.key() == Qt.Key_1:
                self.counter_color = "white"
                self.update_counter_label()
                return
            elif event.key() == Qt.Key_2:
                self.counter_color = "black"
                self.update_counter_label()
                return

        if event.key() == Qt.Key_Z:
            self.hit("left")
        elif event.key() == Qt.Key_M:
            self.hit("right")
        elif event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        try:
            if hasattr(self, "_mouse_listener"):
                self._mouse_listener.stop()
        finally:
            super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseDesktopOpenGL)
    w = Main()
    w.move(200, 200)
    w.show()
    sys.exit(app.exec())
