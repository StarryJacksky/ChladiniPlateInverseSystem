from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import shutil  # 导入命令查找工具 / Import command lookup helper
import subprocess  # 导入子进程工具 / Import subprocess helper
import sys  # 导入 Python 解释器路径 / Import Python interpreter path


PYTHON_CHECKS = [  # 定义 Python 检查命令 / Define Python check commands
    ["scripts/check_docs_links.py"],  # 文档链接检查 / Documentation link check
    ["scripts/check_bilingual_comments.py"],  # 双语注释检查 / Bilingual comment check
    ["scripts/check_config_contract.py"],  # 配置合同检查 / Config contract check
    ["scripts/check_discovery_fixtures.py"],  # 自动发现样例检查 / Discovery fixture check
    ["scripts/check_artifact_cleanup.py"],  # 产物清理检查 / Artifact cleanup check
    ["scripts/check_python_smoke.py"],  # 无 COMSOL 烟测 / Python-only smoke check
]  # 结束 Python 检查命令 / End Python check commands


COMPILE_TARGETS = [  # 定义编译检查目标 / Define compile check targets
    "src",  # 源码目录 / Source directory
    "scripts/check_artifact_cleanup.py",  # 产物清理脚本 / Artifact cleanup script
    "scripts/check_bilingual_comments.py",  # 注释检查脚本 / Comment check script
    "scripts/check_config_contract.py",  # 配置检查脚本 / Config check script
    "scripts/check_discovery_fixtures.py",  # 发现样例脚本 / Discovery fixture script
    "scripts/check_docs_links.py",  # 文档链接脚本 / Documentation link script
    "scripts/check_python_smoke.py",  # 烟测脚本 / Smoke test script
    "scripts/create_ic_target.py",  # 示例目标脚本 / Example target script
    "scripts/launch_chladni_studio.py",  # 启动脚本 / Launcher script
]  # 结束编译目标 / End compile targets


FRONTEND_SYNTAX_SCRIPT = "const fs=require('fs'); const html=fs.readFileSync('frontend/target_designer.html','utf8'); const re=new RegExp('<script[^>]*>([\\\\s\\\\S]*?)<\\\\/script>','g'); const scripts=[...html.matchAll(re)].map(m=>m[1]); for (const script of scripts) new Function(script); console.log('frontend script syntax ok');"  # 定义前端语法检查脚本 / Define frontend syntax check script


def run_command(command: list[str], label: str) -> None:  # 运行检查命令 / Run check command
    print(f"== {label} ==", flush=True)  # 打印检查标题 / Print check heading
    result = subprocess.run(command, text=True)  # 执行命令并继承输出 / Run command and inherit output
    if result.returncode != 0:  # 检查返回码 / Check return code
        raise SystemExit(result.returncode)  # 以失败码退出 / Exit with failure code


def run_python_checks() -> None:  # 运行 Python 检查 / Run Python checks
    for args in PYTHON_CHECKS:  # 遍历检查命令 / Iterate check commands
        run_command([sys.executable, *args], " ".join(args))  # 执行 Python 脚本 / Run Python script


def run_compile_check() -> None:  # 运行编译检查 / Run compile check
    run_command([sys.executable, "-m", "compileall", *COMPILE_TARGETS], "compileall")  # 执行 compileall / Run compileall


def run_frontend_check() -> None:  # 运行前端语法检查 / Run frontend syntax check
    if shutil.which("node") is None:  # 检查 Node 是否存在 / Check whether Node exists
        print("== frontend script syntax ==\nnode not found; skipped optional frontend syntax check. / 未找到 node，已跳过可选前端语法检查。")  # 打印跳过说明 / Print skip note
        return  # 结束前端检查 / Finish frontend check
    run_command(["node", "-e", FRONTEND_SYNTAX_SCRIPT], "frontend script syntax")  # 执行 Node 语法检查 / Run Node syntax check


def main() -> None:  # 主入口 / Main entry point
    run_python_checks()  # 运行 Python 检查 / Run Python checks
    run_compile_check()  # 运行编译检查 / Run compile check
    run_frontend_check()  # 运行前端检查 / Run frontend check
    print("Local quality checks passed. / 本地质量检查通过。")  # 打印成功信息 / Print success message


if __name__ == "__main__":  # 检查直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
