# Cowork Session Manager (Windows版) 仕様書

**ファイル名**: `cowork_session_cleaner_win.py`
**対象OS**: Windows 10 / 11
**言語**: Python 3.8 以上
**作成日**: 2026-03-22
**最終更新**: 2026-03-22（v1.1 — ディレクトリ構造の誤認識を修正）

---

## 1. 概要

Claude Cowork アプリが Windows 上に保存するローカルセッションデータを管理する対話型 CLI ツール。セッション一覧の表示・削除・アーカイブ・アーカイブ解除を行う。

macOS 版（`cowork_session_cleaner.py`）を Windows のパス構造に合わせてリファクタリングしたもので、セッション識別の命名規則（`local_` プレフィックス）・ディレクトリ階層は macOS と共通している。主な差異はベースパスの動的探索のみである。

本ドキュメントには、動作不良発生時に使用する診断ツール `cowork_session_diagnose.py` の仕様も併記する。

---

## 2. 動作環境・前提条件

| 項目 | 内容 |
|------|------|
| OS | Windows 10 / 11 |
| Python | 3.8 以上（標準ライブラリのみ使用） |
| 依存ライブラリ | `os`, `sys`, `json`, `shutil`, `argparse`, `pathlib`, `datetime`（すべて標準） |
| 必要権限 | セッションディレクトリへの読み取り・書き込み・削除権限 |

---

## 3. セッションパス仕様

### 3.1 Windows のセッション格納パス

```
%USERPROFILE%\AppData\Local\Packages\Claude_{uuid}\LocalCache\Roaming\Claude\
    local-agent-mode-sessions\
        {outer_uuid}\
            {project_uuid}\
                local_{session_uuid}\       ← セッションデータ本体
                local_{session_uuid}.json   ← セッションメタデータ
```

各構成要素の意味:

| パス要素 | 説明 |
|----------|------|
| `Claude_{uuid}` | Windows UWP アプリのパッケージディレクトリ（UUID 部分は可変） |
| `local-agent-mode-sessions` | セッションルートディレクトリ（固定） |
| `{outer_uuid}` | 組織/アカウントレベルに対応する UUID ディレクトリ |
| `{project_uuid}` | プロジェクトレベルに対応する UUID ディレクトリ |
| `local_{session_uuid}` | 個々のセッションデータ本体（`local_` プレフィックス付き UUID） |
| `local_{session_uuid}.json` | セッションメタデータ（project_uuid 直下に配置） |

### 3.2 macOS との構造比較

| 項目 | macOS | Windows |
|------|-------|---------|
| ベースパス | `~/Library/Application Support/Claude/local-agent-mode-sessions`（固定） | `%LOCALAPPDATA%\Packages\Claude_{uuid}\LocalCache\Roaming\Claude\local-agent-mode-sessions`（動的探索） |
| ディレクトリ階層 | `{org}/{project}/local_{uuid}`（3 階層） | `{outer_uuid}/{project_uuid}/local_{uuid}`（3 階層・同等） |
| セッションフォルダ命名 | `local_` プレフィックス付き UUID | `local_` プレフィックス付き UUID（**同一**） |
| org/project 命名 | 人間が読みやすい名称 | UUID 形式 |
| パス固定性 | 固定パス | `Claude_{uuid}` 部分が可変（動的探索が必要） |

> **注記（v1.0 からの修正）:** 初期実装ではディレクトリ階層を 2 階層と誤認識しており、実セッションフォルダ（`local_` プレフィックス付き）が未検出となっていた。実環境の診断結果により、macOS と同じ 3 階層構造であることが確認され修正済み。

### 3.3 セッションメタデータ JSON

各セッションに対応する JSON ファイルが存在し、アーカイブ状態とタイトルを保持する。

