from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import base64  # 导入 Base64 解码工具 / Import Base64 decoding tools
import copy  # 导入深拷贝工具 / Import deepcopy helper
import csv  # 导入 CSV 工具 / Import CSV utilities
import html  # 导入 HTML 转义工具 / Import HTML escaping tools
import json  # 导入 JSON 工具 / Import JSON tools
import re  # 导入正则校验工具 / Import regex validation tools
import threading  # 导入后台线程工具 / Import background threading tools
import zipfile  # 导入 ZIP 打包工具 / Import ZIP packaging tools
from datetime import datetime  # 导入时间戳工具 / Import timestamp helper
from http import HTTPStatus  # 导入 HTTP 状态码 / Import HTTP status codes
from http.server import BaseHTTPRequestHandler  # 导入请求处理基类 / Import request handler base class
from http.server import ThreadingHTTPServer  # 导入多线程 HTTP 服务 / Import threaded HTTP server
from io import BytesIO  # 导入内存字节流 / Import in-memory byte stream
from pathlib import Path  # 导入路径工具 / Import path utilities
from urllib.parse import parse_qs  # 导入查询参数解析 / Import query-string parser
from urllib.parse import urlparse  # 导入 URL 解析工具 / Import URL parser

from PIL import Image  # 导入图像库 / Import image library

from src.config import load_config  # 导入配置读取函数 / Import configuration loader
from src.target.analyse_target import save_target_analysis  # 导入目标分析保存函数 / Import target-analysis saver
from src.target.preprocess_target import preprocess_target  # 导入目标预处理函数 / Import target preprocessing function


CANDIDATE_ID_RE = re.compile(r"^candidate_\d{3}_\d{4}$")  # 定义候选编号格式 / Define candidate-id format
PRODUCTION_CANDIDATE_RE = re.compile(r"^[A-Za-z0-9_\-]{1,80}$")  # 生产候选编号格式（更宽松） / Looser production candidate-id format
PRODUCTION_ASSET_RE = re.compile(r"^[A-Za-z0-9_\-]+\.(?:png|svg)$")  # 资源文件名格式 / Asset filename format


MATERIAL_LIMITS = {  # 定义前端材料参数范围 / Define frontend material parameter ranges
    "density_kg_m3": (100.0, 25000.0),  # 密度范围 / Density range
    "poisson_ratio": (0.0, 0.49),  # 泊松比范围 / Poisson-ratio range
    "youngs_modulus_pa": (1.0e6, 5.0e12),  # 杨氏模量范围 / Young's modulus range
    "thermal_conductivity_w_mk": (1.0e-4, 5000.0),  # 导热系数范围 / Thermal-conductivity range
    "heat_capacity_j_kgk": (1.0, 10000.0),  # 热容范围 / Heat-capacity range
    "thermal_expansion_1_k": (0.0, 1.0e-3),  # 热膨胀范围 / Thermal-expansion range
    "stiffness_ratio": (1.0, 4.0),  # 各向异性比 E_||/E_⊥ 范围 / Stiffness anisotropy ratio range
    "shear_ratio": (0.3, 3.0),  # 剪切模量相对比范围 / Shear modulus ratio range
}  # 结束材料参数范围 / End material parameter ranges
SCORING_LIMITS = {  # 定义评分参数范围 / Define scoring parameter ranges
    "roughness_weight": (0.0, 10.0),  # 粗糙度权重范围 / Roughness-weight range
    "mass_weight": (0.0, 10.0),  # 质量权重范围 / Mass-weight range
    "frequency_weight": (0.0, 10.0),  # 频率权重范围 / Frequency-weight range
    "frequency_min_hz": (0.0, 100000.0),  # 最小频率范围 / Minimum-frequency range
    "frequency_max_hz": (0.0, 100000.0),  # 最大频率范围 / Maximum-frequency range
}  # 结束评分参数范围 / End scoring parameter ranges
RETENTION_LIMITS = {  # 定义产物保留参数范围 / Define artifact retention parameter ranges
    "keep_latest_generations": (0, 999),  # 最新代数范围 / Newest-generation range
    "keep_recent_days": (0.0, 3650.0),  # 最近天数范围 / Recent-days range
}  # 结束产物保留参数范围 / End artifact retention ranges

WORKFLOW_LOCK = threading.Lock()  # 创建工作流状态锁 / Create workflow state lock
WORKFLOW_CANCEL_EVENT = threading.Event()  # 创建工作流取消事件 / Create workflow cancellation event
WORKFLOW_EVENT_LIMIT = 80  # 限制保存的工作流事件数量 / Limit stored workflow event count
WORKFLOW_JOB = {"running": False, "cancel_requested": False, "stage": "idle", "message": "Idle", "result": None, "error": "", "current_candidate": "", "current_index": 0, "total": 0, "events": []}  # 创建工作流状态 / Create workflow state


def update_workflow_state(**updates) -> None:  # 更新工作流状态 / Update workflow state
    with WORKFLOW_LOCK:  # 锁定共享状态 / Lock shared state
        WORKFLOW_JOB.update(updates)  # 写入状态更新 / Apply state updates


def workflow_snapshot() -> dict:  # 获取工作流状态快照 / Get workflow state snapshot
    with WORKFLOW_LOCK:  # 锁定共享状态 / Lock shared state
        snapshot = dict(WORKFLOW_JOB)  # 创建浅层状态副本 / Create shallow state copy
        snapshot["events"] = list(WORKFLOW_JOB.get("events", []))  # 复制事件列表 / Copy event list
        return snapshot  # 返回状态副本 / Return state copy


def workflow_state_path(config: dict) -> Path:  # 获取工作流状态文件路径 / Get workflow state file path
    state_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取状态目录 / Read state directory
    state_dir.mkdir(parents=True, exist_ok=True)  # 确保状态目录存在 / Ensure state directory exists
    return state_dir / "workflow_state.json"  # 返回状态文件路径 / Return state file path


