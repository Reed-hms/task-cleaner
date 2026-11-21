#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task-cleaner 三组核心测试：零迁移 / 越界拒绝 / 还原往返。

运行：python scripts/test_registry.py -v
"""

import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry as R  # noqa: E402

REG_FILES = {R.REGISTRY_NAME, R.MD_NAME, R.LOG_NAME, R.PLAN_NAME}


def make_project(base):
    os.makedirs(os.path.join(base, "src"), exist_ok=True)
    os.makedirs(os.path.join(base, "data"), exist_ok=True)
    os.makedirs(os.path.join(base, ".git"), exist_ok=True)
    os.makedirs(os.path.join(base, "logs"), exist_ok=True)
    with open(os.path.join(base, "src", "app.py"), "w", encoding="utf-8") as f:
        f.write("print('hello')\n")
    with open(os.path.join(base, "README.md"), "w", encoding="utf-8") as f:
        f.write("# demo\n")
    with open(os.path.join(base, ".git", "config"), "w", encoding="utf-8") as f:
        f.write("[core]\n")
    with open(os.path.join(base, "logs", "run.log"), "w", encoding="utf-8") as f:
        f.write("log line\n")
    blob = os.path.join(base, "data", "blob.bin")
    with open(blob, "wb") as f:
        f.write(bytes(random.getrandbits(8) for _ in range(4096)))
    return blob


def snapshot(base):
    return R.tree_signature(base, ignore_names=REG_FILES)


class ZeroMigrationTest(unittest.TestCase):
    """登记前后，原有文件的路径/内容/mtime 一字不变。"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="tc-zero-")
        self.blob = make_project(self.root)
        self.reg = os.path.join(self.root, R.REGISTRY_NAME)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_register_does_not_touch_files(self):
        before = snapshot(self.root)
        R.init(self.root)
        R.register(self.reg, "src/app.py", "script", task="t1")
        R.register(self.reg, "data/blob.bin", "data", task="t1")
        R.register(self.reg, "logs/run.log", "log", task="t1")
        after = snapshot(self.root)

        self.assertEqual(before, after, "登记改变了原有文件（零迁移被破坏）")
        self.assertNotIn("src/app.py", {k for k in after if k.startswith(".agent-trash")})

    def test_status_and_plan_do_not_touch_files(self):
        R.init(self.root)
        R.register(self.reg, "logs/run.log", "log", task="t1")
        before = snapshot(self.root)
        R.status([self.reg])
        R.build_plan(self.reg)
        after = snapshot(self.root)
        self.assertEqual(before, after, "status/plan 改变了原有文件")


