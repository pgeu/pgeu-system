# Generic wrappers to handle backwards incompatible changes in dependencies
import jwt


def decode_unverified_jwt(j):
    if jwt.__version__ > 2:
        return jwt.decode(j, options={'verify_signature': False})
    else:
        return jwt.decode(j, verify=False)


def fitz_get_page_png(page):
    import fitz

    if fitz.version[0] > "1.19":
        return page.get_pixmap().tobytes(output='png')
    else:
        return page.getPixmap().getPNGData()


def fitz_get_page_pixmap(page):
    import fitz

    if fitz.version[0] > "1.19":
        return page.get_pixmap()
    else:
        return page.getPixmap()


def fitz_insert_text(page, point, txt, fontname, fontsize):
    import fitz

    if fitz.version[0] > "1.19":
        page.insert_text(point, txt, fontname=fontname, fontsize=fontsize)
    else:
        page.insertText(point, txt, fontname=fontname, fontsize=fontsize)


def fitz_insert_image(page, rect, pixmap, overlay):
    import fitz

    if fitz.version[0] > "1.19":
        page.insert_image(rect, pixmap=pixmap, overlay=overlay)
    else:
        page.insertImage(rect, pixmap=pixmap, overlay=overlay)
