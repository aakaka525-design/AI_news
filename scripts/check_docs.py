#!/usr/bin/env python3
"""文档规则校验脚本 v1

检查 docs/ 目录下的文档是否符合已锁定的治理规则。
只做结构校验，不判断内容正确性。

用法：
    python scripts/check_docs.py

退出码：
    0 — 全部通过
    1 — 有规则未通过
"""

import re
import sys
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HANDOFF_DIR = PROJECT_ROOT / "docs" / "ai-handoff"
PLANS_DIR = PROJECT_ROOT / "docs" / "plans"
HANDOFF_README = HANDOFF_DIR / "README.md"
EXECUTION_PLAN = PROJECT_ROOT / "docs" / "execution-plan-week1-4.md"

# 2026-03-10 起生效的新规则（单文件追加制）
NEW_RULES_CUTOFF = "2026-03-10"

# ── 结果收集 ──────────────────────────────────────────

passed = []
failed = []


def report_pass(filepath: Path):
    passed.append(filepath)


def report_fail(filepath: Path, reasons: list[str]):
    failed.append((filepath, reasons))


# ── 工具函数 ──────────────────────────────────────────

def extract_date_from_filename(filepath: Path) -> str | None:
    """从文件名提取日期前缀 YYYY-MM-DD，返回字符串或 None。"""
    match = re.match(r"(\d{4}-\d{2}-\d{2})", filepath.name)
    return match.group(1) if match else None


def file_has_field(content: str, field: str) -> bool:
    """检查文件内容是否包含指定的元数据字段（如 '作者：'）。"""
    pattern = rf"[-*]\s*{re.escape(field)}"
    return bool(re.search(pattern, content))


def file_has_status_tag(content: str) -> bool:
    """检查文件是否包含状态标签（blockquote 或元数据格式）。"""
    # > **状态：xxx** 或 > 状态：xxx 或 - 状态：xxx
    patterns = [
        r">\s*\*?\*?状态[：:]",
        r"[-*]\s*状态[：:]",
    ]
    return any(re.search(p, content) for p in patterns)


# ── 校验逻辑 ──────────────────────────────────────────

def check_handoff_docs():
    """校验 docs/ai-handoff/ 下的 .md 文件（README 除外）。"""
    for md_file in sorted(HANDOFF_DIR.glob("*.md")):
        if md_file.name == "README.md":
            continue

        content = md_file.read_text(encoding="utf-8")
        reasons = []

        # 所有 handoff 文档必须有 作者 和 日期
        if not file_has_field(content, "作者"):
            reasons.append("缺少字段: 作者")
        if not file_has_field(content, "日期"):
            reasons.append("缺少字段: 日期")

        # 2026-03-10 之后的文档还需要 主题 和 状态
        file_date = extract_date_from_filename(md_file)
        if file_date and file_date >= NEW_RULES_CUTOFF:
            if not file_has_field(content, "主题"):
                reasons.append("缺少字段: 主题（2026-03-10 起新规则要求）")
            if not file_has_field(content, "状态"):
                reasons.append("缺少字段: 状态（2026-03-10 起新规则要求）")

        if reasons:
            report_fail(md_file, reasons)
        else:
            report_pass(md_file)


def check_plan_docs():
    """校验 docs/plans/ 下的 .md 文件和 execution-plan-week1-4.md 是否有状态标签。"""
    plan_files = sorted(PLANS_DIR.glob("*.md"))
    if EXECUTION_PLAN.exists():
        plan_files.append(EXECUTION_PLAN)

    for md_file in plan_files:
        content = md_file.read_text(encoding="utf-8")
        reasons = []

        if not file_has_status_tag(content):
            reasons.append("缺少状态标签（如 > **状态：已完成**）")

        if reasons:
            report_fail(md_file, reasons)
        else:
            report_pass(md_file)


def check_readme_references():
    """校验 README 中反引号引用的 .md 文件是否实际存在于 docs/ai-handoff/ 下。"""
    if not HANDOFF_README.exists():
        report_fail(HANDOFF_README, ["README.md 不存在"])
        return

    content = HANDOFF_README.read_text(encoding="utf-8")

    # 提取所有反引号中的 .md 文件名
    md_refs = re.findall(r"`([^`]+\.md)`", content)

    # 去重，只保留看起来像 handoff 文件名的（不含路径分隔符）
    md_refs = sorted(set(ref for ref in md_refs if "/" not in ref))

    missing = []
    for ref in md_refs:
        # 文件名可能带或不带日期前缀
        # 先直接在 handoff 目录下找
        candidates = list(HANDOFF_DIR.glob(f"*{ref}"))
        if not candidates and not (HANDOFF_DIR / ref).exists():
            missing.append(ref)

    if missing:
        reasons = [f"README 引用的文件不存在: {f}" for f in missing]
        report_fail(HANDOFF_README, reasons)
    else:
        report_pass(HANDOFF_README)


# ── 主入口 ────────────────────────────────────────────

def main():
    print("=" * 60)
    print("文档规则校验 v1")
    print("=" * 60)
    print()

    check_handoff_docs()
    check_plan_docs()
    check_readme_references()

    # 输出结果
    for filepath in passed:
        rel = filepath.relative_to(PROJECT_ROOT)
        print(f"[PASS] {rel}")

    for filepath, reasons in failed:
        rel = filepath.relative_to(PROJECT_ROOT)
        print(f"[FAIL] {rel}")
        for r in reasons:
            print(f"       - {r}")

    print()
    print(f"结果: {len(passed)} 通过, {len(failed)} 失败")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