def persist_workflow_state(config: dict) -> None:  # 持久化工作流状态 / Persist workflow state
    path = workflow_state_path(config)  # 获取状态文件路径 / Get state file path
    temporary_path = path.with_suffix(".tmp")  # 构造临时文件路径 / Build temporary file path
    temporary_path.write_text(json.dumps(workflow_snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")  # 写入临时状态文件 / Write temporary state file
    temporary_path.replace(path)  # 原子替换状态文件 / Atomically replace state file


def normalise_workflow_event(event: dict) -> dict:  # 规范化工作流事件 / Normalise workflow event
    return {"time": event.get("time") or datetime.now().isoformat(timespec="seconds"), "stage": event.get("stage", ""), "message": event.get("message", ""), "current_candidate": event.get("current_candidate", ""), "current_index": int(event.get("current_index", 0) or 0), "total": int(event.get("total", 0) or 0), "log_path": event.get("log_path", "")}  # 返回标准事件 / Return standard event


def update_and_persist_workflow_state(config: dict, event: dict | None = None, **updates) -> None:  # 更新并持久化工作流状态 / Update and persist workflow state
    with WORKFLOW_LOCK:  # 锁定共享状态 / Lock shared state
        WORKFLOW_JOB.update(updates)  # 写入状态更新 / Apply state updates
        if event is not None:  # 检查是否需要追加事件 / Check whether an event should be appended
            events = list(WORKFLOW_JOB.get("events", []))  # 复制现有事件 / Copy existing events
            events.append(normalise_workflow_event(event))  # 追加标准事件 / Append normalised event
            WORKFLOW_JOB["events"] = events[-WORKFLOW_EVENT_LIMIT:]  # 截断旧事件 / Trim old events
    persist_workflow_state(config)  # 写入磁盘状态 / Write disk state


def restore_workflow_state(config: dict) -> None:  # 恢复持久化工作流状态 / Restore persisted workflow state
    path = workflow_state_path(config)  # 获取状态文件路径 / Get state file path
    if not path.exists():  # 检查状态文件是否存在 / Check whether state file exists
        persist_workflow_state(config)  # 写入初始状态 / Write initial state
        return  # 结束恢复 / Finish restore
    try:  # 捕获状态读取错误 / Catch state loading errors
        state = json.loads(path.read_text(encoding="utf-8"))  # 读取状态文件 / Read state file
    except json.JSONDecodeError:  # 处理状态文件损坏 / Handle corrupt state file
        persist_workflow_state(config)  # 用当前内存状态覆盖 / Overwrite with current memory state
        return  # 结束恢复 / Finish restore
    state["events"] = list(state.get("events", []))[-WORKFLOW_EVENT_LIMIT:]  # 恢复事件列表 / Restore event list
    if state.get("running"):  # 检查是否为重启前运行中状态 / Check stale running state before restart
        state.update({"running": False, "cancel_requested": False, "stage": "interrupted", "message": "Previous workflow was interrupted by a UI/server restart. / 上一次工作流被 UI/服务重启中断。", "error": "Workflow interrupted by restart. / 工作流被重启中断。", "current_candidate": "", "current_index": 0, "total": 0})  # 标记中断状态 / Mark interrupted state
        state["events"].append(normalise_workflow_event({"stage": "interrupted", "message": state["message"]}))  # 记录中断事件 / Record interruption event
    state["cancel_requested"] = bool(state.get("cancel_requested", False))  # 规范取消标记 / Normalize cancellation flag
    update_workflow_state(**state)  # 恢复到内存状态 / Restore into memory state
    persist_workflow_state(config)  # 写回规范化状态 / Write normalized state


def run_workflow_thread(config: dict, payload: dict) -> None:  # 后台运行自动工作流 / Run automatic workflow in background
    from src.optimisation.workflow import run_design_workflow  # 延迟导入完整工作流 / Lazily import full workflow
    from src.optimisation.workflow import WorkflowCancelled  # 延迟导入取消异常 / Lazily import cancellation exception
    try:  # 捕获后台工作流错误 / Catch background workflow errors
        workflow_config = copy.deepcopy(config)  # 复制配置避免污染运行时 / Copy config to avoid runtime mutation
        workflow_payload = validate_workflow_payload(payload, workflow_config)  # 校验工作流载荷 / Validate workflow payload
        generation = workflow_payload["generation"]  # 读取代数编号 / Read generation index
        limit = workflow_payload["limit"]  # 读取候选数量 / Read candidate limit
        num_modes = workflow_payload["num_modes"]  # 读取模态数量 / Read mode count
        simulate = workflow_payload["simulate"]  # 读取是否仿真 / Read simulation flag
        iterations = workflow_payload["iterations"]  # 读取迭代次数 / Read iteration count
        def cancel_check() -> bool:  # 定义取消检查函数 / Define cancellation check function
            return WORKFLOW_CANCEL_EVENT.is_set()  # 返回取消事件状态 / Return cancellation event state
        def progress(event: dict) -> None:  # 定义进度回调 / Define progress callback
            if cancel_check():  # 检查是否请求取消 / Check whether cancellation requested
                raise WorkflowCancelled("Workflow cancelled by user. / 用户已取消工作流。")  # 抛出取消异常 / Raise cancellation exception
            update_and_persist_workflow_state(config, event=event, stage=event.get("stage", ""), message=event.get("message", ""), current_candidate=event.get("current_candidate", ""), current_index=int(event.get("current_index", 0) or 0), total=int(event.get("total", 0) or 0), result=event if event.get("stage") == "done" else workflow_snapshot().get("result"))  # 更新进度状态 / Update progress state
        result = run_design_workflow(workflow_config, generation, limit, num_modes, simulate, progress, cancel_check, iterations)  # 运行完整工作流 / Run complete workflow
        update_and_persist_workflow_state(config, running=False, cancel_requested=False, stage="done", message="Workflow complete. / 工作流完成。", result=result, error="", current_candidate="", current_index=0, total=0)  # 写入完成状态 / Store completion state
    except WorkflowCancelled as exc:  # 处理工作流取消 / Handle workflow cancellation
        WORKFLOW_CANCEL_EVENT.clear()  # 清除取消事件 / Clear cancellation event
        update_and_persist_workflow_state(config, event={"stage": "cancelled", "message": str(exc)}, running=False, cancel_requested=False, stage="cancelled", message=str(exc), error="", current_candidate="", current_index=0, total=0)  # 写入取消状态 / Store cancelled state
    except Exception as exc:  # 处理工作流异常 / Handle workflow exception
        WORKFLOW_CANCEL_EVENT.clear()  # 清除取消事件 / Clear cancellation event
        update_and_persist_workflow_state(config, event={"stage": "error", "message": str(exc)}, running=False, cancel_requested=False, stage="error", message=str(exc), error=str(exc))  # 写入错误状态 / Store error state


def discover_candidate_mph_files(candidate_id: str) -> list[dict]:  # 收集候选对应的 .mph 文件 / Collect .mph files for a candidate
    """Find every .mph file related to a given candidate id under data/comsol_exports/."""
    root = project_root() / "data" / "comsol_exports"  # COMSOL exports root / 导出根目录
    if not root.exists():  # 不存在直接空 / Empty if missing
        return []  # / Empty
    if not candidate_id or any(ch in candidate_id for ch in "/\\:*?<>|\""):  # 防注入 / Sanitize
        raise ValueError("Invalid candidate id. / 候选编号非法。")  # / Reject
    candidates: list[dict] = []  # 结果列表 / Result list
    # Direct match (candidate_id is itself an export dir): / 候选本身是导出目录
    direct_dir = root / candidate_id  # / Direct dir
    if direct_dir.is_dir():  # / If dir
        for mph in sorted(direct_dir.rglob("*.mph")):  # 递归 .mph / Recurse for .mph
            if mph.name.startswith("debug_") or "recovery" in {part.lower() for part in mph.parts}:  # 跳过 debug / recovery / Skip debug & recovery
                continue  # / Skip
            kind = "eigenfrequency" if "eigenfrequency" in mph.parent.name else ("forced_response" if "forced_response" in mph.parent.name else "other")  # 类型 / Kind
            candidates.append({  # 加入 / Append
                "path": str(mph),  # 绝对路径 / Absolute path
                "relative_path": str(mph.relative_to(project_root())),  # 相对项目根 / Relative to project root
                "kind": kind,  # 模型类型 / Model kind
                "label": f"{candidate_id} — {kind}",  # 展示名 / Display label
                "variant_dir": direct_dir.name,  # / Variant dir name
                "size_mb": round(mph.stat().st_size / 1024.0 / 1024.0, 2),  # 大小 MB / Size MB
            })
    # Sibling variant dirs that start with the candidate id or contain it: / 同候选派生的 variant
    for variant_dir in sorted(root.iterdir()):  # 遍历同级 / Iterate siblings
        if not variant_dir.is_dir():  # / Skip files
            continue  # / Skip
        if variant_dir.name == candidate_id:  # 已处理 / Already handled
            continue  # / Skip
        if candidate_id not in variant_dir.name:  # 不相关 / Unrelated
            continue  # / Skip
        for mph in sorted(variant_dir.rglob("*.mph")):  # 递归 / Recurse
            if mph.name.startswith("debug_") or "recovery" in {part.lower() for part in mph.parts}:  # / Skip
                continue  # / Skip
            kind = "eigenfrequency" if "eigenfrequency" in mph.parent.name else ("forced_response" if "forced_response" in mph.parent.name else "other")  # / Kind
            # Extract a friendly suffix like "f165Hz" or "eig30" from variant dir name: / 友好后缀
            suffix = variant_dir.name.replace(candidate_id, "").strip("_- ")  # / Suffix
            candidates.append({  # / Append
                "path": str(mph),  # / Path
                "relative_path": str(mph.relative_to(project_root())),  # / Relative
                "kind": kind,  # / Kind
                "label": f"{kind} — {suffix or variant_dir.name}",  # / Display label
                "variant_dir": variant_dir.name,  # / Variant dir
                "size_mb": round(mph.stat().st_size / 1024.0 / 1024.0, 2),  # / Size
            })
    return candidates  # 返回列表 / Return list


def _variant_matches_design(variant_dir: str, design_id: str) -> bool:
    if variant_dir == f"prod_eig_{design_id}":
        return True
    if "_comsol_" in variant_dir:
        prefix = variant_dir.split("_comsol_", 1)[0]
        return prefix.endswith("_" + design_id)
    return variant_dir == design_id


def _frequency_from_variant_dir(variant_dir: str) -> float | None:
    match = re.search(r"_f(\d+(?:p\d+)?)Hz(?:$|_)", variant_dir)
    if not match:
        return None
    try:
        return float(match.group(1).replace("p", "."))
    except ValueError:
        return None


def _best_phase2_entry(summary: dict) -> dict | None:
    phase2 = summary.get("phase2") or {}
    history = phase2.get("history") or []
    best_iter = phase2.get("best_iter")
    for row in history:
        if row.get("iter") == best_iter:
            return row
    if history:
        def score(row: dict) -> float:
            broad = ((row.get("best_composite") or {}).get("broad") or {})
            return float(broad.get("enrich") or -1.0)
        return max(history, key=score)
    return None


def _best_forced_frequency(summary: dict, selected_entry: dict | None, design_id: str) -> float | None:
    best_composite = (selected_entry or {}).get("best_composite") or (summary.get("phase1") or {}).get("best_composite") or {}
    subset = [str(item) for item in (best_composite.get("subset") or [])]
    if not subset:
        return None
    per_freq = (summary.get("phase1") or {}).get("per_freq") or {}
    if design_id == str(summary.get("candidate_id", "")):
        scored = []
        for key in subset:
            broad = (per_freq.get(key) or {}).get("broad") or {}
            if broad.get("enrich") is not None:
                scored.append((float(broad.get("enrich")), key))
        if scored:
            return float(max(scored, key=lambda item: item[0])[1])
    return float(subset[0])


def _production_summary_for_candidate(candidate_id: str) -> dict | None:
    summary_path = project_root() / "reports" / "production" / candidate_id / "production_summary.json"
    if not summary_path.exists():
        return None
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def select_best_candidate_mph_file(candidate_id: str) -> dict:
    files = discover_candidate_mph_files(candidate_id)
    if not files:
        raise FileNotFoundError(f"No .mph saved for candidate {candidate_id}. Re-run with COMSOL enabled to generate one. / 候选 {candidate_id} 没有保存的 .mph 文件，请在启用 COMSOL 的情况下重新运行以生成。")
    if len(files) == 1:
        chosen = dict(files[0])
        chosen["selection_reason"] = "Only saved COMSOL model for this candidate. / 该候选唯一保存的 COMSOL 模型。"
        return chosen

    summary = _production_summary_for_candidate(candidate_id)
    design_id = candidate_id
    target_freq = None
    if summary:
        selected_entry = _best_phase2_entry(summary)
        design_id = str((selected_entry or {}).get("candidate_id") or summary.get("candidate_id") or candidate_id)
        target_freq = _best_forced_frequency(summary, selected_entry, design_id)

    design_files = [file for file in files if _variant_matches_design(str(file.get("variant_dir", "")), design_id)] or files
    forced = [file for file in design_files if file.get("kind") == "forced_response"]
    if forced:
        if target_freq is not None:
            chosen = min(forced, key=lambda file: abs((_frequency_from_variant_dir(str(file.get("variant_dir", ""))) or target_freq) - target_freq))
            chosen = dict(chosen)
            chosen["selection_reason"] = f"Best production forced-response model near {target_freq:g} Hz. / 打开最接近最佳频率 {target_freq:g} Hz 的强迫响应模型。"
            return chosen
        chosen = max(forced, key=lambda file: Path(str(file["path"])).stat().st_mtime)
        chosen = dict(chosen)
        chosen["selection_reason"] = "Most recent forced-response COMSOL model. / 最新的强迫响应 COMSOL 模型。"
        return chosen

    eigen = [file for file in design_files if file.get("kind") == "eigenfrequency"]
    if eigen:
        chosen = max(eigen, key=lambda file: Path(str(file["path"])).stat().st_mtime)
        chosen = dict(chosen)
        chosen["selection_reason"] = "No forced-response model found; opening the eigenfrequency model. / 未找到强迫响应模型，打开特征频率模型。"
        return chosen

    chosen = max(files, key=lambda file: Path(str(file["path"])).stat().st_mtime)
    chosen = dict(chosen)
    chosen["selection_reason"] = "Fallback to the most recent saved COMSOL model. / 回退打开最新保存的 COMSOL 模型。"
    return chosen


def open_mph_in_comsol(config: dict, mph_path: str) -> dict:  # 用 COMSOL 打开 .mph / Launch COMSOL with .mph
    """Spawn COMSOL Multiphysics to open a saved .mph; returns spawn metadata."""
    project = project_root()  # 项目根 / Project root
    resolved = (project / mph_path).resolve() if not Path(mph_path).is_absolute() else Path(mph_path).resolve()  # 解析路径 / Resolve path
    if not resolved.exists():  # 文件不存在 / Missing file
        raise FileNotFoundError(f"MPH file not found: {resolved} / 未找到 MPH 文件：{resolved}")  # / Missing
    if resolved.suffix.lower() != ".mph":  # 后缀检查 / Suffix check
        raise ValueError("Only .mph files can be opened. / 仅支持打开 .mph 文件。")  # / Bad suffix
    try:  # 安全检查：限制只能打开项目目录下的 mph / Confine to project dir
        resolved.relative_to(project)  # / Confined
    except ValueError:  # / Outside
        raise ValueError("Refusing to open files outside the project directory. / 拒绝打开项目目录之外的文件。")  # / Refuse
    import subprocess  # 子进程 / Subprocess
    import platform  # 平台 / Platform
    system = platform.system()  # 平台名 / Platform name
    comsol_command = str(config.get("comsol", {}).get("comsol_command_path", "")).strip()  # 命令行入口 / CLI entry
    # 统一用 `comsol -open <file>`：根据 `comsol --help` 这是把 mph 加载进 Desktop GUI 的官方写法 / Per `comsol --help` this is the official desktop-open flag
    # 之前 `open -a "COMSOL Multiphysics.app" file` 只会启动空 GUI，COMSOL.app 不接受 LSItemContentTypes 文档参数 / `open -a` route doesn't pass docs to COMSOL.app
    if not comsol_command:  # macOS 上兜底找 /Applications/COMSOL*/Multiphysics/bin/comsol / macOS fallback search
        if system == "Darwin":  # / macOS
            for candidate in [
                Path("/Applications/COMSOL64/Multiphysics/bin/comsol"),
                Path("/Applications/COMSOL63/Multiphysics/bin/comsol"),
                Path("/Applications/COMSOL62/Multiphysics/bin/comsol"),
            ]:  # / Candidates
                if candidate.exists():  # / Exists
                    comsol_command = str(candidate)  # / Adopt
                    break  # / Stop
    if not comsol_command:  # 仍无 / Still missing
        raise RuntimeError("comsol.comsol_command_path is empty and no COMSOL was auto-detected. / 未配置 comsol_command_path 且无法自动发现 COMSOL。")  # / Bail
    if not Path(comsol_command).exists():  # 路径无效 / Bad path
        raise FileNotFoundError(f"COMSOL command not found: {comsol_command} / 未找到 COMSOL 命令：{comsol_command}")  # / Bail
    # 每次 spawn 用一份独立的 prefsdir/configuration，强制 COMSOL 当新实例处理；
    # 否则同一份 prefs 下后续启动会复用已开窗口（替换当前模型），用户已开的实例会丢失上下文。
    # Each spawn gets isolated prefsdir/configuration to force COMSOL to start as a fresh GUI instance;
    # otherwise sharing prefs makes a later launch hijack the existing window and replace its model.
    instances_root = project / "data" / "comsol_exports" / ".runtime_instances"  # 隔离根 / Isolation root
    instance_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")  # 唯一 id / Unique id
    instance_dir = instances_root / instance_id  # 当前实例 dir / Current instance dir
    prefs_dir = instance_dir / "prefs"  # / Prefs
    config_dir = instance_dir / "configuration"  # / Config
    tmp_dir = instance_dir / "tmp"  # / Tmp
    recovery_dir = instance_dir / "recovery"  # / Recovery
    for d in [prefs_dir, config_dir, tmp_dir, recovery_dir]:  # 建目录 / Mkdir
        d.mkdir(parents=True, exist_ok=True)  # / Mkdir
    cmd: list[str]  # 命令 / Command
    if system == "Windows":  # Windows / Windows
        cmd = [comsol_command, "-open", str(resolved),
               "-prefsdir", str(prefs_dir), "-configuration", str(config_dir),
               "-tmpdir", str(tmp_dir), "-recoverydir", str(recovery_dir)]  # / Cmd
    else:  # macOS / Linux / macOS & Linux
        cmd = [comsol_command, "-open", str(resolved),
               "-prefsdir", str(prefs_dir), "-configuration", str(config_dir),
               "-tmpdir", str(tmp_dir), "-recoverydir", str(recovery_dir)]  # / Cmd
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)  # 后台启动 / Background spawn
    return {  # 返回元数据 / Metadata
        "pid": proc.pid,  # 进程 PID / Spawned pid
        "command": cmd,  # 实际命令 / Actual command
        "mph_path": str(resolved),  # 实际路径 / Actual path
        "started_at": datetime.now().isoformat(timespec="seconds"),  # 启动时间 / Start time
    }


def validate_production_payload(payload: dict, config: dict) -> dict:  # 校验生产 pipeline 载荷 / Validate production pipeline payload
    stiffness_ratio = float(payload.get("stiffness_ratio", config.get("material", {}).get("stiffness_ratio", 3.0)))  # 各向异性比 / Stiffness ratio
    if stiffness_ratio < 1.0 or stiffness_ratio > 20.0:  # 检查范围 / Check range
        raise ValueError("stiffness_ratio must be between 1.0 and 20.0. / 各向异性比必须在 1.0 到 20.0 之间。")  # 范围错误 / Range error
    shear_ratio = float(payload.get("shear_ratio", config.get("material", {}).get("shear_ratio", 1.0)))  # 剪切比 / Shear ratio
    if shear_ratio < 0.3 or shear_ratio > 3.0:  # 检查范围 / Check range
        raise ValueError("shear_ratio must be between 0.3 and 3.0. / 剪切比必须在 0.3 到 3.0 之间。")  # 范围错误 / Range error
    w10_num_steps = int(payload.get("w10_num_steps", 300))  # W10 步数 / W10 steps
    if w10_num_steps < 30 or w10_num_steps > 2000:  # 检查范围 / Check range
        raise ValueError("w10_num_steps must be between 30 and 2000. / W10 步数必须在 30 到 2000 之间。")  # 范围错误 / Range error
    phase2_max_iters = int(payload.get("phase2_max_iters", 1))  # Phase 2 迭代数 / Phase 2 iters
    if phase2_max_iters < 0 or phase2_max_iters > 10:  # 检查范围 / Check range
        raise ValueError("phase2_max_iters must be between 0 and 10. / Phase 2 迭代数必须在 0 到 10 之间。")  # 范围错误 / Range error
    magic_str = str(payload.get("magic_off_resonance_hz", "165.0")).strip()  # 魔法频率 / Magic freqs
    try:
        magic_freqs = tuple(float(x.strip()) for x in magic_str.split(",") if x.strip())  # 解析逗号分隔 / Parse comma-separated
    except ValueError:
        raise ValueError("magic_off_resonance_hz must be comma-separated numbers. / 魔法频率必须是逗号分隔的数字。")  # 解析错误 / Parse error
    if not magic_freqs:  # 至少一个 / At least one
        magic_freqs = (165.0,)  # 默认 / Default
    candidate_id = str(payload.get("candidate_id", "production_design")).strip()  # 候选编号 / Candidate id
    if not candidate_id or any(ch in candidate_id for ch in "/\\:*?<>|\""):  # 合法字符 / Legal chars
        raise ValueError("candidate_id contains invalid characters. / 候选编号含非法字符。")  # 非法字符 / Bad chars
    return {  # 规范载荷 / Normalised payload
        "candidate_id": candidate_id,  # 候选 / Candidate
        "stiffness_ratio": stiffness_ratio,  # 各向异性 / Stiffness
        "shear_ratio": shear_ratio,  # 剪切 / Shear
        "w10_num_steps": w10_num_steps,  # 步数 / Steps
        "phase2_max_iters": phase2_max_iters,  # Phase 2 / Phase 2
        "magic_off_resonance_hz": magic_freqs,  # 魔法频率 / Magic freqs
        "skip_comsol": bool(payload.get("skip_comsol", False)),  # 跳过 COMSOL / Skip COMSOL
        "skip_phase2": bool(payload.get("skip_phase2", False)),  # 跳过 Phase 2 / Skip Phase 2
    }


def validate_material_sweep_payload(payload: dict, config: dict) -> dict:  # 校验材料预扫频载荷 / Validate material magic-frequency sweep payload
    material = config.get("material", {})  # 当前材料配置 / Current material config
    stiffness_ratio = float(payload.get("stiffness_ratio", material.get("stiffness_ratio", 1.05)))  # 各向异性比 / Stiffness ratio
    if stiffness_ratio < 1.0 or stiffness_ratio > 20.0:  # 检查范围 / Check range
        raise ValueError("stiffness_ratio must be between 1.0 and 20.0. / 各向异性比必须在 1.0 到 20.0 之间。")  # / Range error
    shear_ratio = float(payload.get("shear_ratio", material.get("shear_ratio", 1.0)))  # 剪切比 / Shear ratio
    if shear_ratio < 0.3 or shear_ratio > 3.0:  # 检查范围 / Check range
        raise ValueError("shear_ratio must be between 0.3 and 3.0. / 剪切比必须在 0.3 到 3.0 之间。")  # / Range error
    f_min_hz = float(payload.get("f_min_hz", 80.0))  # 起始频率 / Lower bound
    f_max_hz = float(payload.get("f_max_hz", 1500.0))  # 终止频率 / Upper bound
    if f_min_hz < 10.0 or f_min_hz > 10000.0:  # 检查范围 / Check range
        raise ValueError("f_min_hz must be between 10 and 10000 Hz. / 起始频率必须在 10 到 10000 Hz 之间。")  # / Range error
    if f_max_hz <= f_min_hz or f_max_hz > 20000.0:  # 检查范围 / Check range
        raise ValueError("f_max_hz must be greater than f_min_hz and at most 20000 Hz. / 终止频率必须大于起始且不超过 20000 Hz。")  # / Range error
    n_points = int(payload.get("n_points", 50))  # 扫描点数 / Sweep points
    if n_points < 5 or n_points > 500:  # 检查范围 / Check range
        raise ValueError("n_points must be between 5 and 500. / 扫描点数必须在 5 到 500 之间。")  # / Range error
    top_k = int(payload.get("top_k", 3))  # 返回数 / Top-K
    if top_k < 1 or top_k > 10:  # 检查范围 / Check range
        raise ValueError("top_k must be between 1 and 10. / 返回数必须在 1 到 10 之间。")  # / Range error
    return {  # 规范化载荷 / Normalised payload
        "stiffness_ratio": stiffness_ratio,
        "shear_ratio": shear_ratio,
        "f_min_hz": f_min_hz,
        "f_max_hz": f_max_hz,
        "n_points": n_points,
        "top_k": top_k,
    }


def run_production_pipeline_thread(config: dict, payload: dict) -> None:  # 后台运行生产 pipeline / Run production pipeline in background
    from src.optimisation.production_pipeline import build_default_pipeline_config, run_production_pipeline  # 延迟导入 / Lazy import
    from src.optimisation.workflow import WorkflowCancelled  # 复用取消异常 / Reuse cancellation exception
    try:  # 捕获异常 / Catch exceptions
        cfg = build_default_pipeline_config(  # 用 config.yaml production: 区段 + payload 覆盖构建 / Build from production: section + payload overrides
            "config.yaml",
            overrides={
                "default_candidate_id": payload["candidate_id"],  # 候选 / Candidate
                "stiffness_ratio": payload["stiffness_ratio"],  # 各向异性 / Stiffness
                "shear_ratio": payload["shear_ratio"],  # 剪切 / Shear
                "w10_num_steps": payload["w10_num_steps"],  # 步数 / Steps
                "magic_off_resonance_hz": payload["magic_off_resonance_hz"],  # 魔法频率 / Magic freqs
                "phase2_max_iters": payload["phase2_max_iters"],  # Phase 2 / Phase 2
                "skip_comsol": payload["skip_comsol"],  # 跳过 COMSOL / Skip COMSOL
                "skip_phase2": payload["skip_phase2"],  # 跳过 Phase 2 / Skip Phase 2
            },
        )
        cfg.candidate_id = payload["candidate_id"]  # 强制覆盖候选编号 / Force candidate id
        def cancel_check() -> bool:  # 取消检查 / Cancellation check
            return WORKFLOW_CANCEL_EVENT.is_set()  # / Event state
        def progress(event: dict) -> None:  # 进度回调 / Progress callback
            if cancel_check():  # / Check cancel
                raise WorkflowCancelled("Pipeline cancelled by user. / 用户已取消流水线。")  # / Cancel
            update_and_persist_workflow_state(config, event=event, stage=event.get("stage", ""), message=event.get("message", ""), result=event if event.get("stage") == "done" else workflow_snapshot().get("result"))  # / Update state
        result = run_production_pipeline(cfg, progress=progress)  # 运行 pipeline / Run pipeline
        update_and_persist_workflow_state(config, running=False, cancel_requested=False, stage="done", message="Pipeline complete. / 流水线完成。", result=result, error="", current_candidate="", current_index=0, total=0)  # / Done
    except WorkflowCancelled as exc:  # 处理取消 / Handle cancel
        WORKFLOW_CANCEL_EVENT.clear()  # / Clear
        update_and_persist_workflow_state(config, event={"stage": "cancelled", "message": str(exc)}, running=False, cancel_requested=False, stage="cancelled", message=str(exc), error="", current_candidate="", current_index=0, total=0)  # / Cancelled
    except Exception as exc:  # 处理异常 / Handle exception
        WORKFLOW_CANCEL_EVENT.clear()  # / Clear
        update_and_persist_workflow_state(config, event={"stage": "error", "message": str(exc)}, running=False, cancel_requested=False, stage="error", message=str(exc), error=str(exc))  # / Error


def request_workflow_cancel(config: dict) -> dict:  # 请求取消工作流 / Request workflow cancellation
    state = workflow_snapshot()  # 读取当前状态 / Read current state
    if not state.get("running"):  # 检查是否没有运行中工作流 / Check no running workflow
        raise RuntimeError("No workflow is running. / 当前没有运行中的工作流。")  # 抛出未运行错误 / Raise not-running error
    WORKFLOW_CANCEL_EVENT.set()  # 标记取消事件 / Mark cancellation event
    update_and_persist_workflow_state(config, event={"stage": "cancelling", "message": "Cancel requested; stopping at the next safe checkpoint. / 已请求取消，将在下一个安全检查点停止。"}, cancel_requested=True, stage="cancelling", message="Cancel requested; stopping at the next safe checkpoint. / 已请求取消，将在下一个安全检查点停止。")  # 写入取消请求 / Store cancellation request
    return workflow_snapshot()  # 返回更新状态 / Return updated state


def project_root() -> Path:  # 获取项目根目录 / Get project root directory
    return Path(__file__).resolve().parents[2]  # 返回 src 的上级项目目录 / Return project directory above src


def config_path() -> Path:  # 获取默认配置路径 / Get default config path
    return project_root() / "config.yaml"  # 返回项目配置文件 / Return project config file


def designer_html_path() -> Path:  # 获取绘图页面路径 / Get designer page path
    return project_root() / "frontend" / "target_designer.html"  # 返回单页 HTML 路径 / Return single-page HTML path


MATERIAL_OPTIONAL_DEFAULTS = {  # 新增字段的向后兼容默认值（旧客户端不发这些字段时使用） / Optional defaults for backwards compatibility
    "stiffness_ratio": 1.05,  # SLA grey resin near-isotropic / SLA grey resin near-isotropic
    "shear_ratio": 1.0,  # isotropic shear / isotropic shear
}  # 结束默认值 / End defaults


def validate_material_payload(payload: dict) -> dict[str, float]:  # 校验材料参数输入 / Validate material parameter input
    material = {}  # 创建材料字典 / Create material dictionary
    for key, (minimum, maximum) in MATERIAL_LIMITS.items():  # 遍历参数范围 / Iterate parameter ranges
        if key not in payload:  # 缺失字段处理 / Missing field handling
            if key in MATERIAL_OPTIONAL_DEFAULTS:  # 可选字段，用默认 / Optional, use default
                material[key] = float(MATERIAL_OPTIONAL_DEFAULTS[key])  # 默认值 / Default value
                continue  # 下一个 / Next
            raise ValueError(f"Missing material field: {key}")  # 必需字段缺失 / Required field missing
        value = float(payload[key])  # 转换为浮点数 / Convert to float
        if value < minimum or value > maximum:  # 检查范围 / Check range
            raise ValueError(f"Material field out of range: {key}")  # 抛出范围错误 / Raise range error
        material[key] = value  # 保存参数值 / Store parameter value
    return material  # 返回校验后的材料参数 / Return validated material parameters


def validate_scoring_payload(payload: dict) -> dict[str, float]:  # 校验评分参数输入 / Validate scoring parameter input
    scoring = {}  # 创建评分参数字典 / Create scoring parameter dictionary
    for key, (minimum, maximum) in SCORING_LIMITS.items():  # 遍历评分范围 / Iterate scoring ranges
        if key not in payload:  # 检查必需字段 / Check required field
            raise ValueError(f"Missing scoring field: {key}")  # 抛出缺失字段错误 / Raise missing field error
        value = float(payload[key])  # 转换为浮点数 / Convert to float
        if value < minimum or value > maximum:  # 检查范围 / Check range
            raise ValueError(f"Scoring field out of range: {key}")  # 抛出范围错误 / Raise range error
        scoring[key] = value  # 保存参数值 / Store parameter value
    if scoring["frequency_max_hz"] < scoring["frequency_min_hz"]:  # 检查频率范围顺序 / Check frequency range order
        raise ValueError("frequency_max_hz must be >= frequency_min_hz. / 最大频率必须大于等于最小频率。")  # 抛出频率范围错误 / Raise frequency-range error
    return scoring  # 返回校验后的评分参数 / Return validated scoring parameters


def validate_artifact_retention_payload(payload: dict) -> dict:  # 校验产物保留输入 / Validate artifact retention input
    retention = {}  # 创建保留策略字典 / Create retention policy dictionary
    latest_minimum, latest_maximum = RETENTION_LIMITS["keep_latest_generations"]  # 读取代数范围 / Read generation range
    keep_latest = int(payload.get("keep_latest_generations", 3))  # 转换最近代数 / Convert newest-generation count
    if keep_latest < latest_minimum or keep_latest > latest_maximum:  # 检查代数范围 / Check generation range
        raise ValueError("keep_latest_generations is out of range. / 保留代数超出范围。")  # 抛出范围错误 / Raise range error
    days_minimum, days_maximum = RETENTION_LIMITS["keep_recent_days"]  # 读取天数范围 / Read day range
    keep_days = float(payload.get("keep_recent_days", 14.0))  # 转换最近天数 / Convert recent-day count
    if keep_days < days_minimum or keep_days > days_maximum:  # 检查天数范围 / Check day range
        raise ValueError("keep_recent_days is out of range. / 保留天数超出范围。")  # 抛出范围错误 / Raise range error
    retention["keep_latest_generations"] = keep_latest  # 保存最近代数 / Store newest-generation count
    retention["keep_recent_days"] = keep_days  # 保存最近天数 / Store recent-day count
    retention["regenerable_only"] = bool(payload.get("regenerable_only", True))  # 保存可再生成限制 / Store regenerable-only flag
    return retention  # 返回校验后的保留策略 / Return validated retention policy


def validate_comsol_paths_payload(payload: dict) -> dict[str, str]:  # 校验 COMSOL/MATLAB 路径输入 / Validate COMSOL/MATLAB path input
    paths = {}  # 创建路径字典 / Create path dictionary
    for key in ["comsol_command_path", "matlab_path"]:  # 遍历可写路径字段 / Iterate writable path fields
        value = str(payload.get(key, "")).strip()  # 读取并清理路径值 / Read and clean path value
        if not value:  # 检查空路径 / Check empty path
            raise ValueError(f"Missing path field: {key}")  # 抛出缺失字段错误 / Raise missing field error
        if len(value) > 1000:  # 检查路径长度 / Check path length
            raise ValueError(f"Path field is too long: {key}")  # 抛出长度错误 / Raise length error
        paths[key] = value  # 保存路径字段 / Store path field
    return paths  # 返回校验后的路径 / Return validated paths


def validate_workflow_payload(payload: dict, config: dict) -> dict:  # 校验工作流输入 / Validate workflow input
    limit = int(payload.get("limit", 1))  # 读取候选数量 / Read candidate count
    if limit < 1 or limit > 100:  # 检查候选数量范围 / Check candidate count range
        raise ValueError("Candidate count must be between 1 and 100. / 候选数量必须在 1 到 100 之间。")  # 抛出候选数量错误 / Raise candidate count error
    num_modes = int(payload.get("num_modes", config["simulation"].get("num_modes", 20)))  # 读取模态数量 / Read mode count
    if num_modes < 1 or num_modes > 60:  # 检查模态数量范围 / Check mode count range
        raise ValueError("Mode count must be between 1 and 60. / 模态数量必须在 1 到 60 之间。")  # 抛出模态数量错误 / Raise mode count error
    iterations = int(payload.get("iterations", config.get("optimisation", {}).get("num_iterations", 1)))  # 读取迭代次数 / Read iteration count
    if iterations < 1 or iterations > 50:  # 检查迭代次数范围 / Check iteration count range
        raise ValueError("Iterations must be between 1 and 50. / 迭代次数必须在 1 到 50 之间。")  # 抛出迭代次数错误 / Raise iteration count error
    generation = payload.get("generation")  # 读取可选代数 / Read optional generation
    if generation in {"", None}:  # 检查是否无代数 / Check whether generation is absent
        generation = None  # 规范为空值 / Normalize empty value
    else:  # 处理存在代数 / Handle existing generation
        generation = int(generation)  # 转换代数整数 / Convert generation integer
        if generation < 0:  # 检查代数范围 / Check generation range
            raise ValueError("Generation must be non-negative. / 代数必须为非负数。")  # 抛出代数错误 / Raise generation error
    return {"limit": limit, "num_modes": num_modes, "iterations": iterations, "simulate": bool(payload.get("simulate", True)), "generation": generation}  # 返回规范载荷 / Return normalized payload


def format_config_number(value: float) -> str:  # 格式化配置数值 / Format config number
    number = float(value)  # 转换为浮点数 / Convert to float
    if abs(number) >= 1.0e6:  # 判断是否为大数 / Check large number
        return str(int(number)) if number.is_integer() else f"{number:.12f}".rstrip("0").rstrip(".")  # 返回 YAML 友好的大数 / Return YAML-friendly large number
    if 0.0 < abs(number) < 1.0e-3:  # 判断是否为小数 / Check small number
        return f"{number:.12f}".rstrip("0").rstrip(".")  # 返回 YAML 友好的小数 / Return YAML-friendly small number
    return f"{number:.12g}"  # 返回普通紧凑数值 / Return ordinary compact number


def write_material_to_config(material: dict[str, float], path: Path | None = None) -> None:  # 写回配置材料区 / Write material section back to config
    target = path or config_path()  # 解析配置路径 / Resolve config path
    lines = target.read_text(encoding="utf-8").splitlines()  # 读取配置行 / Read config lines
    replacements = {  # 定义替换行 / Define replacement lines
        "density_kg_m3": f"  density_kg_m3: {format_config_number(material['density_kg_m3'])} # 密度 / Density",  # 密度行 / Density line
        "poisson_ratio": f"  poisson_ratio: {format_config_number(material['poisson_ratio'])} # 泊松比 / Poisson ratio",  # 泊松比行 / Poisson-ratio line
        "youngs_modulus_pa": f"  youngs_modulus_pa: {format_config_number(material['youngs_modulus_pa'])} # 杨氏模量 / Young's modulus",  # 杨氏模量行 / Young's modulus line
        "thermal_conductivity_w_mk": f"  thermal_conductivity_w_mk: {format_config_number(material['thermal_conductivity_w_mk'])} # 导热系数 / Thermal conductivity",  # 导热系数行 / Thermal-conductivity line
        "heat_capacity_j_kgk": f"  heat_capacity_j_kgk: {format_config_number(material['heat_capacity_j_kgk'])} # 定压热容 / Heat capacity",  # 热容行 / Heat-capacity line
        "thermal_expansion_1_k": f"  thermal_expansion_1_k: {format_config_number(material['thermal_expansion_1_k'])} # 热膨胀系数 / Thermal expansion coefficient",  # 热膨胀行 / Thermal-expansion line
        "stiffness_ratio": f"  stiffness_ratio: {format_config_number(material.get('stiffness_ratio', 1.05))} # E_||/E_⊥（沿主刚度方向 vs 垂直），1.0 = 各向同性 / E_||/E_perp, 1.0 = isotropic",  # 各向异性比 / Stiffness ratio line
        "shear_ratio": f"  shear_ratio: {format_config_number(material.get('shear_ratio', 1.0))} # G_pp / G_iso 剪切模量相对各向同性比 / Shear modulus ratio vs isotropic",  # 剪切比 / Shear ratio line
    }  # 结束替换行定义 / End replacement lines
    output = []  # 创建输出行 / Create output lines
    in_material = False  # 标记材料区 / Track material section
    written = set()  # 记录已写字段 / Track written fields
    for line in lines:  # 遍历配置行 / Iterate config lines
        stripped = line.strip()  # 去掉空白 / Strip whitespace
        if stripped == "material:":  # 识别材料区开始 / Detect material section start
            in_material = True  # 进入材料区 / Enter material section
            output.append(line)  # 保留材料区标题 / Keep material heading
            continue  # 继续下一行 / Continue to next line
        if in_material and line and not line.startswith(" "):  # 识别材料区结束 / Detect material section end
            for key, replacement in replacements.items():  # 遍历未写字段 / Iterate unwritten fields
                if key not in written:  # 检查是否未写 / Check not written
                    output.append(replacement)  # 追加字段 / Append field
            in_material = False  # 离开材料区 / Leave material section
        if in_material and ":" in stripped:  # 处理材料字段 / Handle material field
            key = stripped.split(":", 1)[0]  # 读取字段名 / Read field name
            if key in replacements:  # 检查是否需要替换 / Check replacement
                output.append(replacements[key])  # 写入替换行 / Write replacement line
                written.add(key)  # 标记已写 / Mark written
                continue  # 继续下一行 / Continue to next line
        output.append(line)  # 保留原始行 / Keep original line
    if in_material:  # 检查文件是否在材料区结束 / Check file ended in material section
        for key, replacement in replacements.items():  # 遍历未写字段 / Iterate unwritten fields
            if key not in written:  # 检查是否未写 / Check not written
                output.append(replacement)  # 追加字段 / Append field
    target.write_text("\n".join(output) + "\n", encoding="utf-8")  # 写回配置文件 / Write config file


def write_scoring_to_config(scoring: dict[str, float], path: Path | None = None) -> None:  # 写回评分和频率配置 / Write scoring and frequency config
    target = path or config_path()  # 解析配置路径 / Resolve config path
    lines = target.read_text(encoding="utf-8").splitlines()  # 读取配置行 / Read config lines
    replacements = {  # 定义分区替换行 / Define section replacement lines
        "simulation": {  # 定义仿真分区替换 / Define simulation-section replacements
            "frequency_min_hz": f"  frequency_min_hz: {format_config_number(scoring['frequency_min_hz'])} # 最小目标频率 / Minimum target frequency",  # 最小频率行 / Minimum-frequency line
            "frequency_max_hz": f"  frequency_max_hz: {format_config_number(scoring['frequency_max_hz'])} # 最大目标频率 / Maximum target frequency",  # 最大频率行 / Maximum-frequency line
        },  # 结束仿真分区替换 / End simulation replacements
        "optimisation": {  # 定义优化分区替换 / Define optimisation-section replacements
            "roughness_weight": f"  roughness_weight: {format_config_number(scoring['roughness_weight'])} # 粗糙度惩罚权重 / Roughness penalty weight",  # 粗糙度权重行 / Roughness-weight line
            "mass_weight": f"  mass_weight: {format_config_number(scoring['mass_weight'])} # 质量惩罚权重 / Mass penalty weight",  # 质量权重行 / Mass-weight line
            "frequency_weight": f"  frequency_weight: {format_config_number(scoring['frequency_weight'])} # 频率惩罚权重 / Frequency penalty weight",  # 频率权重行 / Frequency-weight line
        },  # 结束优化分区替换 / End optimisation replacements
    }  # 结束替换定义 / End replacement definition
    output = []  # 创建输出行 / Create output lines
    current_section = ""  # 记录当前分区 / Track current section
    written: dict[str, set] = {section: set() for section in replacements}  # 记录已写字段 / Track written fields
    for line in lines:  # 遍历配置行 / Iterate config lines
        stripped = line.strip()  # 去掉空白 / Strip whitespace
        if stripped.endswith(":") and not line.startswith(" "):  # 识别顶层分区 / Detect top-level section
            if current_section in replacements:  # 检查是否离开目标分区 / Check leaving target section
                for key, replacement in replacements[current_section].items():  # 遍历未写字段 / Iterate unwritten fields
                    if key not in written[current_section]:  # 检查字段是否未写 / Check field not written
                        output.append(replacement)  # 追加缺失字段 / Append missing field
            current_section = stripped.rstrip(":")  # 更新当前分区 / Update current section
            output.append(line)  # 保留分区标题 / Keep section heading
            continue  # 继续下一行 / Continue to next line
        if current_section in replacements and ":" in stripped:  # 检查目标分区字段 / Check target-section field
            key = stripped.split(":", 1)[0]  # 读取字段名 / Read field name
            if key in replacements[current_section]:  # 检查字段是否需要替换 / Check whether field needs replacement
                output.append(replacements[current_section][key])  # 写入替换行 / Write replacement line
                written[current_section].add(key)  # 标记已写 / Mark written
                continue  # 继续下一行 / Continue to next line
        output.append(line)  # 保留原始行 / Keep original line
    if current_section in replacements:  # 检查文件是否在目标分区结束 / Check file ended in target section
        for key, replacement in replacements[current_section].items():  # 遍历未写字段 / Iterate unwritten fields
            if key not in written[current_section]:  # 检查字段是否未写 / Check field not written
                output.append(replacement)  # 追加缺失字段 / Append missing field
    target.write_text("\n".join(output) + "\n", encoding="utf-8")  # 写回配置文件 / Write config file


def write_artifact_retention_to_config(retention: dict, path: Path | None = None) -> None:  # 写回产物保留配置 / Write artifact retention config
    target = path or config_path()  # 解析配置路径 / Resolve config path
    lines = target.read_text(encoding="utf-8").splitlines()  # 读取配置行 / Read config lines
    replacements = {  # 定义替换行 / Define replacement lines
        "keep_latest_generations": f"  keep_latest_generations: {int(retention['keep_latest_generations'])} # 始终保留最近代数 / Always keep newest generations",  # 最新代数行 / Newest-generation line
        "keep_recent_days": f"  keep_recent_days: {format_config_number(retention['keep_recent_days'])} # 始终保留最近天数 / Always keep recent days",  # 最近天数行 / Recent-days line
        "regenerable_only": f"  regenerable_only: {str(bool(retention['regenerable_only'])).lower()} # 仅清理可再生成产物 / Only clean regenerable artifacts",  # 可再生成限制行 / Regenerable-only line
    }  # 结束替换行定义 / End replacement lines
    output = []  # 创建输出行 / Create output lines
    in_retention = False  # 标记保留策略区 / Track retention section
    section_found = False  # 标记是否找到分区 / Track whether section exists
    written = set()  # 记录已写字段 / Track written fields
    for line in lines:  # 遍历配置行 / Iterate config lines
        stripped = line.strip()  # 去掉空白 / Strip whitespace
        if stripped == "artifact_retention:":  # 识别保留策略区开始 / Detect retention section start
            in_retention = True  # 进入保留策略区 / Enter retention section
            section_found = True  # 标记找到分区 / Mark section found
            output.append(line)  # 保留分区标题 / Keep section heading
            continue  # 继续下一行 / Continue to next line
        if in_retention and line and not line.startswith(" "):  # 识别保留策略区结束 / Detect retention section end
            for key, replacement in replacements.items():  # 遍历未写字段 / Iterate unwritten fields
                if key not in written:  # 检查字段是否未写 / Check field not written
                    output.append(replacement)  # 追加缺失字段 / Append missing field
            in_retention = False  # 离开保留策略区 / Leave retention section
        if in_retention and ":" in stripped:  # 处理保留策略字段 / Handle retention field
            key = stripped.split(":", 1)[0]  # 读取字段名 / Read field name
            if key in replacements:  # 检查是否需要替换 / Check replacement
                output.append(replacements[key])  # 写入替换行 / Write replacement line
                written.add(key)  # 标记已写 / Mark written
                continue  # 继续下一行 / Continue to next line
        output.append(line)  # 保留原始行 / Keep original line
    if in_retention:  # 检查文件是否在保留策略区结束 / Check file ended in retention section
        for key, replacement in replacements.items():  # 遍历未写字段 / Iterate unwritten fields
            if key not in written:  # 检查字段是否未写 / Check field not written
                output.append(replacement)  # 追加缺失字段 / Append missing field
    if not section_found:  # 检查是否需要新增分区 / Check whether section must be added
        output.extend(["", "# 产物保留策略 / Artifact retention policy", "artifact_retention:", *replacements.values()])  # 追加新分区 / Append new section
    target.write_text("\n".join(output) + "\n", encoding="utf-8")  # 写回配置文件 / Write config file


def load_ranking(config: dict) -> list[dict[str, str]]:  # 读取评分排行 / Load score ranking
    ranking_path = Path(config["paths"]["candidates_dir"]) / "ranked_candidates.csv"  # 构造排行路径 / Build ranking path
    if not ranking_path.exists():  # 检查排行文件是否存在 / Check ranking file existence
        return []  # 返回空排行 / Return empty ranking
    with ranking_path.open("r", encoding="utf-8", newline="") as file_obj:  # 打开排行文件 / Open ranking file
        return list(csv.DictReader(file_obj))  # 读取排行行 / Read ranking rows


def _summarise_production_run(data: dict, run_dir: Path, summary_path: Path) -> dict:  # 把 production_summary.json 压成一行 / Distil production_summary.json into a row
    cand_id = str(data.get("candidate_id", run_dir.name))  # 候选编号 / Candidate id
    stage = str(data.get("stage_reached", "unknown"))  # 完成阶段 / Stage reached
    surrogate = data.get("surrogate_metrics", {}) or {}  # surrogate 指标 / Surrogate metrics
    phase1 = data.get("phase1") or {}  # Phase 1 块 / Phase 1 block
    best_comp = phase1.get("best_composite") or {}  # 最佳合成 / Best composite
    broad = best_comp.get("broad") or {}  # broad 子集 / Broad scoring
    tight = best_comp.get("tight") or {}  # tight 子集 / Tight scoring
    phase2 = data.get("phase2") or {}  # Phase 2 块 / Phase 2 block
    wallclock = data.get("wallclock_seconds") or {}  # 计时 / Wallclock seconds
    return {  # 一条 production run 摘要 / One production-run summary row
        "candidate_id": cand_id,  # 候选编号 / Candidate id
        "stage_reached": stage,  # 阶段 / Stage
        "stiffness_ratio": data.get("stiffness_ratio"),  # 各向异性比 / Stiffness ratio
        "shear_ratio": data.get("shear_ratio"),  # 剪切比 / Shear ratio
        "surrogate_enrichment": surrogate.get("enrichment"),  # surrogate enrichment / Surrogate enrichment
        "surrogate_recall": surrogate.get("recall"),  # surrogate recall / Surrogate recall
        "surrogate_contrast": surrogate.get("contrast"),  # surrogate contrast / Surrogate contrast
        "phase1_drive_freqs": phase1.get("drive_freqs", []),  # 驱动频率 / Drive frequencies
        "phase1_best_subset": best_comp.get("subset", []),  # 最佳子集 / Best subset
        "phase1_method": best_comp.get("method", ""),  # 合成方法 / Composite method
        "phase1_broad_enrich": broad.get("enrich"),  # broad enrichment / Broad enrichment
        "phase1_broad_recall": broad.get("recall"),  # broad recall / Broad recall
        "phase1_broad_contrast": broad.get("contrast"),  # broad contrast / Broad contrast
        "phase1_tight_enrich": tight.get("enrich"),  # tight enrichment / Tight enrichment
        "phase1_tight_recall": tight.get("recall"),  # tight recall / Tight recall
        "phase2_best_iter": phase2.get("best_iter"),  # Phase 2 最佳迭代 / Best iter
        "phase2_best_enrichment": phase2.get("best_enrichment"),  # Phase 2 enrichment / Phase 2 enrichment
        "phase2_improvement_pct": phase2.get("improvement_pct"),  # Phase 2 改善 % / Improvement
        "wallclock_surrogate_s": wallclock.get("surrogate"),  # surrogate 时长 / Surrogate elapsed
        "wallclock_phase1_s": wallclock.get("phase1"),  # Phase 1 时长 / Phase 1 elapsed
        "modified_at": datetime.fromtimestamp(summary_path.stat().st_mtime).isoformat(timespec="seconds"),  # 修改时间 / Modified at
        "summary_path": str(summary_path),  # 摘要文件 / Summary file
        "output_dir": str(run_dir),  # 输出目录 / Output directory
    }


def _is_diagnostic_production_run(row: dict) -> bool:
    candidate_id = str(row.get("candidate_id") or "").lower()
    output_dir = str(row.get("output_dir") or "").lower()
    return "smoke" in candidate_id or "smoke" in output_dir


def load_production_runs(include_diagnostics: bool = False) -> list[dict]:  # 列出所有生产 pipeline 完成的运行 / List every completed production-pipeline run
    base = project_root() / "reports" / "production"  # 生产输出目录 / Production output directory
    if not base.exists():  # 没有运行过 / No runs yet
        return []  # 返回空列表 / Empty list
    rows: list[dict] = []  # 行列表 / Row list
    for d in base.iterdir():  # 遍历子目录 / Iterate subdirs
        if not d.is_dir():  # 跳过非目录 / Skip non-dirs
            continue  # / Continue
        summary = d / "production_summary.json"  # 摘要路径 / Summary path
        if not summary.exists():  # 缺摘要 / Missing summary
            continue  # / Skip
        try:  # 容错读取 / Tolerate parse errors
            data = json.loads(summary.read_text(encoding="utf-8"))  # 解析 / Parse
        except Exception:  # 解析失败 / Parse failed
            continue  # / Skip
        try:  # 容错压缩 / Tolerate summary build errors
            row = _summarise_production_run(data, d, summary)  # 压缩 / Distil
            row["diagnostic_run"] = _is_diagnostic_production_run(row)
            if row["diagnostic_run"] and not include_diagnostics:
                continue
            rows.append(row)  # 加入 / Append
        except Exception:  # 略过 / Skip on summarise error
            continue  # / Continue
    rows.sort(key=lambda r: r.get("modified_at") or "", reverse=True)  # 最新优先 / Newest first
    return rows  # 返回 / Return


def _list_production_comsol_modes(config: dict, candidate_id: str) -> list[dict]:  # 列出生产候选的 COMSOL 模态预览 / List COMSOL mode previews for a production candidate
    eig_dir = Path(config["paths"]["comsol_exports_dir"]) / f"prod_eig_{candidate_id}"  # 生产 eigfreq 目录 / Production eigfreq directory
    previews_dir = eig_dir / "previews"  # 预览目录 / Previews directory
    if not previews_dir.exists():  # 无预览 / No previews
        return []  # 返回空 / Return empty
    rows: list[dict] = []  # 收集行 / Collect rows
    # 读取频率表帮助标注 / Read frequency table for labelling
    freqs_path = eig_dir / "eigenfrequencies.csv"  # 频率 CSV / Frequencies CSV
    freq_for_mode: dict[int, float] = {}  # 模态频率映射 / Mode→freq map
    if freqs_path.exists():  # 文件存在 / Exists
        try:  # 容错 / Tolerate
            import numpy as np  # 延迟导入 / Lazy import
            arr = np.loadtxt(freqs_path, delimiter=",", skiprows=1)  # 加载 / Load
            if arr.ndim == 1:  # 一维 / 1D
                arr = arr.reshape(-1, 2)  # 重塑 / Reshape
            for row in arr:  # 遍历 / Iterate
                freq_for_mode[int(row[0])] = float(row[1])  # 填表 / Fill table
        except Exception:  # 解析失败 / Parse failure
            pass  # / Skip
    for path in sorted(previews_dir.glob("mode_*.png")):  # 遍历模态预览 / Iterate mode previews
        match = re.match(r"^mode_(\d+)\.png$", path.name)  # 匹配编号 / Match number
        if not match:  # 不匹配 / Skip non-matching
            continue  # / Continue
        mode_num = int(match.group(1))  # 模态编号 / Mode number
        rows.append({  # 一条 / Single row
            "mode": mode_num,
            "frequency_hz": freq_for_mode.get(mode_num),
            "name": path.name,
            "url": f"/assets/production/{candidate_id}/{path.name}",
        })
    return rows  # 返回 / Return


def load_production_run_detail(config: dict, candidate_id: str) -> dict:  # 读取生产 pipeline 候选详情 / Load production-run detail
    from src.visualisation.plot_amplitude import render_production_pngs  # 延迟导入 / Lazy import
    from src.visualisation.plot_thickness import render_candidate_preview  # 延迟导入 / Lazy import
    from src.visualisation.production_artefacts import render_production_artefacts  # 延迟导入扩展渲染器 / Lazy import extended renderer
    valid_id = validate_production_candidate_id(candidate_id)  # 校验编号 / Validate id
    base = project_root() / "reports" / "production" / valid_id  # 生产输出目录 / Production output dir
    summary_path = base / "production_summary.json"  # 摘要路径 / Summary path
    if not summary_path.exists():  # 不存在 / Missing
        raise FileNotFoundError(f"Production run not found: {valid_id}. / 生产运行不存在：{valid_id}。")  # 抛出 / Raise

    summary = json.loads(summary_path.read_text(encoding="utf-8"))  # 解析 / Parse
    digest = _summarise_production_run(summary, base, summary_path)  # 压缩 / Distil

    rendered = render_production_pngs(base)  # 渲染 .npy → .png（Phase1/2 振幅） / Render Phase 1/2 amplitude arrays
    try:  # 扩展渲染（surrogate 正向 + 诊断图）出错不阻断 / Extended renders (surrogate-forward + diagnostics) may fail without blocking
        extended = render_production_artefacts(base, config)  # 传 config 以便 surrogate 正向 / Pass config so surrogate-forward can build the plate
        rendered.update(extended)  # 合并 / Merge
    except Exception:  # 容错 / Tolerate
        pass  # / Continue
    previews = {name: f"/assets/production/{valid_id}/{name}" for name in rendered.keys()}  # 预览 URL / Preview URLs

    candidate_dir = Path(config["paths"]["candidates_dir"]) / valid_id  # 候选目录 / Candidate directory
    thickness_url = ""  # 厚度预览 URL / Thickness preview URL
    if (candidate_dir / "H.csv").exists():  # 有厚度矩阵 / Has thickness matrix
        thickness_png = candidate_dir / "preview_thickness.png"  # 厚度 PNG / Thickness PNG
        if output_needs_refresh(thickness_png, [candidate_dir / "H.csv"]):  # 过期检测 / Stale check
            try:  # 容错 / Tolerate
                render_candidate_preview(candidate_dir)  # 渲染 / Render
            except Exception:  # 渲染失败 / Render failure
                pass  # / Continue
        if thickness_png.exists():  # 存在 / Exists
            thickness_url = f"/assets/production/{valid_id}/preview_thickness.png"  # URL / URL

    comsol_modes = _list_production_comsol_modes(config, valid_id)  # COMSOL 模态预览 / COMSOL mode previews

    # 检查 .mph 是否存在；surrogate-only 阶段没有 .mph，前端据此隐藏按钮 / Detect saved .mph so the frontend can hide the COMSOL button for surrogate-only runs
    comsol_available = False  # 默认无 / Default false
    comsol_mph_count = 0  # 计数 / Count
    try:  # 发现可能因路径异常失败 / Discovery may fail on odd paths
        mph_files = discover_candidate_mph_files(valid_id)  # 查找 .mph / Discover .mph
        comsol_mph_count = len(mph_files)  # 个数 / Count
        comsol_available = bool(mph_files)  # 是否有 / Whether any exists
    except Exception:  # 容错 / Tolerate
        pass  # / Continue

    return {  # 详情字典 / Detail dict
        "candidate_id": valid_id,
        "summary": summary,
        "digest": digest,
        "previews": previews,
        "thickness_preview": thickness_url,
        "comsol_modes": comsol_modes,
        "comsol_available": comsol_available,
        "comsol_mph_count": comsol_mph_count,
        "summary_path": str(summary_path),
        "output_dir": str(base),
    }


def resolve_production_asset(config: dict, candidate_id: str, asset_name: str) -> Path | None:  # 解析生产候选的资源路径 / Resolve a production candidate's asset path
    if not PRODUCTION_ASSET_RE.match(asset_name or ""):  # 名称校验 / Name validation
        return None  # 不合法 / Invalid
    try:  # 编号校验 / Id validation
        valid_id = validate_production_candidate_id(candidate_id)  # 校验 / Validate
    except ValueError:  # 失败 / Invalid
        return None  # / None
    base_dirs = [  # 候选目录列表，按优先级 / Candidate directories by priority
        project_root() / "reports" / "production" / valid_id / "previews",  # production 预览 / Production previews
        Path(config["paths"]["candidates_dir"]) / valid_id,  # 候选目录（厚度图） / Candidate dir (thickness)
        Path(config["paths"]["comsol_exports_dir"]) / f"prod_eig_{valid_id}" / "previews",  # COMSOL 模态 / COMSOL modes
    ]
    for base_dir in base_dirs:  # 顺序查找 / Sequential lookup
        candidate = base_dir / asset_name  # 候选路径 / Candidate path
        try:  # 容错 / Tolerate
            if candidate.is_file():  # 存在且为文件 / Exists and is file
                return candidate  # 返回 / Return
        except OSError:  # 文件系统错误 / Filesystem error
            continue  # / Continue
    return None  # 未找到 / Not found


def candidate_generation(candidate_path: Path, metadata: dict) -> int:  # 读取候选代数 / Read candidate generation
    if metadata.get("generation") is not None:  # 检查元数据是否包含代数 / Check whether metadata has generation
        return int(metadata["generation"])  # 返回元数据代数 / Return metadata generation
    return int(candidate_path.name.split("_")[1])  # 从候选编号解析代数 / Parse generation from candidate id


def score_summary(candidate_dir: Path) -> dict:  # 读取候选评分摘要 / Read candidate score summary
    score = read_json_file(candidate_dir / "score.json")  # 读取评分文件 / Read score file
    return {"best_mode": score.get("best_mode", ""), "best_iou": score.get("best_iou", ""), "best_dice": score.get("best_dice", ""), "frequency_hz": score.get("frequency_hz", ""), "final_score": score.get("final_score", "")}  # 返回摘要字段 / Return summary fields


def is_better_score(candidate_score: dict, current_best: dict | None) -> bool:  # 判断候选评分是否更好 / Decide whether candidate score is better
    if candidate_score.get("final_score") in {"", None}:  # 检查候选是否无分数 / Check whether candidate has no score
        return False  # 无分数不能成为最佳 / No score cannot be best
    if current_best is None or current_best.get("final_score") in {"", None}:  # 检查当前最佳是否为空 / Check whether current best is empty
        return True  # 有分数候选更好 / Scored candidate is better
    return float(candidate_score["final_score"]) > float(current_best["final_score"])  # 比较最终分数 / Compare final scores


def load_generation_history(config: dict) -> list[dict]:  # 读取代数历史摘要 / Load generation history summary
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    exports_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取导出目录 / Read export directory
    generations: dict[int, dict] = {}  # 创建代数字典 / Create generation dictionary
    for candidate_dir in sorted(candidates_dir.glob("candidate_*_*")):  # 遍历候选目录 / Iterate candidate directories
        if not (candidate_dir / "H.csv").exists():  # 检查是否为有效候选 / Check whether candidate is valid
            continue  # 跳过无厚度矩阵目录 / Skip directories without thickness matrix
        metadata = read_json_file(candidate_dir / "metadata.json")  # 读取候选元数据 / Read candidate metadata
        generation = candidate_generation(candidate_dir, metadata)  # 解析代数编号 / Resolve generation index
        group = generations.setdefault(generation, {"generation": generation, "candidate_count": 0, "simulated_count": 0, "scored_count": 0, "best": None})  # 获取代数组 / Get generation group
        group["candidate_count"] += 1  # 增加候选数 / Increment candidate count
        export_dir = exports_dir / candidate_dir.name  # 构造导出目录 / Build export directory
        if (export_dir / "frequencies.csv").exists():  # 检查是否已仿真 / Check whether simulated
            group["simulated_count"] += 1  # 增加已仿真数 / Increment simulated count
        candidate_score = score_summary(candidate_dir)  # 读取评分摘要 / Read score summary
        if candidate_score.get("final_score") not in {"", None}:  # 检查是否已评分 / Check whether scored
            group["scored_count"] += 1  # 增加已评分数 / Increment scored count
        if is_better_score(candidate_score, group["best"]):  # 检查是否更新最佳候选 / Check whether to update best candidate
            group["best"] = {"candidate_id": candidate_dir.name, **candidate_score}  # 保存最佳候选 / Store best candidate
    history = []  # 创建历史列表 / Create history list
    for generation, group in sorted(generations.items(), reverse=True):  # 按代数倒序遍历 / Iterate generations descending
        best = group["best"] or {}  # 读取最佳候选 / Read best candidate
        history.append({"generation": generation, "candidate_count": group["candidate_count"], "simulated_count": group["simulated_count"], "scored_count": group["scored_count"], "best_candidate": best.get("candidate_id", ""), "best_mode": best.get("best_mode", ""), "best_iou": best.get("best_iou", ""), "best_dice": best.get("best_dice", ""), "frequency_hz": best.get("frequency_hz", ""), "final_score": best.get("final_score", "")})  # 添加历史行 / Add history row
    return history  # 返回历史列表 / Return history list


def read_log_tail(path: Path, limit: int = 5000) -> dict:  # 读取日志尾部 / Read log tail
    if not path.exists() or not path.is_file():  # 检查日志文件是否存在 / Check whether log file exists
        return {"name": path.name, "path": str(path), "exists": False, "content": "", "size_bytes": 0, "modified": ""}  # 返回缺失日志 / Return missing log
    content = path.read_text(encoding="utf-8", errors="replace")  # 读取日志文本 / Read log text
    stat = path.stat()  # 读取文件状态 / Read file stat
    tail = content[-limit:] if len(content) > limit else content  # 截取尾部文本 / Slice tail text
    return {"name": path.name, "path": str(path), "exists": True, "content": tail, "size_bytes": stat.st_size, "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")}  # 返回日志摘要 / Return log summary


