"""tests/benchmark/test_benchmark_verifiers.py — verifier 正/反例有效性 (不调 LLM)。

每个 verifier 两组沙箱:
- 正例 (fixed): 修复后代码 → verifier (True, ...)。
- 反例 (buggy/未实现): 缺陷原版代码 → verifier (False, ...)。

fixtures 镜像 markpad 生产目录真实代码结构 (缺陷版本) 与合理修复版本;
GREENFIELD verifier 真实运行 todo.py CLI (subprocess, 沙箱内)。

保障: 反例不误判 (False), 正例不误杀 (True) — 样本可执行、验收可信。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.benchmark import verifiers
from exec.benchmark.models import BenchmarkSample, SampleKind
from exec.benchmark.verifiers import get

# ================================================================ fixtures

BUG_001_BUGGY = """\
class SearchService {
  String _replaceQuery = '';

  void replaceCurrent(void Function(String) onContentChanged) {
    onContentChanged(_replaceQuery);
  }

  void replaceAll(void Function(String) onContentChanged, String fullContent) {
    var display = fullContent;
    final match = RegExp(_replaceQuery).firstMatch(fullContent);
    if (match != null) {
      display = display.replaceRange(match.start, match.end, _replaceQuery);
    }
    onContentChanged(display);
  }
}
"""

BUG_001_FIXED = """\
class SearchService {
  String _replaceQuery = '';

  void replaceCurrent(void Function(String) onContentChanged, String fullContent) {
    final match = RegExp(_replaceQuery).firstMatch(fullContent);
    if (match != null) {
      final display = fullContent.replaceRange(match.start, match.end, _replaceQuery);
      onContentChanged(display);
    }
  }

  void replaceAll(void Function(String) onContentChanged, String fullContent) {
    var display = fullContent;
    final match = RegExp(_replaceQuery).firstMatch(fullContent);
    if (match != null) {
      display = display.replaceRange(match.start, match.end, _replaceQuery);
    }
    onContentChanged(display);
  }
}
"""

BUG_002_BUGGY = """\
class FileController {
  bool _readOnly = false;
  bool get readOnly => _readOnly;
  List<dynamic> _openFiles = [];

  void switchToTab(int index) {
    if (index < 0 || index >= _openFiles.length) return;
    _activeTabIndex = index;
    _readOnly = false;
    notifyListeners();
  }
}
"""

BUG_002_FIXED = """\
class FileController {
  bool _readOnly = false;
  bool get readOnly => _readOnly;
  List<dynamic> _openFiles = [];

  void switchToTab(int index) {
    if (index < 0 || index >= _openFiles.length) return;
    _activeTabIndex = index;
    final file = _openFiles[index];
    _readOnly = file.readOnly;
    notifyListeners();
  }
}
"""

BUG_003_BUGGY = """\
class EncodingDetector {
  static String detect(String path) {
    final bytes = File(path).readAsBytesSync();
    if (bytes.length < 4) return 'utf-8';

    if (bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF) return 'utf-8';
    if (bytes[0] == 0xFF && bytes[1] == 0xFE) return 'utf-16le';
    if (bytes[0] == 0xFE && bytes[1] == 0xFF) return 'utf-16be';
    return 'utf-8';
  }
}
"""

BUG_003_FIXED = """\
class EncodingDetector {
  static String detect(String path) {
    final bytes = File(path).readAsBytesSync();
    // BOM 优先于长度守卫: 短 UTF-16 文件不被误判 utf-8
    if (bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF) return 'utf-8';
    if (bytes[0] == 0xFF && bytes[1] == 0xFE) return 'utf-16le';
    if (bytes[0] == 0xFE && bytes[1] == 0xFF) return 'utf-16be';
    if (bytes.length < 4) return 'utf-8';
    return 'utf-8';
  }
}
"""

BUG_004_BUGGY = """\
import '../../core/document/block.dart';

class DocumentSnapshot {
  static Block _cloneBlock(Block block) {
    return switch (block) {
      ParagraphBlock b => ParagraphBlock(b.text, id: b.id),
      TableBlock b => TableBlock(
        b.rows.map((r) => [...r]).toList(),
        id: b.id,
      ),
      _ => throw UnsupportedError('Unknown block type: ${block.runtimeType}'),
    };
  }
}
"""

BUG_004_FIXED = """\
import '../../core/document/block.dart';

