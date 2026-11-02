"""Decode the photo tiles (VRAM BG1, 8bpp) and the text bitmap (VRAM BG2, 2bpp) of a running game (debug aid)."""
import numpy as np


def photo_indices(vram):
    v = np.frombuffer(bytes(vram[0:49152]), np.uint8).reshape(24, 32, 4, 8, 2)   # ty tx pair row byte
    out = np.zeros((24, 32, 8, 8), np.uint8)
    for p in range(8):
        byte = v[:, :, p >> 1, :, p & 1]
        for x in range(8):
            out[:, :, :, x] |= ((byte >> (7 - x)) & 1).astype(np.uint8) << p
    return out.transpose(0, 2, 1, 3).reshape(192, 256)


def text_indices(vram, base=0xC040):
    v = np.frombuffer(bytes(vram[base:base + 11520]), np.uint8).reshape(24, 30, 8, 2)
    out = np.zeros((24, 30, 8, 8), np.uint8)
    for p in range(2):
        byte = v[:, :, :, p]
        for x in range(8):
            out[:, :, :, x] |= ((byte >> (7 - x)) & 1).astype(np.uint8) << p
    return out.transpose(0, 2, 1, 3).reshape(192, 240)
