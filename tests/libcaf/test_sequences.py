import pytest
import os
from libcaf.sequences import LinesSequence

@pytest.fixture
def temp_file(tmp_path):
    """Creates a temporary file for testing."""
    path = tmp_path / "test.txt"
    return path

def test_basic_reading(temp_file):
    content = b"line1\nline2\nline3"
    temp_file.write_bytes(content)

    with open(temp_file, "rb") as f:
        with LinesSequence(f) as seq:
            
            assert len(seq) == 3
            assert seq[0] == b"line1\n"
            assert seq[1] == b"line2\n"
            assert seq[2] == b"line3"  # No newline at EOF

def test_empty_file(temp_file):
    """Crash test for 0-byte files."""
    temp_file.write_bytes(b"")

    with open(temp_file, "rb") as f:
        with LinesSequence(f) as seq:
            assert len(seq) == 0
            
            # Accessing empty seq should raise IndexError
            with pytest.raises(IndexError):
                _ = seq[0]

def test_slicing(temp_file):
    """Ensure slicing works like a standard Python list."""
    temp_file.write_bytes(b"1\n2\n3\n4\n")

    with open(temp_file, "rb") as f:
        with LinesSequence(f) as seq:
            
            slice_result = seq[1:3]
            assert slice_result == [b"2\n", b"3\n"]
            
            step_result = seq[::2]
            assert step_result == [b"1\n", b"3\n"]

def test_negative_indexing(temp_file):
    temp_file.write_bytes(b"A\nB\nC\n")

    with open(temp_file, "rb") as f:
        with LinesSequence(f) as seq:
            assert seq[-1] == b"C\n"
            assert seq[-2] == b"B\n"

def test_large_file_simulation(temp_file):
    """Verify it handles offsets correctly with UNIQUE data."""
    # 1. Create unique lines: "line 0", "line 1", ... "line 99"
    # This ensures that seq[50] isn't accidentally reading line 49 or 51.
    lines = [f"line {i}\n".encode('utf-8') for i in range(100)]
    
    # 2. Write them all to the file
    temp_file.write_bytes(b"".join(lines))

    with open(temp_file, "rb") as f:
        with LinesSequence(f) as seq:
        
            # Check Length
            assert len(seq) == 100
            
            # Check Boundaries
            assert seq[0] == b"line 0\n"
            assert seq[99] == b"line 99\n"
            
            # Check Middle (To ensure offsets didn't drift)
            assert seq[50] == b"line 50\n"