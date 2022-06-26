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

    scale = min(
        float(resolution[0]) / float(img.size[0]),
        float(resolution[1]) / float(img.size[1]),
    )

    newimg = img.resize(
        (int(img.size[0] * scale), int(img.size[1] * scale)),
        Image.BICUBIC,
    )
    saver = io.BytesIO()
    newimg.save(saver, format=img.format)

    return saver.getvalue()