def load_log_tails(config: dict) -> dict:  # 读取最近运行日志 / Load recent run logs
    exports_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取导出目录 / Read export directory
    logs = [read_log_tail(exports_dir / "mphserver.log"), read_log_tail(exports_dir / "livelink_batch.log")]  # 添加全局日志 / Add global logs
    candidate_logs = sorted(exports_dir.glob("candidate_*_*/livelink.log"), key=lambda path: path.stat().st_mtime if path.exists() else 0.0, reverse=True)  # 查找候选日志 / Find candidate logs
    for log_path in candidate_logs[:5]:  # 限制最近五个候选日志 / Limit to five recent candidate logs
        logs.append(read_log_tail(log_path))  # 添加候选日志 / Add candidate log
    return {"logs": logs}  # 返回日志列表 / Return log list


def append_recovery_hint(hints: list[dict], titles: set[str], status: str, title: str, message: str, action: str, source: str = "") -> None:  # 添加去重恢复建议 / Add deduplicated recovery hint
    if title in titles:  # 检查标题是否已存在 / Check whether title already exists
        return  # 跳过去重项 / Skip duplicate item
    titles.add(title)  # 记录标题 / Record title
    hints.append({"status": status, "title": title, "message": message, "action": action, "source": source})  # 添加恢复建议 / Add recovery hint


