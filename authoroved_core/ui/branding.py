"""Логотип «Строки текста»: буква «А» из строк, перекладина подсвечена как признак."""
from pathlib import Path
import struct

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = ASSETS / "logo.svg"
LOGO_SMALL = ASSETS / "logo_small.svg"
# До 24 px полная буква сливается, поэтому для мелких размеров — упрощённый знак.
SMALL_LIMIT = 24
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def logo_image(size: int) -> QImage:
    source = LOGO_SMALL if size <= SMALL_LIMIT else LOGO
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(source)).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def logo_pixmap(size: int, device_ratio: float = 1.0) -> QPixmap:
    pixmap = QPixmap.fromImage(logo_image(round(size * device_ratio)))
    pixmap.setDevicePixelRatio(device_ratio)
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(logo_image(size)))
    return icon


def set_windows_app_id() -> None:
    """Без собственного AppUserModelID Windows показывает на панели задач значок Python."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Avtoroved.Core")
    except (AttributeError, OSError):
        pass


def write_ico(path: Path, sizes=(16, 20, 24, 32, 40, 48, 64, 128, 256)) -> None:
    """Сохраняет многоразмерный .ico (PNG внутри, формат Windows Vista+) для ярлыка."""
    images = []
    for size in sizes:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        logo_image(size).save(buffer, "PNG")
        buffer.close()
        images.append((size, bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, payload = b"", b""
    for size, png in images:
        side = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset + len(payload))
        payload += png
    path.write_bytes(header + entries + payload)
