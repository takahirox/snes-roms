"""Finish and check the 潮鳴りの密室 ROM: size, header fields, vectors, internal checksum.

usage: python3 -I tools/adv/romfix.py ROM.sfc
"""
import sys, pathlib, hashlib

p = pathlib.Path(sys.argv[1])
rom = bytearray(p.read_bytes())
assert len(rom) == 512 * 1024, f'size {len(rom)} (expected 512 KiB, no 512-byte copier header)'
H = 0x7FC0
assert rom[H:H + 21] == b'SHIONARI NO MISSITSU ', rom[H:H + 21]
assert rom[H + 0x15] == 0x20, 'map mode must be LoROM ($20)'
assert rom[H + 0x16] == 0x02, 'cartridge type must be ROM + RAM + battery ($02)'
assert rom[H + 0x17] == 0x09, 'ROM size byte must be $09 (512 KiB)'
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
print(f'{p}: checksum {s:04X}, reset {reset:04X}, nmi {nmi:04X}, sha256 {hashlib.sha256(rom).hexdigest()}')
