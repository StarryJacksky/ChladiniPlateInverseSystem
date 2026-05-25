from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.config import ensure_project_dirs  # 导入目录创建函数 / Import directory creation helper
from src.optimisation.random_search import generate_random_search_batch  # 导入候选生成函数 / Import candidate-generation helper
from src.optimisation.random_search import score_available_candidates  # 导入候选评分函数 / Import candidate-scoring helper


class WorkflowCancelled(RuntimeError):  # 定义工作流取消异常 / Define workflow-cancelled exception
    pass  # 保持异常类型简单 / Keep exception type simple


def raise_if_cancelled(cancel_check) -> None:  # 检查取消请求 / Check cancellation request
    if cancel_check is not None and cancel_check():  # 判断是否请求取消 / Check whether cancellation is requested
        raise WorkflowCancelled("Workflow cancelled by user. / 用户已取消工作流。")  # 抛出取消异常 / Raise cancellation exception


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


def run_design_workflow(config: dict, generation: int | None = None, limit: int | None = None, num_modes: int | None = None, simulate: bool = True, progress=None, cancel_check=None, iterations: int | None = None) -> dict:  # 运行完整设计工作流 / Run complete design workflow
    from src.comsol.run_livelink import run_livelink_candidate  # 延迟导入 LiveLink 单候选运行器 / Lazily import LiveLink single-candidate runner
    ensure_project_dirs(config)  # 创建项目目录 / Ensure project directories
    raise_if_cancelled(cancel_check)  # 检查是否已取消 / Check whether cancelled
    start_generation = next_generation_index(config) if generation is None else int(generation)  # 解析起始代数编号 / Resolve starting generation index
    iteration_count = int(iterations or config.get("optimisation", {}).get("num_iterations", 1) or 1)  # 读取迭代次数 / Read iteration count
    iteration_count = max(1, min(iteration_count, 50))  # 限制迭代次数 / Clamp iteration count
    if limit is not None and limit > 0:  # 检查是否限制候选数 / Check candidate-count override
        config["optimisation"]["population_size"] = int(limit)  # 设置临时候选数量 / Set temporary candidate count
    raise_if_cancelled(cancel_check)  # 检查是否已取消 / Check whether cancelled
    emit(progress, "target", "Preparing target pattern. / 正在处理目标图。")  # 发送目标处理进度 / Emit target progress
    from src.main import prepare_target  # 延迟导入目标处理入口 / Lazily import target preparation entry
    prepare_target(config)  # 处理目标图 / Prepare target pattern
    raise_if_cancelled(cancel_check)  # 检查是否已取消 / Check whether cancelled
    target_binary = np.load(Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy").astype(bool)  # 读取目标二值图 / Load target binary map
    all_candidate_ids = []  # 创建所有候选编号列表 / Create all candidate id list
    simulation_results = []  # 创建仿真结果列表 / Create simulation result list
    rankings = []  # 创建各代排行列表 / Create per-generation ranking list
    total_per_generation = int(config["optimisation"]["population_size"])  # 读取每代候选数 / Read candidates per generation
    total_simulations = total_per_generation * iteration_count if simulate else 0  # 计算总仿真数 / Compute total simulation count
    completed_simulations = 0  # 初始化已完成仿真数 / Initialise completed simulation count
    for offset in range(iteration_count):  # 遍历优化代数 / Iterate optimisation generations
        selected_generation = start_generation + offset  # 计算当前代数 / Compute current generation
        emit(progress, "candidates", f"Generating generation {selected_generation} ({offset + 1}/{iteration_count}). / 正在生成第 {selected_generation} 代（{offset + 1}/{iteration_count}）。", {"generation": selected_generation, "iteration": offset + 1, "iterations": iteration_count})  # 发送候选生成进度 / Emit candidate progress
        candidate_ids = generate_random_search_batch(config, selected_generation)  # 生成候选批次 / Generate candidate batch
        selected_ids = candidate_ids[:limit] if limit else candidate_ids  # 选择实际运行候选 / Select actual candidates to run
        all_candidate_ids.extend(selected_ids)  # 记录当前代候选 / Record current generation candidates
        raise_if_cancelled(cancel_check)  # 检查是否已取消 / Check whether cancelled
        if simulate and selected_ids:  # 检查是否需要仿真 / Check whether simulation should run
            emit(progress, "simulate", f"Running COMSOL generation {selected_generation}. / 正在运行 COMSOL 第 {selected_generation} 代。", {"candidate_ids": selected_ids, "current_index": completed_simulations, "total": total_simulations, "generation": selected_generation})  # 发送仿真进度 / Emit simulation progress
            for index, candidate_id in enumerate(selected_ids, start=1):  # 逐个运行候选以便报告进度 / Run candidates one by one for progress
                raise_if_cancelled(cancel_check)  # 检查是否已取消 / Check whether cancelled
                overall_index = completed_simulations + 1  # 计算全局仿真编号 / Compute global simulation index
                emit(progress, "simulate", f"Simulating {candidate_id} ({index}/{len(selected_ids)}, generation {offset + 1}/{iteration_count}). / 正在仿真 {candidate_id}（本代 {index}/{len(selected_ids)}，总第 {offset + 1}/{iteration_count} 代）。", {"candidate_ids": selected_ids, "current_candidate": candidate_id, "current_index": overall_index, "total": total_simulations, "generation": selected_generation})  # 发送当前候选进度 / Emit current candidate progress
                def live_progress(event: dict) -> None:  # 定义当前候选日志回调 / Define current-candidate log callback
                    emit(progress, event.get("stage", "log"), event.get("message", ""), {"candidate_ids": selected_ids, "current_candidate": candidate_id, "current_index": overall_index, "total": total_simulations, "generation": selected_generation, "log_path": event.get("log_path", "")})  # 转发日志事件 / Forward log event
                simulation_result = run_livelink_candidate(config, candidate_id, num_modes, progress=live_progress)  # 运行当前候选 / Run current candidate
                simulation_results.append(simulation_result)  # 保存仿真结果 / Store simulation result
                completed_simulations += 1  # 更新完成数量 / Update completed count
                raise_if_cancelled(cancel_check)  # 检查是否已取消 / Check whether cancelled
                emit(progress, "simulate", f"Finished {candidate_id}. / 已完成 {candidate_id}。", {"candidate_ids": selected_ids, "current_candidate": candidate_id, "current_index": completed_simulations, "total": total_simulations, "generation": selected_generation, "log_path": simulation_result.get("log_path", "")})  # 发送候选完成进度 / Emit candidate completion progress
        raise_if_cancelled(cancel_check)  # 检查是否已取消 / Check whether cancelled
        emit(progress, "score", f"Scoring generation {selected_generation}. / 正在评分第 {selected_generation} 代。", {"generation": selected_generation, "iteration": offset + 1, "iterations": iteration_count})  # 发送评分进度 / Emit scoring progress
        ranking = score_available_candidates(config, target_binary, None, selected_generation)  # 评分当前代候选 / Score current generation
        rankings.append({"generation": selected_generation, "ranking": ranking})  # 保存当前代排行 / Store generation ranking
        if ranking:  # 检查是否有排行结果 / Check ranking result
            best = ranking[0]  # 读取最佳候选 / Read best candidate
            emit(progress, "score", f"Best of generation {selected_generation}: {best.get('candidate_id')} score {best.get('final_score')}. / 第 {selected_generation} 代最佳：{best.get('candidate_id')}，分数 {best.get('final_score')}。", {"generation": selected_generation, "best": best})  # 发送最佳结果 / Emit best result
            raise_if_cancelled(cancel_check)  # 检查是否已取消 / Check whether cancelled
    final_ranking = rankings[-1]["ranking"] if rankings else []  # 读取最终排行 / Read final ranking
    result = {"generation": start_generation + iteration_count - 1, "start_generation": start_generation, "iterations": iteration_count, "candidate_ids": all_candidate_ids, "simulations": simulation_results, "ranking": final_ranking, "rankings": rankings}  # 创建工作流结果 / Create workflow result
    emit(progress, "done", "Workflow complete. / 工作流完成。", result)  # 发送完成进度 / Emit completion progress
    return result  # 返回工作流结果 / Return workflow result
