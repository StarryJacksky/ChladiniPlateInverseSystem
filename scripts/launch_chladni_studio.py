from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行参数工具 / Import command-line argument tools
import socket  # 导入端口探测工具 / Import port probing tools
import sys  # 导入模块搜索路径工具 / Import module search path tools
import threading  # 导入延迟打开浏览器工具 / Import delayed browser-opening tools
import webbrowser  # 导入浏览器打开工具 / Import browser-opening tools
from pathlib import Path  # 导入路径工具 / Import path helper

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

from src.config import ensure_project_dirs  # 导入目录创建函数 / Import directory creation helper
from src.config import load_config  # 导入配置读取函数 / Import configuration loader
from src.comsol.diagnostics import run_deployment_self_test  # 导入部署自检函数 / Import deployment self-test helper
from src.frontend.target_ui_server import run_target_ui  # 导入本地 UI 服务 / Import local UI server


def build_parser() -> argparse.ArgumentParser:  # 创建启动器参数解析器 / Build launcher argument parser
    parser = argparse.ArgumentParser(description="Launch Chladni Studio. / 启动 Chladni Studio。")  # 初始化参数解析器 / Initialise argument parser
    parser.add_argument("--config", default="config.yaml", help="Config file path. / 配置文件路径。")  # 添加配置路径参数 / Add config path argument
    parser.add_argument("--host", default="127.0.0.1", help="UI host. / UI 主机。")  # 添加主机参数 / Add host argument
    parser.add_argument("--port", type=int, default=8765, help="Preferred UI port. / 首选 UI 端口。")  # 添加端口参数 / Add port argument
    parser.add_argument("--port-tries", type=int, default=20, help="Number of ports to probe. / 端口探测数量。")  # 添加端口探测数量 / Add port probe count
    parser.add_argument("--skip-self-test", action="store_true", help="Skip startup self-test. / 跳过启动自检。")  # 添加跳过自检开关 / Add self-test skip switch
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically. / 不自动打开浏览器。")  # 添加浏览器开关 / Add browser switch
    return parser  # 返回解析器 / Return parser


def is_port_available(host: str, port: int) -> bool:  # 判断端口是否可用 / Decide whether a port is available
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:  # 创建 TCP socket / Create TCP socket
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 设置地址复用 / Set address reuse
        try:  # 捕获绑定错误 / Catch bind errors
            sock.bind((host, port))  # 尝试绑定端口 / Try to bind port
        except OSError:  # 处理端口不可用 / Handle unavailable port
            return False  # 返回不可用 / Return unavailable
    return True  # 返回可用 / Return available


def choose_port(host: str, preferred_port: int, tries: int) -> int:  # 选择可用端口 / Choose an available port
    for offset in range(max(1, tries)):  # 遍历候选端口 / Iterate candidate ports
        port = preferred_port + offset  # 计算当前端口 / Compute current port
        if is_port_available(host, port):  # 检查端口是否可用 / Check whether port is available
            return port  # 返回可用端口 / Return available port
    raise RuntimeError("No available UI port found. / 未找到可用 UI 端口。")  # 抛出端口错误 / Raise port error


def print_self_test(result: dict) -> None:  # 打印自检摘要 / Print self-test summary
    status = "ready" if result.get("ready") else "needs attention"  # 计算总体状态 / Compute overall status
    print(f"Self-test: {status} / 自检：{status}")  # 打印总体状态 / Print overall status
    for item in result.get("checks", []):  # 遍历自检项 / Iterate self-test items
        print(f"- {item.get('status', 'warn')}: {item.get('label', 'Check')} - {item.get('message', '')}")  # 打印自检项 / Print self-test item


def open_browser_later(url: str) -> None:  # 延迟打开浏览器 / Open browser after a delay
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()  # 设置延迟打开 / Schedule delayed open


def main() -> None:  # 启动器入口 / Launcher entry point
    args = build_parser().parse_args()  # 解析命令行参数 / Parse command-line arguments
    config = load_config(args.config)  # 读取配置 / Load configuration
    ensure_project_dirs(config)  # 创建项目目录 / Ensure project directories
    if not args.skip_self_test:  # 检查是否运行自检 / Check whether to run self-test
        print_self_test(run_deployment_self_test(config))  # 运行并打印自检 / Run and print self-test
    port = choose_port(args.host, args.port, args.port_tries)  # 选择可用端口 / Choose available port
    url = f"http://{args.host}:{port}"  # 构造访问地址 / Build access URL
    if port != args.port:  # 检查是否使用备用端口 / Check whether fallback port is used
        print(f"Preferred port {args.port} is busy; using {port}. / 首选端口 {args.port} 已占用，改用 {port}。")  # 打印端口切换 / Print port fallback
    print(f"Starting Chladni Studio at {url} / 正在启动 Chladni Studio：{url}")  # 打印启动地址 / Print launch URL
    if not args.no_browser:  # 检查是否自动打开浏览器 / Check whether to open browser
        open_browser_later(url)  # 延迟打开浏览器 / Open browser later
    run_target_ui(config, args.host, port)  # 启动 UI 服务 / Start UI server


if __name__ == "__main__":  # 判断是否直接运行 / Check direct execution
    main()  # 执行启动器 / Run launcher