class DocumentSnapshot {
  static Block _cloneBlock(Block block) {
    return switch (block) {
      ParagraphBlock b => ParagraphBlock(b.text, id: b.id),
      TableBlock b => TableBlock(
        b.rows.map((r) => [...r]).toList(),
        aligns: b.aligns,
        columnWidths: b.columnWidths,
        id: b.id,
      ),
      _ => throw UnsupportedError('Unknown block type: ${block.runtimeType}'),
    };
  }
}
"""

BUG_005_BUGGY = """\
class MarkdownSerializer {
  String _serializeList(bool ordered, List<ListItem> items) {
    final buf = StringBuffer();
    for (int i = 0; i < items.length; i++) {
      final item = items[i];
      buf.writeln('${'  ' * item.indent}${ordered ? '${i + 1}. ' : '- '}${item.text}');
    }
    return buf.toString().trimRight();
  }

  Document deserialize(String markdown) {
    return Document(blocks: const []);
  }
}
"""

BUG_005_FIXED = """\
class MarkdownSerializer {
  String _serializeList(bool ordered, List<ListItem> items) {
    final buf = StringBuffer();
    int lastIndent = -1;
    int counter = 0;
    for (final item in items) {
      if (item.indent != lastIndent) {
        lastIndent = item.indent;
        counter = 1;
      } else {
        counter++;
      }
      buf.writeln('${'  ' * item.indent}${ordered ? '$counter. ' : '- '}${item.text}');
    }
    return buf.toString().trimRight();
  }

  Document deserialize(String markdown) {
    return Document(blocks: const []);
  }
}
"""

FEAT_001_BUGGY = """\
import 'package:flutter/material.dart';

class FileTree extends StatelessWidget {
  final List<MdFile> recentFiles;
  const FileTree({super.key, required this.recentFiles});

  Widget _buildRecentFiles(BuildContext context) {
    final recent = widget.recentFiles;
    return ListView.builder(
      itemCount: recent.length,
      itemBuilder: (context, index) {
        final file = recent[index];
        return ListTile(
          leading: const Icon(Icons.description_outlined, size: 12),
          title: Text(file.displayName),
          onTap: () {},
        );
      },
    );
  }
}
"""

FEAT_001_FIXED = """\
import 'package:flutter/material.dart';

class FileTree extends StatelessWidget {
  final List<MdFile> recentFiles;
  const FileTree({super.key, required this.recentFiles});

  Widget _buildRecentFiles(BuildContext context) {
    final recent = widget.recentFiles;
    return ListView.builder(
      itemCount: recent.length,
      itemBuilder: (context, index) {
        final file = recent[index];
        return ListTile(
          leading: const Icon(Icons.description_outlined, size: 12),
          title: Text(file.displayName),
          subtitle: Text(_relativeTime(file.modifiedAt)),
          onTap: () {},
        );
      },
    );
  }

  String _relativeTime(DateTime time) {
    final diff = DateTime.now().difference(time);
    if (diff.inMinutes < 1) return '刚刚';
    if (diff.inHours < 1) return '${diff.inMinutes} 分钟前';
    if (diff.inDays < 1) return '${diff.inHours} 小时前';
    return '${diff.inDays} 天前';
  }
}
"""

FEAT_002_BUGGY = """\
class MdFile {
  final String path;
  final String name;
  final int size;

  MdFile({required this.path, required this.name, this.size = 0});
}
"""

FEAT_002_FIXED = """\
class MdFile {
  final String path;
  final String name;
  final int size;

  MdFile({required this.path, required this.name, this.size = 0});

  String get formatSize {
    if (size < 1024) return '$size B';
    if (size < 1024 * 1024) return '${(size / 1024).toStringAsFixed(1)} KB';
    if (size < 1024 * 1024 * 1024) return '${(size / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(size / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }
}
"""

FEAT_003_BUGGY = """\
import 'package:flutter/material.dart';

class EditorTabBar extends StatelessWidget {
  final List<MdFile> openFiles;
  final int activeIndex;
  const EditorTabBar({super.key, required this.openFiles, required this.activeIndex});

