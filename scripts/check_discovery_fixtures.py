from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities
from tempfile import TemporaryDirectory  # 导入临时目录工具 / Import temporary directory helper

from src.comsol.discovery import canonical_executable_path  # 导入路径规范化函数 / Import path canonicalizer
from src.comsol.discovery import config_with_runtime_discovery  # 导入运行时配置补全 / Import runtime config completion
from src.comsol.discovery import decode_process_bytes  # 导入进程输出解码函数 / Import process-output decoder
from src.comsol.discovery import discover_install_candidates  # 导入安装路径发现 / Import install path discovery
from src.comsol.discovery import parse_process_lines  # 导入进程解析函数 / Import process parser
from src.comsol.discovery import suggested_paths  # 导入路径建议函数 / Import path suggestion helper


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


def test_install_fixture() -> None:  # 测试安装路径样例 / Test install path fixture
    with TemporaryDirectory() as tmp:  # 创建临时安装根目录 / Create temporary install root
        root = Path(tmp)  # 转换路径对象 / Convert to path object
        comsol_path = root / "COMSOL64" / "Multiphysics" / "bin" / "comsol"  # 构造 COMSOL 路径 / Build COMSOL path
        matlab_path = root / "MATLAB_R2024a.app" / "bin" / "matlab"  # 构造 MATLAB 路径 / Build MATLAB path
        comsol_path.parent.mkdir(parents=True)  # 创建 COMSOL 目录 / Create COMSOL directory
        matlab_path.parent.mkdir(parents=True)  # 创建 MATLAB 目录 / Create MATLAB directory
        comsol_path.write_text("", encoding="utf-8")  # 写入 COMSOL 占位文件 / Write COMSOL placeholder
        matlab_path.write_text("", encoding="utf-8")  # 写入 MATLAB 占位文件 / Write MATLAB placeholder
        patterns = {"comsol": [str(root / "COMSOL*" / "Multiphysics" / "bin" / "comsol")], "matlab": [str(root / "MATLAB_R*.app" / "bin" / "matlab")]}  # 构造测试模式 / Build test patterns
        installs = discover_install_candidates(patterns)  # 发现临时安装路径 / Discover temporary install paths
        assert_equal(installs["comsol"], [str(comsol_path)], "COMSOL install fixture")  # 检查 COMSOL 安装路径 / Check COMSOL install path
        assert_equal(installs["matlab"], [str(matlab_path)], "MATLAB install fixture")  # 检查 MATLAB 安装路径 / Check MATLAB install path


def test_runtime_config_fill_from_install() -> None:  # 测试配置空路径由安装候选补全 / Test empty config paths filled from installs
    with TemporaryDirectory() as tmp:  # 创建临时目录 / Create temporary directory
        root = Path(tmp)  # 转换路径对象 / Convert to path object
        comsol_path = root / "comsol"  # 构造 COMSOL 路径 / Build COMSOL path
        matlab_path = root / "matlab"  # 构造 MATLAB 路径 / Build MATLAB path
        comsol_path.write_text("", encoding="utf-8")  # 写入 COMSOL 占位文件 / Write COMSOL placeholder
        matlab_path.write_text("", encoding="utf-8")  # 写入 MATLAB 占位文件 / Write MATLAB placeholder
        discovery = {"processes": [], "suggestions": {"comsol_command_path": str(comsol_path), "comsol_source": "install_scan", "matlab_path": str(matlab_path), "matlab_source": "install_scan"}, "summary": {}}  # 构造发现结果 / Build discovery result
        config = {"comsol": {"comsol_command_path": "", "matlab_path": ""}}  # 构造空路径配置 / Build empty-path config
        runtime_config, applied, _runtime_discovery = config_with_runtime_discovery(config, discovery)  # 运行补全 / Run completion
        assert_equal(runtime_config["comsol"]["comsol_command_path"], str(comsol_path), "COMSOL runtime fill")  # 检查 COMSOL 补全 / Check COMSOL fill
        assert_equal(runtime_config["comsol"]["matlab_path"], str(matlab_path), "MATLAB runtime fill")  # 检查 MATLAB 补全 / Check MATLAB fill
        assert_equal(applied, {"comsol_command_path": "install_scan", "matlab_path": "install_scan"}, "runtime applied sources")  # 检查补全来源 / Check applied sources


def test_running_process_priority() -> None:  # 测试运行进程优先于安装目录 / Test running process priority over installs
    with TemporaryDirectory() as tmp:  # 创建临时目录 / Create temporary directory
        root = Path(tmp)  # 转换路径对象 / Convert to path object
        process_comsol = root / "running" / "comsol"  # 构造进程 COMSOL 路径 / Build process COMSOL path
        install_comsol = root / "installed" / "comsol"  # 构造安装 COMSOL 路径 / Build install COMSOL path
        process_matlab = root / "running" / "matlab"  # 构造进程 MATLAB 路径 / Build process MATLAB path
        install_matlab = root / "installed" / "matlab"  # 构造安装 MATLAB 路径 / Build install MATLAB path
        for path in [process_comsol, install_comsol, process_matlab, install_matlab]:  # 遍历占位路径 / Iterate placeholder paths
            path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
            path.write_text("", encoding="utf-8")  # 写入占位文件 / Write placeholder file
        processes = [{"kind": "comsol", "executable": str(process_comsol)}, {"kind": "matlab", "executable": str(process_matlab)}]  # 构造进程发现 / Build process discovery
        installs = {"comsol": [str(install_comsol)], "matlab": [str(install_matlab)]}  # 构造安装发现 / Build install discovery
        suggestions = suggested_paths(processes, installs)  # 生成建议 / Build suggestions
        assert_equal(suggestions["comsol_command_path"], str(process_comsol), "COMSOL process priority")  # 检查 COMSOL 优先级 / Check COMSOL priority
        assert_equal(suggestions["matlab_path"], str(process_matlab), "MATLAB process priority")  # 检查 MATLAB 优先级 / Check MATLAB priority


def test_process_output_decoding() -> None:  # 测试进程输出容错解码 / Test tolerant process-output decoding
    mac_text = decode_process_bytes(b"123 /Applications/COMSOL64/bin/comsol \xff bad\n")  # 解码混入坏字节的 POSIX 输出 / Decode POSIX output with bad bytes
    assert_true("comsol" in mac_text.lower(), "macOS process decode lost COMSOL text")  # 检查文本保留 / Check text preserved
    windows_text = decode_process_bytes("COMPUTER,1234,comsol.exe\r\n".encode("utf-16"))  # 解码 Windows UTF-16 输出 / Decode Windows UTF-16 output
    assert_true("comsol.exe" in windows_text.lower(), "Windows process decode lost COMSOL text")  # 检查 Windows 文本 / Check Windows text


def main() -> None:  # 主入口 / Main entry point
    test_macos_fixture()  # 运行 macOS 样例 / Run macOS fixture
    test_linux_fixture()  # 运行 Linux 样例 / Run Linux fixture
    test_windows_fixture()  # 运行 Windows 样例 / Run Windows fixture
    test_install_fixture()  # 运行安装路径样例 / Run install path fixture
    test_runtime_config_fill_from_install()  # 运行配置补全样例 / Run config completion fixture
    test_running_process_priority()  # 运行优先级样例 / Run priority fixture
    test_process_output_decoding()  # 运行解码样例 / Run decoding fixture
    print("Discovery fixture checks passed. / 自动发现样例检查通过。")  # 打印成功信息 / Print success message


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
