#!/usr/bin/env python3
import argparse
import subprocess
from collections import defaultdict
import os


def run_git_command(repo_path, cmd):
    """Run git command inside target repo"""
    result = subprocess.run(
        cmd, cwd=repo_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        print("Git命令执行失败：", result.stderr)
        exit(1)
    return result.stdout.splitlines()


def should_skip_file(file_path, excluded_dirs):
    """Check if file is in excluded directory"""
    for ex in excluded_dirs:
        if file_path.startswith(ex.rstrip("/") + "/"):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Git贡献统计（按邮箱）")
    parser.add_argument("repo", help="目标仓库路径")
    parser.add_argument(
        "--exclude", nargs="*", default=[], help="排除的目录（相对仓库路径，可多个）"
    )
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    excluded_dirs = args.exclude

    print(f"统计仓库: {repo_path}")
    if excluded_dirs:
        print(f"排除目录: {excluded_dirs}")

    # Use email for author identity
    git_log = run_git_command(
        repo_path, ["git", "log", "--numstat", "--pretty=format:email:%ae"]
    )

    stats = defaultdict(lambda: {"add": 0, "del": 0, "net": 0})
    current_email = None

    for line in git_log:
        if line.startswith("email:"):
            current_email = line[6:].strip().lower()
            continue

        parts = line.split("\t")
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            add, delete, file_path = parts
            add, delete = int(add), int(delete)

            # skip excluded folders
            if should_skip_file(file_path, excluded_dirs):
                continue

            s = stats[current_email]
            s["add"] += add
            s["del"] += delete
            s["net"] = s["add"] - s["del"]

    ranking = sorted(stats.items(), key=lambda x: x[1]["net"], reverse=True)

    print("\nGit贡献统计（按净增行数排序）:\n")
    print(f"{'邮箱':<35}{'添加行':>10}{'删除行':>10}{'净增':>10}")
    print("-" * 70)

    for email, s in ranking:
        print(f"{email:<35}{s['add']:>10}{s['del']:>10}{s['net']:>10}")

    print("\n统计完成！")


if __name__ == "__main__":
    main()
