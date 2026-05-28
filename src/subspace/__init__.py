from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from src.subspace.mosaic_z import optimise_modal_subspace  # 导出 MOSAIC-Z 子空间优化入口 / Export MOSAIC-Z subspace optimiser
from src.subspace.mosaic_z import parse_mode_span  # 导出模态范围解析函数 / Export mode-span parser

__all__ = ["optimise_modal_subspace", "parse_mode_span"]  # 定义公开 API / Define public API