def collect_recovery_hints(config: dict) -> dict:  # 汇总恢复建议 / Collect recovery hints
    from src.comsol.diagnostics import diagnose_comsol_environment  # 延迟导入诊断函数 / Lazily import diagnostics function
    state = workflow_snapshot()  # 读取工作流状态 / Read workflow state
    diagnostics = diagnose_comsol_environment(config)  # 运行环境诊断 / Run environment diagnostics
    logs = load_log_tails(config).get("logs", [])  # 读取日志摘要 / Read log summaries
    text_parts = [state.get("message", ""), state.get("error", "")]  # 收集状态文本 / Collect state text
    text_parts.extend(event.get("message", "") for event in state.get("events", []))  # 收集事件文本 / Collect event text
    text_parts.extend(log.get("content", "") for log in logs if log.get("exists"))  # 收集日志文本 / Collect log text
    text = " ".join(text_parts).lower()  # 合并并小写文本 / Join and lower text
    hints = []  # 创建建议列表 / Create hint list
    titles = set()  # 创建去重标题集合 / Create dedupe title set
    failure_state = state.get("stage") in {"error", "interrupted"} or bool(state.get("error"))  # 判断是否失败状态 / Decide whether workflow failed
    failed_checks = [item for item in diagnostics.get("checks", []) if item.get("status") == "fail"]  # 查找失败诊断 / Find failed diagnostics
    warned_checks = [item for item in diagnostics.get("checks", []) if item.get("status") == "warn"]  # 查找警告诊断 / Find warning diagnostics
    for item in failed_checks:  # 遍历失败诊断 / Iterate failed diagnostics
        append_recovery_hint(hints, titles, "fail", f"Fix {item.get('label', 'diagnostic check')}", item.get("message", "Path or configuration check failed."), item.get("path", "") or "Open Run > Diagnostics, correct this item, then refresh diagnostics.", "diagnostics")  # 添加失败诊断建议 / Add failed diagnostic hint
    if failure_state and ("timeout" in text or "timed out" in text):  # 检查超时文本 / Check timeout text
        append_recovery_hint(hints, titles, "warn", "Reduce run size or increase timeout", "The latest run appears to have timed out.", "Use Smoke, lower mode count, or raise comsol.livelink_timeout_s in config.yaml.", "logs")  # 添加超时建议 / Add timeout hint
    if failure_state and ("license" in text or "licensed" in text or "checkout" in text):  # 检查授权文本 / Check license text
        append_recovery_hint(hints, titles, "warn", "Confirm COMSOL/MATLAB license", "The logs or diagnostics mention license risk.", "Open COMSOL and MATLAB once, confirm login/license dialogs, then rerun diagnostics.", "logs")  # 添加授权建议 / Add license hint
    if failure_state and ("mphserver" in text or "port" in text or "2036" in text):  # 检查 server 文本 / Check server text
        append_recovery_hint(hints, titles, "warn", "Check mphserver connection", "The run may be blocked by COMSOL server startup or port reachability.", "Refresh diagnostics; if needed, close stale mphserver sessions or change comsol.server_port.", "logs")  # 添加 server 建议 / Add server hint
    if failure_state and "matlab" in text and ("not found" in text or "no such file" in text or "permission" in text):  # 检查 MATLAB 路径文本 / Check MATLAB path text
        append_recovery_hint(hints, titles, "fail", "Fix MATLAB command path", "MATLAB path or executable permission looks wrong.", "Use Run > Discover, then Apply paths or Save paths.", "logs")  # 添加 MATLAB 建议 / Add MATLAB hint
    if failure_state and "comsol" in text and ("not found" in text or "no such file" in text or "permission" in text):  # 检查 COMSOL 路径文本 / Check COMSOL path text
        append_recovery_hint(hints, titles, "fail", "Fix COMSOL command path", "COMSOL path or executable permission looks wrong.", "Use Run > Discover, then Apply paths or Save paths.", "logs")  # 添加 COMSOL 建议 / Add COMSOL hint
    if failure_state and (".mph" in text or "model" in text):  # 检查模型文本 / Check model text
        append_recovery_hint(hints, titles, "warn", "Verify bound MPH model", "The failure may involve the bound COMSOL model file or its parameter contract.", "Confirm comsol.model_path exists and matches the 15 x 15 parameterized model.", "logs")  # 添加模型建议 / Add model hint
    if failure_state and ("livelink" in text or "run_chladni_candidate" in text):  # 检查 LiveLink 文本 / Check LiveLink text
        append_recovery_hint(hints, titles, "warn", "Check LiveLink runner", "The MATLAB LiveLink runner may be missing, incompatible, or failing inside MATLAB.", "Run Self-test and inspect the latest candidate livelink.log.", "logs")  # 添加 LiveLink 建议 / Add LiveLink hint
    if not diagnostics.get("ready_for_auto_run"):  # 检查诊断未就绪 / Check diagnostics not ready
        append_recovery_hint(hints, titles, "warn", "Refresh diagnostics before retry", "Automatic COMSOL/MATLAB run readiness is not confirmed.", "Open Run > Diagnostics, click Refresh, then resolve failed required checks.", "diagnostics")  # 添加诊断建议 / Add diagnostics hint
    if not hints and state.get("stage") in {"error", "interrupted"}:  # 检查失败但无具体建议 / Check failed state without specific hints
        append_recovery_hint(hints, titles, "warn", "Inspect latest logs", "No specific recovery pattern was detected.", "Open Logs and inspect the newest livelink.log or mphserver.log tail.", "logs")  # 添加通用建议 / Add generic hint
    if not hints:  # 检查无恢复事项 / Check no recovery actions
        append_recovery_hint(hints, titles, "ok", "No recovery action needed", "Current diagnostics do not show a blocking failure.", "Continue with a Smoke run or refresh diagnostics after changing paths.", "diagnostics")  # 添加正常建议 / Add ok hint
    status = "fail" if any(item.get("status") == "fail" for item in hints) else ("warn" if any(item.get("status") == "warn" for item in hints) else "ok")  # 汇总状态 / Summarize status
    log_matches = [log.get("path", "") for log in logs if log.get("exists") and any(token in log.get("content", "").lower() for token in ["error", "license", "timeout", "failed", "exception"])]  # 收集可疑日志 / Collect suspicious logs
    return {"status": status, "hints": hints, "log_matches": log_matches[:5], "diagnostics_ready": diagnostics.get("ready_for_auto_run", False), "failed_checks": failed_checks, "warned_checks": warned_checks[:5]}  # 返回恢复建议 / Return recovery hints


def summarize_paths(label: str, paths: list[Path]) -> dict:  # 汇总一组文件路径 / Summarize a group of file paths
    existing = [path for path in paths if path.exists() and path.is_file()]  # 筛选存在文件 / Filter existing files
    size_bytes = sum(path.stat().st_size for path in existing)  # 计算总字节数 / Compute total byte size
    newest = max((path.stat().st_mtime for path in existing), default=0.0)  # 计算最新修改时间 / Compute newest modification time
    modified = datetime.fromtimestamp(newest).isoformat(timespec="seconds") if newest else ""  # 格式化最新时间 / Format newest timestamp
    return {"label": label, "count": len(existing), "size_bytes": size_bytes, "modified": modified}  # 返回汇总结果 / Return summary result


def largest_files(paths: list[Path], limit: int = 8) -> list[dict]:  # 查找最大文件 / Find largest files
    existing = [path for path in paths if path.exists() and path.is_file()]  # 筛选存在文件 / Filter existing files
    sorted_files = sorted(existing, key=lambda path: path.stat().st_size, reverse=True)  # 按大小排序 / Sort by file size
    return [{"path": str(path), "size_bytes": path.stat().st_size} for path in sorted_files[:limit]]  # 返回最大文件列表 / Return largest file list


def unique_paths(paths: list[Path]) -> list[Path]:  # 去重文件路径 / Deduplicate file paths
    seen = set()  # 记录已经出现的路径 / Track paths already seen
    unique = []  # 保存去重后的路径 / Store deduplicated paths
    for path in paths:  # 遍历输入路径 / Iterate input paths
        key = str(path.resolve()) if path.exists() else str(path)  # 构造稳定键 / Build stable key
        if key in seen:  # 跳过重复路径 / Skip duplicate path
            continue  # 继续下一项 / Continue to next item
        seen.add(key)  # 标记路径已出现 / Mark path as seen
        unique.append(path)  # 追加唯一路径 / Append unique path
    return unique  # 返回唯一路径列表 / Return unique path list


