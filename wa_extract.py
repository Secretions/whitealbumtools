#!/usr/bin/env python3

from os import makedirs
from os.path import join
from typing import BinaryIO


class LzssBuffer:
    def __init__(self):
        self.d_capacity = 0x800
        self.d = bytearray(b"\x00" * self.d_capacity)
        self.d_size = 0
        self.d_pos = 0

    def input(self, i):
        self.d[self.d_pos] = i
        self.d_pos += 1
        self.d_pos %= self.d_capacity
        if self.d_size < self.d_capacity:
            self.d_size += 1


class Leafpak:
    def __init__(self, filename: str):
        self.pakfile = filename
        self._toc = {}

    @staticmethod
    def _rb(f: BinaryIO, count: int = 1) -> int:
        return int.from_bytes(f.read(count), "little")

    def _toc_entry(self, f: BinaryIO):
        filename = f.read(12).decode()
        f.seek(4, 1)
        size = self._rb(f, 2)
        f.seek(6, 1)
        offset = self._rb(f, 2)
        f.seek(2, 1)
        return filename, {"size": size, "offset": offset}

    @property
    def toc(self):
        if not self._toc:
            with open(self.pakfile, "rb") as f:
                file_count = self._rb(f, 2)
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
            decoded_file = self.lzss_decode(f, self.toc[filename]["offset"])
            print("writing the file")
            with open(output_filename, "wb") as o:
                o.write(decoded_file)

    def lzss_decode(self, f: BinaryIO, start_offset: int = 0) -> bytearray:
        f.seek(start_offset)
        packed_size = int.from_bytes(f.read(4), "little")
        unpacked_size = int.from_bytes(f.read(4), "little")

        print(f"packed_size: {packed_size} {hex(packed_size)}, unpacked_size: {unpacked_size} {hex(unpacked_size)}")

        m_input = f
        m_output = bytearray(b"\x00" * unpacked_size)
        m_size = packed_size

        buf = LzssBuffer()

        dst = 0
        remaining = m_size - 8

        while remaining > 0:
            ctl = int.from_bytes(m_input.read(1), "little")
            remaining -= 1
            bit = 1
            # print(f"Outer loop: {ctl}, {remaining}, {bit}")
            while remaining > 0 and bit != 0x100:
                print(f"\tctl & bit: {ctl} & {bit} = {ctl & bit}")
                if 0 != (ctl & bit):
                    b = int.from_bytes(m_input.read(1), "little")
                    remaining -= 1
                    # print(f"\tVerbatim: setting {hex(dst)} byte to {hex(b)}")
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

                    # print(f"look behind pos: {look_behind_pos}")
                    # print(f"repititions: {repititions}")

                    # print("\t\tDecompress loop")
                    # print(f"remaining: {remaining}")
                    count = repititions
                    offset = look_behind_pos % buf.d_capacity
                    while count != 0:
                        if dst > len(m_output):
                            break
                        v = buf.d[offset]
                        offset += 1
                        offset = offset % buf.d_capacity
                        # print(f"\t\tsetting {hex(dst)} byte to {hex(v)} from {hex(offset)}")
                        m_output[dst] = v
                        buf.input(v)
                        dst += 1
                        count -= 1
                bit <<= 1
        return m_output


lp = Leafpak("WAMES.pak")

# print(lp.toc)

lp.extract_file("n2mes006.mes", output_path="out")

exit(0)
# Note: fails in way that creates multi-gig files on certain files
# don't run until fixed
for filename, _ in lp.toc.items():
    try:
        print(f"Extracting {filename}...")
        lp.extract_file(filename, output_path="out")
    except Exception:
        print(f"Failed on {filename}...")
