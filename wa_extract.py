#!/usr/bin/env python3

import logging
from os import makedirs
from os.path import join
from typing import BinaryIO


# logging.basicConfig(filename='wa_extract.log', level=logging.DEBUG)
logging.basicConfig(level=logging.INFO)


def _rb(f: BinaryIO, count: int = 1) -> int:
    return int.from_bytes(f.read(count), "little")


class LzssBuffer:
    def __init__(self):
        self.d = None
        self.d_capacity = 0x800
        self.d_size = 0
        self.d_pos = 0

    def input(self, input):
        if not self.d:
            self.d = bytearray(self.d_capacity)
            for i in range(0, self.d_capacity):
                self.d[i] = input
        logging.debug(f"Setting buffer offset {hex(self.d_pos)} to {hex(input)}")
        self.d[self.d_pos] = input
        self.d_pos += 1
        self.d_pos %= self.d_capacity
        if self.d_size < self.d_capacity:
            self.d_size += 1


class Leafpak:
    def __init__(self, filename: str):
        self.pakfile = filename
        self._toc = {}

    def _toc_entry(self, f: BinaryIO):
        filename = f.read(16).decode().rstrip("\x00")
        size = _rb(f, 4)
        encoded = bool(_rb(f, 4))
        offset = _rb(f, 4)
        return filename, {"size": size, "offset": offset, "encoded": encoded}

    @property
    def toc(self):
        if not self._toc:
            with open(self.pakfile, "rb") as f:
                file_count = _rb(f, 2)
                f.seek(2, 1)
                for i in range(1, file_count):
                    filename, entry = self._toc_entry(f)
                    self._toc[filename] = entry
        return self._toc

    def extract_file(self, filename: str, output_path: str = None, output_filename: str = None):
        output_path = output_path or "./"
        output_filename = join(output_path, output_filename or filename)

        makedirs(output_path, exist_ok=True)
        with open(self.pakfile, "rb") as f:
            file_offset = self.toc[filename]["offset"]
            file_size = self.toc[filename]['size']
            if not file_size:
                logging.info(f"File {filename} has size of zero, ignoring...")
            elif self.toc[filename]["encoded"]:
                logging.info(f"Decoding {filename} [{file_size}] from offset {file_offset}")
                decoded_file = Lzss.decode(f, file_offset)
                logging.info("writing the file")
                with open(output_filename, "wb") as o:
                    o.write(decoded_file)
            else:
                logging.info(f"Not encoded {filename} [{file_size}] from offset {file_offset}")
                logging.info("writing the file")
                with open(output_filename, "wb") as o:
                    f.seek(file_offset, 0)
                    o.write(f.read(file_size))


class Lzss:
    @classmethod
    def decode(self, f: BinaryIO, start_offset: int = 0) -> bytearray:
        f.seek(start_offset)
        packed_size = int.from_bytes(f.read(4), "little")
        unpacked_size = int.from_bytes(f.read(4), "little")

        logging.debug(f"packed_size: {packed_size} {hex(packed_size)}, unpacked_size: {unpacked_size} {hex(unpacked_size)}")

        m_input = f
        m_output = bytearray(b"\x00" * unpacked_size)
        m_size = packed_size

        if not unpacked_size or m_size <= 8:
            logging.error("Can't decode to file of zero bytes!")
            raise Exception("Can't decode to file of zero bytes!")

        if unpacked_size > 1000000:
            logging.error(f"Unpacked size of {unpacked_size} is too big!")
            raise Exception(f"Unpacked size of {unpacked_size} is too big!")

        buf = LzssBuffer()

        dst = 0
        remaining = m_size - 8

        while remaining > 0:
            ctl = int.from_bytes(m_input.read(1), "little")
            remaining -= 1
            bit = 1
            logging.debug(f"Outer loop: {ctl}, {remaining}, {bit}")
            while remaining > 0 and bit != 0x100:
                logging.debug(f"\tctl & bit: {ctl} & {bit} = {ctl & bit}")
                if 0 != (ctl & bit):
                    b = int.from_bytes(m_input.read(1), "little")
                    remaining -= 1
                    logging.debug(f"\tVerbatim: setting {hex(dst)} byte to {hex(b)}")
                    m_output[dst] = b
                    dst += 1
                    buf.input(b)
                else:
                    tmp = int.from_bytes(m_input.read(2), "little")
                    remaining -= 2
                    look_behind_pos = tmp >> 4
                    repititions = tmp & 0xf

                    if repititions == 0xf:
                        repititions = repititions + int.from_bytes(m_input.read(1), "little")
                        remaining -= 1
                    repititions += 3

                    logging.debug(f"look behind pos: {look_behind_pos}")
                    logging.debug(f"repititions: {repititions}")

                    logging.debug("\t\tDecompress loop")
                    logging.debug(f"remaining: {remaining}")
                    count = repititions
                    offset = look_behind_pos % buf.d_capacity
                    while count != 0:
                        if dst > len(m_output):
                            break
                        v = buf.d[offset]
                        offset += 1
                        offset = offset % buf.d_capacity
                        logging.debug(f"\t\tsetting {hex(dst)} byte to {hex(v)} from {hex(offset)}")
                        m_output[dst] = v
                        dst += 1
                        count -= 1
                    while repititions != 0:
                        c = m_output[dst-repititions]
                        buf.input(c)
                        repititions -= 1
                bit <<= 1
        return m_output


#lp = Leafpak("WAMES.pak")
lp = Leafpak("WAEG.pak")

# print(lp.toc)

# lp.extract_file("n2mes001.mes", output_path="out")

# exit(0)
# Note: fails in way that creates multi-gig files on certain files
# don't run until fixed
for filename, _ in lp.toc.items():
    print(f"Extracting {filename}...")
    lp.extract_file(filename, output_path="out")
