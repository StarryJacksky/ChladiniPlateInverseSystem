from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from src.topology_grammar.primitives import TopologyPrimitive  # 导出拓扑基元数据结构 / Export topology primitive data structure
from src.topology_grammar.primitives import default_actuator_rows  # 导出默认激振器行 / Export default actuator rows
from src.topology_grammar.primitives import default_frequency_row  # 导出默认频率行 / Export default frequency row
from src.topology_grammar.primitives import default_support_row  # 导出默认支撑行 / Export default support row
from src.topology_grammar.primitives import write_operator_contract_csvs  # 导出算子合同写入函数 / Export operator-contract writer

__all__ = ["TopologyPrimitive", "default_actuator_rows", "default_frequency_row", "default_support_row", "write_operator_contract_csvs"]  # 定义公开 API / Define public API
