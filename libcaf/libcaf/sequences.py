from typing import IO, Sequence, Union
import mmap

class LinesSequence(Sequence[bytes]):
    def __init__(self, mmap_obj: mmap.mmap):
        # self._file = file_obj
        self._line_offsets  = None
        self._mm = mmap_obj

    def _ensure_offsets(self) -> None:
        """Builds the index only if it hasn't been built yet."""
        if self._line_offsets is None:
            self._line_offsets = []
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
        self._ensure_offsets()
        return len(self._line_offsets)

    def __getitem__(self, index: Union[int, slice]):
        self._ensure_offsets()
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]

        if index < 0:
            index += len(self)

        start, end = self._line_offsets[index]
        return self._mm[start:end]


