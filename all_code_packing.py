import os
from pathlib import Path

import pathspec


# =========================
# 🐙 GitHub Repo 資訊
# =========================
# 是否為 GitHub Repository。
#
# True：
#   all_code.md 會寫入：
#   # GitHub Repo: <username>/<repo_name>
#
# False：
#   不寫入 GitHub Repo 資訊。
#
# repo_name 不另外設定，
# 直接使用 script 所在 root 目錄名稱。
IS_GITHUB_REPO = True
GITHUB_USERNAME = "a35085605"


# =========================
# ✅ 白名單（掃描起點）
# =========================
# 留空 → 以 script 所在目錄為 root 全量掃描
#
# 填入路徑時遵循 Python pathlib.Path.glob() 語意，
# 不是 gitignore / gitwildmatch 語意。
#
# 範例：
#   "src/field/"   → root/src/field/ 目錄
#   "src/**/*.ts"  → root/src/ 下所有 .ts 檔
INCLUDE_RULES = [
]


# =========================
# ❌ 排除規則（gitignore / gitwildmatch 語意）
# =========================
# 規則說明：
#
#   foo
#       → 匹配任意深度名稱為 foo 的檔案或目錄
#         例如：
#           root/foo
#           root/src/foo
#           root/src/a/foo
#
#   foo/
#       → 匹配任意深度名稱為 foo 的目錄
#
#   *.test.ts
#       → 匹配任意深度的 *.test.ts
#
#   reading/store
#       → pattern 內含 "/"，因此相對於 root
#         只匹配：
#           root/reading/store
#
#         不會自動匹配：
#           root/src/reading/store
#
#   **/reading/store
#       → 匹配任意深度的 reading/store
#
#   **/reading/store/**
#       → 匹配任意深度 reading/store 目錄內所有內容
#
# 若要精確限制 root 正下方，可使用：
#   /foo
EXCLUDE_RULES = [
    # --- 通用目錄 ---
    ".venv/",
    "venv/",
    "__pycache__/",
    ".git/",
    "build/",
    "dist/",
    "node_modules/",
    "old/",
    # "test/",
    # "tests/",
    "unpacked_code/",

    "docs/",

    # --- 測試檔 ---
    "*.test.ts",
    "*.spec.ts",

    # --- 特定檔案 ---
    "vite.config.ts",
    "all_code.md",
    "all_code_packing.py",
    "all_code_unpacking.py",
    "cleanup_whitespace.py",


    "cleanup_whitespace.py",

    # --- 任意深度目錄／模組 ---
    # "**/reading/store",
    # "**/reading/store/**",
]


# =========================
# 🎯 支援輸出檔案類型
# =========================
# key   = 副檔名
# value = Markdown code fence 語言
TARGET_FILE_EXTENSIONS = {
    ".py": "python",

    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",

    ".md": "markdown",

    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",

    ".txt": "text",
}


def build_spec(patterns: list[str]) -> pathspec.PathSpec:
    """
    直接以 gitwildmatch 建立排除規則。

    不對 pattern 做額外修改，
    讓 EXCLUDE_RULES 維持 gitignore / gitwildmatch 語意。
    """
    return pathspec.PathSpec.from_lines(
        "gitwildmatch",
        patterns,
    )


def is_excluded(
    path: Path,
    base: Path,
    exclude_spec: pathspec.PathSpec,
) -> bool:
    """
    判斷 path 是否符合 EXCLUDE_RULES。

    傳給 pathspec 的路徑一律轉成：
    - 相對於 root
    - POSIX-style (/)

    目錄額外補上 "/"，
    讓 trailing-slash directory pattern 能正確匹配。
    """
    rel = path.relative_to(base).as_posix()

    if path.is_dir():
        rel += "/"

    return exclude_spec.match_file(rel)


def resolve_include_paths(base: Path) -> list[Path]:
    """
    解析 INCLUDE_RULES 為實際路徑清單。

    - INCLUDE_RULES 留空：
        回傳 [base]，代表從專案 root 全量掃描。

    - INCLUDE_RULES 有設定：
        使用 pathlib.Path.glob() 解析。

    - pattern 沒有任何匹配：
        印出警告並略過。

    - 多個 pattern 指向同一個實際路徑：
        自動去重。
    """
    if not INCLUDE_RULES:
        return [base]

    results: list[Path] = []
    seen: set[Path] = set()

    for pattern in INCLUDE_RULES:
        matches = sorted(
            base.glob(pattern),
            key=lambda p: p.as_posix(),
        )

        if not matches:
            print(f"⚠️  INCLUDE_RULES 無匹配：{pattern!r}")

        for match in matches:
            resolved = match.resolve()

            if resolved in seen:
                continue

            seen.add(resolved)
            results.append(match)

    return results


