from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from src.comsol.discovery import canonical_executable_path  # 导入路径规范化函数 / Import path canonicalizer
from src.comsol.discovery import parse_process_lines  # 导入进程解析函数 / Import process parser


def assert_equal(actual, expected, label: str) -> None:  # 断言相等 / Assert equality
    if actual != expected:  # 检查是否不相等 / Check inequality
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")  # 抛出断言错误 / Raise assertion error


def assert_true(value, label: str) -> None:  # 断言为真 / Assert truth
    if not value:  # 检查是否为假 / Check false value
        raise AssertionError(label)  # 抛出断言错误 / Raise assertion error


def kinds(parsed: dict) -> list[str]:  # 提取进程类型 / Extract process kinds
    return sorted(item["kind"] for item in parsed["processes"])  # 返回排序类型 / Return sorted kinds


def test_macos_fixture() -> None:  # 测试 macOS 进程样例 / Test macOS process fixture
    lines = [  # 定义 macOS 样例 / Define macOS fixture
        "1870 /bin/bash /bin/bash /Applications/COMSOL64/Multiphysics/bin/comsol",  # COMSOL 启动脚本 / COMSOL launch script
        "2060 /Applications/CO /Applications/COMSOL64/Multiphysics/bin/macarm64/comsollauncher --launcher.ini /Applications/COMSOL64/Multiphysics/bin/macarm64/comsol.ini",  # COMSOL launcher / COMSOL launcher
        "42623 /Applications/MA /Applications/MATLAB_R2024a.app/Contents/MacOS/MATLAB",  # MATLAB GUI 主进程 / MATLAB GUI main process
        "42780 /Applications/MA /Applications/MATLAB_R2024a.app/bin/maca64/MATLABWebUI (GPU).app/Contents/MacOS/MATLABWebUI (GPU)",  # MATLAB 辅助进程 / MATLAB helper process
        "16581 python python -m src.main discover-comsol",  # 本工具命令 / This tool command
    ]  # 结束样例 / End fixture
    parsed = parse_process_lines(lines, "ps")  # 解析样例 / Parse fixture
    assert_equal(kinds(parsed), ["comsol", "comsol", "matlab"], "macOS process kinds")  # 检查类型 / Check kinds
    assert_equal(canonical_executable_path("matlab", "/Applications/MATLAB_R2024a.app/Contents/MacOS/MATLAB"), "/Applications/MATLAB_R2024a.app/bin/matlab", "macOS MATLAB canonical path")  # 检查 MATLAB 路径 / Check MATLAB path


def test_linux_fixture() -> None:  # 测试 Linux 进程样例 / Test Linux process fixture
    lines = [  # 定义 Linux 样例 / Define Linux fixture
        "1122 /usr/local/comsol64/multiphysics/bin/comsol /usr/local/comsol64/multiphysics/bin/comsol mphserver -port 2036",  # Linux COMSOL server / Linux COMSOL server
        "1123 /usr/local/MATLAB/R2024a/bin/matlab /usr/local/MATLAB/R2024a/bin/matlab -desktop",  # Linux MATLAB / Linux MATLAB
        "1124 python python -m src.main diagnose-comsol",  # 本工具命令 / This tool command
    ]  # 结束样例 / End fixture
    parsed = parse_process_lines(lines, "ps")  # 解析样例 / Parse fixture
    assert_equal(kinds(parsed), ["comsol", "matlab", "mphserver"], "Linux process kinds")  # 检查类型 / Check kinds


def test_windows_fixture() -> None:  # 测试 Windows 进程样例 / Test Windows process fixture
    lines = [  # 定义 Windows 样例 / Define Windows fixture
        'COMPUTER,1234,comsol.exe,"C:/Program Files/COMSOL/COMSOL64/Multiphysics/bin/win64/comsol.exe" mphserver -port 2036',  # Windows COMSOL / Windows COMSOL
        'COMPUTER,5678,matlab.exe,"C:/Program Files/MATLAB/R2024a/bin/matlab.exe" -desktop',  # Windows MATLAB / Windows MATLAB
        'COMPUTER,9999,python.exe,"C:/Python/python.exe" -m src.main apply-comsol-discovery',  # 本工具命令 / This tool command
    ]  # 结束样例 / End fixture
    parsed = parse_process_lines(lines, "wmic")  # 解析样例 / Parse fixture
    assert_equal(kinds(parsed), ["comsol", "matlab", "mphserver"], "Windows process kinds")  # 检查类型 / Check kinds
    assert_true(any(item["pid"] == "1234" for item in parsed["processes"]), "Windows COMSOL pid missing")  # 检查 COMSOL 进程号 / Check COMSOL pid
    assert_true(any(item["pid"] == "5678" for item in parsed["processes"]), "Windows MATLAB pid missing")  # 检查 MATLAB 进程号 / Check MATLAB pid
    assert_true(any(item["executable"].endswith("comsol.exe") for item in parsed["processes"]), "Windows COMSOL executable missing")  # 检查 COMSOL 路径 / Check COMSOL path
    assert_true(any(item["executable"].endswith("matlab.exe") for item in parsed["processes"]), "Windows MATLAB executable missing")  # 检查 MATLAB 路径 / Check MATLAB path


def main() -> None:  # 主入口 / Main entry point
    test_macos_fixture()  # 运行 macOS 样例 / Run macOS fixture
    test_linux_fixture()  # 运行 Linux 样例 / Run Linux fixture
    test_windows_fixture()  # 运行 Windows 样例 / Run Windows fixture
    print("Discovery fixture checks passed. / 自动发现样例检查通过。")  # 打印成功信息 / Print success message


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