def candidate_generation_from_path(path: Path) -> int | None:  # 从路径读取候选代数 / Read candidate generation from path
    match = re.search(r"candidate_(\d{3})_\d{4}", str(path))  # 匹配候选路径片段 / Match candidate path fragment
    return int(match.group(1)) if match else None  # 返回代数或空值 / Return generation or none


def artifact_retention_policy(config: dict) -> dict:  # 读取产物保留策略 / Read artifact retention policy
    policy = config.get("artifact_retention", {})  # 读取配置分区 / Read config section
    keep_latest = max(0, int(policy.get("keep_latest_generations", 3)))  # 读取最近代数 / Read newest generation count
    keep_days = max(0.0, float(policy.get("keep_recent_days", 14)))  # 读取最近天数 / Read newest day count
    regenerable_only = bool(policy.get("regenerable_only", True))  # 读取只清理可再生成项 / Read regenerable-only flag
    return {"keep_latest_generations": keep_latest, "keep_recent_days": keep_days, "regenerable_only": regenerable_only}  # 返回规范策略 / Return normalized policy


def latest_generations_for_retention(config: dict, keep_latest: int) -> set[int]:  # 计算保留的最新代数 / Compute newest generations to keep
    if keep_latest <= 0:  # 检查是否不保留最新代数 / Check whether no newest generations are kept
        return set()  # 返回空集合 / Return empty set
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    exports_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取导出目录 / Read export directory
    generations = set()  # 创建代数集合 / Create generation set
    for base_dir in [candidates_dir, exports_dir]:  # 遍历候选和导出目录 / Iterate candidate and export directories
        for path in base_dir.glob("candidate_*_*"):  # 遍历候选目录 / Iterate candidate directories
            generation = candidate_generation_from_path(path)  # 读取代数 / Read generation
            if generation is not None:  # 检查代数有效 / Check valid generation
                generations.add(generation)  # 添加代数 / Add generation
    return set(sorted(generations, reverse=True)[:keep_latest])  # 返回最新代数集合 / Return newest generation set


def artifact_age_days(path: Path) -> float:  # 计算文件年龄天数 / Compute file age in days
    age_seconds = datetime.now().timestamp() - path.stat().st_mtime  # 计算年龄秒数 / Compute age seconds
    return max(0.0, age_seconds / 86400.0)  # 返回非负天数 / Return non-negative days


def apply_artifact_retention(config: dict, paths: list[Path]) -> list[Path]:  # 应用产物保留策略 / Apply artifact retention policy
    policy = artifact_retention_policy(config)  # 读取保留策略 / Read retention policy
    protected_generations = latest_generations_for_retention(config, int(policy["keep_latest_generations"]))  # 计算受保护代数 / Compute protected generations
    retained = []  # 创建可清理列表 / Create cleanable list
    for path in unique_paths(paths):  # 遍历去重路径 / Iterate deduplicated paths
        if not path.exists() or not path.is_file():  # 跳过缺失路径 / Skip missing paths
            continue  # 继续下一项 / Continue to next item
        generation = candidate_generation_from_path(path)  # 读取文件代数 / Read file generation
        if generation in protected_generations:  # 检查是否属于最新代数 / Check newest generation protection
            continue  # 保留最新代数 / Keep newest generation
        if artifact_age_days(path) < float(policy["keep_recent_days"]):  # 检查是否太新 / Check recent file protection
            continue  # 保留近期文件 / Keep recent file
        retained.append(path)  # 追加可清理文件 / Append cleanable file
    return retained  # 返回符合策略的文件 / Return policy-matching files


def load_artifact_summary(config: dict) -> dict:  # 读取产物占用摘要 / Load artifact storage summary
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    exports_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取导出目录 / Read export directory
    processed_dir = Path(config["paths"]["processed_targets_dir"])  # 读取目标处理目录 / Read processed target directory
    candidate_files = [path for path in candidates_dir.glob("candidate_*_*/*") if path.is_file()]  # 收集候选文件 / Collect candidate files
    export_files = [path for path in exports_dir.glob("candidate_*_*/*") if path.is_file()]  # 收集候选导出文件 / Collect candidate export files
    nested_export_files = [path for path in exports_dir.glob("candidate_*_*/*/*") if path.is_file()]  # 收集嵌套导出文件 / Collect nested export files
    all_export_files = export_files + nested_export_files  # 合并导出文件 / Merge export files
    processed_files = [path for path in processed_dir.glob("*") if path.is_file()]  # 收集目标处理文件 / Collect processed target files
    log_files = [path for path in exports_dir.rglob("*.log") if path.is_file()]  # 收集日志文件 / Collect log files
    mode_files = [path for path in exports_dir.glob("candidate_*_*/mode_*.csv") if path.is_file()]  # 收集模态 CSV / Collect mode CSV files
    image_files = [path for path in exports_dir.glob("candidate_*_*/*/*.png") if path.is_file()] + [path for path in candidates_dir.glob("candidate_*_*/preview_thickness.png") if path.is_file()]  # 收集预览和对比图 / Collect preview and comparison images
    mph_files = [path for path in exports_dir.glob("candidate_*_*/last_run_model.mph") if path.is_file()]  # 收集保存模型 / Collect saved model files
    state_files = [workflow_state_path(config)]  # 收集状态文件 / Collect state files
    all_files = unique_paths(candidate_files + all_export_files + processed_files + log_files + state_files)  # 合并并去重所有文件 / Merge and deduplicate all files
    groups = [summarize_paths("Candidates", candidate_files), summarize_paths("COMSOL exports", all_export_files), summarize_paths("Mode CSV", mode_files), summarize_paths("Preview images", image_files), summarize_paths("Logs", log_files), summarize_paths("Saved MPH models", mph_files), summarize_paths("Processed targets", processed_files), summarize_paths("Workflow state", state_files)]  # 构造分组摘要 / Build grouped summaries
    total_size_bytes = sum(path.stat().st_size for path in all_files if path.exists() and path.is_file())  # 计算去重总大小 / Compute deduplicated total size
    return {"groups": groups, "total_size_bytes": total_size_bytes, "largest_files": largest_files(all_files)}  # 返回产物摘要 / Return artifact summary


def cleanup_group(label: str, reason: str, paths: list[Path]) -> dict:  # 构建清理预览分组 / Build cleanup preview group
    cleanable = [path for path in unique_paths(paths) if path.exists() and path.is_file()]  # 收集全部可清理文件 / Collect all cleanable files
    size_bytes = sum(path.stat().st_size for path in cleanable)  # 计算全部预估释放空间 / Compute full estimated freeable space
    files = largest_files(cleanable, 20)  # 只展示最大的若干文件 / Show only largest files
    return {"label": label, "reason": reason, "count": len(cleanable), "size_bytes": size_bytes, "files": files}  # 返回清理分组 / Return cleanup group


def load_artifact_cleanup_preview(config: dict) -> dict:  # 读取安全清理预览 / Load safe cleanup preview
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    exports_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取导出目录 / Read export directory
    policy = artifact_retention_policy(config)  # 读取保留策略 / Read retention policy
    mph_files = [path for path in exports_dir.glob("candidate_*_*/last_run_model.mph") if path.is_file()]  # 收集模型副本 / Collect model copies
    export_previews = [path for path in exports_dir.glob("candidate_*_*/*/*.png") if path.is_file()]  # 收集导出预览图 / Collect export preview images
    candidate_previews = [path for path in candidates_dir.glob("candidate_*_*/preview_thickness.png") if path.is_file()]  # 收集候选厚度预览 / Collect candidate thickness previews
    temporary_files = [path for path in [exports_dir / "workflow_state.tmp"] if path.exists() and path.is_file()]  # 收集临时状态文件 / Collect temporary state files
    stale_mph_files = apply_artifact_retention(config, mph_files)  # 按策略筛选模型副本 / Filter model copies by policy
    stale_preview_files = apply_artifact_retention(config, export_previews + candidate_previews)  # 按策略筛选预览图 / Filter preview images by policy
    groups = [cleanup_group("Retention-eligible MPH model copies", "Large LiveLink model snapshots older than the retention window. / 超过保留窗口的大型 LiveLink 模型快照。", stale_mph_files), cleanup_group("Retention-eligible preview images", "Regenerable preview and comparison images outside the retention window. / 超过保留窗口且可再生成的预览和对比图。", stale_preview_files), cleanup_group("Temporary workflow files", "Temporary workflow files are safe to remove when no workflow is running. / 没有工作流运行时，临时工作流文件可以安全移除。", temporary_files)]  # 构建清理建议 / Build cleanup suggestions
    total_size_bytes = sum(group["size_bytes"] for group in groups)  # 计算总可释放空间 / Compute total reclaimable size
    message = f"Preview only; retaining latest {policy['keep_latest_generations']} generations and files newer than {policy['keep_recent_days']:g} days. / 仅预览；保留最近 {policy['keep_latest_generations']} 代和 {policy['keep_recent_days']:g} 天内文件。"  # 构造策略消息 / Build policy message
    return {"dry_run": True, "groups": groups, "policy": policy, "total_size_bytes": total_size_bytes, "message": message}  # 返回只读预览 / Return read-only preview


def cleanable_artifact_paths(config: dict) -> list[Path]:  # 收集允许删除的产物路径 / Collect allowed cleanup artifact paths
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    exports_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取导出目录 / Read export directory
    mph_files = [path for path in exports_dir.glob("candidate_*_*/last_run_model.mph") if path.is_file()]  # 收集模型副本 / Collect model copies
    export_previews = [path for path in exports_dir.glob("candidate_*_*/*/*.png") if path.is_file()]  # 收集导出预览图 / Collect export preview images
    candidate_previews = [path for path in candidates_dir.glob("candidate_*_*/preview_thickness.png") if path.is_file()]  # 收集候选厚度预览 / Collect candidate thickness previews
    temporary_files = [path for path in [exports_dir / "workflow_state.tmp"] if path.exists() and path.is_file()]  # 收集临时状态文件 / Collect temporary state files
    retained_regenerable = apply_artifact_retention(config, mph_files + export_previews + candidate_previews)  # 按保留策略筛选可再生成文件 / Filter regenerable files by retention policy
    return unique_paths(retained_regenerable + temporary_files)  # 返回去重清理路径 / Return deduplicated cleanup paths


def delete_artifact_cleanup_files(config: dict, confirm: bool) -> dict:  # 删除确认后的可清理产物 / Delete confirmed cleanable artifacts
    if not confirm:  # 检查确认标记 / Check confirmation flag
        raise ValueError("Cleanup requires confirm=true. / 清理需要 confirm=true。")  # 拒绝未确认删除 / Reject unconfirmed deletion
    if workflow_snapshot().get("running"):  # 检查工作流是否运行中 / Check whether workflow is running
        raise RuntimeError("Cannot clean artifacts while workflow is running. / 工作流运行时不能清理产物。")  # 拒绝运行中清理 / Reject cleanup during workflow
    deleted = []  # 创建已删除列表 / Create deleted list
    failed = []  # 创建失败列表 / Create failure list
    for path in cleanable_artifact_paths(config):  # 遍历允许删除的路径 / Iterate allowed delete paths
        try:  # 捕获删除错误 / Catch deletion errors
            size_bytes = path.stat().st_size  # 读取文件大小 / Read file size
            path.unlink()  # 删除文件 / Delete file
            deleted.append({"path": str(path), "size_bytes": size_bytes})  # 记录删除文件 / Record deleted file
        except OSError as exc:  # 处理删除失败 / Handle deletion failure
            failed.append({"path": str(path), "error": str(exc)})  # 记录失败文件 / Record failed file
    return {"deleted_count": len(deleted), "deleted_size_bytes": sum(item["size_bytes"] for item in deleted), "deleted": deleted[:50], "failed": failed, "message": "Cleanup complete. / 清理完成。"}  # 返回删除结果 / Return deletion result


def validate_candidate_id(candidate_id: str) -> str:  # 校验候选编号 / Validate candidate id
    if not CANDIDATE_ID_RE.match(candidate_id):  # 检查候选编号格式 / Check candidate-id format
        raise ValueError("Invalid candidate id. / 候选编号格式无效。")  # 抛出格式错误 / Raise format error
    return candidate_id  # 返回候选编号 / Return candidate id


def validate_production_candidate_id(candidate_id: str) -> str:  # 校验生产 pipeline 候选编号 / Validate production candidate id
    if not candidate_id or not PRODUCTION_CANDIDATE_RE.match(candidate_id):  # 检查格式 / Check format
        raise ValueError("Invalid production candidate id. / 生产候选编号格式无效。")  # 抛出格式错误 / Raise format error
    return candidate_id  # 返回候选编号 / Return candidate id


def output_needs_refresh(output: Path, inputs: list[Path]) -> bool:  # 判断输出是否需要刷新 / Decide whether output needs refresh
    if not output.exists():  # 检查输出是否缺失 / Check whether output is missing
        return True  # 缺失输出需要重建 / Missing output needs rebuild
    output_mtime = output.stat().st_mtime  # 读取输出修改时间 / Read output modification time
    return any(input_path.exists() and input_path.stat().st_mtime > output_mtime for input_path in inputs)  # 判断输入是否更新 / Decide whether inputs are newer


def comparison_asset_urls(candidate_id: str) -> dict[str, str]:  # 构造对比图资源地址 / Build comparison asset URLs
    return {"target": f"/assets/export/{candidate_id}/comparison/target_binary.png", "simulated": f"/assets/export/{candidate_id}/comparison/simulated_nodal.png", "overlay": f"/assets/export/{candidate_id}/comparison/target_sim_overlay.png"}  # 返回固定资源地址 / Return fixed asset URLs


def comparison_asset_paths(export_dir: Path) -> dict[str, Path]:  # 构造对比图文件路径 / Build comparison asset paths
    comparison_dir = export_dir / "comparison"  # 构造对比图目录 / Build comparison directory
    return {"target": comparison_dir / "target_binary.png", "simulated": comparison_dir / "simulated_nodal.png", "overlay": comparison_dir / "target_sim_overlay.png"}  # 返回固定文件路径 / Return fixed file paths


def read_json_file(path: Path) -> dict:  # 读取 JSON 文件 / Read JSON file
    if not path.exists():  # 检查文件是否存在 / Check file existence
        return {}  # 返回空对象 / Return empty object
    return json.loads(path.read_text(encoding="utf-8"))  # 读取并解析 JSON / Read and parse JSON


def load_target_analysis_summary(config: dict) -> dict:  # 读取目标分析摘要 / Read target analysis summary
    processed_dir = Path(config["paths"]["processed_targets_dir"])  # 读取处理目录 / Read processed target directory
    analysis_path = processed_dir / "target_analysis.json"  # 构造分析文件路径 / Build analysis file path
    preview_path = processed_dir / "target_preview.png"  # 构造预览图路径 / Build preview image path
    analysis = read_json_file(analysis_path)  # 读取分析数据 / Read analysis data
    return {"analysis": analysis, "analysis_exists": bool(analysis), "analysis_path": str(analysis_path), "preview_exists": preview_path.exists(), "preview_url": "/api/preview.png" if preview_path.exists() else ""}  # 返回摘要 / Return summary


def read_frequencies(path: Path) -> list[dict[str, str]]:  # 读取频率表 / Read frequency table
    if not path.exists():  # 检查频率文件是否存在 / Check frequency file existence
        return []  # 返回空频率表 / Return empty frequencies
    with path.open("r", encoding="utf-8", newline="") as file_obj:  # 打开频率文件 / Open frequency file
        return list(csv.DictReader(file_obj))  # 返回频率行 / Return frequency rows


def render_needed_mode_previews(config: dict, candidate_id: str, score: dict) -> list[Path]:  # 渲染候选模态预览 / Render candidate mode previews
    from src.visualisation.plot_modes import render_mode_preview  # 延迟导入单模态预览渲染 / Lazily import one-mode preview renderer
    export_dir = Path(config["paths"]["comsol_exports_dir"]) / candidate_id  # 构造导出目录 / Build export directory
    if not export_dir.exists():  # 检查导出目录 / Check export directory
        return []  # 返回空预览 / Return empty previews
    best_mode = int(score.get("best_mode", 1) or 1)  # 读取最佳模态 / Read best mode
    image_size = int(config["nodal_extraction"]["image_size"])  # 读取图像尺寸 / Read image size
    epsilon_ratio = float(config["nodal_extraction"]["epsilon_ratio"])  # 读取阈值比例 / Read epsilon ratio
    center_radius_px = int(image_size * float(config["project"]["center_clamp_radius_mm"]) / float(config["project"]["plate_length_mm"])) if config["nodal_extraction"].get("remove_center_region", True) else 0  # 计算中心掩膜半径 / Compute centre mask radius
    mode_files = sorted(export_dir.glob("mode_*.csv"))[:best_mode]  # 选择到最佳模态为止的文件 / Select files through best mode
    preview_dir = export_dir / "previews"  # 构造预览目录 / Build preview directory
    for mode_file in mode_files:  # 遍历需要的模态文件 / Iterate needed mode files
        preview_path = preview_dir / f"{mode_file.stem}.png"  # 构造预览路径 / Build preview path
        if output_needs_refresh(preview_path, [mode_file]):  # 检查预览是否过期 / Check whether preview is stale
            render_mode_preview(mode_file, preview_path, image_size, epsilon_ratio, center_radius_px)  # 重建过期预览 / Rebuild stale preview
    previews = sorted((export_dir / "previews").glob("mode_*.png"))  # 查找预览图 / Find preview images
    return previews  # 返回预览列表 / Return previews


def render_candidate_comparison_assets(config: dict, candidate_id: str, score: dict) -> dict[str, str]:  # 渲染候选对比图资源 / Render candidate comparison image assets
    import numpy as np  # 延迟导入 NumPy / Lazily import NumPy
    from src.visualisation.plot_modes import render_candidate_comparison  # 延迟导入对比图渲染 / Lazily import comparison renderer
    export_dir = Path(config["paths"]["comsol_exports_dir"]) / candidate_id  # 构造导出目录 / Build export directory
    target_path = Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 构造目标数组路径 / Build target array path
    if not export_dir.exists() or not target_path.exists() or not score.get("best_mode"):  # 检查必要输入 / Check required inputs
        return {}  # 返回空资源 / Return empty assets
    mode_path = export_dir / f"mode_{int(score['best_mode']):02d}.csv"  # 构造最佳模态文件 / Build best-mode file
    outputs = comparison_asset_paths(export_dir)  # 构造对比图输出路径 / Build comparison output paths
    if mode_path.exists() and all(not output_needs_refresh(path, [target_path, mode_path]) for path in outputs.values()):  # 检查缓存是否可用 / Check whether cache is usable
        return comparison_asset_urls(candidate_id)  # 复用已有对比图 / Reuse existing comparison images
    image_size = int(config["nodal_extraction"]["image_size"])  # 读取图像尺寸 / Read image size
    epsilon_ratio = float(config["nodal_extraction"]["epsilon_ratio"])  # 读取节点阈值 / Read nodal threshold
    center_radius_px = int(image_size * float(config["project"]["center_clamp_radius_mm"]) / float(config["project"]["plate_length_mm"])) if config["nodal_extraction"].get("remove_center_region", True) else 0  # 计算中心掩膜半径 / Compute centre mask radius
    target_binary = np.load(target_path).astype(bool)  # 读取目标二值图 / Load target binary map
    assets = render_candidate_comparison(export_dir, target_binary, int(score["best_mode"]), image_size, epsilon_ratio, center_radius_px)  # 渲染对比图 / Render comparison images
    return {key: f"/assets/export/{candidate_id}/comparison/{path.name}" for key, path in assets.items()} if assets else {}  # 返回前端资源 URL / Return frontend asset URLs


def mode_metrics_from_score(score: dict, mode_number: int) -> dict:  # 从评分文件读取单模态指标 / Read one-mode metrics from score file
    for item in score.get("all_modes", []):  # 遍历所有模态指标 / Iterate all mode metrics
        if int(item.get("mode", 0)) == mode_number:  # 匹配模态编号 / Match mode number
            return item  # 返回模态指标 / Return mode metrics
    if int(score.get("best_mode", 0) or 0) == mode_number:  # 检查是否为最佳模态 / Check whether mode is best mode
        return {"mode": mode_number, "iou": score.get("best_iou", 0.0), "dice": score.get("best_dice", 0.0), "similarity": score.get("best_similarity", 0.0)}  # 返回最佳模态指标 / Return best-mode metrics
    return {"mode": mode_number, "iou": 0.0, "dice": 0.0, "similarity": 0.0}  # 返回空指标 / Return empty metrics


