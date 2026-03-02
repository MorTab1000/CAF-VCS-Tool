from typing import IO, Sequence, Union
import mmap
import os
from contextlib import contextmanager

class LinesSequence(Sequence[bytes]):
    def __init__(self, mmap_obj: mmap.mmap, line_offsets: list[tuple[int, int]]):
        self._line_offsets  = line_offsets
        self._mm = mmap_obj

    def __len__(self) -> int:
        return len(self._line_offsets)

    def __getitem__(self, index: Union[int, slice]):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]

        if index < 0:
            index += len(self)

        start, end = self._line_offsets[index]
        return self._mm[start:end]



def get_line_offsets(mm: mmap.mmap) -> list[tuple[int, int]]:
    offsets = []
    start = 0
    mm_len = len(mm)

    while start < mm_len:
        end = mm.find(b"\n", start)
        if end == -1:
            # last line without '\n'
            offsets.append((start, mm_len))
            break
        offsets.append((start, end + 1))
        start = end + 1
    return offsets

@contextmanager
def prepare_lines_sequence(file_path: str) :
    f = open(file_path, 'rb')
    try:
        if os.fstat(f.fileno()).st_size == 0:
            # Handle empty file case
            yield []
        else:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                offsets = get_line_offsets(mm)
                yield LinesSequence(mm, offsets)

    finally:
        f.close()


