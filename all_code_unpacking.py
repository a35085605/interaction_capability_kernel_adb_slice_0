from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


FILE_HEADER_RE = re.compile(r"^## FILE:\s*`(.+?)`\s*$")
FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})(?:[^`~]*)$")


@dataclass(frozen=True)
class PackedFile:
    relative_path: str
    content: str
    header_line: int


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description="將 all_code_packing.py 產生的 Markdown 彙整檔還原成原始目錄與檔案。"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=script_dir / "all_code.md",
        help="輸入 Markdown 檔（預設：script 同目錄下的 all_code.md）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=script_dir / "unpacked_code",
        help="還原根目錄（預設：script 同目錄下的 unpacked_code）",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="允許覆寫已存在的檔案；預設會跳過",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只顯示將執行的操作，不建立或覆寫檔案",
    )
    return parser.parse_args()


def is_section_boundary(lines: list[str], closing_index: int) -> bool:
    """確認 closing fence 後方是下一個區段或檔案結尾。"""
    index = closing_index + 1

    while index < len(lines) and not lines[index].strip():
        index += 1

    return index >= len(lines) or lines[index].strip() == "---"


def remove_packer_added_newline(content: str) -> str:
    """
    packing 腳本在每份原始內容後固定追加一個換行再寫 closing fence。
    拆包時移除這一個額外換行，以盡量精確還原原檔。
    """
    if content.endswith("\n"):
        return content[:-1]
    return content


def parse_bundle(markdown: str) -> tuple[list[PackedFile], list[str]]:
    """解析 all_code.md，回傳檔案區段與格式警告。"""
    lines = markdown.splitlines(keepends=True)
    packed_files: list[PackedFile] = []
    warnings: list[str] = []
    index = 0

    while index < len(lines):
        header_match = FILE_HEADER_RE.match(lines[index].rstrip("\r\n"))
        if not header_match:
            index += 1
            continue

        raw_path = header_match.group(1)
        header_line = index + 1
        cursor = index + 1

        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1

        if cursor >= len(lines):
            warnings.append(f"第 {header_line} 行：{raw_path!r} 缺少 code fence。")
            break

        opening_line = lines[cursor].rstrip("\r\n")
        fence_match = FENCE_OPEN_RE.match(opening_line)
        if not fence_match:
            warnings.append(
                f"第 {header_line} 行：{raw_path!r} 後方不是有效的 Markdown code fence。"
            )
            index = cursor + 1
            continue

        fence = fence_match.group(1)
        content_start = cursor + 1
        closing_index: int | None = None

        cursor = content_start
        while cursor < len(lines):
            if (
                lines[cursor].strip() == fence
                and is_section_boundary(lines, cursor)
            ):
                closing_index = cursor
                break
            cursor += 1

        if closing_index is None:
            warnings.append(f"第 {header_line} 行：{raw_path!r} 找不到 closing fence。")
            break

        content = "".join(lines[content_start:closing_index])
        packed_files.append(
            PackedFile(
                relative_path=raw_path,
                content=remove_packer_added_newline(content),
                header_line=header_line,
            )
        )
        index = closing_index + 1

    return packed_files, warnings


def safe_destination(output_root: Path, raw_path: str) -> Path:
    """將彙整檔中的相對路徑轉成安全的輸出路徑，阻擋路徑穿越。"""
    if "\x00" in raw_path:
        raise ValueError("路徑含 NUL 字元")

    normalized = raw_path.strip().replace("\\", "/")
    pure_path = PurePosixPath(normalized)

    if not normalized or normalized.startswith("//"):
        raise ValueError("空路徑或 UNC 絕對路徑")
    if pure_path.is_absolute():
        raise ValueError("不允許絕對路徑")
    if any(part in {"", ".", ".."} for part in pure_path.parts):
        raise ValueError("路徑包含空白、. 或 .. 區段")
    if pure_path.parts[0].endswith(":"):
        raise ValueError("不允許 Windows 磁碟機絕對路徑")

    root_resolved = output_root.resolve()
    destination = root_resolved.joinpath(*pure_path.parts)
    destination_resolved = destination.resolve(strict=False)

    try:
        destination_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("路徑超出輸出根目錄") from exc

    return destination_resolved


def unpack_bundle(
    packed_files: list[PackedFile],
    output_root: Path,
    *,
    overwrite: bool,
    dry_run: bool,
) -> tuple[int, int, int]:
    """寫出所有檔案，回傳 restored、skipped、failed 數量。"""
    restored = 0
    skipped = 0
    failed = 0
    seen_destinations: set[Path] = set()

    if not dry_run:
        output_root.mkdir(parents=True, exist_ok=True)

    for packed in packed_files:
        try:
            destination = safe_destination(output_root, packed.relative_path)
        except ValueError as exc:
            print(
                f"❌ 第 {packed.header_line} 行：拒絕不安全路徑 "
                f"{packed.relative_path!r}（{exc}）"
            )
            failed += 1
            continue

        if destination in seen_destinations:
            print(f"⚠️  重複路徑，略過後續區段：{packed.relative_path}")
            skipped += 1
            continue
        seen_destinations.add(destination)

        if destination.exists() and not overwrite:
            print(f"⏭️  已存在，略過：{destination}")
            skipped += 1
            continue

        if dry_run:
            action = "覆寫" if destination.exists() else "建立"
            print(f"🔎 將{action}：{destination}")
            restored += 1
            continue

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("w", encoding="utf-8", newline="") as out:
                out.write(packed.content)
            print(f"✅ 已還原：{destination}")
            restored += 1
        except OSError as exc:
            print(f"❌ 寫入失敗：{destination}（{exc}）")
            failed += 1

    return restored, skipped, failed


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    output_root = args.output.expanduser().resolve()

    if not input_path.is_file():
        print(f"❌ 找不到輸入檔：{input_path}")
        return 1

    try:
        markdown = input_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"❌ 無法讀取輸入檔：{input_path}（{exc}）")
        return 1

    packed_files, warnings = parse_bundle(markdown)

    for warning in warnings:
        print(f"⚠️  {warning}")

    if not packed_files:
        print("❌ 沒有找到可還原的 FILE 區段。")
        return 1

    restored, skipped, failed = unpack_bundle(
        packed_files,
        output_root,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )

    mode = "預覽完成" if args.dry_run else "拆包完成"
    print(
        f"\n{mode}：共解析 {len(packed_files)} 個檔案，"
        f"處理 {restored}、略過 {skipped}、失敗 {failed}。"
    )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
