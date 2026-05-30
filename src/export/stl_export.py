"""Dependency-free STL export of the optimised plate thickness field. /
零依赖的优化板厚度场 STL 导出。

The optimiser produces a ``grid_size`` x ``grid_size`` thickness matrix ``H``
(in millimetres). For 3D printing we turn that into a *stepped* solid: every
cell ``(i, j)`` becomes a ``cell_mm`` x ``cell_mm`` x ``H[i, j]`` box sitting on
a common flat bottom at ``z = 0`` (good print-bed contact). The boxes are
emitted as one binary-STL triangle soup — exactly what
``trimesh.util.concatenate`` would produce, but without pulling in trimesh.

This module intentionally has **no third-party dependencies** beyond numpy
(scipy is only imported lazily for the optional smoothing path), so it works on
machines where trimesh / numpy-stl are not installed and avoids adding heavy
packages on a near-full disk. /

优化器输出 ``grid_size`` x ``grid_size`` 的厚度矩阵 ``H``（单位 mm）。3D 打印时
把它变成阶梯实体：每个 cell 是一个 ``cell_mm`` x ``cell_mm`` x ``H[i,j]`` 的
长方体，统一坐落在 ``z=0`` 的平底上（贴合打印床）。所有长方体作为一个二进制
STL 三角面片"汤"导出——与 ``trimesh.util.concatenate`` 等价，但不引入 trimesh。
"""

from __future__ import annotations

import struct
from io import BytesIO

import numpy as np


class HFieldExportError(ValueError):
    """Raised when the thickness field cannot be turned into a printable STL. /
    厚度场无法转成可打印 STL 时抛出。"""


def h_field_stats(H: np.ndarray, plate_length_mm: float) -> dict:
    """Summary geometry stats for the UI (size, thickness range, volume, mass-ish). /
    给 UI 的几何摘要（尺寸、厚度范围、体积）。"""
    H = np.asarray(H, dtype=float)
    grid = int(H.shape[0])
    cell_mm = float(plate_length_mm) / grid
    cell_area_mm2 = cell_mm * cell_mm
    volume_mm3 = float(np.sum(H) * cell_area_mm2)
    return {
        "grid_size": grid,
        "plate_length_mm": float(plate_length_mm),
        "cell_mm": round(cell_mm, 4),
        "thickness_min_mm": round(float(H.min()), 4),
        "thickness_max_mm": round(float(H.max()), 4),
        "thickness_mean_mm": round(float(H.mean()), 4),
        "volume_mm3": round(volume_mm3, 2),
        "volume_cm3": round(volume_mm3 / 1000.0, 3),
    }


def smooth_h_field(H: np.ndarray, sigma_cells: float = 0.6) -> np.ndarray:
    """Optional gaussian smoothing of the thickness field to soften 1 mm steps. /
    可选：对厚度场做高斯平滑，柔化相邻 cell 的台阶。"""
    H = np.asarray(H, dtype=float)
    if sigma_cells <= 0:
        return H
    try:
        from scipy.ndimage import gaussian_filter
    except Exception:  # scipy missing → return unsmoothed / 无 scipy 则原样返回
        return H
    return gaussian_filter(H, sigma=float(sigma_cells), mode="nearest")


def _box_triangles(x0: float, x1: float, y0: float, y1: float,
                   z0: float, z1: float) -> list[tuple]:
    """12 outward-facing triangles (2 per face) of an axis-aligned box. /
    轴对齐长方体的 12 个朝外三角面片（每面 2 个）。"""
    # 8 corners / 8 个角点
    v = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),  # bottom 0-3
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),  # top    4-7
    ]
    # Each face as two CCW triangles when viewed from outside / 每面两 CCW 三角
    faces = [
        (0, 2, 1), (0, 3, 2),  # bottom (-z) outward = downward
        (4, 5, 6), (4, 6, 7),  # top (+z)
        (0, 1, 5), (0, 5, 4),  # front (-y)
        (2, 3, 7), (2, 7, 6),  # back (+y)
        (1, 2, 6), (1, 6, 5),  # right (+x)
        (3, 0, 4), (3, 4, 7),  # left (-x)
    ]
    return [(v[a], v[b], v[c]) for a, b, c in faces]


def _triangle_normal(p0, p1, p2) -> tuple[float, float, float]:
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    norm = (nx * nx + ny * ny + nz * nz) ** 0.5
    if norm < 1e-12:
        return (0.0, 0.0, 0.0)
    return (nx / norm, ny / norm, nz / norm)


def h_field_to_stl_bytes(H: np.ndarray, plate_length_mm: float,
                         *, min_thickness_mm: float = 0.0,
                         smooth_sigma_cells: float = 0.0,
                         header: str = "ChladniPlate") -> bytes:
    """Build a binary STL (bytes) of the stepped plate from thickness field ``H``. /
    由厚度场 ``H`` 生成阶梯板的二进制 STL（bytes）。

    Args:
        H: ``grid x grid`` thickness matrix in mm. / mm 厚度矩阵。
        plate_length_mm: physical side length of the (square) plate. / 方板物理边长。
        min_thickness_mm: floor applied to every cell so no zero-height boxes. /
            每个 cell 的最小厚度下限，避免零高长方体。
        smooth_sigma_cells: if > 0, gaussian-smooth H first. / >0 则先高斯平滑。
        header: ASCII tag written into the 80-byte STL header. / 写入 STL 头的标签。
    """
    H = np.asarray(H, dtype=float)
    if H.ndim != 2 or H.shape[0] != H.shape[1] or H.shape[0] < 2:
        raise HFieldExportError(
            f"Thickness field must be a square 2D grid, got shape {H.shape}. / "
            f"厚度场必须是方形二维网格，实际形状 {H.shape}。")
    if not np.all(np.isfinite(H)):
        raise HFieldExportError("Thickness field contains non-finite values. / 厚度场含非有限值。")

    if smooth_sigma_cells and smooth_sigma_cells > 0:
        H = smooth_h_field(H, sigma_cells=float(smooth_sigma_cells))

    if min_thickness_mm > 0:
        H = np.maximum(H, float(min_thickness_mm))
    if float(H.max()) <= 0:
        raise HFieldExportError("All thicknesses are <= 0; nothing to print. / 全部厚度<=0，无可打印实体。")

    grid = int(H.shape[0])
    cell = float(plate_length_mm) / grid

    triangles: list[tuple] = []
    # Row i -> y axis, col j -> x axis. Bottom of every box at z=0. /
    # 行 i 对应 y，列 j 对应 x；每个长方体底部在 z=0。
    for i in range(grid):
        y0 = i * cell
        y1 = y0 + cell
        for j in range(grid):
            h = float(H[i, j])
            if h <= 0:
                continue
            x0 = j * cell
            x1 = x0 + cell
            triangles.extend(_box_triangles(x0, x1, y0, y1, 0.0, h))

    if not triangles:
        raise HFieldExportError("No printable cells. / 没有可打印的 cell。")

    buf = BytesIO()
    head = header.encode("ascii", "ignore")[:80]
    buf.write(head + b"\x00" * (80 - len(head)))
    buf.write(struct.pack("<I", len(triangles)))
    for p0, p1, p2 in triangles:
        nx, ny, nz = _triangle_normal(p0, p1, p2)
        buf.write(struct.pack("<3f", nx, ny, nz))
        buf.write(struct.pack("<3f", *p0))
        buf.write(struct.pack("<3f", *p1))
        buf.write(struct.pack("<3f", *p2))
        buf.write(struct.pack("<H", 0))
    return buf.getvalue()
