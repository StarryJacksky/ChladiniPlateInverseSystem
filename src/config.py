from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from ast import literal_eval  # 导入安全字面量解析 / Import safe literal parser
from pathlib import Path  # 导入路径工具 / Import path utilities

try:  # 尝试使用标准 YAML 库 / Try to use standard YAML library
    import yaml  # 导入 YAML 读取库 / Import YAML reader
except ModuleNotFoundError:  # 处理依赖未安装情况 / Handle missing dependency
    yaml = None  # 标记 YAML 库不可用 / Mark YAML library as unavailable


def parse_scalar(value: str):  # 解析简单配置值 / Parse simple config value
    text = value.split("#", 1)[0].strip()  # 移除行内注释 / Remove inline comment
    if text.lower() == "true":  # 识别布尔真值 / Detect boolean true
        return True  # 返回真值 / Return true
    if text.lower() == "false":  # 识别布尔假值 / Detect boolean false
        return False  # 返回假值 / Return false
    if text.startswith("[") and text.endswith("]"):  # 识别列表文本 / Detect list text
        return literal_eval(text)  # 安全解析列表 / Safely parse list
    if text.startswith('"') and text.endswith('"'):  # 识别双引号字符串 / Detect double-quoted string
        return text.strip('"')  # 返回去引号字符串 / Return unquoted string
    try:  # 尝试解析数字 / Try to parse number
        return int(text) if "." not in text and "e" not in text.lower() else float(text)  # 返回整数或浮点数 / Return integer or float
    except ValueError:  # 处理普通字符串 / Handle plain string
        return text  # 返回原始文本 / Return raw text


def simple_yaml_load(text: str) -> dict:  # 轻量 YAML 解析器 / Lightweight YAML parser
    config = {}  # 创建配置字典 / Create configuration dictionary
    current_section = None  # 初始化当前分区 / Initialise current section
    for raw_line in text.splitlines():  # 遍历配置行 / Iterate configuration lines
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):  # 跳过空行和注释 / Skip blanks and comments
            continue  # 继续下一行 / Continue to next line
        if not raw_line.startswith(" ") and raw_line.rstrip().endswith(":"):  # 识别顶层分区 / Detect top-level section
            current_section = raw_line.strip().rstrip(":")  # 保存分区名称 / Store section name
            config[current_section] = {}  # 创建分区字典 / Create section dictionary
            continue  # 继续下一行 / Continue to next line
        if current_section is None:  # 检查是否缺少分区 / Check missing section
            raise ValueError("Config value found before section. / 配置值出现在分区之前。")  # 抛出格式错误 / Raise format error
        key, value = raw_line.strip().split(":", 1)  # 拆分键值 / Split key and value
        config[current_section][key.strip()] = parse_scalar(value)  # 写入解析后的值 / Store parsed value
    return config  # 返回配置字典 / Return configuration dictionary


def load_config(config_path: str | Path = "config.yaml") -> dict:  # 读取配置文件 / Load configuration file
    path = Path(config_path)  # 转换为路径对象 / Convert to a path object
    text = path.read_text(encoding="utf-8")  # 读取配置文本 / Read configuration text
    if yaml is not None:  # 判断 YAML 库是否可用 / Check whether YAML library is available
        config = yaml.safe_load(text)  # 安全读取 YAML / Safely load YAML
    else:  # 使用内置解析器 / Use built-in parser
        config = simple_yaml_load(text)  # 读取简单 YAML / Load simple YAML
    return config  # 返回配置字典 / Return configuration dictionary


def ensure_project_dirs(config: dict) -> None:  # 创建项目所需目录 / Create required project directories
    paths = config["paths"]  # 读取路径配置 / Read path configuration
    Path(paths["processed_targets_dir"]).mkdir(parents=True, exist_ok=True)  # 创建目标输出目录 / Create target output directory
    Path(paths["candidates_dir"]).mkdir(parents=True, exist_ok=True)  # 创建候选目录 / Create candidate directory
    Path(paths["comsol_exports_dir"]).mkdir(parents=True, exist_ok=True)  # 创建 COMSOL 导出目录 / Create COMSOL export directory
    Path(paths["target_pattern"]).parent.mkdir(parents=True, exist_ok=True)  # 创建目标图目录 / Create target image directory
