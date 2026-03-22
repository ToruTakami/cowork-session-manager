#!/usr/bin/env python3
"""
Cowork Session Diagnostic Tool (Windows)
-----------------------------------------
セッションが正しく検出されない場合の診断ツール。
ディレクトリ構造・UUID判定・JSON検索の詳細をレポートします。

Usage:
    python cowork_session_diagnose.py
"""

import os
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# パス探索（cleaner_win.py と同じロジック）
# ---------------------------------------------------------------------------

def find_sessions_root():
    packages_dir = Path.home() / "AppData" / "Local" / "Packages"
    if not packages_dir.exists():
        return None, []

    claude_dirs = sorted(
        packages_dir.glob("Claude_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    found_root = None
    for claude_dir in claude_dirs:
        candidate = (
            claude_dir / "LocalCache" / "Roaming" / "Claude" / "local-agent-mode-sessions"
        )
        if candidate.exists():
            found_root = candidate
            break

    return found_root, claude_dirs


def _looks_like_uuid(name):
    stripped = name.replace("-", "")
    return 32 <= len(stripped) <= 36 and all(c in "0123456789abcdefABCDEF" for c in stripped)


# ---------------------------------------------------------------------------
# 診断メイン
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("  Cowork Session Diagnostic Tool")
    print("=" * 70)

    # --- 1. Packages ディレクトリ確認 ---
    packages_dir = Path.home() / "AppData" / "Local" / "Packages"
    print(f"\n[1] Packages ディレクトリ: {packages_dir}")
    print(f"    存在: {packages_dir.exists()}")

    if not packages_dir.exists():
        print("\n  ERROR: Packages ディレクトリが見つかりません。")
        return

    # --- 2. Claude_* パッケージ一覧 ---
    claude_dirs = sorted(
        packages_dir.glob("Claude_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    print(f"\n[2] Claude_* パッケージ ({len(claude_dirs)} 件):")
    for d in claude_dirs:
        print(f"    {d.name}")

    if not claude_dirs:
        print("  ERROR: Claude パッケージが見つかりません。")
        return

    # --- 3. セッションルート確認 ---
    sessions_root, _ = find_sessions_root()
    print(f"\n[3] セッションルート:")
    print(f"    パス  : {sessions_root}")
    print(f"    存在  : {sessions_root.exists() if sessions_root else 'N/A'}")

    if not sessions_root or not sessions_root.exists():
        print("\n  ERROR: セッションルートが見つかりません。")
        # 各パッケージ内を詳しく調査
        for d in claude_dirs:
            lc = d / "LocalCache" / "Roaming" / "Claude"
            print(f"\n  パッケージ内確認: {d.name}")
            print(f"    LocalCache\\Roaming\\Claude 存在: {lc.exists()}")
            if lc.exists():
                entries = list(lc.iterdir())
                print(f"    直下のエントリ ({len(entries)} 件):")
                for e in entries:
                    print(f"      {e.name}  ({'dir' if e.is_dir() else 'file'})")
        return

    # --- 4. セッションルート直下の構造 ---
    root_entries = [e for e in sessions_root.iterdir() if e.is_dir()]
    print(f"\n[4] セッションルート直下のディレクトリ ({len(root_entries)} 件):")
    for entry in sorted(root_entries):
        is_uuid = _looks_like_uuid(entry.name)
        print(f"    [{'+' if is_uuid else 'X'}] {entry.name}  (UUID判定: {is_uuid})")

    # --- 5. 各外側ディレクトリの中身 ---
    print(f"\n[5] 各外側ディレクトリの中のセッション調査:")
    total_dirs = 0
    uuid_ok = 0
    uuid_ng = 0

    for outer_dir in sorted(root_entries):
        inner_entries = [e for e in outer_dir.iterdir() if e.is_dir()]
        print(f"\n  [{outer_dir.name[:16]}...]  {len(inner_entries)} エントリ")

        for inner in sorted(inner_entries):
            is_uuid = _looks_like_uuid(inner.name)
            total_dirs += 1
            if is_uuid:
                uuid_ok += 1
            else:
                uuid_ng += 1

            # JSON ファイル探索
            json_in_session = inner / f"{inner.name}.json"
            json_in_outer   = outer_dir / f"{inner.name}.json"
            json_found = "なし"
            if json_in_session.exists():
                json_found = f"セッション内 ({inner.name}.json)"
            elif json_in_outer.exists():
                json_found = f"親ディレクトリ ({inner.name}.json)"
            else:
                # ブロードサーチ
                for f in inner.iterdir():
                    if f.suffix == ".json":
                        json_found = f"セッション内 ({f.name}) ※stem不一致"
                        break
                if json_found == "なし":
                    for f in outer_dir.iterdir():
                        if f.suffix == ".json":
                            json_found = f"親ディレクトリ ({f.name}) ※stem不一致"
                            break

            # アーカイブ状態取得試行
            archive_status = "不明"
            json_path = None
            if json_in_session.exists():
                json_path = json_in_session
            elif json_in_outer.exists():
                json_path = json_in_outer
            if json_path:
                try:
                    with open(json_path, encoding="utf-8") as f:
                        data = json.load(f)
                    archived = data.get("isArchived", False)
                    title = data.get("title") or data.get("name") or "(タイトルなし)"
                    archive_status = f"{'ARCHIVED' if archived else 'active'} / {title[:30]}"
                except Exception as e:
                    archive_status = f"JSON読込エラー: {e}"

            marker = "+" if is_uuid else "X"
            print(f"    [{marker}] {inner.name[:36]}  JSON:{json_found}  状態:{archive_status}")

    print(f"\n[6] 集計:")
    print(f"    調査したディレクトリ総数 : {total_dirs}")
    print(f"    UUID判定 OK (検出対象)  : {uuid_ok}")
    print(f"    UUID判定 NG (スキップ)  : {uuid_ng}")

    # --- 7. local_ プレフィックス確認（macOS形式が混在しないか）---
    local_prefix_count = 0
    for outer_dir in root_entries:
        for inner in outer_dir.iterdir():
            if inner.is_dir() and inner.name.startswith("local_"):
                local_prefix_count += 1

    print(f"    'local_' プレフィックス : {local_prefix_count} 件")
    if local_prefix_count > 0:
        print("    ※ macOS形式のフォルダが混在しています。プログラムの修正が必要な可能性があります。")

    print("\n" + "=" * 70)
    print("  診断完了。この出力内容をご共有ください。")
    print("=" * 70)


if __name__ == "__main__":
    main()