**探索優先順位（`find_session_json` の検索順）:**
1. `{project_dir}\local_{uuid}.json`（親ディレクトリ内・プレフィックス付き — Windows の標準配置）
2. `{session_dir}\local_{uuid}.json`（セッションディレクトリ内・プレフィックス付き）
3. `{project_dir}\{uuid}.json`（親ディレクトリ内・プレフィックスなし — macOS 形式のフォールバック）
4. `{session_dir}\{uuid}.json`（セッションディレクトリ内・プレフィックスなし）
5. 上記いずれにも一致しない場合のブロードサーチ（両ディレクトリを走査）

**JSON スキーマ（主要フィールド）:**

```json
{
  "isArchived": false,
  "title": "セッションタイトル",
  "name": "代替名称"
}
```

---

## 4. コマンドライン引数

```
python cowork_session_cleaner_win.py [オプション]
```

| 引数 | 型 | デフォルト | 説明 |
|------|----|-----------|------|
| `--dry-run` | フラグ | `False` | 変更を行わずプレビューのみ実行 |
| `--sort` | `date` / `size` / `name` | `date` | セッション一覧の並び順 |
| `--archived` | フラグ | — | アーカイブ済みセッションのみ表示（`--active` と排他） |
| `--active` | フラグ | — | アクティブなセッションのみ表示（`--archived` と排他） |

`--archived` と `--active` は `argparse` の排他グループで制御されており、同時指定はエラーとなる。

---

## 5. 処理フロー

```
起動
  │
  ├─ find_sessions_root()  ← Claude_{uuid} を動的探索してセッションルートを特定
  │
  ├─ 引数パース (argparse)
  │
  ├─ discover_sessions()   ← 3階層を走査・local_ フォルダを収集
  │
  ├─ フィルタリング（--archived / --active）
  │
  ├─ ソート（--sort）
  │
  ├─ display_sessions()    ← 番号付き一覧を表示
  │
  ├─ アクション選択 [D / A / U / Q]
  │
  ├─ セッション番号入力
  │
  └─ アクション実行
       ├─ action_delete()
       ├─ action_archive()
       └─ action_unarchive()
```

---

## 6. 関数仕様

### 6.1 `find_sessions_root() → Path | None`

セッションルートディレクトリを動的に探索する。

**処理手順:**
1. `%USERPROFILE%\AppData\Local\Packages` の存在確認
2. `Claude_*` にマッチするディレクトリを最終更新日時の降順でソート
3. 各ディレクトリ配下の `LocalCache\Roaming\Claude\local-agent-mode-sessions` を確認
4. 最初に存在が確認できたパスを返す
5. 見つからない場合は `None` を返す

**複数 Claude パッケージへの対応:** 最終更新日時が最新のパッケージを優先するため、複数バージョンがインストールされている環境でも概ね正しいパスを選択できる。

---

### 6.2 `discover_sessions() → list[dict]`

セッションルート配下を **3 階層** 走査し、全セッション情報をリストとして返す。

**走査構造:**
```
SESSIONS_ROOT/
  {outer_uuid}/             ← outer_dir（組織/アカウントレベル）
    {project_uuid}/         ← project_dir（プロジェクトレベル）
      local_{session_uuid}/ ← session_dir（local_ プレフィックスで識別）
```

`local_` プレフィックスを持たないディレクトリはスキップする。

**返却データ（各セッション辞書のキー）:**

| キー | 型 | 説明 |
|------|----|------|
| `path` | `Path` | セッションディレクトリの絶対パス |
| `name` | `str` | セッションフォルダ名（`local_{uuid}` 形式） |
| `outer` | `str` | 外側 UUID の先頭 8 文字 + `...` |
| `project` | `str` | プロジェクト UUID の先頭 8 文字 + `...` |
| `size` | `int` | ディレクトリ合計サイズ（バイト） |
| `size_str` | `str` | 人間が読みやすい形式のサイズ |
| `last_modified` | `float` | Unix タイムスタンプ（最終更新） |
| `last_modified_str` | `str` | `YYYY-MM-DD HH:MM` 形式の日時文字列 |
| `is_archived` | `bool` | アーカイブ状態 |
| `json_path` | `Path \| None` | メタデータ JSON のパス |
| `title` | `str \| None` | セッションタイトル（JSON から取得） |

