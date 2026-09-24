"""回填悬空的产物 ref（E23）：把 artifacts.json 里的内容落盘到
`<root>/projects/<P>/docs/<type>-<id>.json`, 并把 ref 指向真实文件 ✓。

安全第一（Founder 铁律: 动他数据前先备份 ✓）:
  · 先备份原 artifacts.json 到 ~/.factory-backups/artifact-refs-backfill-<ts>/ ✓
  · 支持 --dry-run（只看要改什么 ✓）
  · 幂等: ref 已经指向存在的文件 ⇒ 跳过 ✓
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path.home() / ".factory"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = Path(args.root)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bk = Path.home() / ".factory-backups" / f"artifact-refs-backfill-{ts}"
    touched = skipped = 0
    for pdir in sorted((root / "projects").glob("P-*")):
        f = pdir / "artifacts.json"
        if not f.is_file():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        arts = data.get("artifacts") or {}
        changed = False
        for aid, a in arts.items():
            ref = str(a.get("ref") or "")
            real = Path(ref.replace("file://", "")) if ref.startswith("file://") else None
            if real is not None and real.is_file():
                skipped += 1
                continue
            if "/docs/" not in ref and ref:
                skipped += 1                       # 不是占位符的, 不碰 ✓
                continue
            docs = pdir / "docs"
            tgt = docs / f"{str(a.get('type') or 'artifact').lower()}-{aid}.json"
            print(f"  {pdir.name} {aid} ({a.get('type')}) → {tgt}")
            touched += 1
            if args.dry_run:
                continue
            docs.mkdir(parents=True, exist_ok=True)
            tgt.write_text(json.dumps(
                {"id": aid, "type": a.get("type"), "project_id": pdir.name,
                 "producer_role": a.get("producer_role"), "producer_agent": a.get("producer_agent"),
                 "content": a.get("metadata") or {}}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            a["ref"] = "file://" + str(tgt)
            changed = True
        if changed and not args.dry_run:
            bk.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, bk / f"{pdir.name}-artifacts.json")
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  要回填 {touched} 个 · 跳过 {skipped} 个" + ("（dry-run, 没落盘 ✓）" if args.dry_run else ""))
    if touched and not args.dry_run:
        print(f"  备份: {bk}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