  @override
  Widget build(BuildContext context) {
    return Row(children: const [Text('tab')]);
  }
}
"""

FEAT_003_FIXED = """\
import 'package:flutter/material.dart';

class EditorTabBar extends StatelessWidget {
  final List<MdFile> openFiles;
  final int activeIndex;
  final Map<String, bool> dirty;
  const EditorTabBar({
    super.key,
    required this.openFiles,
    required this.activeIndex,
    this.dirty = const {},
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: openFiles.map((f) {
        return Row(children: [
          Text(f.displayName),
          if (dirty[f.path] == true)
            const Icon(Icons.circle, size: 8, color: Colors.orange),
        ]);
      }).toList(),
    );
  }
}
"""

GREENFIELD_TODO_PY = """\
#!/usr/bin/env python3
\"\"\"todo.py — 命令行待办管理 (Python 3 标准库, 零第三方依赖).\"\"\"
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent / "todo.json"


def load():
    if not DATA.exists():
        return []
    return json.loads(DATA.read_text(encoding="utf-8"))


def save(tasks):
    DATA.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def next_id(tasks):
    return max([t["id"] for t in tasks], default=0) + 1


def main(argv):
    cmd = argv[0] if argv else "list"
    tasks = load()
    if cmd == "add":
        task = {"id": next_id(tasks), "text": " ".join(argv[1:]), "done": False}
        tasks.append(task)
        save(tasks)
        print(f"added {task['id']}: {task['text']}")
    elif cmd == "list":
        show = tasks if "--all" in argv else [t for t in tasks if not t["done"]]
        for t in show:
            mark = "[x]" if t["done"] else "[ ]"
            print(f"{t['id']}. {mark} {t['text']}")
    elif cmd == "done":
        tid = int(argv[1])
        for t in tasks:
            if t["id"] == tid:
                t["done"] = True
        save(tasks)
    elif cmd == "remove":
        tid = int(argv[1])
        tasks = [t for t in tasks if t["id"] != tid]
        save(tasks)
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
"""


# ================================================================ helpers

def _write(sandbox: Path, rel: str, content: str) -> Path:
    target = sandbox / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _sample(sample_id: str, verifier_id: str) -> BenchmarkSample:
    return BenchmarkSample(id=sample_id, kind=SampleKind.BUG, objective="x",
                           verifier_id=verifier_id)


# ================================================================ 5 Bug 正/反例

BUG_CASES = [
    ("verify_bug_001_replace_current", "BUG-MKP-001",
     "lib/editor/services/search_service.dart", BUG_001_BUGGY, BUG_001_FIXED),
    ("verify_bug_002_readonly_tab", "BUG-MKP-002",
     "lib/editor/controllers/file_controller.dart", BUG_002_BUGGY, BUG_002_FIXED),
    ("verify_bug_003_bom_order", "BUG-MKP-003",
     "lib/editor/services/encoding_service.dart", BUG_003_BUGGY, BUG_003_FIXED),
    ("verify_bug_004_snapshot_fields", "BUG-MKP-004",
     "lib/editor/undo/document_snapshot.dart", BUG_004_BUGGY, BUG_004_FIXED),
    ("verify_bug_005_nested_list_numbering", "BUG-MKP-005",
     "lib/core/document/serializer.dart", BUG_005_BUGGY, BUG_005_FIXED),
]


@pytest.mark.parametrize("vid,sid,rel,buggy,fixed", BUG_CASES,
                         ids=[c[0] for c in BUG_CASES])
def test_bug_verifier_negative_rejects_buggy(tmp_path: Path,
                                             vid: str, sid: str, rel: str,
                                             buggy: str, fixed: str) -> None:
    """反例: 缺陷原版 → verifier False (不误判)。"""
    sandbox = tmp_path / "neg"
    _write(sandbox, rel, buggy)
    passed, detail = get(vid)(sandbox, _sample(sid, vid))
    assert passed is False, f"{vid} 反例误判通过: {detail}"


@pytest.mark.parametrize("vid,sid,rel,buggy,fixed", BUG_CASES,
                         ids=[c[0] for c in BUG_CASES])
def test_bug_verifier_positive_accepts_fixed(tmp_path: Path,
                                             vid: str, sid: str, rel: str,
                                             buggy: str, fixed: str) -> None:
    """正例: 修复后代码 → verifier True (不误杀)。"""
    sandbox = tmp_path / "pos"
    _write(sandbox, rel, fixed)
    passed, detail = get(vid)(sandbox, _sample(sid, vid))
    assert passed is True, f"{vid} 正例误判失败: {detail}"


def test_bug_verifier_missing_file_fails(tmp_path: Path) -> None:
    """验收文件缺失 → verifier 响亮 False (FileNotFoundError 转 False)。

