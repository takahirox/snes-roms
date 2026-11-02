"""Finish and check the 夜鳴き鐘 ROM: size (from the header), header fields, vectors, internal checksum.

usage: python3 -I tools/yonaki/romfix.py ROM.sfc
"""
import sys, pathlib, hashlib

p = pathlib.Path(sys.argv[1])
rom = bytearray(p.read_bytes())
H = 0x7FC0
size = 1024 << rom[H + 0x17]
assert len(rom) == size, f'size {len(rom)} (header says {size}; no 512-byte copier header)'
assert rom[H:H + 21] == b'YONAKIGANE           ', rom[H:H + 21]
assert rom[H + 0x15] == 0x30, 'map mode must be LoROM + FastROM ($30)'
assert rom[H + 0x16] == 0x02, 'cartridge type must be ROM + RAM + battery ($02)'
assert rom[H + 0x18] == 0x03, 'SRAM size byte must be $03 (8 KiB)'
rom[H + 0x1C:H + 0x20] = b'\xff\xff\x00\x00'
s = sum(rom) & 0xFFFF
rom[H + 0x1E] = s & 0xFF
rom[H + 0x1F] = s >> 8
rom[H + 0x1C] = (s ^ 0xFFFF) & 0xFF
rom[H + 0x1D] = (s ^ 0xFFFF) >> 8
assert sum(rom) & 0xFFFF == s
p.write_bytes(rom)
reset = rom[0x7FFC] | rom[0x7FFD] << 8
nmi = rom[0x7FEA] | rom[0x7FEB] << 8
assert 0x8000 <= reset < 0x10000 and 0x8000 <= nmi < 0x10000
print(f'{p}: {len(rom) // 1024} KiB, checksum {s:04X}, reset {reset:04X}, nmi {nmi:04X}, '
      f'sha256 {hashlib.sha256(rom).hexdigest()}')
