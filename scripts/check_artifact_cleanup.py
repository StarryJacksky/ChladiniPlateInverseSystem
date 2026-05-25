from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import os  # 导入文件时间工具 / Import file time helpers
from pathlib import Path  # 导入路径工具 / Import path utilities
from tempfile import TemporaryDirectory  # 导入临时目录工具 / Import temporary directory helper

from src.frontend.target_ui_server import cleanable_artifact_paths  # 导入可清理路径收集函数 / Import cleanable path collector
from src.frontend.target_ui_server import delete_artifact_cleanup_files  # 导入清理执行函数 / Import cleanup executor
from src.frontend.target_ui_server import load_artifact_cleanup_preview  # 导入清理预览函数 / Import cleanup preview loader


def write_file(path: Path, text: str = "x") -> Path:  # 写入测试文件 / Write test file
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    path.write_text(text, encoding="utf-8")  # 写入文本内容 / Write text content
    return path  # 返回文件路径 / Return file path


def make_old(path: Path) -> None:  # 设置旧修改时间 / Set old modification time
    old_time = 946684800  # 使用固定旧时间戳 / Use fixed old timestamp
    os.utime(path, (old_time, old_time))  # 更新访问和修改时间 / Update access and modification times


def build_config(root: Path) -> dict:  # 构造临时配置 / Build temporary config
    return {  # 返回最小配置 / Return minimal config
        "paths": {  # 路径配置 / Path config
            "candidates_dir": str(root / "candidates"),  # 候选目录 / Candidates directory
            "comsol_exports_dir": str(root / "exports"),  # 导出目录 / Exports directory
            "processed_targets_dir": str(root / "processed"),  # 目标处理目录 / Processed target directory
        },  # 路径配置结束 / End path config
        "artifact_retention": {  # 保留策略 / Retention policy
            "keep_latest_generations": 1,  # 保留最新一代 / Keep latest one generation
            "keep_recent_days": 1,  # 保留一天内文件 / Keep files newer than one day
            "regenerable_only": True,  # 仅清理可再生成项 / Clean regenerable items only
        },  # 保留策略结束 / End retention policy
    }  # 返回配置 / Return config


def create_fixture(config: dict) -> dict[str, Path]:  # 创建清理样例 / Create cleanup fixture
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidates directory
    exports_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取导出目录 / Read exports directory
    stale_preview = write_file(candidates_dir / "candidate_001_0000" / "preview_thickness.png")  # 创建旧候选预览 / Create stale candidate preview
    stale_mph = write_file(exports_dir / "candidate_001_0000" / "last_run_model.mph")  # 创建旧模型副本 / Create stale model copy
    stale_overlay = write_file(exports_dir / "candidate_001_0000" / "comparison" / "target_sim_overlay.png")  # 创建旧对比图 / Create stale comparison image
    protected_preview = write_file(candidates_dir / "candidate_002_0000" / "preview_thickness.png")  # 创建最新候选预览 / Create protected candidate preview
    protected_mph = write_file(exports_dir / "candidate_002_0000" / "last_run_model.mph")  # 创建最新模型副本 / Create protected model copy
    protected_mode = write_file(exports_dir / "candidate_001_0000" / "mode_01.csv")  # 创建不可再生成模态数据样例 / Create non-regenerable mode sample
    temporary_state = write_file(exports_dir / "workflow_state.tmp")  # 创建临时状态文件 / Create temporary state file
    for path in [stale_preview, stale_mph, stale_overlay, protected_preview, protected_mph, protected_mode]:  # 遍历需要变旧的文件 / Iterate files to age
        make_old(path)  # 设置旧时间 / Set old time
    return {"stale_preview": stale_preview, "stale_mph": stale_mph, "stale_overlay": stale_overlay, "protected_preview": protected_preview, "protected_mph": protected_mph, "protected_mode": protected_mode, "temporary_state": temporary_state}  # 返回文件字典 / Return file dictionary


def assert_in(path: Path, paths: list[Path], label: str) -> None:  # 断言路径在列表中 / Assert path is in list
    if path not in paths:  # 检查路径缺失 / Check missing path
        raise AssertionError(f"{label} was not marked cleanable: {path}")  # 抛出断言错误 / Raise assertion error


