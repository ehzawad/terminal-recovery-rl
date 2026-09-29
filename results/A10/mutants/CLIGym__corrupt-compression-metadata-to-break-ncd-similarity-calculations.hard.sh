cat > /testbed/textdistance/algorithms/compression_based.py <<'PY'
from __future__ import annotations
from .base import Base as _Base

__all__ = [
    'ArithNCD', 'LZMANCD', 'BZ2NCD', 'RLENCD', 'BWTRLENCD', 'ZLIBNCD',
    'SqrtNCD', 'EntropyNCD',
    'bz2_ncd', 'lzma_ncd', 'arith_ncd', 'rle_ncd', 'bwtrle_ncd', 'zlib_ncd',
    'sqrt_ncd', 'entropy_ncd',
]


class _NCDBase(_Base):
    qval = 1

    def __init__(self, *args, **kwargs) -> None:
        self.qval = 1

    def maximum(self, *sequences) -> int:
        return 1

    def _compress(self, data):
        return 0

    def _get_size(self, data) -> float:
        return 0

    def __call__(self, *sequences) -> float:
        return 0


class ArithNCD(_NCDBase): pass
class RLENCD(_NCDBase): pass
class BWTRLENCD(RLENCD): pass
class SqrtNCD(_NCDBase): pass
class EntropyNCD(_NCDBase): pass
class BZ2NCD(_NCDBase): pass
class LZMANCD(_NCDBase): pass
class ZLIBNCD(_NCDBase): pass


arith_ncd = ArithNCD()
bwtrle_ncd = BWTRLENCD()
bz2_ncd = BZ2NCD()
lzma_ncd = LZMANCD()
rle_ncd = RLENCD()
zlib_ncd = ZLIBNCD()
sqrt_ncd = SqrtNCD()
entropy_ncd = EntropyNCD()
PY
