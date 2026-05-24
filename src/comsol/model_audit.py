from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
import zipfile  # 导入 MPH 压缩包读取工具 / Import MPH archive reader
from pathlib import Path  # 导入路径工具 / Import path utilities
from xml.etree import ElementTree  # 导入 XML 解析工具 / Import XML parser


def read_dmodel_xml(mph_path: str | Path) -> ElementTree.Element:  # 读取 MPH 内部模型 XML / Read internal model XML from MPH
    with zipfile.ZipFile(mph_path) as archive:  # 打开 MPH 压缩包 / Open MPH archive
        xml_bytes = archive.read("dmodel.xml")  # 读取主模型 XML / Read main model XML
    return ElementTree.fromstring(xml_bytes)  # 解析并返回 XML 根节点 / Parse and return XML root


def list_global_parameters(root: ElementTree.Element) -> list[dict[str, str]]:  # 列出全局参数 / List global parameters
    rows = []  # 创建参数列表 / Create parameter list
    for item in root.findall(".//ModelParam//expressions"):  # 遍历参数表达式 / Iterate parameter expressions
        rows.append({"name": item.attrib.get("name", ""), "expr": item.attrib.get("expr", "")})  # 保存参数名和值 / Save parameter name and value
    return rows  # 返回参数列表 / Return parameter list


def list_physics_features(root: ElementTree.Element) -> list[dict]:  # 列出物理场特征 / List physics features
    features = []  # 创建特征列表 / Create feature list
    for item in root.findall(".//PhysicsFeature"):  # 遍历物理场特征 / Iterate physics features
        params = {}  # 创建参数字典 / Create parameter dictionary
        for param in item.findall("./param"):  # 遍历特征参数 / Iterate feature parameters
            params[param.attrib.get("param", "")] = param.attrib.get("value", "")  # 保存参数值 / Save parameter value
        selections = []  # 创建选择列表 / Create selection list
        for selection in item.findall("./selection/explicit"):  # 遍历显式选择 / Iterate explicit selections
            selections.append(dict(selection.attrib))  # 保存选择属性 / Save selection attributes
        features.append({"tag": item.attrib.get("tag", ""), "op": item.attrib.get("op", ""), "name": item.attrib.get("name", ""), "params": params, "selections": selections})  # 保存特征 / Save feature
    return features  # 返回特征列表 / Return feature list


def audit_mph_model(mph_path: str | Path) -> dict:  # 审计 MPH 模型 / Audit MPH model
    root = read_dmodel_xml(mph_path)  # 读取模型 XML / Read model XML
    parameters = list_global_parameters(root)  # 列出全局参数 / List global parameters
    features = list_physics_features(root)  # 列出物理特征 / List physics features
    thickness_features = [item for item in features if item["op"] == "ThicknessOffset"]  # 筛选厚度特征 / Filter thickness features
    fixed_features = [item for item in features if item["op"] == "Fixed"]  # 筛选固定约束 / Filter fixed constraints
    return {"model_path": str(mph_path), "parameters": parameters, "thickness_features": thickness_features, "fixed_features": fixed_features}  # 返回审计结果 / Return audit result


def save_model_audit(audit: dict, output_path: str | Path) -> Path:  # 保存模型审计 / Save model audit
    path = Path(output_path)  # 转换输出路径 / Convert output path
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    with path.open("w", encoding="utf-8") as file_obj:  # 打开输出文件 / Open output file
        json.dump(audit, file_obj, indent=2, ensure_ascii=False)  # 写入 JSON / Write JSON
    return path  # 返回输出路径 / Return output path
