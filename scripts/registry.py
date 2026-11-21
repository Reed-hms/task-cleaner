#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task-cleaner · registry.py

旁路登记 + 用户勾选清理。三条铁律：
  1. 零迁移  —— 登记不移动、不改名、不改任何原有文件
  2. 零自动  —— 只有用户下达"删除/清理"指令才动作
  3. 全局只读 —— 环境/连接器/技能目录永不删；仅 pip/npm/浏览器缓存走独立入口

纯标准库，Python 3.8+。既可 CLI 调用，也可 import 后按函数调用（测试用）。
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timedelta

REGISTRY_NAME = "agent-registry.json"
MD_NAME = "agent-registry.md"
LOG_NAME = "agent-registry.log"
PLAN_NAME = "agent-registry.plan.json"
TRASH_NAME = ".agent-trash"
SCHEMA = "agent-registry/1"
DEFAULT_RETENTION_DAYS = 30

KINDS = ("artifact", "script", "data", "temp", "dependency", "cache", "log", "config")
CANDIDATE_KINDS = ("temp", "script", "cache", "log")
PROTECTED_NAMES = {".git", ".svn", ".hg", ".vscode", ".idea", ".agent-trash"}
PROTECTED_FILES = {
    "requirements.txt", "package.json", "package-lock.json", "pyproject.toml",
    "setup.py", "setup.cfg", "readme.md", "readme.txt", ".gitignore",
    ".gitattributes", REGISTRY_NAME, MD_NAME,
}
SKIP_WALK_DIRS = {".git", ".svn", ".hg", ".agent-trash", "node_modules", ".venv",
                  "venv", "__pycache__", ".idea"}


class CleanError(Exception):
    """被拒绝或被阻断的操作；CLI 捕获后以退出码 2 结束。"""


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def _now():
    return datetime.now().astimezone()


def _iso(dt=None):
    return (dt or _now()).isoformat(timespec="seconds")


def _parse_iso(text):
    return datetime.fromisoformat(text)


def human_size(n):
    n = float(n or 0)
    if n < 1024:
        return "%d B" % int(n)
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024 or unit == "TB":
            return "%.1f %s" % (n, unit)


def norm(p):
    return os.path.normcase(os.path.abspath(p))


def is_within(child, parent):
    c, p = norm(child), norm(parent)
    if c == p:
        return True
    try:
        return os.path.commonpath([c, p]) == p
    except (ValueError, AttributeError):
        return False


def is_link(p):
    try:
        if os.path.islink(p):
            return True
    except OSError:
        pass
    isj = getattr(os.path, "isjunction", None)
    if isj:
        try:
            return bool(isj(p))
        except OSError:
            return False
    return False


def has_link_component(path, root):
    """检查 path 自身及其到 root 之间的每一层是否是符号链接/联接点。"""
    p = os.path.abspath(path)
    while norm(p) != norm(root) and is_within(p, root):
        if is_link(p):
            return True
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return False


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def measure(path):
    """返回 (字节数, 文件数)。目录递归，跳过符号链接与受保护目录。"""
    path = os.path.abspath(path)
    if os.path.isfile(path):
        try:
            return os.path.getsize(path), 1
        except OSError:
            return 0, 0
    total, count = 0, 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames
                       if d.lower() not in SKIP_WALK_DIRS and not is_link(os.path.join(dirpath, d))]
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            try:
                if is_link(fp):
                    continue
                total += os.path.getsize(fp)
                count += 1
            except OSError:
                continue
    return total, count


def tree_signature(root, ignore_names=()):
    """(相对路径 -> (大小, sha256, mtime)) 快照，用于零迁移断言。"""
    ignore = {n.lower() for n in ignore_names}
    sig = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in ignore]
        for fn in filenames:
            if fn.lower() in ignore:
                continue
            fp = os.path.join(dirpath, fn)
            try:
                st = os.stat(fp)
                sig[os.path.relpath(fp, root).replace(os.sep, "/")] = (
                    st.st_size, file_sha256(fp), int(st.st_mtime))
            except OSError:
                sig[os.path.relpath(fp, root).replace(os.sep, "/")] = ("ERROR",)
    return sig


# --------------------------------------------------------------------------
# 安全护栏
# --------------------------------------------------------------------------

