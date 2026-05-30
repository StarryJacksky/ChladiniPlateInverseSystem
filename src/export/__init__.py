"""3D-printing / manufacturing export helpers (STL from the thickness field). /
3D 打印 / 制造导出助手（由厚度场生成 STL）。"""

from .stl_export import (
    HFieldExportError,
    h_field_to_stl_bytes,
    h_field_stats,
    smooth_h_field,
)

__all__ = [
    "HFieldExportError",
    "h_field_to_stl_bytes",
    "h_field_stats",
    "smooth_h_field",
]