**エラー処理:** `SESSIONS_ROOT` が `None` または存在しない場合、エラーメッセージとパス例を表示して `sys.exit(1)` で終了する。

---

### 6.3 `find_session_json(session_dir: Path) → Path | None`

セッションメタデータ JSON ファイルを探索して返す。

セッションフォルダ名（`local_{uuid}`）を基にファイルを探索する。Windows では JSON がプロジェクトディレクトリ直下に `local_{uuid}.json` として配置されるため、これを最優先で探す。見つからない場合はプレフィックスなし形式やブロードサーチにフォールバックする（探索順の詳細は「3.3 セッションメタデータ JSON」参照）。

---

### 6.4 `get_archive_status(session_dir: Path) → tuple[bool, Path | None, str | None]`

JSON を読み取り、アーカイブ状態・JSON パス・タイトルをタプルで返す。

**フォールバック動作:**
- JSON が見つからない場合: `(False, None, None)`
- JSON が不正/読み取り不可の場合: `(False, json_path, None)`
- タイトルは `title` キー → `name` キーの順で取得

---

### 6.5 `set_archive_status(json_path: Path, archived: bool) → bool`

JSON の `isArchived` フィールドを書き換える。

ファイルは `encoding="utf-8"` で読み書きする（Windows のロケール依存エンコーディング回避）。成功時 `True`、失敗時 `False` を返す。

---

### 6.6 `get_folder_size(path: Path) → int`

`os.walk` でディレクトリを再帰走査し、全ファイルのサイズ合計をバイト単位で返す。アクセス不可ファイルは無視する。

---

### 6.7 `get_last_modified(path: Path) → float`

`os.walk` でディレクトリを再帰走査し、最も新しいファイルの `mtime` を Unix タイムスタンプで返す。ファイルが存在しない場合は `0` を返す。

---

### 6.8 `human_size(num_bytes: int) → str`

バイト数を B / KB / MB / GB / TB の単位付き文字列に変換する（小数点 1 桁）。

---

### 6.9 `display_sessions(sessions: list[dict]) → None`

セッション一覧をターミナルに表形式で出力する。

**ヘッダー情報:**
- セッション総数、アクティブ数、アーカイブ数
- 合計ディスク使用量
- セッションルートの実パス

**テーブル列:**
- `#`（番号）、`Status`（active / ARCHIVED）、`Last Modified`、`Size`、`Title / Session ID`
- タイトルが存在するセッションが 1 件以上ある場合、列名を `Title / Session ID` に切り替える
- Session ID 表示時は `local_` プレフィックスを除去した UUID のみを表示する
- タイトルが 50 文字を超える場合は 47 文字 + `...` に切り詰める

---

### 6.10 `parse_selection(text: str, count: int) → set[int]`

ユーザーの入力文字列をセッションインデックス（0 始まり）の集合に変換する。

**入力書式:**

| 書式 | 説明 | 例 |
|------|------|-----|
| `all` / `a` / `*` | 全件選択 | `all` |
| 数値 | 単一選択 | `3` |
| カンマ区切り | 複数選択 | `1,3,5` |
| ハイフン範囲 | 範囲選択 | `1-5` |
| 混合 | 組み合わせ | `1,3-5,7` |
| スペース区切り | カンマと同等 | `1 3 5` |

範囲外・非数値の入力は警告メッセージを表示してスキップする。

---

### 6.11 `action_delete(sessions, selected, dry_run) → None`

選択セッションを永続的に削除する。

**処理:**
1. 削除対象と合計解放サイズを表示
2. `--dry-run` 時はここで終了
3. `yes` / `y` の確認入力を要求
4. `shutil.rmtree()` でセッションディレクトリを削除
5. JSON メタデータがセッションディレクトリ外（project_dir 直下）にある場合は `unlink()` で削除
6. 削除件数と解放サイズを表示

---

### 6.12 `action_archive(sessions, selected, dry_run) → None`

