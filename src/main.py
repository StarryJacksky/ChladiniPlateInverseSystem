from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行参数工具 / Import command-line argument tools
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

from src.config import ensure_project_dirs  # 导入目录创建函数 / Import directory creation helper
from src.config import load_config  # 导入配置读取函数 / Import configuration loader
from src.optimisation.random_search import generate_existing_candidate_previews  # 导入预览生成函数 / Import preview generation function
from src.optimisation.random_search import generate_random_search_batch  # 导入批量生成函数 / Import batch generation function
from src.optimisation.random_search import score_available_candidates  # 导入候选评分函数 / Import candidate scoring function


def build_parser() -> argparse.ArgumentParser:  # 创建命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Chladni inverse design MVP. / Chladni 逆向设计 MVP。")  # 初始化解析器 / Initialise parser
    commands = ["prepare-target", "target-ui", "run-workflow", "generate-candidates", "generate-previews", "simulate-candidate", "simulate-forced-response", "simulate-batch", "render-mode-previews", "audit-comsol-model", "apply-comsol-design-contract", "discover-comsol", "apply-comsol-discovery", "diagnose-comsol", "diagnose-feasibility", "self-test", "validate-comsol-exports", "score-candidates"]  # 定义可用命令 / Define available commands
    parser.add_argument("command", choices=commands, help="Workflow command. / 工作流命令。")  # 添加命令参数 / Add command argument
    parser.add_argument("--config", default="config.yaml", help="Config file path. / 配置文件路径。")  # 添加配置路径参数 / Add config path argument
    parser.add_argument("--host", default="127.0.0.1", help="Target UI host. / 目标 UI 主机。")  # 添加 UI 主机参数 / Add UI host argument
    parser.add_argument("--port", type=int, default=8765, help="Target UI port. / 目标 UI 端口。")  # 添加 UI 端口参数 / Add UI port argument
    parser.add_argument("--generation", type=int, default=None, help="Candidate generation index. / 候选代数编号。")  # 添加代数参数 / Add generation argument
    parser.add_argument("--model", default="", help="COMSOL MPH model path for audit. / 用于审计的 COMSOL MPH 模型路径。")  # 添加模型路径参数 / Add model path argument
    parser.add_argument("--output-model", default="", help="Output MPH model path for design-contract upgrade. / 设计变量合同升级输出 MPH 路径。")  # 添加输出模型路径参数 / Add output model path argument
    parser.add_argument("--candidate-id", default="", help="Candidate id for COMSOL simulation. / 用于 COMSOL 仿真的候选编号。")  # 添加候选编号参数 / Add candidate id argument
    parser.add_argument("--num-modes", type=int, default=0, help="Number of COMSOL modes to export. / COMSOL 导出模态数量。")  # 添加模态数量参数 / Add mode-count argument
    parser.add_argument("--limit", type=int, default=0, help="Preview render limit. / 预览渲染数量上限。")  # 添加预览数量参数 / Add preview limit argument
    parser.add_argument("--iterations", type=int, default=0, help="Optimisation generations to run. / 要运行的优化代数。")  # 添加迭代次数参数 / Add iteration-count argument
    return parser  # 返回解析器 / Return parser


def prepare_target(config: dict):  # 准备目标图案 / Prepare target pattern
    from src.target.analyse_target import save_target_analysis  # 延迟导入目标分析函数 / Lazily import target analysis function
    from src.target.preprocess_target import preprocess_target  # 延迟导入目标预处理函数 / Lazily import target preprocessing function
    image_size = int(config["nodal_extraction"]["image_size"])  # 读取图像尺寸 / Read image size
    line_width = int(config["nodal_extraction"]["target_line_width_px"])  # 读取目标线宽 / Read target line width
    target_mode = str(config["nodal_extraction"].get("target_mode", "chladni"))  # 读取目标提取模式 / Read target extraction mode
    plate_radius_px = int(image_size * config["project"]["center_clamp_radius_mm"] / config["project"]["plate_length_mm"])  # 计算中心半径像素 / Compute center radius in pixels
    target = preprocess_target(config["paths"]["target_pattern"], image_size, line_width, plate_radius_px, config["paths"]["processed_targets_dir"], target_mode)  # 执行目标预处理 / Run target preprocessing
    save_target_analysis(target, config["paths"]["processed_targets_dir"], int(config["project"]["grid_size"]), line_width)  # 保存目标分析 / Save target analysis
    return target  # 返回目标二值图 / Return target binary map