    直接调 verifier 时缺失文件抛 FileNotFoundError (runner 内会转 FAIL);
    测试按同一语义捕获 → (False, 缺失说明), 断言不依赖异常传播细节。
    """
    sandbox = tmp_path / "empty"
    try:
        passed, detail = get("verify_bug_001_replace_current")(
            sandbox, _sample("BUG-MKP-001", "verify_bug_001_replace_current"))
    except FileNotFoundError as exc:
        passed, detail = False, str(exc)
    assert passed is False
    assert "缺失" in detail


# ================================================================ 3 Feature 正/反例

FEAT_CASES = [
    ("verify_feat_001_recent_time", "FEAT-MKP-001",
     "lib/shared/pages/file_tree.dart", FEAT_001_BUGGY, FEAT_001_FIXED),
    ("verify_feat_002_format_size", "FEAT-MKP-002",
     "lib/shared/models/md_file.dart", FEAT_002_BUGGY, FEAT_002_FIXED),
    ("verify_feat_003_tab_dirty", "FEAT-MKP-003",
     "lib/shared/widgets/tab_bar.dart", FEAT_003_BUGGY, FEAT_003_FIXED),
]


@pytest.mark.parametrize("vid,sid,rel,buggy,fixed", FEAT_CASES,
                         ids=[c[0] for c in FEAT_CASES])
def test_feature_verifier_negative_rejects_unimplemented(tmp_path: Path,
                                                         vid: str, sid: str, rel: str,
                                                         buggy: str, fixed: str) -> None:
    """反例: 未实现版本 (现状) → verifier False (零改动不得通过)。"""
    sandbox = tmp_path / "neg"
    _write(sandbox, rel, buggy)
    passed, detail = get(vid)(sandbox, _sample(sid, vid))
    assert passed is False, f"{vid} 反例误判通过: {detail}"


@pytest.mark.parametrize("vid,sid,rel,buggy,fixed", FEAT_CASES,
                         ids=[c[0] for c in FEAT_CASES])
def test_feature_verifier_positive_accepts_implemented(tmp_path: Path,
                                                       vid: str, sid: str, rel: str,
                                                       buggy: str, fixed: str) -> None:
    """正例: 实现后代码 → verifier True (不误杀)。"""
    sandbox = tmp_path / "pos"
    _write(sandbox, rel, fixed)
    passed, detail = get(vid)(sandbox, _sample(sid, vid))
    assert passed is True, f"{vid} 正例误判失败: {detail}"


# ================================================================ GREENFIELD

def test_greenfield_verifier_missing_script_fails(tmp_path: Path) -> None:
    """todo.py 缺失 → False ('todo.py 缺失')。"""
    passed, detail = get("verify_greenfield_todo_cli")(
        tmp_path, _sample("GREENFIELD-001", "verify_greenfield_todo_cli"))
    assert passed is False
    assert "todo.py 缺失" in detail


def test_greenfield_verifier_real_behavior_passes(tmp_path: Path) -> None:
    """正例: 真实运行 todo.py CLI → add/list/done/remove/list --all 行为全通过。"""
    _write(tmp_path, "todo.py", GREENFIELD_TODO_PY)
    passed, detail = get("verify_greenfield_todo_cli")(
        tmp_path, _sample("GREENFIELD-001", "verify_greenfield_todo_cli"))
    assert passed is True, f"todo CLI 行为验证失败: {detail}"
    # JSON 持久化产物落在沙箱 cwd
    assert (tmp_path / "todo.json").is_file()


def test_greenfield_verifier_rejects_broken_cli(tmp_path: Path) -> None:
    """反例: 残缺实现 (add 不持久化任务 → 添加无实际效果) → False。"""
    broken = GREENFIELD_TODO_PY.replace(
        "tasks.append(task)", "pass  # 残缺: add 不真正添加任务"
    )
    _write(tmp_path, "todo.py", broken)
    passed, detail = get("verify_greenfield_todo_cli")(
        tmp_path, _sample("GREENFIELD-001", "verify_greenfield_todo_cli"))
    assert passed is False, "残缺 todo CLI 不应通过"


def test_verifiers_registry_has_all_nine() -> None:
    """注册表: 5 bug + 3 feature + 1 greenfield 全部注册。"""
    expected = {
        "verify_bug_001_replace_current", "verify_bug_002_readonly_tab",
        "verify_bug_003_bom_order", "verify_bug_004_snapshot_fields",
        "verify_bug_005_nested_list_numbering",
        "verify_feat_001_recent_time", "verify_feat_002_format_size",
        "verify_feat_003_tab_dirty",
        "verify_greenfield_todo_cli",
    }
    assert expected <= set(verifiers.VERIFIERS)
