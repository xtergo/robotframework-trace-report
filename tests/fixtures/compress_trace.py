#!/usr/bin/env python3
"""Compress an NDJSON trace file with gzip."""

import gzip
import os
import sys


def main():
    input_path = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/large_diverse_trace.json"
    output_path = input_path + ".gz"

    data = open(input_path, "rb").read()
    original_size = len(data)

    with gzip.open(output_path, "wb") as f:
        f.write(data)

    compressed_size = os.path.getsize(output_path)
    ratio = original_size / compressed_size if compressed_size else 0

    print(f"Original:    {original_size:>12,} bytes")
    print(f"Compressed:  {compressed_size:>12,} bytes")
    print(f"Ratio:       {ratio:>12.2f}x")


if __name__ == "__main__":
    main()
