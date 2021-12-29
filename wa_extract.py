#!/usr/bin/env python3

import argparse
import logging
from os import makedirs, walk
from os.path import basename, getsize, join
from typing import BinaryIO


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

    def create_file(self, filename: str, input_directory: str):
        input_files = next(walk(input_directory), (None, None, []))[2]
        with open(self.pakfile, "wb") as f:
            toc_entries = {name: {"size": getsize(join(input_directory, name))} for name in sorted(input_files)}
            entry_offset = 4
            name_size = 16
            attr_size = 4
            entry_size = name_size + (attr_size*3)
            data_offset = (len(toc_entries) * entry_size) + entry_offset
            data_pos = data_offset
            logging.info(f"Data offset: {data_offset}")
            toc_count = len(toc_entries) + 1
            f.write(toc_count.to_bytes(4, "little"))
            c = 0 # iter
            f.seek(data_pos)
            for name, entry in toc_entries.items():
                entry_pos = entry_offset + (entry_size*c)
                size_pos = entry_pos + name_size
                encoding_pos = size_pos + attr_size
                offset_pos = encoding_pos + attr_size
                encoding = 0
                logging.info(f"{name}: [{entry['size']}]")
                f.seek(entry_pos)
                f.write(name.encode("ascii").ljust(16, b"\x00"))
                f.write(entry["size"].to_bytes(4, "little"))
                f.write(encoding.to_bytes(4, "little"))
                f.write(data_pos.to_bytes(4, "little"))
                with open(join(input_directory, name), "rb") as data_input:
                    f.seek(data_pos)
                    f.write(data_input.read())
                data_pos += entry["size"]
                c += 1


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

        m_input = f
        m_output = bytearray(unpacked_size)
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
            while remaining > 0 and bit != 0x100:
                if 0 != (ctl & bit):
                    b = int.from_bytes(m_input.read(1), "little")
                    remaining -= 1
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

                    count = repititions
                    offset = look_behind_pos % buf.d_capacity
                    while count != 0:
                        if dst > unpacked_size:
                            break
                        v = buf.d[offset]
                        offset += 1
                        offset = offset % buf.d_capacity
                        m_output[dst] = v
                        dst += 1
                        count -= 1
                    while repititions != 0:
                        c = m_output[dst-repititions]
                        buf.input(c)
                        repititions -= 1
                bit <<= 1
        return m_output


def parse_args():
    parser = argparse.ArgumentParser(description="White Album Extractor")
    parser.add_argument("-p", "--pakfile", help=".pak filename to extract from", required=True)
    parser.add_argument("-l", "--list", help="List contents of .pak file", action="store_true")
    parser.add_argument("-x", "--extract", help="Extract files from .pak file", action="store_true")
    parser.add_argument("-c", "--create", help="Create .pak file", action="store_true")
    parser.add_argument("-f", "--filename", help="Individual filename to extract")
    parser.add_argument("-i", "--input-directory", help="Directory with files to create")
    parser.add_argument("-d", "--output-directory", help="Output directory for extracted files (will create)", default="out")
    parser.add_argument("-o", "--output-filename", help="Output filename for extracted file (optional)")
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.list and not args.extract and not args.create:
        logging.error("Must specify either `--list`, `--create` or `--extract`!")
        exit(1)

    if args.output_filename and not args.filename:
        logging.error("Can only specify `--output-filename` with `--filename`!")
        exit(1)

    if args.create and not args.input_directory:
        logging.error("Must specify `--input-directory` with `--create`!")
        exit(1)

    lp = Leafpak(args.pakfile)
    if not args.create:
        logging.info(f"Loaded {args.pakfile}, {len(lp.toc)} files...")

    if args.list:
        for filename, entry in lp.toc.items():
            print(f"* {filename} [{entry['size']}b], offset={entry['offset']}, encoded={entry['encoded']}")
    elif args.create:
        lp.create_file(args.filename, args.input_directory)
    elif args.extract:
        if args.filename:
            lp.extract_file(args.filename, args.output_directory, args.output_filename)
        else:
            for filename, _ in lp.toc.items():
                print(f"Extracting {filename}...")
                lp.extract_file(filename, args.output_directory)


if __name__ == "__main__":
    main()
