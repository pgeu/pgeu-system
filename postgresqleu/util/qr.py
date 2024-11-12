from PIL import Image
import base64
from io import BytesIO


# Support both the qrcode library (current) and the qrencode one (legacy)
def generate_base64_qr(s, version, requested_size):
    if not version:
        version = 5

    try:
        import qrcode

        qrimage = qrcode.make(s, version=version, border=0)
    except ImportError:
        try:
            import qrencode

            (ver, size, qrimage) = qrencode.encode(s, version=version, level=qrencode.QR_ECLEVEL_M)
        except ImportError:
            return ""

    if qrimage.size[0] != requested_size:
        if qrimage.size[0] < requested_size:
            size = (requested_size // qrimage.size[0]) * qrimage.size[0]
        else:
            size = qrimage.size[0] // (qrimage.size[0] // requested_size + 1)
        qrimage = qrimage.resize((size, size), Image.NEAREST)

    b = BytesIO()
    qrimage.save(b, "png")
    return base64.b64encode(b.getvalue()).decode('ascii')