def guard(path, root):
    """返回拒绝原因字符串；None 表示允许操作。"""
    ap = os.path.abspath(path)
    real = os.path.realpath(ap)
    if not is_within(real, root):
        return "路径不在本项目根内（越界拒绝）：%s" % real
    if norm(real) == norm(root):
        return "项目根目录本身不允许删除"
    if is_within(real, os.path.join(root, TRASH_NAME)):
        return "回收站内的内容不允许再次清理"
    if has_link_component(ap, root):
        return "路径含符号链接/联接点，拒绝递归（只允许手动断链）"
    parts = os.path.relpath(real, root).split(os.sep)
    for part in parts:
        if part.lower() in PROTECTED_NAMES:
            return "位于受保护目录：%s" % part
    base = parts[-1].lower()
    if base in PROTECTED_FILES:
        return "受保护文件：%s" % parts[-1]
    return None


def _entry_parts(root, entry):
    """把登记里的相对路径还原成绝对路径（拒绝穿越）。"""
    rel = entry["path"]
    if os.path.isabs(rel):
        raise CleanError("登记中存在绝对路径，拒绝处理：%s" % rel)
    abs_path = os.path.abspath(os.path.join(root, rel.replace("/", os.sep)))
    if not is_within(abs_path, root):
        raise CleanError("登记路径越界（疑似被篡改）：%s" % rel)
    return abs_path


# --------------------------------------------------------------------------
# 登记文件读写
# --------------------------------------------------------------------------

def find_registry(start):
    p = os.path.abspath(start)
    if os.path.isfile(p) or (not os.path.isdir(p) and os.path.splitext(p)[1]):
        p = os.path.dirname(p)
    while True:
        cand = os.path.join(p, REGISTRY_NAME)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def iter_registries(base):
    found = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d.lower() not in SKIP_WALK_DIRS and not is_link(os.path.join(dirpath, d))]
        if REGISTRY_NAME in filenames:
            found.append(os.path.join(dirpath, REGISTRY_NAME))
    return found