def main() -> None:  # 主程序入口 / Main program entry
    sys.stdout.reconfigure(encoding="utf-8")  # 设置 UTF-8 输出 / Set UTF-8 output
    parser = build_parser()  # 创建命令行解析器 / Build command-line parser
    args = parser.parse_args()  # 读取命令行参数 / Parse command-line arguments
    config = load_config(args.config)  # 读取配置文件 / Load configuration file
    ensure_project_dirs(config)  # 创建必要目录 / Create required directories
    if args.command == "prepare-target":  # 判断是否处理目标图 / Check target-preparation command
        prepare_target(config)  # 处理目标图 / Prepare target image
        print("Target prepared. / 目标图已处理。")  # 打印完成信息 / Print completion message
    if args.command == "target-ui":  # 判断是否启动目标绘图界面 / Check target-UI command
        from src.frontend.credential_ui_server import run_target_ui  # 延迟导入本地 UI 服务 / Lazily import local UI server
        run_target_ui(config, args.host, args.port)  # 启动绘图界面服务 / Start drawing UI server
    if args.command == "run-workflow":  # 判断是否运行完整工作流 / Check full-workflow command
        from src.optimisation.workflow import run_design_workflow  # 延迟导入完整工作流 / Lazily import full workflow
        result = run_design_workflow(config, args.generation, args.limit or None, args.num_modes or None, True, iterations=args.iterations or None)  # 运行完整自动流程 / Run complete automatic workflow
        print(result)  # 打印工作流结果 / Print workflow result
    if args.command == "generate-candidates":  # 判断是否生成候选 / Check candidate-generation command
        if args.limit:  # 检查是否指定候选数量 / Check candidate-count override
            config["optimisation"]["population_size"] = args.limit  # 临时设置候选数量 / Temporarily set candidate count
        candidate_ids = generate_random_search_batch(config, args.generation or 0)  # 生成候选批次 / Generate candidate batch
        print(f"Generated {len(candidate_ids)} candidates. / 已生成 {len(candidate_ids)} 个候选。")  # 打印候选数量 / Print candidate count
    if args.command == "generate-previews":  # 判断是否生成预览 / Check preview-generation command
        preview_paths = generate_existing_candidate_previews(config)  # 生成已有候选预览 / Generate existing candidate previews
        print(f"Generated {len(preview_paths)} previews. / 已生成 {len(preview_paths)} 个预览。")  # 打印预览数量 / Print preview count
    if args.command == "simulate-candidate":  # 判断是否仿真候选 / Check candidate-simulation command
        from src.comsol.run_livelink import run_livelink_candidate  # 延迟导入 LiveLink runner / Lazily import LiveLink runner
        if not args.candidate_id:  # 检查候选编号 / Check candidate id
            raise ValueError("--candidate-id is required for simulate-candidate. / simulate-candidate 需要 --candidate-id。")  # 抛出参数错误 / Raise argument error
        result = run_livelink_candidate(config, args.candidate_id, args.num_modes or None, args.model or None)  # 运行候选仿真 / Run candidate simulation
        print(f"Simulated {result['candidate_id']} into {result['export_dir']}. / 已仿真 {result['candidate_id']}，导出到 {result['export_dir']}。")  # 打印仿真结果 / Print simulation result
    if args.command == "simulate-forced-response":  # 判断是否运行强迫响应验证 / Check forced-response simulation command
        from src.comsol.run_livelink import run_livelink_forced_response  # 延迟导入强迫响应 runner / Lazily import forced-response runner
        if not args.candidate_id:  # 检查候选编号 / Check candidate id
            raise ValueError("--candidate-id is required for simulate-forced-response. / simulate-forced-response 需要 --candidate-id。")  # 抛出参数错误 / Raise argument error
        result = run_livelink_forced_response(config, args.candidate_id, args.model or None)  # 运行强迫响应仿真 / Run forced-response simulation
        print(f"Forced-response simulated {result['candidate_id']} into {result['export_dir']}. / 已完成 {result['candidate_id']} 的强迫响应仿真，导出到 {result['export_dir']}。")  # 打印强迫响应结果 / Print forced-response result
    if args.command == "simulate-batch":  # 判断是否批量仿真 / Check batch-simulation command
        from src.comsol.run_livelink import run_livelink_batch  # 延迟导入批量 LiveLink runner / Lazily import batch LiveLink runner
        candidate_ids = [args.candidate_id] if args.candidate_id else None  # 读取指定候选编号 / Read optional candidate id
        results = run_livelink_batch(config, candidate_ids, args.generation, args.limit or None, args.num_modes or None, args.model or None)  # 批量仿真候选 / Run candidate batch
        print(f"Simulated {len(results)} candidates. / 已仿真 {len(results)} 个候选。")  # 打印批量结果 / Print batch result
    if args.command == "render-mode-previews":  # 判断是否渲染模态预览 / Check mode-preview command
        from src.visualisation.plot_modes import render_export_previews  # 延迟导入模态预览函数 / Lazily import mode preview renderer
        if not args.candidate_id:  # 检查候选编号 / Check candidate id
            raise ValueError("--candidate-id is required for render-mode-previews. / render-mode-previews 需要 --candidate-id。")  # 抛出参数错误 / Raise argument error
        export_dir = Path(config["paths"]["comsol_exports_dir"]) / args.candidate_id  # 构造导出目录 / Build export directory
        center_radius_px = int(int(config["nodal_extraction"]["image_size"]) * float(config["project"]["center_clamp_radius_mm"]) / float(config["project"]["plate_length_mm"])) if config["nodal_extraction"].get("remove_center_region", True) else 0  # 计算中心掩膜半径 / Compute centre mask radius
        previews = render_export_previews(export_dir, int(config["nodal_extraction"]["image_size"]), float(config["nodal_extraction"]["epsilon_ratio"]), args.limit or None, center_radius_px)  # 渲染预览 / Render previews
        print(f"Rendered {len(previews)} mode previews. / 已渲染 {len(previews)} 个模态预览。")  # 打印预览数量 / Print preview count
    if args.command == "audit-comsol-model":  # 判断是否审计 COMSOL 模型 / Check COMSOL-model audit command
        from src.comsol.model_audit import audit_mph_model  # 延迟导入模型审计函数 / Lazily import model audit function
        from src.comsol.model_audit import save_model_audit  # 延迟导入审计保存函数 / Lazily import audit saver
        model_path = args.model or config.get("comsol", {}).get("model_path", "comsol_templates/baseline_model.mph")  # 读取模型路径 / Read model path
        audit = audit_mph_model(model_path)  # 审计模型结构 / Audit model structure
        report_path = Path("reports") / "comsol_model_audit.json"  # 构造审计报告路径 / Build audit report path
        save_model_audit(audit, report_path)  # 保存审计报告 / Save audit report
        print(f"Model audit saved: {report_path} / 模型审计已保存：{report_path}")  # 打印审计报告路径 / Print audit report path
    if args.command == "apply-comsol-design-contract":  # 判断是否应用 COMSOL 设计变量合同 / Check COMSOL design-contract application command
        import json  # 延迟导入 JSON / Lazily import JSON
        from src.comsol.design_contract_runner import apply_design_variable_contract  # 延迟导入设计合同应用器 / Lazily import design-contract applier
        result = apply_design_variable_contract(config, args.model or None, args.output_model or None)  # 应用设计变量合同 / Apply design-variable contract
        print(json.dumps(result, ensure_ascii=False, indent=2))  # 打印应用结果 / Print application result
    if args.command == "diagnose-comsol":  # 判断是否诊断 COMSOL 环境 / Check COMSOL diagnostics command
        import json  # 延迟导入 JSON / Lazily import JSON
        from src.comsol.diagnostics import diagnose_comsol_environment  # 延迟导入环境诊断 / Lazily import environment diagnostics
        print(json.dumps(diagnose_comsol_environment(config), ensure_ascii=False, indent=2))  # 打印诊断结果 / Print diagnostics result
    if args.command == "diagnose-feasibility":  # 判断是否诊断逆向可行性 / Check inverse-feasibility diagnostics command
        from src.scoring.feasibility import save_feasibility_report  # 延迟导入可行性报告保存 / Lazily import feasibility report saver
        from src.scoring.feasibility import summarize_feasibility_report  # 延迟导入可行性摘要 / Lazily import feasibility summary
        report = save_feasibility_report(config)  # 保存可行性报告 / Save feasibility report
        print(summarize_feasibility_report(report))  # 打印可行性摘要 / Print feasibility summary
    if args.command == "discover-comsol":  # 判断是否发现 COMSOL/MATLAB / Check COMSOL/MATLAB discovery command
        import json  # 延迟导入 JSON / Lazily import JSON
        from src.comsol.discovery import discover_runtime_environment  # 延迟导入运行环境发现 / Lazily import runtime discovery
        print(json.dumps(discover_runtime_environment(), ensure_ascii=False, indent=2))  # 打印发现结果 / Print discovery result
    if args.command == "apply-comsol-discovery":  # 判断是否写入发现路径 / Check discovery-apply command
        import json  # 延迟导入 JSON / Lazily import JSON
        from src.comsol.discovery import write_discovered_paths_to_config  # 延迟导入发现写入函数 / Lazily import discovery writer
        print(json.dumps(write_discovered_paths_to_config(args.config), ensure_ascii=False, indent=2))  # 写入并打印结果 / Write and print result
    if args.command == "self-test":  # 判断是否运行部署自检 / Check deployment self-test command
        import json  # 延迟导入 JSON / Lazily import JSON
        from src.comsol.diagnostics import run_deployment_self_test  # 延迟导入部署自检 / Lazily import deployment self-test
        print(json.dumps(run_deployment_self_test(config), ensure_ascii=False, indent=2))  # 打印自检结果 / Print self-test result
    if args.command == "validate-comsol-exports":  # 判断是否验证 COMSOL 导出 / Check COMSOL-export validation command
        from src.comsol.validate_exports import save_validation_report  # 延迟导入报告保存函数 / Lazily import report saver
        from src.comsol.validate_exports import validate_all_exports  # 延迟导入导出验证函数 / Lazily import export validator
        results = validate_all_exports(config)  # 检查所有导出目录 / Validate all export directories
        report_path = Path(config["paths"]["comsol_exports_dir"]) / "validation_report.json"  # 构造报告路径 / Build report path
        save_validation_report(results, report_path)  # 保存验证报告 / Save validation report
        print(f"Validated {len(results)} export folders. Report: {report_path} / 已验证 {len(results)} 个导出目录。报告：{report_path}")  # 打印验证结果 / Print validation result
    if args.command == "score-candidates":  # 判断是否评分候选 / Check candidate-scoring command
        target_path = Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 构造目标数组路径 / Build target array path
        if not target_path.exists():  # 检查目标数组是否存在 / Check whether target array exists
            prepare_target(config)  # 自动处理目标图 / Automatically prepare target
        import numpy as np  # 延迟导入 NumPy / Lazily import NumPy
        target_binary = np.load(target_path).astype(bool)  # 读取目标二值图 / Load target binary map
        ranking = score_available_candidates(config, target_binary, args.candidate_id or None, args.generation)  # 评分已有候选 / Score available candidates
        print(ranking if ranking else "No scored candidates yet. / 暂无可评分候选。")  # 打印排名或提示 / Print ranking or message


if __name__ == "__main__":  # 判断是否直接运行 / Check direct execution
    main()  # 执行主程序 / Run main program