def assert_not_in(path: Path, paths: list[Path], label: str) -> None:  # 断言路径不在列表中 / Assert path is not in list
    if path in paths:  # 检查路径误入 / Check unexpected path
        raise AssertionError(f"{label} was unexpectedly marked cleanable: {path}")  # 抛出断言错误 / Raise assertion error


def assert_exists(path: Path, label: str) -> None:  # 断言文件存在 / Assert file exists
    if not path.exists():  # 检查文件缺失 / Check missing file
        raise AssertionError(f"{label} missing: {path}")  # 抛出断言错误 / Raise assertion error


def assert_missing(path: Path, label: str) -> None:  # 断言文件缺失 / Assert file is missing
    if path.exists():  # 检查文件仍存在 / Check file still exists
        raise AssertionError(f"{label} still exists: {path}")  # 抛出断言错误 / Raise assertion error


def main() -> None:  # 主入口 / Main entry point
    with TemporaryDirectory() as temporary_dir:  # 创建临时目录 / Create temporary directory
        config = build_config(Path(temporary_dir))  # 构造临时配置 / Build temporary config
        files = create_fixture(config)  # 创建测试样例 / Create test fixture
        preview = load_artifact_cleanup_preview(config)  # 读取清理预览 / Load cleanup preview
        cleanable = cleanable_artifact_paths(config)  # 收集可清理路径 / Collect cleanable paths
        assert preview["dry_run"] is True  # 确认预览不执行删除 / Confirm preview is dry run
        assert_in(files["stale_preview"], cleanable, "stale preview")  # 确认旧预览可清理 / Confirm stale preview cleanable
        assert_in(files["stale_mph"], cleanable, "stale model copy")  # 确认旧模型可清理 / Confirm stale model cleanable
        assert_in(files["stale_overlay"], cleanable, "stale comparison image")  # 确认旧对比图可清理 / Confirm stale comparison cleanable
        assert_in(files["temporary_state"], cleanable, "temporary state")  # 确认临时状态可清理 / Confirm temporary state cleanable
        assert_not_in(files["protected_preview"], cleanable, "latest preview")  # 确认最新预览受保护 / Confirm latest preview protected
        assert_not_in(files["protected_mph"], cleanable, "latest model copy")  # 确认最新模型受保护 / Confirm latest model protected
        assert_not_in(files["protected_mode"], cleanable, "mode CSV")  # 确认模态数据不清理 / Confirm mode CSV protected
        try:  # 测试未确认删除 / Test unconfirmed delete
            delete_artifact_cleanup_files(config, False)  # 尝试未确认清理 / Try unconfirmed cleanup
        except ValueError:  # 捕获预期错误 / Catch expected error
            pass  # 未确认删除应失败 / Unconfirmed delete should fail
        else:  # 处理未抛错情况 / Handle missing error
            raise AssertionError("Cleanup without confirm did not fail. / 未确认清理没有失败。")  # 抛出错误 / Raise error
        result = delete_artifact_cleanup_files(config, True)  # 执行确认清理 / Run confirmed cleanup
        if result["deleted_count"] != 4:  # 检查删除数量 / Check deleted count
            raise AssertionError(result)  # 抛出结果 / Raise result
        assert_missing(files["stale_preview"], "stale preview")  # 确认旧预览已删除 / Confirm stale preview deleted
        assert_missing(files["stale_mph"], "stale model copy")  # 确认旧模型已删除 / Confirm stale model deleted
        assert_missing(files["stale_overlay"], "stale comparison image")  # 确认旧对比图已删除 / Confirm stale comparison deleted
        assert_missing(files["temporary_state"], "temporary state")  # 确认临时状态已删除 / Confirm temporary state deleted
        assert_exists(files["protected_preview"], "latest preview")  # 确认最新预览仍存在 / Confirm latest preview remains
        assert_exists(files["protected_mph"], "latest model copy")  # 确认最新模型仍存在 / Confirm latest model remains
        assert_exists(files["protected_mode"], "mode CSV")  # 确认模态数据仍存在 / Confirm mode CSV remains
    print("Artifact cleanup checks passed. / 产物清理检查通过。")  # 打印通过信息 / Print success message


if __name__ == "__main__":  # 检查直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
