import importlib, inspect, pkgutil, re, sys, types


def iter_members(mod, prefix, max_depth=3, seen=None):
    if seen is None:
        seen = set()
    if max_depth < 0:
        return
    if mod in seen:
        return
    seen.add(mod)

    # 列出可见成员
    for name in dir(mod):
        if name.startswith("_"):  # 跳过私有符号，减少噪音
            continue
        try:
            obj = getattr(mod, name)
        except Exception:
            continue
        dotted = f"{prefix}.{name}" if prefix else name
        yield dotted, obj

        # 递归进入子模块/子包（尽量只在同一顶级包内）
        if isinstance(obj, types.ModuleType):
            if getattr(obj, "__package__", "").split(".")[0] == prefix.split(".")[0]:
                yield from iter_members(obj, dotted, max_depth - 1, seen)


def doc_of(obj):
    try:
        sig = None
        if (
            inspect.isfunction(obj)
            or inspect.ismethod(obj)
            or inspect.isclass(obj)
            or inspect.isbuiltin(obj)
        ):
            try:
                sig = str(inspect.signature(obj))
            except Exception:
                pass
        doc = inspect.getdoc(obj) or ""
        first = doc.splitlines()[0] if doc else ""
        return sig, first, doc
    except Exception:
        return None, "", ""


def main():
    if len(sys.argv) < 3:
        print("Usage: python docsearch.py <top_module> <regex> [max_depth]")
        print("Example: python docsearch.py matplotlib savefig 3")
        sys.exit(1)

    top, pattern = sys.argv[1], sys.argv[2]
    max_depth = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    rx = re.compile(pattern, re.IGNORECASE)

    mod = importlib.import_module(top)
    hits = []
    for dotted, obj in iter_members(mod, top, max_depth=max_depth):
        sig, first, full = doc_of(obj)
        text = "\n".join(t for t in [dotted, str(sig) if sig else "", first, full] if t)
        if rx.search(text):
            hits.append((dotted, sig, first))

    for dotted, sig, first in sorted(hits):
        sig_str = f"{sig}" if sig else ""
        print(f"- {dotted}{sig_str}  :: {first}")


if __name__ == "__main__":
    main()
