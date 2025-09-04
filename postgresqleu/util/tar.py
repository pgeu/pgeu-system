import io
import tarfile


class TarStreamer:
    def __init__(self):
        self.buf = io.BytesIO()
        self.ofs = 0

    def write(self, s):
        self.buf.write(s)
        self.ofs += len(s)

    def tell(self):
        return self.ofs

    def close(self):
        self.buf.close()

    def pop(self):
        print("Returning {} bytes at offset {}".format(len(self.buf.getvalue()), self.ofs))
        s = self.buf.getvalue()
        self.buf.close()
        self.buf = io.BytesIO()
        return s


class BytesReader:
    def __init__(self, buf):
        self.buf = buf
        self.len = len(buf)
        self.pos = 0

    def read(self, size=-1):
        if size == -1:
            readsize = self.len - self.pos
        else:
            if self.pos + size > self.len:
                readsize = self.len - self.pos
            else:
                readsize = size

        oldpos = self.pos
        self.pos += readsize
        return self.buf[oldpos:oldpos + readsize]


def generate_streaming_tar(tar_generator):
    streamer = TarStreamer()
    tar = tarfile.TarFile.open(mode='w|gz', fileobj=streamer, bufsize=tarfile.BLOCKSIZE)
    for name, mtime, data, datalen in tar_generator():
        info = tarfile.TarInfo(name)
        info.size = int(datalen)
        info.mtime = mtime
        tar.addfile(info, BytesReader(data))
        yield streamer.pop()
    tar.close()
    yield streamer.pop()