選択セッションをアーカイブする（Cowork UI から非表示にする）。

**処理:**
1. 既アーカイブ済みセッションをスキップし件数を報告
2. `--dry-run` 時はプレビュー表示のみで終了
3. JSON ファイルが存在しないセッションを警告して除外
4. 確認入力後、`set_archive_status(json_path, True)` を呼び出す
5. 「Claude アプリの再起動が必要」旨を表示

---

### 6.13 `action_unarchive(sessions, selected, dry_run) → None`

選択セッションのアーカイブを解除する（Cowork UI に再表示する）。

`action_archive` と対称的な処理。`set_archive_status(json_path, False)` を呼び出す。

---

### 6.14 `main() → None`

エントリポイント。引数パース・セッション取得・フィルタ・ソート・表示・操作ループを統括する。

---

## 7. エラー処理・例外対応

| 状況 | 対応 |
|------|------|
| セッションルートが見つからない | エラーメッセージ + パス例を表示して `sys.exit(1)` |
| JSON 読み取り失敗（不正 JSON・権限エラー） | アーカイブ状態を `False`、タイトルを `None` として処理続行 |
| JSON 書き込み失敗 | エラーメッセージを表示し、そのセッションをスキップ |
| ファイル削除失敗 | エラーメッセージを表示し、他セッションの処理を続行 |
| `KeyboardInterrupt` / `EOFError`（Ctrl+C 等） | 「Cancelled.」を表示して正常終了 |
| ファイルサイズ取得失敗（`OSError`） | そのファイルのサイズを 0 として処理続行 |

---

## 8. 使用例

```bat
rem すべてのセッションを表示・管理
python cowork_session_cleaner_win.py

rem アーカイブ済みのみ表示
python cowork_session_cleaner_win.py --archived

rem アクティブのみ表示
python cowork_session_cleaner_win.py --active

rem サイズの大きい順に表示
python cowork_session_cleaner_win.py --sort size

rem 名前順に表示
python cowork_session_cleaner_win.py --sort name

rem 変更なしでプレビュー
python cowork_session_cleaner_win.py --dry-run

rem 組み合わせ例: アクティブセッションをサイズ順でドライラン
python cowork_session_cleaner_win.py --active --sort size --dry-run
```

---

## 9. macOS 版からの変更点一覧

| カテゴリ | macOS 版 | Windows 版 |
|----------|----------|-----------|
| セッションルートパス | `~/Library/Application Support/Claude/local-agent-mode-sessions`（固定） | `%LOCALAPPDATA%\Packages\Claude_{uuid}\LocalCache\...`（動的探索） |
| パス探索関数 | なし（定数 `SESSIONS_ROOT`） | `find_sessions_root()` を新設 |
| ディレクトリ階層 | `{org}/{project}/local_{uuid}`（3 階層） | `{outer_uuid}/{project_uuid}/local_{uuid}`（3 階層・同等） |
| セッション識別 | `local_` プレフィックスで判定 | `local_` プレフィックスで判定（**同一**） |
| UUID 取得 | `session_dir.name.replace("local_", "")` | `session_dir.name.replace("local_", "")`（**同一**） |
| JSON ファイル名 | `{uuid}.json`（プレフィックスなし） | `local_{uuid}.json`（プレフィックス付き） |
| JSON 配置場所 | project ディレクトリ直下 | project ディレクトリ直下（**同一**） |
| セッション辞書キー | `org`, `project` | `outer`, `project` |
| ファイル I/O | エンコーディング未指定 | `encoding="utf-8"` を明示 |
| ヘッダー表示 | セッション数・サイズのみ | セッションルートパスを追加 |
| コマンド例 | `python3` | `python` |

---

## 10. 注意事項

