from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
from dataclasses import dataclass  # 导入数据类工具 / Import dataclass helper
from pathlib import Path  # 导入路径工具 / Import path utilities


@dataclass(frozen=True)  # 声明不可变数据类 / Declare immutable dataclass
class TopologyPrimitive:  # 定义拓扑基元 / Define topology primitive
    id: int  # 基元编号 / Primitive identifier
    type: str  # 基元类型 / Primitive type
    x_mm: float  # 中心 x 坐标毫米值 / Centre x coordinate in millimetres
    y_mm: float  # 中心 y 坐标毫米值 / Centre y coordinate in millimetres
    length_mm: float  # 长度毫米值 / Length in millimetres
    width_mm: float  # 宽度毫米值 / Width in millimetres
    angle_deg: float  # 旋转角度 / Rotation angle in degrees
    depth_or_height_mm: float | str  # 深度或高度 / Depth or height

    def as_row(self) -> dict[str, object]:  # 转换为 CSV 行 / Convert to CSV row
        return {"id": int(self.id), "type": str(self.type), "x_mm": float(self.x_mm), "y_mm": float(self.y_mm), "length_mm": float(self.length_mm), "width_mm": float(self.width_mm), "angle_deg": float(self.angle_deg), "depth_or_height_mm": self.depth_or_height_mm}  # 返回行字典 / Return row dictionary


def default_support_row(config: dict) -> dict[str, float]:  # 构造默认支撑参数 / Build default support parameters
    radius = float(config.get("project", {}).get("center_clamp_radius_mm", 8.0))  # 读取中心夹持半径 / Read centre clamp radius
    return {"center_x_mm": 0.0, "center_y_mm": 0.0, "clamp_radius_mm": radius}  # 返回默认中心支撑 / Return default centre support


def default_actuator_rows() -> list[dict[str, float]]:  # 构造默认激振器参数 / Build default actuator parameters
    return [{"id": 1, "x_mm": 0.0, "y_mm": 0.0, "amplitude": 1.0, "phase_deg": 0.0}]  # 返回单中心激振器 / Return one centre actuator


def default_frequency_row(config: dict) -> dict[str, float]:  # 构造默认驱动频率参数 / Build default drive-frequency parameters
    frequency_min = float(config.get("simulation", {}).get("frequency_min_hz", 0.0))  # 读取最小频率 / Read minimum frequency
    frequency_max = float(config.get("simulation", {}).get("frequency_max_hz", 1000.0))  # 读取最大频率 / Read maximum frequency
    drive = 0.5 * (frequency_min + frequency_max) if frequency_max > frequency_min else max(1.0, frequency_max)  # 选择中点频率 / Choose midpoint frequency
    return {"drive_frequency_hz": float(drive), "damping_ratio": 0.015, "force_sigma_mm": 2.5}  # 返回默认频率行 / Return default frequency row


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> Path:  # 写入通用 CSV / Write generic CSV
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    with path.open("w", encoding="utf-8", newline="") as file_obj:  # 打开输出文件 / Open output file
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)  # 创建字典写入器 / Create dictionary writer
        writer.writeheader()  # 写入表头 / Write header
        for row in rows:  # 遍历行数据 / Iterate rows
            writer.writerow(row)  # 写入一行 / Write one row
    return path  # 返回输出路径 / Return output path


def write_topology_primitives(path: str | Path, primitives: list[TopologyPrimitive] | None = None) -> Path:  # 写入拓扑基元合同 / Write topology primitive contract
    rows = [primitive.as_row() for primitive in (primitives or [])]  # 转换基元为行 / Convert primitives to rows
    return write_csv(Path(path), ["id", "type", "x_mm", "y_mm", "length_mm", "width_mm", "angle_deg", "depth_or_height_mm"], rows)  # 写入拓扑 CSV / Write topology CSV


def write_support_parameters(path: str | Path, config: dict) -> Path:  # 写入支撑参数合同 / Write support parameter contract
    return write_csv(Path(path), ["center_x_mm", "center_y_mm", "clamp_radius_mm"], [default_support_row(config)])  # 写入支撑 CSV / Write support CSV


def write_actuator_parameters(path: str | Path, rows: list[dict[str, float]] | None = None) -> Path:  # 写入激振器参数合同 / Write actuator parameter contract
    return write_csv(Path(path), ["id", "x_mm", "y_mm", "amplitude", "phase_deg"], rows or default_actuator_rows())  # 写入激振器 CSV / Write actuator CSV


def write_frequency_parameters(path: str | Path, config: dict, row: dict[str, float] | None = None) -> Path:  # 写入频率参数合同 / Write frequency parameter contract
    return write_csv(Path(path), ["drive_frequency_hz", "damping_ratio", "force_sigma_mm"], [row or default_frequency_row(config)])  # 写入频率 CSV / Write frequency CSV


def write_operator_contract_csvs(candidate_dir: str | Path, config: dict, primitives: list[TopologyPrimitive] | None = None, actuator_rows: list[dict[str, float]] | None = None, frequency_row: dict[str, float] | None = None) -> dict[str, Path]:  # 写入完整算子塑形合同 / Write full operator-sculpting contract
    path = Path(candidate_dir)  # 转换候选目录 / Convert candidate directory
    topology_path = path / "topology_primitives.csv"  # 构造拓扑合同路径 / Build topology contract path
    support_path = path / "support_parameters.csv"  # 构造支撑合同路径 / Build support contract path
    actuator_path = path / "actuator_parameters.csv"  # 构造激振器合同路径 / Build actuator contract path
    frequency_path = path / "frequency_parameters.csv"  # 构造频率合同路径 / Build frequency contract path
    if primitives is not None or not topology_path.exists():  # 仅在显式传入或缺失时写拓扑 / Write topology only when explicit or missing
        write_topology_primitives(topology_path, primitives)  # 写入拓扑合同 / Write topology contract
    if not support_path.exists():  # 检查支撑合同是否缺失 / Check whether support contract is missing
        write_support_parameters(support_path, config)  # 写入默认支撑合同 / Write default support contract
    if actuator_rows is not None or not actuator_path.exists():  # 仅在显式传入或缺失时写激振器 / Write actuators only when explicit or missing
        write_actuator_parameters(actuator_path, actuator_rows)  # 写入激振器合同 / Write actuator contract
    if frequency_row is not None or not frequency_path.exists():  # 仅在显式传入或缺失时写频率 / Write frequency only when explicit or missing
        write_frequency_parameters(frequency_path, config, frequency_row)  # 写入频率合同 / Write frequency contract
    return {"topology_primitives": topology_path, "support_parameters": support_path, "actuator_parameters": actuator_path, "frequency_parameters": frequency_path}  # 返回合同路径 / Return contract paths