def load_registry(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema") != SCHEMA:
        raise CleanError("登记文件版本不匹配：%s" % path)
    data.setdefault("tasks", [])
    data.setdefault("entries", [])
    data.setdefault("batches", [])
    data.setdefault("project_root", os.path.dirname(os.path.abspath(path)))
    return data


def registry_hash(data):
    payload = [[e.get("id"), e.get("path"), e.get("status"), e.get("size")]
               for e in data.get("entries", [])]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def save_registry(path, data):
    data["updated_at"] = _iso()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
    os.replace(tmp, path)
    render_md(path, data)


def render_md(path, data):
    root = os.path.abspath(data["project_root"])
    lines = ["# 任务登记清单 · %s" % os.path.basename(root), "",
             "更新于 %s　｜　登记文件：`%s`" % (data.get("updated_at", "-"), REGISTRY_NAME), ""]
    lines += ["## 按任务", "",
              "| 任务 | 状态 | 条目 | 体积 |", "|---|---|---|---|"]
    total_by_task = {}
    count_by_task = {}
    for e in data["entries"]:
        t = e.get("task", "-")
        total_by_task[t] = total_by_task.get(t, 0) + int(e.get("size") or 0)
        count_by_task[t] = count_by_task.get(t, 0) + 1
    tasks = {t["id"]: t for t in data["tasks"]}
    for tid, size in sorted(total_by_task.items(), key=lambda kv: -kv[1]):
        t = tasks.get(tid, {})
        title = t.get("title", "") or ""
        label = tid if title in ("", tid) else "%s %s" % (tid, title)
        lines.append("| %s | %s | %d | %s |" % (
            label, t.get("status", "-"),
            count_by_task.get(tid, 0), human_size(size)))
    if not total_by_task:
        lines.append("| （暂无登记） | - | 0 | 0 B |")

    lines += ["", "## 明细", "",
              "| 编号 | 任务 | 类型 | 路径 | 体积 | 状态 | 备注 |",
              "|---|---|---|---|---|---|---|"]
    for e in sorted(data["entries"], key=lambda x: (x.get("kind", ""), x.get("path", ""))):
        lines.append("| %s | %s | %s | `%s` | %s | %s | %s |" % (
            e.get("id"), e.get("task", "-"), e.get("kind", "-"), e.get("path", "-"),
            human_size(e.get("size")), e.get("status", "ok"), e.get("note", "") or ""))
    if not data["entries"]:
        lines.append("| - | - | - | - | - | - | - |")

    active = [b for b in data["batches"] if not b.get("purged")]
    if active:
        lines += ["", "## 回收站批次", "",
                  "| 批次 | 建立时间 | 到期时间 | 条目数 |", "|---|---|---|---|"]
        for b in active:
            lines.append("| %s | %s | %s | %d |" % (
                b["id"], b.get("created_at", "-"), b.get("expires_at", "-"),
                len(b.get("entries", []))))
    with open(path.replace(REGISTRY_NAME, MD_NAME), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _append_log(registry_path, record):
    rec = dict(record)
    rec["at"] = _iso()
    with open(os.path.join(os.path.dirname(registry_path), LOG_NAME), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _resolve(args):
    if getattr(args, "registry", None):
        p = os.path.abspath(args.registry)
        if not os.path.isfile(p):
            raise CleanError("指定的登记文件不存在：%s" % p)
        return p
    start = getattr(args, "root", None) or os.getcwd()
    p = find_registry(start)
    if not p:
        raise CleanError("未找到 %s，请先执行：task-cleaner init --root <项目目录>" % REGISTRY_NAME)
    return p


# --------------------------------------------------------------------------
# 核心动作（可被 import 调用）
# --------------------------------------------------------------------------

def init(root, kind="root", force=False):
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise CleanError("目录不存在：%s" % root)
    path = os.path.join(root, REGISTRY_NAME)
    if os.path.exists(path) and not force:
        raise CleanError("登记文件已存在（如需重建请加 --force）：%s" % path)
    data = {"schema": SCHEMA, "type": kind, "project_root": root,
            "updated_at": _iso(), "tasks": [], "entries": [], "batches": []}
    save_registry(path, data)
    _append_log(path, {"op": "init", "kind": kind, "root": root})
    return {"registry": path, "root": root, "type": kind}


def register(registry_path, path, kind, task=None, title=None,
             protected=False, note=""):
    if kind not in KINDS:
        raise CleanError("kind 必须是：%s" % ", ".join(KINDS))
    data = load_registry(registry_path)
    root = os.path.abspath(data["project_root"])
    target = os.path.abspath(path if os.path.isabs(path) else os.path.join(root, path))
    if not os.path.exists(target):
        raise CleanError("路径不存在：%s" % target)
    if not is_within(os.path.realpath(target), root):
        raise CleanError("拒绝登记项目根之外的路径（全局项只做统计）：%s" % target)
    rel = os.path.relpath(target, root).replace(os.sep, "/")
    if rel.startswith(".."):
        raise CleanError("拒绝登记越界路径：%s" % rel)

    base = os.path.basename(target).lower()
    auto_protected = base in PROTECTED_NAMES or base in PROTECTED_FILES
    protected = bool(protected or auto_protected)

    size, files = measure(target)
    try:
        mtime = _iso(datetime.fromtimestamp(os.path.getmtime(target)).astimezone())
    except OSError:
        mtime = _iso()

    task_id = task or "t-untracked"
    if task and task not in [t["id"] for t in data["tasks"]]:
        data["tasks"].append({"id": task, "title": title or task,
                              "status": "done", "created_at": _iso()})

    eid = "e" + hashlib.sha1(rel.encode("utf-8")).hexdigest()[:8]
    prev = next((e for e in data["entries"] if e["path"] == rel), None)
    # 同一路径被不同任务登记过 → 视为共享，候选表里建议保留
    shared = bool(prev and prev.get("task") != task_id)
    entry = {"id": eid, "task": task_id, "path": rel, "kind": kind,
             "size": size, "files": files, "mtime": mtime,
             "protected": protected, "shared": shared, "note": note,
             "status": "ok", "registered_at": _iso()}
    data["entries"] = [e for e in data["entries"] if e["path"] != rel]
    data["entries"].append(entry)
    save_registry(registry_path, data)
    _append_log(registry_path, {"op": "register", "id": eid, "path": rel, "kind": kind})
    return entry


def build_plan(registry_path, include_artifacts=False, scope="project"):
    data = load_registry(registry_path)
    root = os.path.abspath(data["project_root"])
    cand, prot, missing = [], [], []
    for e in data["entries"]:
        if e.get("status") not in (None, "ok"):
            continue
        try:
            p = _entry_parts(root, e)
        except CleanError:
            missing.append(e)
            continue
        if not os.path.exists(p):
            missing.append(e)
            continue
        if e.get("protected") or e.get("shared"):
            prot.append(e)
            continue
        kind = e.get("kind")
        if kind == "artifact" and not include_artifacts:
            prot.append(e)
            continue
        if kind in CANDIDATE_KINDS:
            cand.append(e)
        elif kind == "dependency":
            cand.append(e)
        else:
            prot.append(e)

    cand.sort(key=lambda x: (x.get("kind", ""), x.get("path", "")))
    numbers = {}
    table = []
    for i, e in enumerate(cand, 1):
        numbers[str(i)] = e["id"]
        risk = "无"
        if e["kind"] == "dependency":
            risk = "删除后需重装（下载/编译耗时）"
        elif e["kind"] == "cache":
            risk = "可重建，下次运行会重新生成"
        table.append({"no": i, "id": e["id"], "kind": e["kind"], "path": e["path"],
                      "size": e.get("size"), "size_h": human_size(e.get("size")),
                      "risk": risk})

    plan = {"created_at": _iso(), "registry": registry_path,
            "registry_hash": registry_hash(data), "root": root,
            "include_artifacts": bool(include_artifacts),
            "numbers": numbers, "candidates": table,
            "protected": [e["path"] for e in prot],
            "missing": [e["path"] for e in missing]}
    with open(os.path.join(root, PLAN_NAME), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    return plan


def remove(registry_path, picks, yes=False, force=False):
    if not yes:
        raise CleanError("真实移动必须显式确认（--yes）")
    data = load_registry(registry_path)
    root = os.path.abspath(data["project_root"])
    plan_path = os.path.join(root, PLAN_NAME)
    if not os.path.isfile(plan_path):
        raise CleanError("没有可用的清理计划，请先执行 plan")
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    if plan.get("registry") != registry_path or plan.get("registry_hash") != registry_hash(data):
        raise CleanError("登记内容已变化，请重新执行 plan 再勾选")

    picked = []
    for n in picks:
        eid = plan["numbers"].get(str(n))
        if not eid:
            raise CleanError("编号不存在：%s" % n)
        picked.append(eid)

    entries = {e["id"]: e for e in data["entries"]}
    batch_id = "b-" + time.strftime("%Y%m%d-%H%M%S") + "-%02d" % (len(data["batches"]) + 1)
    batch_dir = os.path.join(root, TRASH_NAME, batch_id)
    moved, skipped = [], []
    total = 0

    for eid in picked:
        entry = entries.get(eid)
        if not entry:
            skipped.append({"id": eid, "reason": "登记中不存在"})
            continue
        if entry.get("status") != "ok":
            skipped.append({"id": eid, "reason": "状态为 %s" % entry.get("status")})
            continue
        p = _entry_parts(root, entry)
        reason = guard(p, root)
        if reason:
            skipped.append({"id": eid, "path": entry["path"], "reason": reason})
            continue
        if not os.path.exists(p):
            skipped.append({"id": eid, "path": entry["path"], "reason": "路径已不存在"})
            continue
        size, _ = measure(p)
        if size > 2 * 1024 ** 3 and not force:
            skipped.append({"id": eid, "path": entry["path"],
                            "reason": "超过 2 GB，需 --force 二次确认"})
            continue
        dst = os.path.join(batch_dir, entry["path"].replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            skipped.append({"id": eid, "path": entry["path"], "reason": "回收站目标已存在"})
            continue
        try:
            os.rename(p, dst)
        except OSError as exc:
            skipped.append({"id": eid, "path": entry["path"], "reason": "移动失败：%s" % exc})
            continue
        entry["status"] = "trashed"
        entry["batch"] = batch_id
        moved.append({"id": eid, "path": entry["path"], "size": size})
        total += size

    if not moved:
        if os.path.isdir(batch_dir) and not os.listdir(batch_dir):
            os.rmdir(batch_dir)
        raise CleanError("没有成功移动任何条目：%s" % json.dumps(skipped, ensure_ascii=False))

    now = _now()
    data["batches"].append({
        "id": batch_id, "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(days=DEFAULT_RETENTION_DAYS)),
        "entries": [m["id"] for m in moved], "purged": False, "restored": False})
    save_registry(registry_path, data)
    _append_log(registry_path, {"op": "remove", "batch": batch_id,
                                "moved": len(moved), "bytes": total})
    try:
        os.remove(plan_path)
    except OSError:
        pass
    return {"batch": batch_id, "moved": moved, "skipped": skipped, "bytes": total}


def restore(registry_path, batch_id):
    data = load_registry(registry_path)
    root = os.path.abspath(data["project_root"])
    batch = next((b for b in data["batches"] if b["id"] == batch_id), None)
    if not batch:
        raise CleanError("批次不存在：%s" % batch_id)
    if batch.get("purged"):
        raise CleanError("批次已被彻底删除，无法还原：%s" % batch_id)
    batch_dir = os.path.join(root, TRASH_NAME, batch_id)
    entries = {e["id"]: e for e in data["entries"]}
    restored, skipped = [], []
    for eid in batch["entries"]:
        entry = entries.get(eid)
        if not entry:
            skipped.append({"id": eid, "reason": "登记中不存在"})
            continue
        src = os.path.join(batch_dir, entry["path"].replace("/", os.sep))
        dst = _entry_parts(root, entry)
        if not os.path.exists(src):
            skipped.append({"id": eid, "reason": "回收站中已无该文件"})
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            conflict = dst + ".conflict-" + time.strftime("%Y%m%d%H%M%S")
            os.rename(dst, conflict)
        try:
            os.rename(src, dst)
        except OSError as exc:
            skipped.append({"id": eid, "reason": "还原失败：%s" % exc})
            continue
        entry["status"] = "ok"
        entry.pop("batch", None)
        restored.append({"id": eid, "path": entry["path"]})
    if restored:
        batch["restored"] = True
        save_registry(registry_path, data)
        _append_log(registry_path, {"op": "restore", "batch": batch_id, "n": len(restored)})
    return {"batch": batch_id, "restored": restored, "skipped": skipped}


def purge(registry_path, older_than_days=DEFAULT_RETENTION_DAYS, yes=False, force=False):
    if not yes:
        raise CleanError("彻底删除必须显式确认（--yes）")
    data = load_registry(registry_path)
    root = os.path.abspath(data["project_root"])
    trash_root = os.path.join(root, TRASH_NAME)
    now = _now()
    cutoff = now - timedelta(days=older_than_days)
    purged = []
    for batch in data["batches"]:
        if batch.get("purged"):
            continue
        expires = _parse_iso(batch["expires_at"])
        if not force and expires > now and _parse_iso(batch["created_at"]) > cutoff:
            continue
        batch_dir = os.path.join(trash_root, batch["id"])
        if not is_within(batch_dir, trash_root):
            raise CleanError("批次路径越界，拒绝删除：%s" % batch_dir)
        if os.path.isdir(batch_dir):
            shutil.rmtree(batch_dir, ignore_errors=True)
        batch["purged"] = True
        for eid in batch["entries"]:
            entry = next((e for e in data["entries"] if e["id"] == eid), None)
            if entry and entry.get("status") == "trashed":
                entry["status"] = "purged"
        purged.append(batch["id"])
    if purged:
        save_registry(registry_path, data)
        _append_log(registry_path, {"op": "purge", "batches": purged})
    if os.path.isdir(trash_root) and not os.listdir(trash_root):
        try:
            os.rmdir(trash_root)
        except OSError:
            pass
    return {"purged": purged}


def status(registry_paths, include_global=True):
    out = {"projects": [], "totals": {}, "global_caches": []}
    totals = {}
    for rp in registry_paths:
        data = load_registry(rp)
        root = os.path.abspath(data["project_root"])
        by_kind = {}
        for e in data["entries"]:
            if e.get("status") in ("purged",):
                continue
            k = e.get("kind", "-")
            by_kind[k] = by_kind.get(k, 0) + int(e.get("size") or 0)
            totals[k] = totals.get(k, 0) + int(e.get("size") or 0)
        trash = os.path.join(root, TRASH_NAME)
        trash_size = measure(trash)[0] if os.path.isdir(trash) else 0
        expired = [b["id"] for b in data["batches"]
                   if not b.get("purged") and _parse_iso(b["expires_at"]) <= _now()]
        out["projects"].append({
            "registry": rp, "root": root, "type": data.get("type", "-"),
            "entries": len(data["entries"]), "by_kind": by_kind,
            "trash_bytes": trash_size, "trash_batches": len([b for b in data["batches"] if not b.get("purged")]),
            "expired_batches": expired})
    out["totals"] = totals
    out["totals"]["trash"] = sum(p["trash_bytes"] for p in out["projects"])
    if include_global:
        out["global_caches"] = global_candidates()
    return out


def global_candidates():
    """D 组：只含可重建的下载缓存；环境/连接器/技能目录不在此列。"""
    items = []
    local = os.environ.get("LOCALAPPDATA", "")
    roam = os.environ.get("APPDATA", "")
    cands = [
        ("pip 缓存", os.path.join(local, "pip", "Cache")),
        ("npm 缓存(Local)", os.path.join(local, "npm-cache")),
        ("npm 缓存(Roaming)", os.path.join(roam, "npm-cache")),
    ]
    for label, path in cands:
        if not path:
            continue
        if os.path.isdir(path):
            size, files = measure(path)
            items.append({"label": label, "path": path, "size": size,
                          "size_h": human_size(size), "files": files,
                          "safe": True})
    return items


def gclean(picks, yes=False):
    if not yes:
        raise CleanError("清理全局缓存必须显式确认（--yes）")
    items = global_candidates()
    if not items:
        raise CleanError("未发现可清理的全局缓存")
    picked = []
    for n in picks:
        idx = int(n) - 1
        if idx < 0 or idx >= len(items):
            raise CleanError("编号不存在：%s" % n)
        picked.append(items[idx])
    started = _now()
    batch = "gb-" + started.strftime("%Y%m%d-%H%M%S")
    moved = []
    for item in picked:
        path = item["path"]
        trash_dir = os.path.join(path, ".housekeeper-trash", batch)
        os.makedirs(trash_dir, exist_ok=True)
        for name in sorted(os.listdir(path)):
            if name in (".housekeeper-trash",):
                continue
            src = os.path.join(path, name)
            dst = os.path.join(trash_dir, name)
            if os.path.exists(dst):
                continue
            try:
                os.rename(src, dst)
                moved.append({"cache": item["label"], "name": name})
            except OSError as exc:
                moved.append({"cache": item["label"], "name": name,
                              "error": str(exc)})
        ledger_path = os.path.join(path, ".housekeeper-trash", "ledger.json")
        ledger = {"batches": []}
        if os.path.isfile(ledger_path):
            with open(ledger_path, "r", encoding="utf-8") as f:
                ledger = json.load(f)
        ledger["batches"].append({
            "id": batch, "created_at": _iso(started),
            "expires_at": _iso(started + timedelta(days=DEFAULT_RETENTION_DAYS)),
            "cache": item["label"], "path": path, "purged": False})
        with open(ledger_path, "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False, indent=2)
    return {"batch": batch, "moved": moved}


def gpurge(older_than_days=DEFAULT_RETENTION_DAYS, yes=False, force=False):
    if not yes:
        raise CleanError("彻底删除必须显式确认（--yes）")
    now = _now()
    purged = []
    for item in global_candidates():
        trash_root = os.path.join(item["path"], ".housekeeper-trash")
        ledger_path = os.path.join(trash_root, "ledger.json")
        if not os.path.isfile(ledger_path):
            continue
        with open(ledger_path, "r", encoding="utf-8") as f:
            ledger = json.load(f)
        for batch in ledger.get("batches", []):
            if batch.get("purged"):
                continue
            if not force and _parse_iso(batch["expires_at"]) > now:
                continue
            batch_dir = os.path.join(trash_root, batch["id"])
            if is_within(batch_dir, trash_root) and os.path.isdir(batch_dir):
                shutil.rmtree(batch_dir, ignore_errors=True)
            batch["purged"] = True
            purged.append("%s/%s" % (item["label"], batch["id"]))
        with open(ledger_path, "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False, indent=2)
    return {"purged": purged}


def doctor(registry_paths):
    issues = []
    for rp in registry_paths:
        data = load_registry(rp)
        root = os.path.abspath(data["project_root"])
        for e in data["entries"]:
            if e.get("status") != "ok":
                continue
            try:
                p = _entry_parts(root, e)
            except CleanError as exc:
                issues.append({"registry": rp, "level": "error", "msg": str(exc)})
                continue
            if not os.path.exists(p):
                issues.append({"registry": rp, "level": "warn",
                               "msg": "登记条目已不存在：%s" % e["path"]})
        for b in data["batches"]:
            if b.get("purged"):
                continue
            if _parse_iso(b["expires_at"]) <= _now():
                issues.append({"registry": rp, "level": "info",
                               "msg": "批次已过期，可 purge：%s" % b["id"]})
        plan_path = os.path.join(root, PLAN_NAME)
        if os.path.isfile(plan_path):
            with open(plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
            if plan.get("registry_hash") != registry_hash(data):
                issues.append({"registry": rp, "level": "info",
                               "msg": "清理计划已过期（登记有变化），建议重新 plan"})
    return issues


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

def print_plan(plan):
    print("[候选] 编号  类型        体积       最近使用   路径")
    if not plan["candidates"]:
        print("      （无可清理条目）")
    for row in plan["candidates"]:
        print("  %-4d %-10s %-11s %-10s %s" % (
            row["no"], row["kind"], row["size_h"], "-", row["path"]))
        if row["risk"] != "无":
            print("       └ 风险：%s" % row["risk"])
    if plan.get("protected"):
        print("[保护] " + "  ".join(plan["protected"]))
    if plan.get("missing"):
        print("[失效] " + "  ".join(plan["missing"]))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="task-cleaner",
                                     description="旁路登记 + 用户勾选清理（零迁移/零自动/全局默认只读）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="建立登记文件（不动任何其他东西）")
    p_init.add_argument("--root", default=None)
    p_init.add_argument("--type", default="root", choices=["root", "sub"])
    p_init.add_argument("--force", action="store_true")

    p_reg = sub.add_parser("register", help="登记一个路径")
    p_reg.add_argument("--path", required=True)
    p_reg.add_argument("--kind", required=True, choices=list(KINDS))
    p_reg.add_argument("--task", default=None)
    p_reg.add_argument("--title", default=None)
    p_reg.add_argument("--note", default="")
    p_reg.add_argument("--protected", action="store_true")
    p_reg.add_argument("--registry", default=None)
    p_reg.add_argument("--root", default=None)

    p_status = sub.add_parser("status", help="体积看板")
    p_status.add_argument("--root", default=None)
    p_status.add_argument("--registry", default=None)
    p_status.add_argument("--all", action="store_true")
    p_status.add_argument("--no-global", action="store_true")

    p_list = sub.add_parser("list", help="列出登记条目")
    p_list.add_argument("--root", default=None)
    p_list.add_argument("--registry", default=None)
    p_list.add_argument("--task", default=None)
    p_list.add_argument("--kind", default=None)

    p_plan = sub.add_parser("plan", help="生成清理候选表（不改文件）")
    p_plan.add_argument("--root", default=None)
    p_plan.add_argument("--registry", default=None)
    p_plan.add_argument("--include-artifacts", action="store_true")

    p_rm = sub.add_parser("remove", help="按勾选移入回收站")
    p_rm.add_argument("--pick", required=True)
    p_rm.add_argument("--yes", action="store_true")
    p_rm.add_argument("--force", action="store_true")
    p_rm.add_argument("--registry", default=None)
    p_rm.add_argument("--root", default=None)

    p_restore = sub.add_parser("restore", help="还原批次")
    p_restore.add_argument("batch")
    p_restore.add_argument("--registry", default=None)
    p_restore.add_argument("--root", default=None)

    p_purge = sub.add_parser("purge", help="彻底删除过期批次")
    p_purge.add_argument("--older-than", type=int, default=DEFAULT_RETENTION_DAYS)
    p_purge.add_argument("--yes", action="store_true")
    p_purge.add_argument("--force", action="store_true")
    p_purge.add_argument("--registry", default=None)
    p_purge.add_argument("--root", default=None)

    p_doctor = sub.add_parser("doctor", help="一致性自检")
    p_doctor.add_argument("--root", default=None)
    p_doctor.add_argument("--registry", default=None)
    p_doctor.add_argument("--all", action="store_true")

    p_gplan = sub.add_parser("gplan", help="列出全局可重建缓存（只读）")
    p_gclean = sub.add_parser("gclean", help="把全局缓存同盘移入回收站")
    p_gclean.add_argument("--pick", required=True)
    p_gclean.add_argument("--yes", action="store_true")
    p_gpurge = sub.add_parser("gpurge", help="彻底删除全局缓存回收批次")
    p_gpurge.add_argument("--older-than", type=int, default=DEFAULT_RETENTION_DAYS)
    p_gpurge.add_argument("--yes", action="store_true")
    p_gpurge.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "init":
            result = init(args.root or os.getcwd(), args.type, args.force)
        elif args.cmd == "register":
            rp = _resolve(args)
            result = register(rp, args.path, args.kind, args.task,
                              args.title, args.protected, args.note)
        elif args.cmd == "status":
            if args.all:
                base = os.path.abspath(args.root or os.getcwd())
                regs = iter_registries(base)
            else:
                regs = [_resolve(args)]
            result = status(regs, include_global=not args.no_global)
        elif args.cmd == "list":
            data = load_registry(_resolve(args))
            rows = [e for e in data["entries"]
                    if (not args.task or e.get("task") == args.task)
                    and (not args.kind or e.get("kind") == args.kind)]
            result = {"root": data["project_root"], "entries": rows}
        elif args.cmd == "plan":
            result = build_plan(_resolve(args), args.include_artifacts)
        elif args.cmd == "remove":
            picks = [x.strip() for x in args.pick.split(",") if x.strip()]
            result = remove(_resolve(args), picks, args.yes, args.force)
        elif args.cmd == "restore":
            result = restore(_resolve(args), args.batch)
        elif args.cmd == "purge":
            result = purge(_resolve(args), args.older_than, args.yes, args.force)
        elif args.cmd == "doctor":
            if args.all:
                regs = iter_registries(os.path.abspath(args.root or os.getcwd()))
            else:
                regs = [_resolve(args)]
            result = doctor(regs)
        elif args.cmd == "gplan":
            result = {"candidates": global_candidates()}
        elif args.cmd == "gclean":
            result = gclean([x.strip() for x in args.pick.split(",") if x.strip()], args.yes)
        elif args.cmd == "gpurge":
            result = gpurge(args.older_than, args.yes, args.force)
        else:
            raise CleanError("未知命令：%s" % args.cmd)
    except CleanError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print("[拒绝] %s" % exc)
        return 2

    if args.json:
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "plan":
        print_plan(result)
    elif args.cmd == "status":
        for proj in result["projects"]:
            print("项目 %s（%s）" % (proj["root"], proj["type"]))
            print("  登记 %d 条  回收站 %s / %d 批" % (
                proj["entries"], human_size(proj["trash_bytes"]), proj["trash_batches"]))
            for k, v in sorted(proj["by_kind"].items(), key=lambda kv: -kv[1]):
                print("    %-10s %s" % (k, human_size(v)))
            if proj["expired_batches"]:
                print("  ⚠ 已过期批次（可 purge）：%s" % ", ".join(proj["expired_batches"]))
        if result.get("global_caches"):
            print("全局可重建缓存（只读统计，需 gplan/gclean 单独处理）：")
            for i, item in enumerate(result["global_caches"], 1):
                print("  %d) %-18s %-10s %s" % (i, item["label"], item["size_h"], item["path"]))
    elif args.cmd == "gplan":
        if not result["candidates"]:
            print("未发现可清理的全局缓存")
        for i, item in enumerate(result["candidates"], 1):
            print("  %d) %-18s %-10s %s" % (i, item["label"], item["size_h"], item["path"]))
        print("提示：gclean --pick 1 --yes  # 同盘移入回收站，30 天可还原")
    elif args.cmd == "list":
        for e in result["entries"]:
            print("%-10s %-10s %-10s %s" % (e["id"], e["kind"], e["status"], e["path"]))
        print("共 %d 条" % len(result["entries"]))
    elif args.cmd == "doctor":
        if not result:
            print("未发现问题")
        for issue in result:
            print("[%s] %s" % (issue["level"], issue["msg"]))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