def frequency_for_mode(frequencies: list[dict[str, str]], mode_number: int) -> float:  # 读取指定模态频率 / Read frequency for one mode
    for row in frequencies:  # 遍历频率行 / Iterate frequency rows
        if int(row.get("mode", 0)) == mode_number:  # 匹配模态编号 / Match mode number
            return float(row.get("frequency_hz", 0.0))  # 返回频率 / Return frequency
    return 0.0  # 未找到返回零 / Return zero when missing


def render_mode_assets(config: dict, candidate_id: str, mode_number: int, frequencies: list[dict[str, str]], score: dict) -> dict:  # 渲染单模态详情资产 / Render one-mode detail assets
    import numpy as np  # 延迟导入 NumPy / Lazily import NumPy
    from src.visualisation.plot_modes import render_candidate_comparison  # 延迟导入对比图渲染 / Lazily import comparison renderer
    from src.visualisation.plot_modes import render_mode_preview  # 延迟导入模态图渲染 / Lazily import mode preview renderer
    export_dir = Path(config["paths"]["comsol_exports_dir"]) / candidate_id  # 构造导出目录 / Build export directory
    target_path = Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 构造目标数组路径 / Build target array path
    mode_path = export_dir / f"mode_{mode_number:02d}.csv"  # 构造模态 CSV 路径 / Build mode CSV path
    if not export_dir.exists() or not target_path.exists() or not mode_path.exists():  # 检查必要文件 / Check required files
        return {"candidate_id": candidate_id, "mode": mode_number, "metrics": mode_metrics_from_score(score, mode_number), "frequency_hz": frequency_for_mode(frequencies, mode_number), "comparison": {}, "mode_preview": ""}  # 返回无资产详情 / Return detail without assets
    image_size = int(config["nodal_extraction"]["image_size"])  # 读取图像尺寸 / Read image size
    epsilon_ratio = float(config["nodal_extraction"]["epsilon_ratio"])  # 读取节点阈值 / Read nodal threshold
    center_radius_px = int(image_size * float(config["project"]["center_clamp_radius_mm"]) / float(config["project"]["plate_length_mm"])) if config["nodal_extraction"].get("remove_center_region", True) else 0  # 计算中心掩膜半径 / Compute centre mask radius
    preview_path = export_dir / "previews" / f"mode_{mode_number:02d}.png"  # 构造模态预览路径 / Build mode preview path
    if output_needs_refresh(preview_path, [mode_path]):  # 检查模态预览是否过期 / Check whether mode preview is stale
        render_mode_preview(mode_path, preview_path, image_size, epsilon_ratio, center_radius_px)  # 重建过期模态预览 / Rebuild stale mode preview
    if int(score.get("best_mode", 0) or 0) == mode_number:  # 检查是否为最佳模态 / Check whether this is the best mode
        comparison = render_candidate_comparison_assets(config, candidate_id, score)  # 复用最佳模态对比缓存 / Reuse best-mode comparison cache
        return {"candidate_id": candidate_id, "mode": mode_number, "metrics": mode_metrics_from_score(score, mode_number), "frequency_hz": frequency_for_mode(frequencies, mode_number), "comparison": comparison, "mode_preview": f"/assets/export/{candidate_id}/previews/{preview_path.name}"}  # 返回最佳模态详情 / Return best-mode detail
    target_binary = np.load(target_path).astype(bool)  # 读取目标二值图 / Load target binary map
    assets = render_candidate_comparison(export_dir, target_binary, mode_number, image_size, epsilon_ratio, center_radius_px)  # 渲染对比图 / Render comparison images
    comparison = {key: f"/assets/export/{candidate_id}/comparison/{path.name}" for key, path in assets.items()}  # 构造对比图 URL / Build comparison URLs
    return {"candidate_id": candidate_id, "mode": mode_number, "metrics": mode_metrics_from_score(score, mode_number), "frequency_hz": frequency_for_mode(frequencies, mode_number), "comparison": comparison, "mode_preview": f"/assets/export/{candidate_id}/previews/{preview_path.name}"}  # 返回单模态详情 / Return one-mode detail


def load_candidate_mode_detail(config: dict, candidate_id: str, mode_number: int) -> dict:  # 读取单模态候选详情 / Load one-mode candidate detail
    valid_id = validate_candidate_id(candidate_id)  # 校验候选编号 / Validate candidate id
    candidate_dir = Path(config["paths"]["candidates_dir"]) / valid_id  # 构造候选目录 / Build candidate directory
    export_dir = Path(config["paths"]["comsol_exports_dir"]) / valid_id  # 构造导出目录 / Build export directory
    if not candidate_dir.exists():  # 检查候选目录 / Check candidate directory
        raise FileNotFoundError(f"Candidate not found: {valid_id}")  # 抛出候选缺失 / Raise missing candidate error
    score = read_json_file(candidate_dir / "score.json")  # 读取评分详情 / Read score detail
    frequencies = read_frequencies(export_dir / "frequencies.csv")  # 读取频率表 / Read frequencies
    return render_mode_assets(config, valid_id, int(mode_number), frequencies, score)  # 渲染并返回单模态详情 / Render and return one-mode detail


def add_zip_file(package: zipfile.ZipFile, path: Path, arcname: str, manifest: list[dict]) -> None:  # 向结果包添加文件 / Add one file to result package
    if path.exists() and path.is_file():  # 检查文件是否存在 / Check whether file exists
        package.write(path, arcname)  # 写入 ZIP 文件 / Write file into ZIP
        manifest.append({"path": arcname, "source": str(path), "size_bytes": path.stat().st_size})  # 记录清单 / Record manifest item


def build_candidate_package(config: dict, candidate_id: str) -> tuple[bytes, str]:  # 构建候选结果包 / Build candidate result package
    valid_id = validate_candidate_id(candidate_id)  # 校验候选编号 / Validate candidate id
    candidate_dir = Path(config["paths"]["candidates_dir"]) / valid_id  # 构造候选目录 / Build candidate directory
    export_dir = Path(config["paths"]["comsol_exports_dir"]) / valid_id  # 构造导出目录 / Build export directory
    if not candidate_dir.exists():  # 检查候选目录 / Check candidate directory
        raise FileNotFoundError(f"Candidate not found: {valid_id}")  # 抛出候选缺失 / Raise missing candidate error
    buffer = BytesIO()  # 创建内存 ZIP 缓冲 / Create in-memory ZIP buffer
    manifest: list[dict] = []  # 创建包内文件清单 / Create package manifest
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:  # 创建 ZIP 包 / Create ZIP package
        for name in ["H.csv", "comsol_parameters.csv", "material_parameters.csv", "metadata.json", "score.json", "preview_thickness.png"]:  # 遍历候选文件 / Iterate candidate files
            add_zip_file(package, candidate_dir / name, f"candidate/{name}", manifest)  # 添加候选文件 / Add candidate file
        for name in ["frequencies.csv", "livelink.log"]:  # 遍历导出摘要文件 / Iterate export summary files
            add_zip_file(package, export_dir / name, f"exports/{name}", manifest)  # 添加导出摘要文件 / Add export summary file
        for mode_file in sorted(export_dir.glob("mode_*.csv")):  # 遍历模态 CSV / Iterate mode CSV files
            add_zip_file(package, mode_file, f"exports/{mode_file.name}", manifest)  # 添加模态 CSV / Add mode CSV file
        for preview_file in sorted((export_dir / "previews").glob("*.png")):  # 遍历模态预览图 / Iterate mode preview images
            add_zip_file(package, preview_file, f"exports/previews/{preview_file.name}", manifest)  # 添加模态预览图 / Add mode preview image
        for comparison_file in sorted((export_dir / "comparison").glob("*.png")):  # 遍历对比图 / Iterate comparison images
            add_zip_file(package, comparison_file, f"exports/comparison/{comparison_file.name}", manifest)  # 添加对比图 / Add comparison image
        package.writestr("manifest.json", json.dumps({"candidate_id": valid_id, "created_at": datetime.now().isoformat(timespec="seconds"), "last_run_model_included": False, "last_run_model_exists": (export_dir / "last_run_model.mph").exists(), "files": manifest}, ensure_ascii=False, indent=2))  # 写入包清单 / Write package manifest
    return buffer.getvalue(), f"{valid_id}_results.zip"  # 返回 ZIP 字节和文件名 / Return ZIP bytes and filename


def report_value(value, fallback: str = "-") -> str:  # 格式化报告值 / Format report value
    if value in {"", None}:  # 检查空值 / Check empty value
        return fallback  # 返回回退值 / Return fallback value
    return html.escape(str(value))  # 返回转义文本 / Return escaped text


def report_size_label(size_bytes: int | float | str | None) -> str:  # 格式化报告文件大小 / Format report file size
    try:  # 捕获大小转换错误 / Catch size conversion errors
        size = float(size_bytes or 0)  # 转换为浮点字节数 / Convert to float bytes
    except (TypeError, ValueError):  # 处理非法大小 / Handle invalid size
        return "-"  # 返回回退值 / Return fallback value
    units = ["B", "KB", "MB", "GB"]  # 定义单位列表 / Define unit list
    unit_index = 0  # 初始化单位索引 / Initialize unit index
    while size >= 1024 and unit_index < len(units) - 1:  # 循环缩放单位 / Scale units iteratively
        size /= 1024  # 转换到下一单位 / Convert to next unit
        unit_index += 1  # 增加单位索引 / Increment unit index
    return f"{size:.1f} {units[unit_index]}"  # 返回格式化大小 / Return formatted size


def report_metric_rows(score: dict) -> str:  # 构建报告指标行 / Build report metric rows
    metrics = [("Best mode", score.get("best_mode")), ("IoU", score.get("best_iou")), ("Dice", score.get("best_dice")), ("Frequency Hz", score.get("frequency_hz")), ("Final score", score.get("final_score"))]  # 定义指标列表 / Define metric list
    return "\n".join(f"<div class='metric'><span>{html.escape(label)}</span><strong>{report_value(value)}</strong></div>" for label, value in metrics)  # 返回指标 HTML / Return metric HTML


def report_mode_table(score: dict) -> str:  # 构建模态指标表 / Build mode metric table
    rows = score.get("all_modes", [])[:20] if isinstance(score.get("all_modes", []), list) else []  # 读取模态行 / Read mode rows
    if not rows:  # 检查是否无模态行 / Check whether mode rows are absent
        return "<p>No per-mode metrics were recorded.</p>"  # 返回空表提示 / Return empty-table note
    body = "\n".join(f"<tr><td>{report_value(row.get('mode'))}</td><td>{report_value(row.get('iou'))}</td><td>{report_value(row.get('dice'))}</td><td>{report_value(row.get('similarity'))}</td></tr>" for row in rows)  # 构建表格主体 / Build table body
    return f"<table><thead><tr><th>Mode</th><th>IoU</th><th>Dice</th><th>Similarity</th></tr></thead><tbody>{body}</tbody></table>"  # 返回表格 / Return table


def report_ranking_table(rows: list[dict]) -> str:  # 构建运行报告排行表 / Build run-report ranking table
    if not rows:  # 检查是否无排行 / Check whether ranking is absent
        return "<p>No ranking data has been generated yet.</p>"  # 返回空排行提示 / Return empty-ranking note
    body = "\n".join(f"<tr><td>{index + 1}</td><td>{report_value(row.get('candidate_id'))}</td><td>{report_value(row.get('best_mode'))}</td><td>{report_value(row.get('best_iou'))}</td><td>{report_value(row.get('best_dice'))}</td><td>{report_value(row.get('frequency_hz'))}</td><td>{report_value(row.get('final_score'))}</td></tr>" for index, row in enumerate(rows[:50]))  # 构建排行表体 / Build ranking body
    return f"<table><thead><tr><th>Rank</th><th>Candidate</th><th>Mode</th><th>IoU</th><th>Dice</th><th>Hz</th><th>Score</th></tr></thead><tbody>{body}</tbody></table>"  # 返回排行表 / Return ranking table


def report_history_table(rows: list[dict]) -> str:  # 构建运行报告历史表 / Build run-report history table
    if not rows:  # 检查是否无历史 / Check whether history is absent
        return "<p>No generation history has been generated yet.</p>"  # 返回空历史提示 / Return empty-history note
    body = "\n".join(f"<tr><td>{report_value(row.get('generation'))}</td><td>{report_value(row.get('candidate_count'))}</td><td>{report_value(row.get('simulated_count'))}</td><td>{report_value(row.get('scored_count'))}</td><td>{report_value(row.get('best_candidate'))}</td><td>{report_value(row.get('final_score'))}</td></tr>" for row in rows[:50])  # 构建历史表体 / Build history body
    return f"<table><thead><tr><th>Generation</th><th>Candidates</th><th>Simulated</th><th>Scored</th><th>Best</th><th>Score</th></tr></thead><tbody>{body}</tbody></table>"  # 返回历史表 / Return history table


def report_artifact_table(summary: dict) -> str:  # 构建运行报告产物表 / Build run-report artifact table
    groups = summary.get("groups", []) if isinstance(summary.get("groups", []), list) else []  # 读取产物分组 / Read artifact groups
    if not groups:  # 检查是否无产物摘要 / Check whether artifact summary is absent
        return "<p>No artifact summary is available.</p>"  # 返回空产物提示 / Return empty-artifact note
    body = "\n".join(f"<tr><td>{report_value(group.get('label'))}</td><td>{report_value(group.get('count'))}</td><td>{report_value(report_size_label(group.get('size_bytes')))}</td></tr>" for group in groups)  # 构建产物表体 / Build artifact body
    return f"<table><thead><tr><th>Group</th><th>Files</th><th>Size</th></tr></thead><tbody>{body}</tbody></table>"  # 返回产物表 / Return artifact table


def build_run_report_html(config: dict) -> str:  # 构建整次运行 HTML 报告 / Build full-run HTML report
    ranking = load_ranking(config)  # 读取候选排行 / Load candidate ranking
    history = load_generation_history(config)  # 读取代数历史 / Load generation history
    artifacts = load_artifact_summary(config)  # 读取产物摘要 / Load artifact summary
    target_summary = load_target_analysis_summary(config)  # 读取目标摘要 / Load target summary
    workflow = workflow_snapshot()  # 读取工作流状态 / Read workflow state
    best = ranking[0] if ranking else {}  # 读取最佳候选 / Read best candidate
    analysis = target_summary.get("analysis", {})  # 读取目标分析 / Read target analysis
    created_at = datetime.now().isoformat(timespec="seconds")  # 生成报告时间 / Build report timestamp
    lines = [  # 创建 HTML 行列表 / Create HTML line list
        "<!doctype html>",  # 添加文档类型 / Add doctype
        "<html lang='en'>",  # 添加 HTML 开始 / Add HTML start
        "<head>",  # 添加头部开始 / Add head start
        "  <meta charset='utf-8'>",  # 添加字符集 / Add charset
        "  <meta name='viewport' content='width=device-width, initial-scale=1'>",  # 添加视口 / Add viewport
        "  <title>Chladni run report</title>",  # 添加标题 / Add title
        "  <style>",  # 添加样式开始 / Add style start
        "    body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #eef2f3; color: #18211f; }",  # 添加页面样式 / Add page style
        "    main { max-width: 1120px; margin: 0 auto; padding: 28px; }",  # 添加主体样式 / Add main style
        "    header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; padding-bottom: 18px; border-bottom: 1px solid #cfd8d2; }",  # 添加头部样式 / Add header style
        "    h1 { margin: 0; font-size: 30px; line-height: 1.1; }",  # 添加一级标题样式 / Add h1 style
        "    h2 { margin: 28px 0 12px; font-size: 15px; text-transform: uppercase; letter-spacing: 0; }",  # 添加二级标题样式 / Add h2 style
        "    .muted { color: #68746f; font-size: 13px; line-height: 1.45; }",  # 添加弱文本样式 / Add muted text style
        "    .metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin-top: 18px; }",  # 添加指标网格样式 / Add metric grid style
        "    .metric { display: grid; gap: 6px; padding: 12px; border: 1px solid #d7ddd7; border-radius: 8px; background: #fffdf8; }",  # 添加指标卡样式 / Add metric card style
        "    .metric span { color: #68746f; font-size: 11px; text-transform: uppercase; }",  # 添加指标标签样式 / Add metric label style
        "    .metric strong { font-size: 16px; overflow-wrap: anywhere; }",  # 添加指标值样式 / Add metric value style
        "    table { width: 100%; border-collapse: collapse; background: #fbfcfb; border: 1px solid #d7ddd7; }",  # 添加表格样式 / Add table style
        "    th, td { padding: 8px 10px; border-bottom: 1px solid #d7ddd7; text-align: left; font-size: 13px; }",  # 添加单元格样式 / Add cell style
        "    th { color: #68746f; font-size: 11px; text-transform: uppercase; }",  # 添加表头样式 / Add table head style
        "    pre { white-space: pre-wrap; background: #101716; color: #fffdf8; padding: 12px; border-radius: 8px; overflow: auto; }",  # 添加代码块样式 / Add pre style
        "    @media (max-width: 760px) { .metrics { grid-template-columns: 1fr; } header { display: grid; } main { padding: 16px; } }",  # 添加响应式样式 / Add responsive style
        "  </style>",  # 添加样式结束 / Add style end
        "</head>",  # 添加头部结束 / Add head end
        "<body>",  # 添加正文开始 / Add body start
        "  <main>",  # 添加主体开始 / Add main start
        "    <header>",  # 添加报告头部开始 / Add report header start
        "      <div>",  # 添加标题容器开始 / Add title container start
        "        <h1>Chladni run report</h1>",  # 添加报告标题 / Add report title
        "        <div class='muted'>Full workflow summary / 整次运行摘要</div>",  # 添加双语说明 / Add bilingual note
        "      </div>",  # 添加标题容器结束 / Add title container end
        f"      <div class='muted'>Created {report_value(created_at)}<br>Status {report_value(workflow.get('stage'))}</div>",  # 添加生成时间和状态 / Add created time and status
        "    </header>",  # 添加报告头部结束 / Add report header end
        "    <section class='metrics'>",  # 添加指标区开始 / Add metric section start
        f"      <div class='metric'><span>Best candidate</span><strong>{report_value(best.get('candidate_id'))}</strong></div>",  # 添加最佳候选 / Add best candidate
        f"      <div class='metric'><span>Best mode</span><strong>{report_value(best.get('best_mode'))}</strong></div>",  # 添加最佳模态 / Add best mode
        f"      <div class='metric'><span>IoU</span><strong>{report_value(best.get('best_iou'))}</strong></div>",  # 添加 IoU / Add IoU
        f"      <div class='metric'><span>Score</span><strong>{report_value(best.get('final_score'))}</strong></div>",  # 添加分数 / Add score
        f"      <div class='metric'><span>Artifacts</span><strong>{report_value(report_size_label(artifacts.get('total_size_bytes')))}</strong></div>",  # 添加产物大小 / Add artifact size
        "    </section>",  # 添加指标区结束 / Add metric section end
        "    <h2>Target Analysis</h2>",  # 添加目标分析标题 / Add target analysis heading
        f"    <pre>{html.escape(json.dumps(analysis, ensure_ascii=False, indent=2))}</pre>",  # 添加目标分析 JSON / Add target-analysis JSON
        "    <h2>Ranking</h2>",  # 添加排行标题 / Add ranking heading
        f"    {report_ranking_table(ranking)}",  # 添加排行表 / Add ranking table
        "    <h2>Generation History</h2>",  # 添加历史标题 / Add history heading
        f"    {report_history_table(history)}",  # 添加历史表 / Add history table
        "    <h2>Artifacts</h2>",  # 添加产物标题 / Add artifact heading
        f"    {report_artifact_table(artifacts)}",  # 添加产物表 / Add artifact table
        "    <h2>Workflow State</h2>",  # 添加工作流标题 / Add workflow heading
        f"    <pre>{html.escape(json.dumps(workflow, ensure_ascii=False, indent=2))}</pre>",  # 添加工作流 JSON / Add workflow JSON
        "  </main>",  # 添加主体结束 / Add main end
        "</body>",  # 添加正文结束 / Add body end
        "</html>",  # 添加 HTML 结束 / Add HTML end
    ]  # 结束 HTML 行列表 / End HTML line list
    return "\n".join(lines)  # 返回完整 HTML / Return complete HTML