class BoundaryRejectTest(unittest.TestCase):
    """越界、保护、篡改三类必须拒绝。"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="tc-bound-")
        self.outside = tempfile.mkdtemp(prefix="tc-outside-")
        make_project(self.root)
        self.reg = os.path.join(self.root, R.REGISTRY_NAME)
        R.init(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)

    def test_register_outside_root_rejected(self):
        victim = os.path.join(self.outside, "secret.txt")
        with open(victim, "w", encoding="utf-8") as f:
            f.write("x")
        with self.assertRaises(R.CleanError):
            R.register(self.reg, victim, "data")

    def test_register_system_path_rejected(self):
        with self.assertRaises(R.CleanError):
            R.register(self.reg, os.environ.get("WINDIR", "C:\\Windows"), "data")

    def test_guard_rejects_root_and_parent(self):
        self.assertIsNotNone(R.guard(self.root, self.root))
        self.assertIsNotNone(R.guard(os.path.dirname(self.root), self.root))

    def test_guard_rejects_protected(self):
        self.assertIsNotNone(R.guard(os.path.join(self.root, ".git"), self.root))
        self.assertIsNotNone(R.guard(os.path.join(self.root, ".git", "config"), self.root))
        self.assertIsNotNone(R.guard(os.path.join(self.root, "README.md"), self.root))

    def test_entry_path_traversal_rejected(self):
        forged = {"id": "e-forged", "path": "../escape.txt"}
        with self.assertRaises(R.CleanError):
            R._entry_parts(self.root, forged)

    def test_tampered_plan_rejected(self):
        R.register(self.reg, "logs/run.log", "log", task="t1")
        R.build_plan(self.reg)
        # 篡改登记后计划即失效
        data = R.load_registry(self.reg)
        data["entries"][0]["size"] = 999
        R.save_registry(self.reg, data)
        with self.assertRaises(R.CleanError):
            R.remove(self.reg, ["1"], yes=True)

    def test_remove_requires_yes(self):
        R.register(self.reg, "logs/run.log", "log", task="t1")
        R.build_plan(self.reg)
        with self.assertRaises(R.CleanError):
            R.remove(self.reg, ["1"], yes=False)

    def test_protected_entries_never_candidates(self):
        R.register(self.reg, ".git", "data", task="t1")
        R.register(self.reg, "README.md", "data", task="t1")
        plan = R.build_plan(self.reg)
        paths = {c["path"] for c in plan["candidates"]}
        self.assertNotIn(".git", paths)
        self.assertNotIn("README.md", paths)

    def test_sub_project_cannot_reach_parent(self):
        sub = os.path.join(self.root, "subproj")
        os.makedirs(sub)
        sub_reg = os.path.join(sub, R.REGISTRY_NAME)
        R.init(sub, kind="sub")
        with self.assertRaises(R.CleanError):
            R.register(sub_reg, os.path.join(self.root, "src", "app.py"), "script")
        # 但自己根内的可以
        f = os.path.join(sub, "note.txt")
        with open(f, "w", encoding="utf-8") as h:
            h.write("in sub")
        R.register(sub_reg, f, "temp")
        self.assertEqual(len(R.load_registry(sub_reg)["entries"]), 1)


class RestoreRoundTripTest(unittest.TestCase):
    """删除→还原 往返三次，内容与体积保持一致。"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="tc-restore-")
        make_project(self.root)
        self.reg = os.path.join(self.root, R.REGISTRY_NAME)
        R.init(self.root)
        self.targets = []
        for i in range(3):
            rel = "logs/cache_%d.bin" % i
            p = os.path.join(self.root, rel.replace("/", os.sep))
            with open(p, "wb") as f:
                f.write(bytes(random.getrandbits(8) for _ in range(1024)))
            R.register(self.reg, p, "cache", task="t1")
            self.targets.append((rel, p, R.file_sha256(p)))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_three_roundtrips(self):
        for round_no in range(1, 4):
            plan = R.build_plan(self.reg)
            picks = [str(c["no"]) for c in plan["candidates"]]
            self.assertEqual(len(picks), 3, "候选数不对：%s" % plan["candidates"])

            result = R.remove(self.reg, picks, yes=True)
            self.assertEqual(len(result["moved"]), 3)
            batch = result["batch"]
            self.assertTrue(os.path.isdir(os.path.join(self.root, R.TRASH_NAME, batch)))

            for rel, p, _ in self.targets:
                self.assertFalse(os.path.exists(p), "第 %d 轮：原文件未被移走 %s" % (round_no, rel))

            back = R.restore(self.reg, batch)
            self.assertEqual(len(back["restored"]), 3)
            for rel, p, sha in self.targets:
                self.assertTrue(os.path.exists(p), "第 %d 轮：%s 未还原" % (round_no, rel))
                self.assertEqual(R.file_sha256(p), sha,
                                 "第 %d 轮：%s 内容不一致" % (round_no, rel))

    def test_purge_then_restore_fails(self):
        plan = R.build_plan(self.reg)
        result = R.remove(self.reg, [str(c["no"]) for c in plan["candidates"]], yes=True)
        batch = result["batch"]
        purged = R.purge(self.reg, older_than_days=0, yes=True)
        self.assertIn(batch, purged["purged"])
        self.assertFalse(os.path.isdir(os.path.join(self.root, R.TRASH_NAME, batch)))
        with self.assertRaises(R.CleanError):
            R.restore(self.reg, batch)


class PathAliasTest(unittest.TestCase):
    """项目根用别名写法（软链 / 8.3 短名 / `/var`→`/private/var`）时，
    根内文件仍必须被当作正常内容，不能被误判成越界。"""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="tc-alias-")
        self.root = os.path.join(self.base, "real")
        os.makedirs(self.root)
        make_project(self.root)
        self.alias = os.path.join(self.base, "alias")
        try:
            os.symlink(self.root, self.alias, target_is_directory=True)
        except (OSError, AttributeError, NotImplementedError):
            # Windows 普通账户没有创建符号链接的特权，但目录联接（junction）可以，
            # 效果等价：realpath 会解析到另一套真实路径。
            try:
                import subprocess
                subprocess.run(["cmd", "/c", "mklink", "/J", self.alias, self.root],
                               check=True, capture_output=True)
            except Exception as exc:
                self.skipTest("当前平台不允许创建目录别名：%s" % exc)
        self.alias_reg = os.path.join(self.alias, R.REGISTRY_NAME)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_register_inside_aliased_root(self):
        R.init(self.alias)
        entry = R.register(self.alias_reg, "src/app.py", "script", task="t1")
        # 记录的是相对路径，不能因为根写法不同而写成 "..\..\real\src\app.py"
        self.assertEqual(entry["path"], "src/app.py")

    def test_roundtrip_through_aliased_root(self):
        R.init(self.alias)
        target = os.path.join(self.alias, "logs", "run.log")
        R.register(self.alias_reg, target, "log", task="t1")
        plan = R.build_plan(self.alias_reg)
        picks = [str(c["no"]) for c in plan["candidates"]]
        self.assertEqual(len(picks), 1, "别名根下应正常生成候选：%s" % plan)

        result = R.remove(self.alias_reg, picks, yes=True)
        self.assertEqual(len(result["moved"]), 1)
        self.assertFalse(os.path.exists(target), "原文件未被移走")

        back = R.restore(self.alias_reg, result["batch"])
        self.assertEqual(len(back["restored"]), 1)
        self.assertTrue(os.path.exists(target), "文件未还原")


if __name__ == "__main__":
    unittest.main(verbosity=2)
