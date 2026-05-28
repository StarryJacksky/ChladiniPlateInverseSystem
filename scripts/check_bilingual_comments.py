from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities


SOURCE_SUFFIXES = {".py", ".m", ".html"}  # 定义需要检查的源码后缀 / Define source suffixes to check
EXCLUDED_PATHS = {Path("reports/chladni_baseline_export.m")}  # 排除自动导出的巨大参考文件 / Exclude huge generated reference file
EXCLUDED_DIR_NAMES = {".venv", "venv", ".git", "__pycache__", "node_modules", ".tox", "build", "dist", ".mypy_cache", ".pytest_cache"}  # 排除虚拟环境与缓存目录 / Exclude virtual envs and cache dirs


def has_bilingual_marker(line: str) -> bool:  # 判断一行是否含中英注释标记 / Decide whether a line has bilingual comment marker
    return " / " in line and any(token in line for token in ("#", "%", "//", "/*", "<!--"))  # 检查常见注释符 / Check common comment tokens


def is_ignored_line(line: str) -> bool:  # 判断空行是否可跳过 / Decide whether a blank line can be skipped
    return not line.strip()  # 空行不需要注释 / Blank lines do not need comments


def is_frontend_comment_context(previous: str) -> bool:  # 判断前一行是否解释当前前端行 / Decide whether previous line explains current frontend line
    return has_bilingual_marker(previous)  # 前端允许上一行注释解释下一行 / Frontend allows previous-line comments


def check_file(path: Path) -> list[str]:  # 检查单个文件 / Check one file
    issues = []  # 创建问题列表 / Create issue list
    previous = ""  # 保存上一行内容 / Keep previous line
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):  # 遍历文件行 / Iterate file lines
        if is_ignored_line(line):  # 跳过空行 / Skip blank lines
            previous = line  # 更新上一行 / Update previous line
            continue  # 继续下一行 / Continue to next line
        if has_bilingual_marker(line):  # 检查当前行是否已注释 / Check whether current line is commented
            previous = line  # 更新上一行 / Update previous line
            continue  # 继续下一行 / Continue to next line
        if path.suffix == ".html" and is_frontend_comment_context(previous):  # 检查前端上一行注释 / Check frontend previous-line comment
            previous = line  # 更新上一行 / Update previous line
            continue  # 继续下一行 / Continue to next line
        issues.append(f"{path}:{number}: missing bilingual comment")  # 记录缺失注释 / Record missing comment
        previous = line  # 更新上一行 / Update previous line
    return issues  # 返回问题列表 / Return issues


def iter_source_files(root: Path) -> list[Path]:  # 枚举源码文件 / Enumerate source files
    files = []  # 创建文件列表 / Create file list
    for path in root.rglob("*"):  # 遍历项目文件 / Iterate project files
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):  # 跳过排除目录 / Skip excluded directories
            continue  # 继续下一项 / Continue to next item
        if path.is_file() and path.suffix in SOURCE_SUFFIXES and path not in EXCLUDED_PATHS:  # 筛选源码文件 / Filter source files
            files.append(path)  # 添加源码路径 / Add source path
    return sorted(files)  # 返回排序后的文件 / Return sorted files


def main() -> None:  # 主入口 / Main entry point
    issues = []  # 创建总问题列表 / Create aggregate issue list
    for path in iter_source_files(Path(".")):  # 遍历源码文件 / Iterate source files
        issues.extend(check_file(path))  # 合并单文件问题 / Merge file issues
    if issues:  # 检查是否存在问题 / Check whether issues exist
        print("\n".join(issues))  # 打印所有问题 / Print all issues
        raise SystemExit(1)  # 以失败状态退出 / Exit with failure
    print("Bilingual comment check passed. / 双语注释检查通过。")  # 打印通过信息 / Print success message


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
