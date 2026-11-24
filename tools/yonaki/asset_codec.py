"""Lossless silhouette spans and optional asset size benchmarks."""
import re
import zlib

MASK_TILE_BYTES = 16


def encode_mask(mask, width, height):
    """Store (start, count) per row followed by its tiles or dictionary indices."""
    stride = width * MASK_TILE_BYTES
    assert len(mask) == stride * height
    rows = []
    for row in range(height):
        offset = row * stride
        tiles = [mask[i:i + MASK_TILE_BYTES] for i in range(offset, offset + stride, MASK_TILE_BYTES)]
        occupied = [col for col, tile in enumerate(tiles) if any(tile[::2])]
        if occupied:
            start, end = occupied[0], occupied[-1] + 1
            rows.append((bytes((start, end - start)), tiles[start:end]))
        else:
            rows.append((b'\0\0', []))
    raw = b''.join(header + b''.join(tiles) for header, tiles in rows)

    dictionary = {}
    indices = bytearray()
    for header, tiles in rows:
        indices += header
        for tile in tiles:
            index = dictionary.setdefault(tile, len(dictionary))
            if index >= 256:
                return raw, 0
            indices.append(index)
    if len(indices) + len(dictionary) * MASK_TILE_BYTES >= len(raw):
        return raw, 0
    return bytes(indices) + b''.join(dictionary), len(indices)


def decode_mask(data, dictionary_offset, width, height):
    """Reconstruct the original rectangular mask, including empty tiles."""
    mask = bytearray(width * height * MASK_TILE_BYTES)
    pos = 0
    for row in range(height):
        start, count = data[pos:pos + 2]
        pos += 2
        dest = (row * width + start) * MASK_TILE_BYTES
        size = count * MASK_TILE_BYTES
        if dictionary_offset:
            for index in data[pos:pos + count]:
                tile = dictionary_offset + MASK_TILE_BYTES * index
                mask[dest:dest + MASK_TILE_BYTES] = data[tile:tile + MASK_TILE_BYTES]
                dest += MASK_TILE_BYTES
            pos += count
        else:
            mask[dest:dest + size] = data[pos:pos + size]
            pos += size
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