- アーカイブ操作（Archive / Unarchive）を行った後は **Claude アプリの再起動が必要**。再起動しないと UI への反映が行われない。
- 削除操作は **元に戻せない**。`--dry-run` で事前確認することを推奨する。
- JSON ファイルが存在しないセッションはアーカイブ操作の対象外となる（削除は可能）。
- 複数の `Claude_*` パッケージが存在する場合、最終更新日時が最新のものを自動選択する。意図しないパッケージが選択された場合は診断ツール（次節参照）を使用して確認すること。

---

## 11. 診断ツール仕様 — `cowork_session_diagnose.py`

### 11.1 目的

`cowork_session_cleaner_win.py` でセッションが正しく検出されない場合に実行する調査ツール。ディレクトリ構造・UUID 判定・JSON 探索の詳細を段階的にレポートし、問題箇所を特定する。

### 11.2 使用方法

```bat
python cowork_session_diagnose.py
```

引数・オプションなし。ファイルの場所はどこでも実行可能。

### 11.3 出力セクション

| セクション | 内容 |
|-----------|------|
| `[1]` | `%LOCALAPPDATA%\Packages` ディレクトリの存在確認 |
| `[2]` | `Claude_*` パッケージの一覧（最終更新日時降順） |
| `[3]` | セッションルートのフルパスと存在確認。見つからない場合は各パッケージ内の `LocalCache\Roaming\Claude` を詳細調査 |
| `[4]` | セッションルート直下のディレクトリ一覧と UUID 形式判定結果（`[+]` = UUID 形式、`[X]` = 非UUID） |
| `[5]` | 各外側ディレクトリ配下のエントリを走査し、JSON の存在場所・アーカイブ状態・タイトルを表示 |
| `[6]` | 集計（調査総数・UUID 判定 OK/NG 件数・`local_` プレフィックス件数） |

### 11.4 `[5]` セクションの見方

```
[bb413cbc-3e36-41...]  1 エントリ
    [+] e9c04f1c-be3c-4431-ae38-3875b9296599  JSON:セッション内 (local_07bbb101.json) ※stem不一致  状態:不明
```

- `[+]` / `[X]` ： UUID 形式かどうか（`+` = UUID 形式 = 検出対象）
- `JSON:` ： JSON ファイルの検出場所（「なし」の場合はアーカイブ操作不可）
- `※stem不一致` ： JSON のファイル名がディレクトリ名と異なる（**これが検出できていた場合、3 階層目の実セッションが存在する証拠**）
- `状態:` ： `active` / `ARCHIVED` / `不明`（JSON が見つからない場合）

### 11.5 `local_` プレフィックス件数の解釈

| 件数 | 意味 |
|------|------|
| `0` | セッションが 2 階層目に配置されていない（正常、または別の問題） |
| `1` 以上 | 実セッションフォルダが 3 階層目に存在する。`cowork_session_cleaner_win.py` の探索が 2 階層止まりだった場合に検出漏れが発生していた（v1.0 の不具合） |

### 11.6 主要な内部関数

| 関数 | 説明 |
|------|------|
| `find_sessions_root() → (Path\|None, list)` | セッションルートと Claude パッケージ一覧を返す（`cleaner_win.py` と同ロジック） |
| `_looks_like_uuid(name: str) → bool` | ハイフン除去後 32〜36 文字の 16 進数文字列かを判定。診断用に使用（`cleaner_win.py` では不使用） |
| `main()` | 診断処理全体を実行し、結果を標準出力に出力する |

### 11.7 診断結果の提供方法

出力結果をそのままテキストとして共有することで、問題の原因特定と修正対応が可能になる。個人情報（UUID 等）が含まれるが、これらは内部識別子であり、外部から意味のある情報は得られない。

---

## 12. バージョン履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| v1.0 | 2026-03-22 | 初版作成（macOS 版からの Windows リファクタリング） |
| v1.1 | 2026-03-22 | ディレクトリ構造を 2 階層から 3 階層に修正。`discover_sessions()` に project_dir ループを追加。`find_session_json()` の探索順を Windows 実環境に合わせて更新。`_looks_like_uuid()` を `cleaner_win.py` から削除し、`local_` プレフィックスによるセッション識別に統一。 |
