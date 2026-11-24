"""Lossless silhouette tile dictionaries and optional asset size benchmarks."""
import re
import zlib

MASK_TILE_BYTES = 16


def encode_mask(mask):
    """Return (stored bytes, dictionary offset), with offset 0 for the raw form."""
    assert len(mask) % MASK_TILE_BYTES == 0
    dictionary = {}
    indices = bytearray()
    for pos in range(0, len(mask), MASK_TILE_BYTES):
        tile = mask[pos:pos + MASK_TILE_BYTES]
        index = dictionary.setdefault(tile, len(dictionary))
        if index >= 256:
            return mask, 0
        indices.append(index)
    if len(indices) + len(dictionary) * MASK_TILE_BYTES >= len(mask):
        return mask, 0
    return bytes(indices) + b''.join(dictionary), len(indices)


def decode_mask(data, dictionary_offset):
    if not dictionary_offset:
        return data
    mask = bytearray()
    for index in data[:dictionary_offset]:
        start = dictionary_offset + MASK_TILE_BYTES * index
        mask += data[start:start + MASK_TILE_BYTES]
    return bytes(mask)


def packbits_stats(data):
    """Size and number of packets, with up to 128 bytes per packet and repeats from length 3."""
    size = packets = pos = 0
    for run in re.finditer(rb'(.)\1{2,}', data, re.DOTALL):
        literals = run.start() - pos
        repeats = run.end() - run.start()
        literal_packets = (literals + 127) // 128
        repeat_packets = (repeats + 127) // 128
        size += literals + literal_packets + 2 * repeat_packets
        packets += literal_packets + repeat_packets
        pos = run.end()
    literals = len(data) - pos
    literal_packets = (literals + 127) // 128
    return size + literals + literal_packets, packets + literal_packets


def benchmark(blocks):
    """Compare sizes at independently addressable boundaries, excluding pointer metadata."""
    packets = [packbits_stats(block) for block in blocks]
    return dict(blocks=len(blocks), raw=sum(map(len, blocks)),
                packbits=sum(size for size, _ in packets),
                packbits_max_packets=max((count for _, count in packets), default=0),
                deflate=sum(len(zlib.compress(block, wbits=-15)) for block in blocks))