def build_candidate_report_html(config: dict, candidate_id: str) -> str:  # 构建候选 HTML 报告 / Build candidate HTML report
    detail = load_candidate_detail(config, candidate_id)  # 读取候选详情 / Load candidate detail
    valid_id = detail["candidate_id"]  # 读取候选编号 / Read candidate id
    score = detail.get("score", {})  # 读取评分 / Read score
    metadata = detail.get("metadata", {})  # 读取元数据 / Read metadata
    comparison = detail.get("comparison", {})  # 读取对比图 / Read comparison images
    best_mode = str(score.get("best_mode", "1")).zfill(2)  # 读取最佳模态 / Read best mode
    best_preview = next((src for src in detail.get("mode_previews", []) if f"mode_{best_mode}" in src), detail.get("mode_previews", [""])[0] if detail.get("mode_previews") else "")  # 选择最佳预览 / Select best preview
    created_at = datetime.now().isoformat(timespec="seconds")  # 生成报告时间 / Build report timestamp
    lines = [  # 创建 HTML 行列表 / Create HTML line list
        "<!doctype html>",  # 添加文档类型 / Add doctype
        "<html lang='en'>",  # 添加 HTML 开始 / Add HTML start
        "<head>",  # 添加头部开始 / Add head start
        "  <meta charset='utf-8'>",  # 添加字符集 / Add charset
        "  <meta name='viewport' content='width=device-width, initial-scale=1'>",  # 添加视口 / Add viewport
        f"  <title>{report_value(valid_id)} report</title>",  # 添加标题 / Add title
        "  <style>",  # 添加样式开始 / Add style start
        "    body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #eef2f3; color: #18211f; }",  # 添加页面样式 / Add page style
        "    main { max-width: 1040px; margin: 0 auto; padding: 28px; }",  # 添加主体样式 / Add main style
        "    header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; padding-bottom: 18px; border-bottom: 1px solid #cfd8d2; }",  # 添加头部样式 / Add header style
        "    h1 { margin: 0; font-size: 28px; line-height: 1.1; }",  # 添加一级标题样式 / Add h1 style
        "    h2 { margin: 28px 0 12px; font-size: 15px; text-transform: uppercase; letter-spacing: 0; }",  # 添加二级标题样式 / Add h2 style
        "    .muted { color: #68746f; font-size: 13px; line-height: 1.45; }",  # 添加弱文本样式 / Add muted text style
        "    .metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin-top: 18px; }",  # 添加指标网格样式 / Add metric grid style
        "    .metric { display: grid; gap: 6px; padding: 12px; border: 1px solid #d7ddd7; border-radius: 8px; background: #fffdf8; }",  # 添加指标卡样式 / Add metric card style
        "    .metric span { color: #68746f; font-size: 11px; text-transform: uppercase; }",  # 添加指标标签样式 / Add metric label style
        "    .metric strong { font-size: 16px; overflow-wrap: anywhere; }",  # 添加指标值样式 / Add metric value style
        "    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }",  # 添加媒体网格样式 / Add media grid style
        "    .media { display: grid; gap: 8px; padding: 10px; border: 1px solid #d7ddd7; border-radius: 8px; background: #fbfcfb; }",  # 添加媒体卡样式 / Add media card style
        "    .media img { width: 100%; border: 1px solid #d7ddd7; border-radius: 6px; background: #fff; object-fit: contain; }",  # 添加图片样式 / Add image style
        "    table { width: 100%; border-collapse: collapse; background: #fbfcfb; border: 1px solid #d7ddd7; }",  # 添加表格样式 / Add table style
        "    th, td { padding: 8px 10px; border-bottom: 1px solid #d7ddd7; text-align: left; font-size: 13px; }",  # 添加单元格样式 / Add cell style
        "    th { color: #68746f; font-size: 11px; text-transform: uppercase; }",  # 添加表头样式 / Add table head style
        "    pre { white-space: pre-wrap; background: #101716; color: #fffdf8; padding: 12px; border-radius: 8px; overflow: auto; }",  # 添加代码块样式 / Add pre style
        "    @media (max-width: 760px) { .metrics, .grid { grid-template-columns: 1fr; } header { display: grid; } main { padding: 16px; } }",  # 添加响应式样式 / Add responsive style
        "  </style>",  # 添加样式结束 / Add style end
        "</head>",  # 添加头部结束 / Add head end
        "<body>",  # 添加正文开始 / Add body start
        "  <main>",  # 添加主体开始 / Add main start
        "    <header>",  # 添加报告头部开始 / Add report header start
        "      <div>",  # 添加标题容器开始 / Add title container start
        f"        <h1>{report_value(valid_id)}</h1>",  # 添加候选标题 / Add candidate title
        "        <div class='muted'>Chladni candidate report / Chladni 候选报告</div>",  # 添加双语说明 / Add bilingual note
        "      </div>",  # 添加标题容器结束 / Add title container end
        f"      <div class='muted'>Created {report_value(created_at)}<br>Generated by local Chladni Studio</div>",  # 添加生成时间 / Add created time
        "    </header>",  # 添加报告头部结束 / Add report header end
        f"    <section class='metrics'>{report_metric_rows(score)}</section>",  # 添加指标区 / Add metric section
        "    <h2>Pattern Match</h2>",  # 添加匹配标题 / Add match heading
        "    <section class='grid'>",  # 添加匹配网格开始 / Add match grid start
        f"      <div class='media'><strong>Target</strong><img src='{report_value(comparison.get('target', ''))}' alt='target binary'></div>",  # 添加目标图 / Add target image
        f"      <div class='media'><strong>Simulated</strong><img src='{report_value(comparison.get('simulated', ''))}' alt='simulated nodal'></div>",  # 添加仿真图 / Add simulated image
        f"      <div class='media'><strong>Overlay</strong><img src='{report_value(comparison.get('overlay', ''))}' alt='target simulation overlay'></div>",  # 添加叠加图 / Add overlay image
        "    </section>",  # 添加匹配网格结束 / Add match grid end
        "    <h2>Design Fields</h2>",  # 添加设计场标题 / Add design field heading
        "    <section class='grid'>",  # 添加设计网格开始 / Add design grid start
        f"      <div class='media'><strong>Thickness field</strong><img src='{report_value(detail.get('thickness_preview', ''))}' alt='thickness preview'></div>",  # 添加厚度图 / Add thickness image
        f"      <div class='media'><strong>Best mode preview</strong><img src='{report_value(best_preview)}' alt='best mode preview'></div>",  # 添加模态图 / Add mode image
        "    </section>",  # 添加设计网格结束 / Add design grid end
        "    <h2>Mode Metrics</h2>",  # 添加模态指标标题 / Add mode metric heading
        f"    {report_mode_table(score)}",  # 添加模态指标表 / Add mode metric table
        "    <h2>Metadata</h2>",  # 添加元数据标题 / Add metadata heading
        f"    <pre>{html.escape(json.dumps(metadata, ensure_ascii=False, indent=2))}</pre>",  # 添加元数据 JSON / Add metadata JSON
        "  </main>",  # 添加主体结束 / Add main end
        "</body>",  # 添加正文结束 / Add body end
        "</html>",  # 添加 HTML 结束 / Add HTML end
    ]  # 结束 HTML 行列表 / End HTML line list
    return "\n".join(lines)  # 返回完整 HTML / Return complete HTML


def load_candidate_detail(config: dict, candidate_id: str) -> dict:  # 读取候选详情 / Load candidate detail
    from src.visualisation.plot_thickness import render_candidate_preview  # 延迟导入厚度预览 / Lazily import thickness preview renderer
    valid_id = validate_candidate_id(candidate_id)  # 校验候选编号 / Validate candidate id
    candidate_dir = Path(config["paths"]["candidates_dir"]) / valid_id  # 构造候选目录 / Build candidate directory
    export_dir = Path(config["paths"]["comsol_exports_dir"]) / valid_id  # 构造导出目录 / Build export directory
    if not candidate_dir.exists():  # 检查候选目录 / Check candidate directory
        raise FileNotFoundError(f"Candidate not found: {valid_id}")  # 抛出候选缺失 / Raise missing candidate error
    if (candidate_dir / "H.csv").exists() and output_needs_refresh(candidate_dir / "preview_thickness.png", [candidate_dir / "H.csv"]):  # 检查厚度矩阵预览是否过期 / Check whether thickness preview is stale
        render_candidate_preview(candidate_dir)  # 确保厚度预览存在 / Ensure thickness preview exists
    score = read_json_file(candidate_dir / "score.json")  # 读取评分详情 / Read score detail
    previews = render_needed_mode_previews(config, valid_id, score)  # 渲染模态预览 / Render mode previews
    comparison = render_candidate_comparison_assets(config, valid_id, score)  # 渲染目标仿真对比图 / Render target-simulation comparison
    frequencies = read_frequencies(export_dir / "frequencies.csv")  # 读取频率表 / Read frequencies
    return {"candidate_id": valid_id, "metadata": read_json_file(candidate_dir / "metadata.json"), "score": score, "frequencies": frequencies, "thickness_preview": f"/assets/candidate/{valid_id}/preview_thickness.png", "comparison": comparison, "mode_previews": [f"/assets/export/{valid_id}/previews/{path.name}" for path in previews]}  # 返回候选详情 / Return candidate detail


def normalise_target_image(raw_png: bytes, output_path: Path) -> None:  # 保存规范化目标图 / Save normalised target image
    image = Image.open(BytesIO(raw_png)).convert("RGB")  # 读取上传图并转为 RGB / Read uploaded image and convert to RGB
    resized = image.resize((512, 512), Image.Resampling.LANCZOS) if image.size != (512, 512) else image  # 保持 512 画布 / Keep a 512 canvas
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 创建目标目录 / Create target directory
    resized.save(output_path, format="PNG")  # 保存 PNG 文件 / Save PNG file


def prepare_target_outputs(config: dict, target_mode_override: str | None = None) -> dict:  # 按配置处理目标图 / Prepare target using config
    image_size = int(config["nodal_extraction"]["image_size"])  # 读取内部图像尺寸 / Read internal image size
    line_width = int(config["nodal_extraction"]["target_line_width_px"])  # 读取目标线宽 / Read target line width
    target_mode = target_mode_override or str(config["nodal_extraction"].get("target_mode", "chladni"))  # 读取目标模式 / Read target mode
    if target_mode not in {"chladni", "stroke", "edge", "filled"}:  # 检查目标模式是否合法 / Check target mode validity
        raise ValueError("Unsupported target mode. / 不支持的目标模式。")  # 抛出模式错误 / Raise mode error
    plate_radius_px = int(image_size * float(config["project"]["center_clamp_radius_mm"]) / float(config["project"]["plate_length_mm"]))  # 计算夹持区像素半径 / Compute clamp radius in pixels
    binary = preprocess_target(config["paths"]["target_pattern"], image_size, line_width, plate_radius_px, config["paths"]["processed_targets_dir"], target_mode)  # 运行目标预处理 / Run target preprocessing
    analysis = save_target_analysis(binary, config["paths"]["processed_targets_dir"], int(config["project"]["grid_size"]), line_width)  # 保存目标分析 / Save target analysis
    return analysis  # 返回分析摘要 / Return analysis summary


def image_bytes(path: Path) -> bytes:  # 读取或生成目标 PNG 字节 / Read or create target PNG bytes
    if path.exists():  # 判断目标图是否存在 / Check whether target image exists
        return path.read_bytes()  # 返回现有目标图 / Return existing target image
    image = Image.new("RGB", (512, 512), "white")  # 创建空白白底图 / Create blank white image
    buffer = BytesIO()  # 创建内存缓冲 / Create memory buffer
    image.save(buffer, format="PNG")  # 保存到内存 PNG / Save PNG to memory
    return buffer.getvalue()  # 返回 PNG 字节 / Return PNG bytes


def decode_data_url(data_url: str) -> bytes:  # 解码前端 data URL / Decode frontend data URL
    prefix = "data:image/png;base64,"  # 定义 PNG data URL 前缀 / Define PNG data URL prefix
    if not data_url.startswith(prefix):  # 检查上传格式 / Check uploaded format
        raise ValueError("Expected a PNG data URL. / 需要 PNG data URL。")  # 抛出格式错误 / Raise format error
    return base64.b64decode(data_url[len(prefix):])  # 解码 Base64 数据 / Decode Base64 payload


