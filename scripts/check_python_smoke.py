from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import copy  # 导入配置复制工具 / Import configuration copy helper
import shutil  # 导入文件复制工具 / Import file copy helper
from pathlib import Path  # 导入路径工具 / Import path utilities
from tempfile import TemporaryDirectory  # 导入临时目录工具 / Import temporary directory helper

from PIL import Image  # 导入图像工具 / Import image helper
from PIL import ImageDraw  # 导入绘图工具 / Import drawing helper

from src.config import load_config  # 导入配置加载函数 / Import config loader
from src.optimisation.workflow import run_design_workflow  # 导入工作流函数 / Import workflow function


def make_smoke_target(path: Path) -> None:  # 创建烟测目标图 / Create smoke-test target image
    image = Image.new("RGB", (512, 512), "white")  # 创建白底图像 / Create white canvas
    draw = ImageDraw.Draw(image)  # 创建绘图对象 / Create drawing context
    draw.line((96, 256, 416, 256), fill="black", width=18)  # 绘制横向目标线 / Draw horizontal target line
    draw.line((256, 96, 256, 416), fill="black", width=18)  # 绘制纵向目标线 / Draw vertical target line
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建目标目录 / Create target directory
    image.save(path, format="PNG")  # 保存 PNG 目标 / Save PNG target


def build_smoke_config() -> tuple[dict, TemporaryDirectory]:  # 构造临时烟测配置 / Build temporary smoke config
    temporary = TemporaryDirectory()  # 创建临时目录对象 / Create temporary directory object
    root = Path(temporary.name)  # 读取临时根目录 / Read temporary root
    config = copy.deepcopy(load_config("config.yaml"))  # 复制项目配置 / Copy project config
    target_path = root / "target_patterns" / "target.png"  # 构造临时目标路径 / Build temporary target path
    source_target = Path(config["paths"]["target_pattern"])  # 读取原目标路径 / Read source target path
    if source_target.exists():  # 检查原目标是否存在 / Check whether source target exists
        target_path.parent.mkdir(parents=True, exist_ok=True)  # 创建目标目录 / Create target directory
        shutil.copyfile(source_target, target_path)  # 复制现有目标 / Copy existing target
    else:  # 处理无目标图情况 / Handle missing source target
        make_smoke_target(target_path)  # 创建默认烟测目标 / Create default smoke target
    config["paths"]["target_pattern"] = str(target_path)  # 设置临时目标路径 / Set temporary target path
    config["paths"]["processed_targets_dir"] = str(root / "processed_targets")  # 设置临时处理目录 / Set temporary processed directory
    config["paths"]["candidates_dir"] = str(root / "candidates")  # 设置临时候选目录 / Set temporary candidates directory
    config["paths"]["comsol_exports_dir"] = str(root / "comsol_exports")  # 设置临时导出目录 / Set temporary export directory
    config["optimisation"]["population_size"] = 1  # 限制烟测候选数量 / Limit smoke candidate count
    return config, temporary  # 返回配置和临时目录 / Return config and temporary directory


def assert_exists(path: Path, label: str) -> None:  # 断言文件存在 / Assert file existence
    if not path.exists():  # 检查路径缺失 / Check missing path
        raise AssertionError(f"Missing {label}: {path}")  # 抛出缺失错误 / Raise missing error


def main() -> None:  # 主入口 / Main entry point
    config, temporary = build_smoke_config()  # 构建烟测配置 / Build smoke config
    try:  # 确保临时目录清理 / Ensure temporary cleanup
        result = run_design_workflow(config, generation=0, limit=1, num_modes=0, simulate=False)  # 运行无 COMSOL 工作流 / Run workflow without COMSOL
        processed_dir = Path(config["paths"]["processed_targets_dir"])  # 读取处理目录 / Read processed directory
        candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidates directory
        candidate_id = result["candidate_ids"][0]  # 读取生成候选编号 / Read generated candidate id
        candidate_dir = candidates_dir / candidate_id  # 构造候选目录 / Build candidate directory
        assert_exists(processed_dir / "target_binary.npy", "target binary")  # 检查目标数组 / Check target array
        assert_exists(processed_dir / "target_preview.png", "target preview")  # 检查目标预览 / Check target preview
        assert_exists(processed_dir / "target_analysis.json", "target analysis")  # 检查目标分析 / Check target analysis
        assert_exists(candidate_dir / "H.csv", "candidate thickness matrix")  # 检查厚度矩阵 / Check thickness matrix
        assert_exists(candidate_dir / "metadata.json", "candidate metadata")  # 检查候选元数据 / Check candidate metadata
        print(f"Python-only smoke check passed with {candidate_id}. / 无 COMSOL 烟测通过，候选 {candidate_id}。")  # 打印通过信息 / Print success message
    finally:  # 最终清理 / Final cleanup
        temporary.cleanup()  # 清理临时目录 / Clean temporary directory


if __name__ == "__main__":  # 检查直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
