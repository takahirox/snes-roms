"""Round-trip mask format boundaries in addition to the asset checks in the builder."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/yonaki'))
from asset_codec import decode_mask, encode_mask  # noqa: E402


def main():
    # Distinct tiles through index $FF, then reuse them in reverse order.
    width = 32
    empty = bytes(16)
    tiles = [bytes((255, i & 255, 255, i >> 8)) * 4 for i in range(257)]
    indexed = b''.join(tiles[:256] + tiles[255::-1])
    indices = bytes(range(256)) + bytes(range(255, -1, -1))
    stored, offset = encode_mask(indexed, width, 16)
    assert offset == 16 * (width + 2)
    assert stored[:offset] == b''.join(bytes((0, width)) + indices[i:i + width]
                                      for i in range(0, len(indices), width))
    assert decode_mask(stored, offset, width, 16) == indexed

    # A 257th tile forces raw even though the repeats would make a wider dictionary smaller.
    over_limit = indexed + tiles[-1] + empty * (width - 1)
    stored, offset = encode_mask(over_limit, width, 17)
    assert offset == 0
    assert decode_mask(stored, offset, width, 17) == over_limit

    # Nonzero starts, an empty row and an empty tile inside a span.
    mask = b''.join((empty, tiles[0], empty, tiles[0], empty, empty,
                     empty, empty, tiles[0], tiles[0], tiles[0], empty))
    stored, offset = encode_mask(mask, 6, 2)
    assert offset != 0
    assert decode_mask(stored, offset, 6, 2) == mask
    stored, offset = encode_mask(empty * 6 + mask, 6, 3)
    assert stored[:2] == bytes(2)
    assert decode_mask(stored, offset, 6, 3) == empty * 6 + mask

    # At equal size the builder keeps the raw span.
    raw = b''.join(tiles[:15] + tiles[:1])
    assert encode_mask(raw, 16, 1) == (bytes((0, 16)) + raw, 0)
    assert decode_mask(bytes((0, 16)) + raw, 0, 16, 1) == raw
    print('Yonaki mask round trips passed')


if __name__ == '__main__':
    main()
