from libcaf.merge_algo import is_binary_blob
import pytest
from pathlib import Path


def test_is_binary_blob_with_text(tmp_path):
    p = tmp_path / "text.txt"
    p.write_text("This is a normal text file.")
    assert is_binary_blob(p) is False


def test_is_binary_blob_with_binary(tmp_path):
    p = tmp_path / "image.bin"
    # A null byte right at the start
    p.write_bytes(b"\x00\x01\x02\x03")
    assert is_binary_blob(p) is True


def test_is_binary_blob_empty_file(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_bytes(b"")
    assert is_binary_blob(p) is False


def test_is_binary_blob_boundary_condition(tmp_path):
    p = tmp_path / "edge.bin"
    # Put a null byte exactly at the 8192nd position
    content = b"a" * 8191 + b"\x00"
    p.write_bytes(content)
    assert is_binary_blob(p) is True


def test_is_binary_blob_missing_file():
    with pytest.raises(IOError):
        is_binary_blob(Path("non_existent_file_12345"))

