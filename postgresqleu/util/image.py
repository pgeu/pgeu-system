import io

from PIL import Image, ImageFile


# Rescale an image in the form of bytes to a new set of bytes
# in the same format. Assumes the aspect is correct and that
# the incoming data is valid (it's expected to be for example
# the output of previous image operations)
def rescale_image_bytes(origbytes, resolution):
    p = ImageFile.Parser()
    p.feed(origbytes)
    p.close()
    img = p.image

    return rescale_image(img, resolution)


def rescale_image(img, resolution, centered=False):
    scale = min(
        float(resolution[0]) / float(img.size[0]),
        float(resolution[1]) / float(img.size[1]),
    )

    newimg = img.resize(
        (int(img.size[0] * scale), int(img.size[1] * scale)),
        Image.BICUBIC,
    )
    saver = io.BytesIO()
    if centered and newimg.size[0] != newimg.size[1]:
        # This is not a square, so we have to roll it again
        centeredimg = Image.new('RGBA', resolution)
        centeredimg.paste(newimg, (
            (resolution[0] - newimg.size[0]) // 2,
            (resolution[1] - newimg.size[1]) // 2,
        ))
        centeredimg.save(saver, format='PNG')
    else:
        newimg.save(saver, format=img.format)

    return saver.getvalue()


def get_image_contenttype_from_bytes(image):
    if bytearray(image[:3]) == b'\xFF\xD8\xFF':
        return 'image/jpeg'
    elif bytearray(image[:8]) == b'\x89\x50\x4e\x47\x0d\x0a\x1a\x0a':
        return 'image/png'
    raise Exception("Could not determine image format")