def process_file(
    filepath: Path,
    root: Path,
    out,
) -> bool:
    """
    將單一檔案寫入輸出。

    成功寫入時回傳 True。

    以下情況回傳 False：
    - 不支援的副檔名
    - 檔案讀取失敗
    """
    suffix = filepath.suffix.lower()

    if suffix not in TARGET_FILE_EXTENSIONS:
        return False

    relative_path = filepath.relative_to(root)
    lang = TARGET_FILE_EXTENSIONS[suffix]

    try:
        content = filepath.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except Exception as e:
        print(f"❌ 讀取失敗：{filepath} ({e})")
        return False

    out.write(
        "---\n\n"
        f"## FILE: `{relative_path}`\n\n"
        f"```{lang}\n"
        f"{content}\n"
        "```\n\n"
    )

    return True


def main():
    script = Path(__file__).resolve()
    root = script.parent
    output = root / "all_code.md"

    exclude_spec = build_spec(EXCLUDE_RULES)
    start_points = resolve_include_paths(root)

    file_count = 0

    # 防止 INCLUDE_RULES 重疊時，
    # 同一個實際檔案被輸出多次。
    processed_files: set[Path] = set()

    with output.open("w", encoding="utf-8") as out:
        # =========================
        # Markdown Header
        # =========================
        out.write("# 專案程式碼彙整\n\n")

        if IS_GITHUB_REPO:
            repo_name = root.name

            out.write(
                f"# GitHub Repo: "
                f"{GITHUB_USERNAME}/{repo_name}\n\n"
            )

        # =========================
        # 掃描 INCLUDE 起點
        # =========================
        for start in start_points:

            # =========================
            # 單一檔案
            # =========================
            if start.is_file():

                # 不把 packing script 自己寫進輸出
                if start.resolve() == script:
                    continue

                # 避免 all_code*.md 被重新包入
                if (
                    start.name.startswith("all_code")
                    and start.suffix.lower() == ".md"
                ):
                    continue

                # 套用 EXCLUDE_RULES
                if is_excluded(
                    start,
                    root,
                    exclude_spec,
                ):
                    continue

                resolved = start.resolve()

                # 防止重複輸出
                if resolved in processed_files:
                    continue

                if process_file(
                    start,
                    root,
                    out,
                ):
                    processed_files.add(resolved)
                    file_count += 1

                continue

            # =========================
            # 目錄：遞迴走訪
            # =========================
            for dirpath, dirs, files in os.walk(start):
                root_path = Path(dirpath)

                # =========================
                # 目錄剪枝
                # =========================
                # 修改 dirs[:] 會讓 os.walk()
                # 完全不進入被排除的目錄。
                dirs[:] = sorted(
                    d
                    for d in dirs
                    if not is_excluded(
                        root_path / d,
                        root,
                        exclude_spec,
                    )
                )

                # =========================
                # 處理目前目錄內的檔案
                # =========================
                for filename in sorted(files):
                    filepath = root_path / filename

                    # 不輸出 packing script 自己
                    if filepath.resolve() == script:
                        continue

                    # 避免 all_code*.md 被重新包入
                    if (
                        filename.startswith("all_code")
                        and filepath.suffix.lower() == ".md"
                    ):
                        continue

                    # 套用 EXCLUDE_RULES
                    if is_excluded(
                        filepath,
                        root,
                        exclude_spec,
                    ):
                        continue

                    resolved = filepath.resolve()

                    # 防止重複輸出
                    if resolved in processed_files:
                        continue

                    if process_file(
                        filepath,
                        root,
                        out,
                    ):
                        processed_files.add(resolved)
                        file_count += 1

    print(
        f"✅ 輸出完成：{output.name}"
        f"（共 {file_count} 個檔案）"
    )


if __name__ == "__main__":
    main()
