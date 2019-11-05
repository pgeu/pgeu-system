from PIL import Image
import base64
from io import BytesIO


def generate_base64_qr(s, version, requested_size):
    try:
        import qrencode
    except ImportError:
        return ""

    (ver, size, qrimage) = qrencode.encode(s, version=5, level=qrencode.QR_ECLEVEL_M)
    if size < requested_size:
        size = (requested_size // size) * size
        qrimage = qrimage.resize((size, size), Image.NEAREST)

    b = BytesIO()
    qrimage.save(b, "png")
    return base64.b64encode(b.getvalue()).decode('ascii')
