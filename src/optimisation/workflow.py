from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.config import ensure_project_dirs  # 导入目录创建函数 / Import directory creation helper
from src.optimisation.random_search import generate_random_search_batch  # 导入候选生成函数 / Import candidate-generation helper
from src.optimisation.random_search import score_available_candidates  # 导入候选评分函数 / Import candidate-scoring helper


def next_generation_index(config: dict) -> int:  # 计算下一代编号 / Compute next generation index
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    generation_ids = []  # 创建代数列表 / Create generation list
    for path in candidates_dir.glob("candidate_*_*"):  # 遍历候选目录 / Iterate candidate directories
        parts = path.name.split("_")  # 拆分候选名 / Split candidate name
        if len(parts) >= 3 and parts[1].isdigit():  # 检查候选名格式 / Check candidate-name format
            generation_ids.append(int(parts[1]))  # 记录代数 / Record generation index
    return max(generation_ids, default=-1) + 1  # 返回下一代编号 / Return next generation index


def emit(progress, stage: str, message: str, extra: dict | None = None) -> None:  # 发送进度事件 / Emit progress event
    if progress is not None:  # 检查是否有回调 / Check progress callback
        progress({"stage": stage, "message": message, **(extra or {})})  # 调用进度回调 / Call progress callback


def run_design_workflow(config: dict, generation: int | None = None, limit: int | None = None, num_modes: int | None = None, simulate: bool = True, progress=None) -> dict:  # 运行完整设计工作流 / Run complete design workflow
    from src.comsol.run_livelink import run_livelink_candidate  # 延迟导入 LiveLink 单候选运行器 / Lazily import LiveLink single-candidate runner
    ensure_project_dirs(config)  # 创建项目目录 / Ensure project directories
    selected_generation = next_generation_index(config) if generation is None else int(generation)  # 解析代数编号 / Resolve generation index
    if limit is not None and limit > 0:  # 检查是否限制候选数 / Check candidate-count override
        config["optimisation"]["population_size"] = int(limit)  # 设置临时候选数量 / Set temporary candidate count
    emit(progress, "target", "Preparing target pattern. / 正在处理目标图。")  # 发送目标处理进度 / Emit target progress
    from src.main import prepare_target  # 延迟导入目标处理入口 / Lazily import target preparation entry
    prepare_target(config)  # 处理目标图 / Prepare target pattern
    emit(progress, "candidates", "Generating candidate thickness fields. / 正在生成候选厚度矩阵。")  # 发送候选生成进度 / Emit candidate progress
    candidate_ids = generate_random_search_batch(config, selected_generation)  # 生成候选批次 / Generate candidate batch
    selected_ids = candidate_ids[:limit] if limit else candidate_ids  # 选择实际运行候选 / Select actual candidates to run
    simulation_results = []  # 创建仿真结果列表 / Create simulation result list
    if simulate and selected_ids:  # 检查是否需要仿真 / Check whether simulation should run
        total = len(selected_ids)  # 计算候选总数 / Count selected candidates
        emit(progress, "simulate", "Running COMSOL LiveLink simulation. / 正在运行 COMSOL LiveLink 仿真。", {"candidate_ids": selected_ids, "current_index": 0, "total": total})  # 发送仿真进度 / Emit simulation progress
        for index, candidate_id in enumerate(selected_ids, start=1):  # 逐个运行候选以便报告进度 / Run candidates one by one for progress
            emit(progress, "simulate", f"Simulating {candidate_id} ({index}/{total}). / 正在仿真 {candidate_id}（{index}/{total}）。", {"candidate_ids": selected_ids, "current_candidate": candidate_id, "current_index": index, "total": total})  # 发送当前候选进度 / Emit current candidate progress
            def live_progress(event: dict) -> None:  # 定义当前候选日志回调 / Define current-candidate log callback
                emit(progress, event.get("stage", "log"), event.get("message", ""), {"candidate_ids": selected_ids, "current_candidate": candidate_id, "current_index": index, "total": total, "log_path": event.get("log_path", "")})  # 转发日志事件 / Forward log event
            simulation_result = run_livelink_candidate(config, candidate_id, num_modes, progress=live_progress)  # 运行当前候选 / Run current candidate
            simulation_results.append(simulation_result)  # 保存仿真结果 / Store simulation result
            emit(progress, "simulate", f"Finished {candidate_id} ({index}/{total}). / 已完成 {candidate_id}（{index}/{total}）。", {"candidate_ids": selected_ids, "current_candidate": candidate_id, "current_index": index, "total": total, "log_path": simulation_result.get("log_path", "")})  # 发送候选完成进度 / Emit candidate completion progress
    emit(progress, "score", "Scoring available simulation exports. / 正在评分可用仿真结果。")  # 发送评分进度 / Emit scoring progress
    target_binary = np.load(Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy").astype(bool)  # 读取目标二值图 / Load target binary map
    ranking = score_available_candidates(config, target_binary, None, selected_generation)  # 评分当前代候选 / Score current generation
    result = {"generation": selected_generation, "candidate_ids": selected_ids, "simulations": simulation_results, "ranking": ranking}  # 创建工作流结果 / Create workflow result
    emit(progress, "done", "Workflow complete. / 工作流完成。", result)  # 发送完成进度 / Emit completion progress
    return result  # 返回工作流结果 / Return workflow result
