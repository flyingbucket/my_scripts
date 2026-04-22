import os
import sys
import ast
import argparse
import sqlite3
import textwrap
import time
from pathlib import Path
from typing import Optional, List

DB_DEFAULT = Path.home() / ".cache" / "envdoc" / "envdoc.sqlite"


def ensure_db(conn: sqlite3.Connection):
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA mmap_size=30000000000;")

    # ✅ 用 path 做 PRIMARY KEY，最简单最稳妥
    conn.execute("""
    CREATE TABLE IF NOT EXISTS files(
        path TEXT PRIMARY KEY,
        package TEXT,
        relpath TEXT,
        mtime REAL
    );
    """)

    conn.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(
        qualname UNINDEXED,
        kind UNINDEXED,
        package UNINDEXED,
        path UNINDEXED,
        relpath UNINDEXED,
        text,
        tokenize='porter'
    );
    """)
    conn.commit()


def get_site_roots():
    import site, sysconfig

    roots = []

    # 1) 来自 sys.path（包含 zip-stdlib、lib-dynload、项目根等）
    for p in sys.path:
        if not p:
            continue
        pp = Path(p)
        if pp.exists() and pp.is_dir():
            roots.append(pp)

    # 2) 标准安装位
    for p in site.getsitepackages() + [site.getusersitepackages()]:
        if p and Path(p).exists():
            roots.append(Path(p))

    # 3) sysconfig 的 purelib / platlib（兼容多平台/发行版）
    for k in ("purelib", "platlib", "stdlib"):
        try:
            v = sysconfig.get_paths().get(k)
            if v and Path(v).exists():
                roots.append(Path(v))
        except Exception:
            pass

    # 4) conda 常见路径（兜底）
    pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    conda_guess = Path(sys.prefix) / "lib" / pyver / "site-packages"
    if conda_guess.exists():
        roots.append(conda_guess)

    # 去重、保序
    out, seen = [], set()
    for r in roots:
        if r not in seen:
            out.append(r)
            seen.add(r)
    print(f"in get_site_roots")
    print(f"out:{out}")
    print(f"seen:{seen}")
    return out


def iter_py_files(root: Path):
    SKIP = {
        "tests",
        "testing",
        "test",
        "benchmarks",
        "docs",
        "doc",
        "__pycache__",
        "examples",
        "example",
    }
    for dirpath, dirnames, filenames in os.walk(root):
        dn = os.path.basename(dirpath).lower()
        if dn in SKIP:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(".py") and not fn.startswith("."):
                yield Path(dirpath) / fn


def detect_package(file_path: Path, roots: List[Path]):
    best_root = None
    for r in roots:
        try:
            file_path.relative_to(r)
            if best_root is None or len(str(r)) > len(str(best_root)):
                best_root = r
        except ValueError:
            continue
    if best_root is None:
        return ("", str(file_path))
    rel = file_path.relative_to(best_root)
    parts = rel.parts
    pkg = ""
    if parts:
        first = parts[0]
        pkg = first.split(".")[0]
    return (pkg, str(rel))


class DocCollector(ast.NodeVisitor):
    def __init__(self, module_qualname: str):
        self.items = []
        self.module = module_qualname

    def add(self, qualname: str, kind: str, doc):
        if doc:
            self.items.append((qualname, kind, doc))

    def visit_Module(self, node: ast.Module):
        self.add(self.module, "module", ast.get_docstring(node))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        q = f"{self.module}.{node.name}"
        self.add(q, "class", ast.get_docstring(node))
        for b in node.body:
            if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qq = f"{q}.{b.name}"
                self.add(qq, "method", ast.get_docstring(b))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        q = f"{self.module}.{node.name}"
        self.add(q, "function", ast.get_docstring(node))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        q = f"{self.module}.{node.name}"
        self.add(q, "function", ast.get_docstring(node))
        self.generic_visit(node)


def module_qualname_from_path(path: Path) -> str:
    parts = list(path.parts)
    if parts and parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts:
        parts[-1] = parts[-1][:-3]

    def ok(s: str) -> bool:
        return (
            s
            and (s[0].isalpha() or s[0] == "_")
            and all(c.isalnum() or c == "_" for c in s)
        )

    parts = [p for p in parts if ok(p)]
    return ".".join(parts)


def index_env(db_path: Path, extra_roots: Optional[List[Path]] = None):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    ensure_db(conn)

    roots = get_site_roots()
    if extra_roots:
        for er in extra_roots:
            er = Path(er)
            if er.exists() and er.is_dir():
                roots.append(er)

    # 去重
    uniq_roots, seen = [], set()
    for r in roots:
        if r not in seen:
            uniq_roots.append(r)
            seen.add(r)

    # ✅ 仅这一段：全量遍历 uniq_roots（不要再来第二遍带过滤的循环）
    files = []
    total_py = 0
    for root in uniq_roots:
        cnt = 0
        for f in iter_py_files(root):
            files.append((root, f))
            cnt += 1
        # 可选调试：每个 root 找到了多少 .py
        # print(f"[collect] {root} -> {cnt} .py")
        total_py += cnt

    print(f"[collect] total .py files discovered: {total_py}")

    cur = conn.cursor()
    cur.execute("BEGIN;")
    for root, f in files:
        mtime = f.stat().st_mtime
        pkg, rel = detect_package(f, uniq_roots)  # 用 uniq_roots 即可
        # ✅ 表结构改了（path 是主键），ON CONFLICT 仍可用
        cur.execute(
            """
        INSERT INTO files(path, package, relpath, mtime)
        VALUES(?,?,?,?)
        ON CONFLICT(path) DO UPDATE SET
            mtime=excluded.mtime,
            package=excluded.package,
            relpath=excluded.relpath;
        """,
            (str(f), pkg, rel, mtime),
        )
    conn.commit()

    # 下面保持你的 reindex docs 的逻辑不变即可
    ...

    cur = conn.cursor()
    cur.execute("SELECT path, package, relpath, mtime FROM files;")
    rows = cur.fetchall()
    reindexed = 0
    scanned = 0
    t0 = time.time()
    for path, package, relpath, mtime in rows:
        scanned += 1
        p = Path(path)
        if not p.exists():
            continue
        cur.execute("DELETE FROM docs WHERE path = ?;", (path,))
        try:
            source = p.read_text(encoding="utf-8", errors="ignore")
            modname = module_qualname_from_path(Path(package) / Path(relpath))
            tree = ast.parse(source)
            collector = DocCollector(modname)
            collector.visit(tree)
            for qualname, kind, doc in collector.items:
                cur.execute(
                    "INSERT INTO docs(qualname, kind, package, path, relpath, text) VALUES(?,?,?,?,?,?);",
                    (qualname, kind, package, path, relpath, doc),
                )
            reindexed += 1
        except Exception:
            pass
        if reindexed % 500 == 0:
            conn.commit()
    conn.commit()
    dt = time.time() - t0
    print(f"Indexed {reindexed} files (scanned {scanned}) in {dt:.1f}s into {db_path}")


def search_db(
    db_path: Path, query: str, limit: int = 50, package: Optional[str] = None
):
    if not db_path.exists():
        print(
            f"Index not found at {db_path}. Run: python envdoc.py index",
            file=sys.stderr,
        )
        sys.exit(2)
    conn = sqlite3.connect(db_path)
    ensure_db(conn)
    cur = conn.cursor()
    if package:
        q = "SELECT qualname, kind, package, path, snippet(docs, 5, '[', ']', ' … ', 10) FROM docs WHERE text MATCH ? AND package = ? LIMIT ?;"
        params = (query, package, limit)
    else:
        q = "SELECT qualname, kind, package, path, snippet(docs, 5, '[', ']', ' … ', 10) FROM docs WHERE text MATCH ? LIMIT ?;"
        params = (query, limit)
    try:
        rows = list(cur.execute(q, params))
    except sqlite3.OperationalError as e:
        print(
            "Search error:",
            e,
            "\\nTip: Use simple terms or FTS5 operators like AND, OR, NEAR/5.",
            file=sys.stderr,
        )
        sys.exit(3)

    if not rows:
        print("No results.")
        return
    for i, (qualname, kind, package, path, snippet_txt) in enumerate(rows, 1):
        print(f"{i:>3}. {qualname}  [{kind}]  (pkg: {package})")
        print(f"     {path}")
        if snippet_txt:
            sn = " ".join(snippet_txt.split())
            print("     └─", textwrap.shorten(sn, width=160, placeholder=" … "))
        print()


def main():
    parser = argparse.ArgumentParser(
        prog="envdoc",
        description="Search docstrings from your CURRENT Python environment without importing packages.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_DEFAULT,
        help="Path to SQLite index file (default: %(default)s)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_idx = sub.add_parser("index", help="Index all packages in current environment")
    p_idx.add_argument(
        "--extra",
        type=Path,
        action="append",
        default=[],
        help="Extra source root to include (currently unused)",
    )

    p_s = sub.add_parser("search", help="Full-text search in indexed docstrings")
    p_s.add_argument(
        "query", help='FTS query, e.g. "spectrogram OR mel", "graph NEAR/5 convolution"'
    )
    p_s.add_argument("--limit", type=int, default=50, help="Max results")
    p_s.add_argument(
        "--package", help="Limit to a specific top-level package (e.g., numpy)"
    )

    args = parser.parse_args()

    if args.cmd == "index":
        index_env(args.db, extra_roots=args.extra)
        print("Done.")
    elif args.cmd == "search":
        search_db(args.db, args.query, args.limit, args.package)


if __name__ == "__main__":
    main()
