from typing import IO, Sequence, Union, List, Tuple
import mmap
import os

class LinesSequence(Sequence[bytes]):
    def __init__(self, file_obj: IO[bytes]):
        self._file = file_obj
        self._line_offsets: List[Tuple[int, int]] = []
        if os.fstat(self._file.fileno()).st_size == 0:
            self._mm = b""  # Use empty bytes, not mmap
            # self._line_offsets remains []
            return
        self._mm = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
        self._build_line_offsets()

    def _build_line_offsets(self) -> None:
        start = 0
        mm_len = len(self._mm)

        while start < mm_len:
            end = self._mm.find(b"\n", start)
            if end == -1:
                # last line without '\n'
                self._line_offsets.append((start, mm_len))
                break
            self._line_offsets.append((start, end + 1))
            start = end + 1

    def __len__(self) -> int:
        return len(self._line_offsets)

    def __getitem__(self, index: Union[int, slice]):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]

        if index < 0:
            index += len(self)

        start, end = self._line_offsets[index]
        return self._mm[start:end]

    def close(self) -> None:
        if isinstance(self._mm, mmap.mmap):
            self._mm.close()

    def __enter__(self) -> "LinesSequence":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