def make_handler(config: dict):  # 创建绑定配置的处理类 / Create config-bound handler class
    restore_workflow_state(config)  # 启动时恢复工作流状态 / Restore workflow state on startup
    target_path = Path(config["paths"]["target_pattern"])  # 读取目标图路径 / Read target image path
    processed_dir = Path(config["paths"]["processed_targets_dir"])  # 读取处理输出目录 / Read processed output directory
    html_path = designer_html_path()  # 读取 HTML 路径 / Read HTML path

    class TargetUiHandler(BaseHTTPRequestHandler):  # 定义本地目标 UI 处理器 / Define local target UI handler
        def log_message(self, format: str, *args) -> None:  # 降低默认日志噪声 / Reduce default log noise
            return None  # 不打印每个请求 / Do not print every request

        def send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:  # 发送字节响应 / Send byte response
            self.send_response(status)  # 写入状态码 / Write status code
            self.send_header("Content-Type", content_type)  # 写入内容类型 / Write content type
            self.send_header("Content-Length", str(len(body)))  # 写入内容长度 / Write content length
            self.end_headers()  # 结束响应头 / Finish headers
            self.wfile.write(body)  # 写入响应体 / Write response body

        def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:  # 发送 JSON 响应 / Send JSON response
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")  # 编码 JSON / Encode JSON body
            self.send_bytes(body, "application/json; charset=utf-8", status)  # 发送 JSON 字节 / Send JSON bytes

        def send_file(self, path: Path, content_type: str) -> None:  # 发送本地文件 / Send local file
            if not path.exists():  # 检查文件是否存在 / Check file existence
                self.send_json({"error": "File not found. / 文件不存在。"}, HTTPStatus.NOT_FOUND)  # 返回 404 / Return 404
                return  # 结束请求 / Finish request
            self.send_bytes(path.read_bytes(), content_type)  # 发送文件字节 / Send file bytes

        def send_download(self, body: bytes, filename: str, content_type: str) -> None:  # 发送下载文件 / Send downloadable file
            self.send_response(HTTPStatus.OK)  # 写入成功状态码 / Write success status code
            self.send_header("Content-Type", content_type)  # 写入内容类型 / Write content type
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')  # 写入下载文件名 / Write download filename
            self.send_header("Content-Length", str(len(body)))  # 写入内容长度 / Write content length
            self.end_headers()  # 结束响应头 / Finish headers
            self.wfile.write(body)  # 写入响应体 / Write response body

        def do_GET(self) -> None:  # 处理 GET 请求 / Handle GET requests
            parsed = urlparse(self.path)  # 解析请求 URL / Parse request URL
            route = parsed.path  # 读取请求路径 / Read request path
            query = parse_qs(parsed.query)  # 解析查询参数 / Parse query string
            if route in {"/", "/target_designer.html"}:  # 判断是否请求主页 / Check designer page request
                self.send_bytes(html_path.read_bytes(), "text/html; charset=utf-8")  # 返回 HTML 页面 / Return HTML page
                return  # 结束请求 / Finish request
            if route == "/api/config":  # 判断是否请求配置 / Check config request
                self.send_json({"grid_size": int(config["project"]["grid_size"]), "center_clamp_radius_mm": float(config["project"]["center_clamp_radius_mm"]), "plate_length_mm": float(config["project"]["plate_length_mm"]), "target_path": str(target_path), "processed_targets_dir": str(processed_dir), "target_mode": str(config["nodal_extraction"].get("target_mode", "chladni")), "material": config.get("material", {}), "simulation": config.get("simulation", {}), "optimisation": config.get("optimisation", {}), "comsol": config.get("comsol", {}), "artifact_retention": artifact_retention_policy(config)})  # 返回前端配置 / Return frontend config
                return  # 结束请求 / Finish request
            if route == "/api/ranking":  # 判断是否请求评分排行 / Check ranking request
                self.send_json({"ranking": load_ranking(config)})  # 返回评分排行 / Return ranking data
                return  # 结束请求 / Finish request
            if route == "/api/history":  # 判断是否请求代数历史 / Check generation-history request
                self.send_json({"history": load_generation_history(config)})  # 返回代数历史 / Return generation history
                return  # 结束请求 / Finish request
            if route == "/api/target-analysis":  # 判断是否请求目标分析 / Check target-analysis request
                self.send_json(load_target_analysis_summary(config))  # 返回目标分析 / Return target analysis
                return  # 结束请求 / Finish request
            if route == "/api/production-runs":  # 列出生产 pipeline 完成的运行 / List completed production runs
                try:  # 容错 / Tolerate read errors
                    include_diagnostics = str(query.get("include_diagnostics", [""])[0]).lower() in {"1", "true", "yes", "on"}  # include smoke/dev runs when requested
                    self.send_json({"runs": load_production_runs(include_diagnostics=include_diagnostics)})  # 返回 / Return
                except Exception as exc:  # 处理异常 / Handle exception
                    self.send_json({"error": str(exc), "runs": []}, HTTPStatus.INTERNAL_SERVER_ERROR)  # / 500
                return  # 结束请求 / Finish request
            if route == "/api/production-run-detail":  # 单个生产运行的详情 / Single production-run detail
                try:  # 容错 / Tolerate
                    candidate_id = query.get("id", [""])[0]  # 读取编号 / Read id
                    self.send_json(load_production_run_detail(config, candidate_id))  # 返回详情 / Return detail
                except FileNotFoundError as exc:  # 不存在 / Missing
                    self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)  # 404 / 404
                except ValueError as exc:  # 编号无效 / Invalid id
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 400 / 400
                except Exception as exc:  # 其他错误 / Other errors
                    self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)  # 500 / 500
                return  # 结束请求 / Finish request
            if route == "/api/logs":  # 判断是否请求运行日志 / Check run-log request
                self.send_json(load_log_tails(config))  # 返回日志尾部 / Return log tails
                return  # 结束请求 / Finish request
            if route == "/api/artifacts":  # 判断是否请求产物摘要 / Check artifact-summary request
                self.send_json(load_artifact_summary(config))  # 返回产物占用摘要 / Return artifact storage summary
                return  # 结束请求 / Finish request
            if route == "/api/artifacts/cleanup-preview":  # 判断是否请求清理预览 / Check cleanup-preview request
                self.send_json(load_artifact_cleanup_preview(config))  # 返回只读清理预览 / Return read-only cleanup preview
                return  # 结束请求 / Finish request
            if route == "/api/candidate":  # 判断是否请求候选详情 / Check candidate-detail request
                try:  # 捕获详情读取错误 / Catch detail-loading errors
                    candidate_id = query.get("id", [""])[0]  # 读取候选编号 / Read candidate id
                    self.send_json(load_candidate_detail(config, candidate_id))  # 返回候选详情 / Return candidate detail
                except Exception as exc:  # 处理异常 / Handle exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/candidate-mode":  # 判断是否请求单模态详情 / Check candidate-mode detail request
                try:  # 捕获详情读取错误 / Catch detail-loading errors
                    candidate_id = query.get("id", [""])[0]  # 读取候选编号 / Read candidate id
                    mode_number = int(query.get("mode", ["1"])[0])  # 读取模态编号 / Read mode number
                    self.send_json(load_candidate_mode_detail(config, candidate_id, mode_number))  # 返回单模态详情 / Return one-mode detail
                except Exception as exc:  # 处理异常 / Handle exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/candidate-package":  # 判断是否请求候选结果包 / Check candidate-package request
                try:  # 捕获打包错误 / Catch packaging errors
                    candidate_id = query.get("id", [""])[0]  # 读取候选编号 / Read candidate id
                    body, filename = build_candidate_package(config, candidate_id)  # 构建 ZIP 包 / Build ZIP package
                    self.send_download(body, filename, "application/zip")  # 发送 ZIP 下载 / Send ZIP download
                except Exception as exc:  # 处理异常 / Handle exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/candidate-report":  # 判断是否请求候选报告 / Check candidate-report request
                try:  # 捕获报告错误 / Catch report errors
                    candidate_id = query.get("id", [""])[0]  # 读取候选编号 / Read candidate id
                    self.send_bytes(build_candidate_report_html(config, candidate_id).encode("utf-8"), "text/html; charset=utf-8")  # 返回 HTML 报告 / Return HTML report
                except Exception as exc:  # 处理异常 / Handle exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/candidate-mph":  # 列出候选关联的 .mph / List candidate-related .mph files
                try:  # 捕获错误 / Catch errors
                    candidate_id = query.get("id", [""])[0]  # 读取候选编号 / Read candidate id
                    files = discover_candidate_mph_files(candidate_id)  # 收集文件 / Collect files
                    self.send_json({"candidate_id": candidate_id, "count": len(files), "files": files})  # 返回 / Return
                except Exception as exc:  # 处理异常 / Handle exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 错误 / Error
                return  # 结束 / Finish
            if route == "/api/run-report":  # 判断是否请求整次运行报告 / Check full-run report request
                self.send_bytes(build_run_report_html(config).encode("utf-8"), "text/html; charset=utf-8")  # 返回 HTML 报告 / Return HTML report
                return  # 结束请求 / Finish request
            if route == "/api/workflow":  # 判断是否请求工作流状态 / Check workflow-status request
                self.send_json(workflow_snapshot())  # 返回工作流状态 / Return workflow status
                return  # 结束请求 / Finish request
            if route == "/api/recovery":  # 判断是否请求恢复建议 / Check recovery-hints request
                self.send_json(collect_recovery_hints(config))  # 返回恢复建议 / Return recovery hints
                return  # 结束请求 / Finish request
            if route == "/api/diagnostics":  # 判断是否请求环境诊断 / Check diagnostics request
                from src.comsol.diagnostics import diagnose_comsol_environment  # 延迟导入诊断函数 / Lazily import diagnostics function
                self.send_json(diagnose_comsol_environment(config))  # 返回诊断信息 / Return diagnostics data
                return  # 结束请求 / Finish request
            if route == "/api/comsol-discovery":  # 判断是否请求 COMSOL 发现 / Check COMSOL discovery request
                from src.comsol.discovery import discover_runtime_environment  # 延迟导入发现函数 / Lazily import discovery function
                self.send_json(discover_runtime_environment())  # 返回发现结果 / Return discovery result
                return  # 结束请求 / Finish request
            if route == "/api/self-test":  # 判断是否请求部署自检 / Check deployment self-test request
                from src.comsol.diagnostics import run_deployment_self_test  # 延迟导入自检函数 / Lazily import self-test function
                self.send_json(run_deployment_self_test(config))  # 返回自检信息 / Return self-test data
                return  # 结束请求 / Finish request
            if route.startswith("/assets/candidate/"):  # 判断是否请求候选资源 / Check candidate asset request
                parts = route.split("/")  # 拆分路径 / Split path
                candidate_id = validate_candidate_id(parts[3]) if len(parts) == 5 else ""  # 读取候选编号 / Read candidate id
                asset_name = parts[4] if len(parts) == 5 else ""  # 读取资源名 / Read asset name
                if asset_name != "preview_thickness.png":  # 检查资源名 / Check asset name
                    self.send_json({"error": "Asset not found. / 资源不存在。"}, HTTPStatus.NOT_FOUND)  # 返回 404 / Return 404
                    return  # 结束请求 / Finish request
                self.send_file(Path(config["paths"]["candidates_dir"]) / candidate_id / asset_name, "image/png")  # 返回厚度预览 / Return thickness preview
                return  # 结束请求 / Finish request
            if route.startswith("/assets/production/"):  # 判断是否请求生产候选资源 / Check production-candidate asset request
                parts = route.split("/")  # 拆分 / Split
                if len(parts) == 5:  # /assets/production/<id>/<name> / Path shape check
                    asset_path = resolve_production_asset(config, parts[3], parts[4])  # 解析 / Resolve
                    if asset_path is not None:  # 命中 / Hit
                        self.send_file(asset_path, "image/png")  # 返回 PNG / Return PNG
                        return  # 结束 / Finish
                self.send_json({"error": "Asset not found. / 资源不存在。"}, HTTPStatus.NOT_FOUND)  # 404 / 404
                return  # 结束 / Finish
            if route.startswith("/assets/export/"):  # 判断是否请求导出资源 / Check export asset request
                parts = route.split("/")  # 拆分路径 / Split path
                candidate_id = validate_candidate_id(parts[3]) if len(parts) == 6 else ""  # 读取候选编号 / Read candidate id
                folder_name = parts[4] if len(parts) == 6 else ""  # 读取资源目录 / Read asset folder
                asset_name = parts[5] if len(parts) == 6 else ""  # 读取资源名 / Read asset name
                valid_preview = folder_name == "previews" and re.match(r"^mode_\d{2}\.png$", asset_name)  # 检查模态图名 / Check mode image name
                valid_comparison = folder_name == "comparison" and asset_name in {"target_binary.png", "simulated_nodal.png", "target_sim_overlay.png"}  # 检查对比图名 / Check comparison image name
                if not valid_preview and not valid_comparison:  # 检查资源是否合法 / Check asset validity
                    self.send_json({"error": "Asset not found. / 资源不存在。"}, HTTPStatus.NOT_FOUND)  # 返回 404 / Return 404
                    return  # 结束请求 / Finish request
                self.send_file(Path(config["paths"]["comsol_exports_dir"]) / candidate_id / folder_name / asset_name, "image/png")  # 返回导出资源 / Return export asset
                return  # 结束请求 / Finish request
            if route == "/api/target.png":  # 判断是否请求目标图 / Check target image request
                self.send_bytes(image_bytes(target_path), "image/png")  # 返回目标 PNG / Return target PNG
                return  # 结束请求 / Finish request
            if route == "/api/preview.png":  # 判断是否请求预览图 / Check preview image request
                preview_path = processed_dir / "target_preview.png"  # 构造预览图路径 / Build preview path
                self.send_bytes(image_bytes(preview_path), "image/png")  # 返回预览 PNG / Return preview PNG
                return  # 结束请求 / Finish request
            self.send_json({"error": "Not found. / 未找到。"}, HTTPStatus.NOT_FOUND)  # 返回 404 / Return 404

        def do_POST(self) -> None:  # 处理 POST 请求 / Handle POST requests
            route = self.path.split("?", 1)[0]  # 去掉查询参数 / Remove query string
            if route == "/api/material":  # 检查材料保存路由 / Check material save route
                try:  # 捕获材料保存错误 / Catch material save errors
                    length = int(self.headers.get("Content-Length", "0"))  # 读取请求体长度 / Read request body length
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))  # 读取并解析 JSON / Read and parse JSON
                    material = validate_material_payload(payload)  # 校验材料参数 / Validate material parameters
                    config["material"] = material  # 更新运行时配置 / Update runtime config
                    write_material_to_config(material)  # 写回配置文件 / Write back config file
                    self.send_json({"saved_at": datetime.now().isoformat(timespec="seconds"), "material": material})  # 返回保存结果 / Return save result
                except Exception as exc:  # 处理异常 / Handle exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/scoring-config":  # 检查评分配置保存路由 / Check scoring config save route
                try:  # 捕获评分配置保存错误 / Catch scoring config save errors
                    length = int(self.headers.get("Content-Length", "0"))  # 读取请求体长度 / Read request body length
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))  # 读取并解析 JSON / Read and parse JSON
                    scoring = validate_scoring_payload(payload)  # 校验评分参数 / Validate scoring parameters
                    config["simulation"]["frequency_min_hz"] = scoring["frequency_min_hz"]  # 更新最小频率 / Update minimum frequency
                    config["simulation"]["frequency_max_hz"] = scoring["frequency_max_hz"]  # 更新最大频率 / Update maximum frequency
                    config["optimisation"]["roughness_weight"] = scoring["roughness_weight"]  # 更新粗糙度权重 / Update roughness weight
                    config["optimisation"]["mass_weight"] = scoring["mass_weight"]  # 更新质量权重 / Update mass weight
                    config["optimisation"]["frequency_weight"] = scoring["frequency_weight"]  # 更新频率权重 / Update frequency weight
                    write_scoring_to_config(scoring)  # 写回配置文件 / Write config file
                    self.send_json({"saved_at": datetime.now().isoformat(timespec="seconds"), "scoring": scoring})  # 返回保存结果 / Return save result
                except Exception as exc:  # 处理异常 / Handle exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/artifact-retention":  # 检查产物保留配置保存路由 / Check artifact retention save route
                try:  # 捕获保留策略保存错误 / Catch retention save errors
                    length = int(self.headers.get("Content-Length", "0"))  # 读取请求体长度 / Read request body length
                    payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}  # 读取并解析 JSON / Read and parse JSON
                    retention = validate_artifact_retention_payload(payload)  # 校验保留策略 / Validate retention policy
                    config["artifact_retention"] = retention  # 更新运行时配置 / Update runtime config
                    write_artifact_retention_to_config(retention)  # 写回配置文件 / Write config file
                    self.send_json({"artifact_retention": retention, "saved_at": datetime.now().isoformat(timespec="seconds")})  # 返回保存结果 / Return save result
                except Exception as exc:  # 处理保存异常 / Handle save exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/comsol-paths":  # 检查 COMSOL 路径保存路由 / Check COMSOL path save route
                try:  # 捕获路径保存错误 / Catch path save errors
                    from src.comsol.discovery import write_comsol_paths_to_config  # 延迟导入路径写入函数 / Lazily import path writer
                    length = int(self.headers.get("Content-Length", "0"))  # 读取请求体长度 / Read request body length
                    payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}  # 读取并解析 JSON / Read and parse JSON
                    paths = validate_comsol_paths_payload(payload)  # 校验路径载荷 / Validate path payload
                    result = write_comsol_paths_to_config(config_path(), paths)  # 写入配置文件 / Write config file
                    config.update(load_config(config_path()))  # 刷新运行时配置 / Refresh runtime config
                    self.send_json({"saved_at": datetime.now().isoformat(timespec="seconds"), **result})  # 返回保存结果 / Return save result
                except Exception as exc:  # 处理路径保存异常 / Handle path save exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/cancel-workflow":  # 检查取消工作流路由 / Check workflow cancellation route
                try:  # 捕获取消错误 / Catch cancellation errors
                    self.send_json(request_workflow_cancel(config))  # 请求取消并返回状态 / Request cancellation and return state
                except RuntimeError as exc:  # 处理没有运行中的工作流 / Handle no running workflow
                    self.send_json({"error": str(exc)}, HTTPStatus.CONFLICT)  # 返回冲突错误 / Return conflict error
                except Exception as exc:  # 处理取消异常 / Handle cancellation exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/open-in-comsol":  # 用本机 COMSOL 打开 .mph / Launch local COMSOL with selected .mph
                try:  # 捕获错误 / Catch errors
                    length = int(self.headers.get("Content-Length", "0"))  # 请求体长度 / Body length
                    payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}  # 解析 JSON / Parse JSON
                    mph_path = str(payload.get("path", "")).strip()  # 读取路径 / Read path
                    auto_selected_mph = None  # 自动选择的模型 / Auto-selected model
                    if not mph_path:  # 缺失 / Missing
                        candidate_id = str(payload.get("candidate_id", "")).strip()  # 候选编号 / Candidate id
                        if not candidate_id:  # 完全无线索 / No clue
                            raise ValueError("Provide either 'path' or 'candidate_id'. / 必须提供 path 或 candidate_id。")  # / Reject
                        auto_selected_mph = select_best_candidate_mph_file(candidate_id)  # 选择最佳模型 / Select best model
                        mph_path = str(auto_selected_mph["path"])  # 使用最佳模型 / Use best model
                    result = open_mph_in_comsol(config, mph_path)  # 启动 / Launch
                    if auto_selected_mph is not None:  # 候选自动选择时附带选择理由 / Include selection metadata for candidate auto-pick
                        result["selection"] = auto_selected_mph  # 最佳模型元数据 / Best-model metadata
                    self.send_json(result)  # 返回元数据 / Return metadata
                except FileNotFoundError as exc:  # 文件不存在 / Missing file
                    self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)  # 404 / 404
                except ValueError as exc:  # 参数错误 / Bad params
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 400 / 400
                except Exception as exc:  # 其他异常 / Other
                    self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)  # 500 / 500
                return  # 结束 / Finish
            if route == "/api/run-workflow":  # 检查自动工作流路由 / Check automatic workflow route
                try:  # 捕获启动错误 / Catch startup errors
                    if workflow_snapshot().get("running"):  # 检查是否已有工作流运行 / Check existing workflow
                        self.send_json({"error": "Workflow is already running. / 工作流已在运行。"}, HTTPStatus.CONFLICT)  # 返回冲突错误 / Return conflict error
                        return  # 结束请求 / Finish request
                    WORKFLOW_CANCEL_EVENT.clear()  # 清除旧取消事件 / Clear stale cancellation event
                    length = int(self.headers.get("Content-Length", "0"))  # 读取请求体长度 / Read request body length
                    raw_payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}  # 读取并解析 JSON / Read and parse JSON
                    payload = validate_workflow_payload(raw_payload, config)  # 校验工作流载荷 / Validate workflow payload
                    update_and_persist_workflow_state(config, event={"stage": "queued", "message": "Workflow queued. / 工作流已排队。"}, running=True, cancel_requested=False, stage="queued", message="Workflow queued. / 工作流已排队。", result=None, error="", current_candidate="", current_index=0, total=0, events=[])  # 设置排队状态 / Set queued state
                    thread = threading.Thread(target=run_workflow_thread, args=(config, payload), daemon=True)  # 创建后台线程 / Create background thread
                    thread.start()  # 启动后台线程 / Start background thread
                    self.send_json(workflow_snapshot())  # 返回初始状态 / Return initial status
                except Exception as exc:  # 处理启动异常 / Handle startup exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/material-frequency-sweep":  # 材料预扫频路由 / Material magic-frequency pre-sweep route
                try:  # 捕获扫频错误 / Catch sweep errors
                    length = int(self.headers.get("Content-Length", "0"))  # 读取请求体长度 / Read body length
                    raw_payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}  # 解析 JSON / Parse JSON
                    params = validate_material_sweep_payload(raw_payload, config)  # 校验载荷 / Validate payload
                    target_binary_path = Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 目标二值图路径 / Target binary path
                    if not target_binary_path.exists():  # 缺少目标 / Missing target
                        self.send_json({"error": "Target not saved yet — draw and save a target first. / 请先在画板保存目标后再扫频。"}, HTTPStatus.BAD_REQUEST)  # 400 / 400
                        return  # 结束 / Finish
                    import numpy as np  # 延迟导入 NumPy / Lazy import
                    from src.optimisation.material_frequency_sweep import MaterialSweepConfig  # 延迟导入扫频配置 / Lazy import sweep config
                    from src.optimisation.material_frequency_sweep import run_material_frequency_sweep  # 延迟导入扫频函数 / Lazy import sweep
                    target_binary = np.load(target_binary_path).astype(bool)  # 加载目标 / Load target
                    sweep_cfg = MaterialSweepConfig(  # 构建扫频配置 / Build sweep config
                        stiffness_ratio=params["stiffness_ratio"],
                        shear_ratio=params["shear_ratio"],
                        f_min_hz=params["f_min_hz"],
                        f_max_hz=params["f_max_hz"],
                        n_points=params["n_points"],
                        top_k=params["top_k"],
                    )
                    result = run_material_frequency_sweep(config, target_binary, sweep_cfg)  # 同步运行（~10-30s） / Run synchronously (~10-30s)
                    self.send_json(result)  # 返回完整结果 / Return full result
                except ValueError as exc:  # 校验错误 / Validation error
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 400 / 400
                except Exception as exc:  # 其他错误 / Other errors
                    self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)  # 500 / 500
                return  # 结束 / Finish

            if route == "/api/run-production-pipeline":  # 检查 W10+Phase pipeline 路由 / Check W10+Phase production pipeline route
                try:  # 捕获启动错误 / Catch startup errors
                    if workflow_snapshot().get("running"):  # 检查是否已有任务运行 / Check existing task
                        self.send_json({"error": "Workflow is already running. / 工作流已在运行。"}, HTTPStatus.CONFLICT)  # 返回冲突错误 / Return conflict error
                        return  # 结束请求 / Finish request
                    WORKFLOW_CANCEL_EVENT.clear()  # 清除旧取消事件 / Clear stale cancellation event
                    length = int(self.headers.get("Content-Length", "0"))  # 读取请求体长度 / Read request body length
                    raw_payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}  # 读取并解析 JSON / Read and parse JSON
                    payload = validate_production_payload(raw_payload, config)  # 校验 pipeline 载荷 / Validate pipeline payload
                    update_and_persist_workflow_state(config, event={"stage": "queued", "message": "Production pipeline queued. / 生产流水线已排队。"}, running=True, cancel_requested=False, stage="queued", message="Production pipeline queued. / 生产流水线已排队。", result=None, error="", current_candidate="", current_index=0, total=0, events=[])  # 设置排队状态 / Set queued state
                    thread = threading.Thread(target=run_production_pipeline_thread, args=(config, payload), daemon=True)  # 创建后台线程 / Create background thread
                    thread.start()  # 启动后台线程 / Start background thread
                    self.send_json(workflow_snapshot())  # 返回初始状态 / Return initial status
                except Exception as exc:  # 处理启动异常 / Handle startup exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/artifacts/cleanup":  # 检查产物清理路由 / Check artifact cleanup route
                try:  # 捕获清理错误 / Catch cleanup errors
                    length = int(self.headers.get("Content-Length", "0"))  # 读取请求体长度 / Read request body length
                    payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}  # 读取确认载荷 / Read confirmation payload
                    self.send_json(delete_artifact_cleanup_files(config, bool(payload.get("confirm"))))  # 执行并返回清理结果 / Run and return cleanup result
                except Exception as exc:  # 处理清理异常 / Handle cleanup exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route == "/api/apply-comsol-discovery":  # 检查 COMSOL 发现写入路由 / Check COMSOL discovery apply route
                try:  # 捕获发现写入错误 / Catch discovery apply errors
                    from src.comsol.discovery import write_discovered_paths_to_config  # 延迟导入发现写入函数 / Lazily import discovery writer
                    result = write_discovered_paths_to_config(config_path())  # 写入配置文件 / Write config file
                    config.update(load_config(config_path()))  # 刷新运行时配置 / Refresh runtime config
                    self.send_json(result)  # 返回写入结果 / Return apply result
                except Exception as exc:  # 处理异常 / Handle exception
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message
                return  # 结束请求 / Finish request
            if route != "/api/save-target":  # 检查保存路由 / Check save route
                self.send_json({"error": "Not found. / 未找到。"}, HTTPStatus.NOT_FOUND)  # 返回 404 / Return 404
                return  # 结束请求 / Finish request
            try:  # 捕获保存错误 / Catch save errors
                length = int(self.headers.get("Content-Length", "0"))  # 读取请求体长度 / Read request body length
                payload = json.loads(self.rfile.read(length).decode("utf-8"))  # 读取并解析 JSON / Read and parse JSON
                raw_png = decode_data_url(str(payload.get("image", "")))  # 解码上传图像 / Decode uploaded image
                normalise_target_image(raw_png, target_path)  # 保存规范化目标图 / Save normalised target image
                target_mode = str(payload.get("target_mode", config["nodal_extraction"].get("target_mode", "chladni")))  # 读取保存时目标模式 / Read save-time target mode
                analysis = prepare_target_outputs(config, target_mode) if payload.get("preprocess", True) else {}  # 可选运行预处理 / Optionally run preprocessing
                self.send_json({"saved_at": datetime.now().isoformat(timespec="seconds"), "target_path": str(target_path), "processed_targets_dir": str(processed_dir), "analysis": analysis})  # 返回保存结果 / Return save result
            except Exception as exc:  # 处理异常 / Handle exception
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)  # 返回错误信息 / Return error message

    return TargetUiHandler  # 返回处理类 / Return handler class


def run_target_ui(config: dict, host: str = "127.0.0.1", port: int = 8765) -> None:  # 启动本地目标 UI / Start local target UI
    server = ThreadingHTTPServer((host, port), make_handler(config))  # 创建 HTTP 服务 / Create HTTP server
    print(f"Target designer running at http://{host}:{port} / 目标绘图器运行于 http://{host}:{port}")  # 打印访问地址 / Print access URL
    server.serve_forever()  # 持续提供服务 / Serve until interrupted
