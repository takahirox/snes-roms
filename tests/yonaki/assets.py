"""Round-trip mask format boundaries in addition to the asset checks in the builder."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/yonaki'))
from asset_codec import decode_mask, encode_mask  # noqa: E402


def main():
    # Distinct tiles through index $FF, then reuse them in reverse order.
    tiles = [i.to_bytes(2, 'little') * 8 for i in range(257)]
    indexed = b''.join(tiles[:256] + tiles[255::-1])
    stored, offset = encode_mask(indexed)
    assert offset == 512 and stored[:offset] == bytes(range(256)) + bytes(range(255, -1, -1))
    assert decode_mask(stored, offset) == indexed

    # A 257th tile forces raw even though the repeats would make a wider dictionary smaller.
    over_limit = indexed + tiles[-1]
    for raw in (over_limit, b''.join(tiles[:256]), tiles[0]):
        assert encode_mask(raw) == (raw, 0)
        assert decode_mask(raw, 0) == raw
    print('Yonaki mask round trips passed')


if __name__ == '__main__':
    main()
