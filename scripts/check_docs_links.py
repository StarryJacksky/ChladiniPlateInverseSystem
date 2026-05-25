from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import re  # 导入正则工具 / Import regex tools
from pathlib import Path  # 导入路径工具 / Import path utilities
from urllib.parse import unquote  # 导入 URL 解码工具 / Import URL decoding helper


MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")  # 匹配 Markdown 链接 / Match Markdown links
DOC_PATTERNS = ["README*.md", "docs/*.md", "reports/remaining_work_plan*.md"]  # 定义文档扫描范围 / Define document scan scope


def iter_docs(root: Path) -> list[Path]:  # 遍历文档文件 / Iterate documentation files
    docs = []  # 创建文档列表 / Create document list
    for pattern in DOC_PATTERNS:  # 遍历扫描模式 / Iterate scan patterns
        docs.extend(root.glob(pattern))  # 添加匹配文档 / Add matching docs
    return sorted(path for path in docs if path.is_file())  # 返回排序文件 / Return sorted files


def is_external_link(target: str) -> bool:  # 判断是否外部链接 / Decide whether link is external
    lowered = target.lower()  # 转为小写 / Lowercase target
    return lowered.startswith(("http://", "https://", "mailto:", "tel:"))  # 返回外部链接判断 / Return external-link decision


def local_link_path(source: Path, target: str) -> Path | None:  # 解析本地链接路径 / Resolve local link path
    clean_target = target.strip().split("#", 1)[0].strip()  # 去掉锚点 / Remove anchor
    if not clean_target or is_external_link(clean_target):  # 跳过空锚点或外部链接 / Skip empty anchors or external links
        return None  # 返回空路径 / Return no path
    if clean_target.startswith("<") and clean_target.endswith(">"):  # 处理尖括号链接 / Handle angle-bracket link
        clean_target = clean_target[1:-1]  # 去除尖括号 / Remove angle brackets
    return (source.parent / unquote(clean_target)).resolve()  # 返回解析路径 / Return resolved path


def check_document_links(root: Path) -> list[str]:  # 检查文档链接 / Check document links
    failures = []  # 创建失败列表 / Create failure list
    for doc_path in iter_docs(root):  # 遍历文档 / Iterate documents
        text = doc_path.read_text(encoding="utf-8")  # 读取文档文本 / Read document text
        for match in MARKDOWN_LINK_RE.finditer(text):  # 遍历链接匹配 / Iterate link matches
            target_path = local_link_path(doc_path, match.group(1))  # 解析本地目标 / Resolve local target
            if target_path is None:  # 检查是否无需验证 / Check whether validation is skipped
                continue  # 跳过该链接 / Skip this link
            if not target_path.exists():  # 检查目标是否存在 / Check target existence
                failures.append(f"{doc_path}: missing {match.group(1)}")  # 记录断链 / Record broken link
    return failures  # 返回失败列表 / Return failures


def main() -> None:  # 主入口 / Main entry point
    failures = check_document_links(Path.cwd())  # 检查当前仓库文档 / Check current repository docs
    if failures:  # 检查是否有断链 / Check broken links
        raise AssertionError("\n".join(failures))  # 抛出断链错误 / Raise broken-link error
    print("Documentation link checks passed. / 文档链接检查通过。")  # 打印成功信息 / Print success message


if __name__ == "__main__":  # 检查直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
