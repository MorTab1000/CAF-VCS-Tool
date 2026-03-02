import mmap
from libcaf.sequences import LinesSequence, get_line_offsets, prepare_lines_sequence


def test_basic_reading():
    content = b"line1\nline2\nline3"
    with mmap.mmap(-1, len(content)) as mm:                
        mm.write(content)
        offsets = get_line_offsets(mm)
        seq = LinesSequence(mm, offsets)
        assert len(seq) == 3
        assert seq[0] == b"line1\n"
        assert seq[1] == b"line2\n"
        assert seq[2] == b"line3"  # No newline at EOF



def test_slicing():
    """Ensure slicing works like a standard Python list."""
    content = b"1\n2\n3\n4\n"

    with mmap.mmap(-1, len(content)) as mm:
        mm.write(content)
        offsets = get_line_offsets(mm)
        seq = LinesSequence(mm, offsets)
        slice_result = seq[1:3]
        assert slice_result == [b"2\n", b"3\n"]
        step_result = seq[::2]
        assert step_result == [b"1\n", b"3\n"]

def test_negative_indexing():
    content = b"A\nB\nC\n"
    with mmap.mmap(-1, len(content)) as mm:
        mm.write(content)
        offsets = get_line_offsets(mm)
        seq = LinesSequence(mm, offsets)
        assert seq[-1] == b"C\n"
        assert seq[-2] == b"B\n"

def test_prepare_lines_sequence_with_real_file(tmp_path):
    file_path = tmp_path / "test.txt"
    file_content = b"first line\nsecond line\nthird line"
    file_path.write_bytes(file_content)

    with prepare_lines_sequence(str(file_path)) as seq:
        assert len(seq) == 3
        assert seq[0] == b"first line\n"
        assert seq[1] == b"second line\n"
        assert seq[2] == b"third line"

def test_empty_file(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_bytes(b"")  

    with prepare_lines_sequence(str(file_path)) as seq:
        assert seq == []