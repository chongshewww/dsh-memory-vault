#!/usr/bin/env python3
"""记忆保险箱 —— 把「人格 + 记忆」打包、校验、还原。

给 DSH 上那些有本子的 AI 用：崩了配置、覆盖了文件夹，还能整条退回来。

用法：
    python 记忆保险箱.py 打包            # 打包到默认位置
    python 记忆保险箱.py 打包 E:\\baks    # 指定放哪儿
    python 记忆保险箱.py 列表            # 看看有哪些包
    python 记忆保险箱.py 校验 xxx.zip    # 检查包完不完整
    python 记忆保险箱.py 还原 xxx.zip    # 把包解回去（先给旧目录留 .bak）

默认会打包这些（存在才打）：
    ~/.dsh/my-life                     自己的本子
    ~/.dsh/browser-sessions/AGENTS.md  工作区人设
    ~/.dsh/personas                    角色卡
    ~/.dsh/.agent-presets              预设
    <profile>/node_modules/dsh-rofm/config.json     归档插件的配置
    <profile>/node_modules/dsh-soul 的配置文件（如果有）
"""

import hashlib
import json
import os
import shutil
import sys
import time
import zipfile

家 = os.path.expanduser("~")
DSH = os.path.join(家, ".dsh")
配置档 = os.path.join(DSH, "profiles", "desktop")
默认输出 = os.path.join(DSH, "记忆保险箱")

要包的 = [
    ("本子", os.path.join(DSH, "my-life")),
    ("人设", os.path.join(DSH, "browser-sessions", "AGENTS.md")),
    ("角色卡", os.path.join(DSH, "personas")),
    ("预设", os.path.join(DSH, ".agent-presets")),
    ("归档配置", os.path.join(配置档, "node_modules", "dsh-rofm", "config.json")),
]
# 目录里这些不打包（缓存、依赖）
跳过 = {"node_modules", "__pycache__", ".git", ".venv", "whisper"}


def 收集():
    清单 = []
    for 名, 路径 in 要包的:
        if not os.path.exists(路径):
            continue
        if os.path.isfile(路径):
            清单.append((名, 路径, None))
        else:
            for 根, 目录们, 文件们 in os.walk(路径):
                目录们[:] = [d for d in 目录们 if d not in 跳过]
                for f in 文件们:
                    p = os.path.join(根, f)
                    相对 = os.path.relpath(p, 路径)
                    清单.append((名, p, 相对))
    return 清单


def sha(路径):
    h = hashlib.sha256()
    with open(路径, "rb") as f:
        for 块 in iter(lambda: f.read(1 << 20), b""):
            h.update(块)
    return h.hexdigest()


def 打包(输出目录=None):
    输出目录 = 输出目录 or 默认输出
    os.makedirs(输出目录, exist_ok=True)
    清单 = 收集()
    if not 清单:
        print("没找到可打包的东西")
        return 1

    名 = time.strftime("记忆-%Y%m%d-%H%M%S.zip")
    包 = os.path.join(输出目录, 名)
    记录 = []
    with zipfile.ZipFile(包, "w", zipfile.ZIP_DEFLATED) as z:
        for 组, 路径, 相对 in 清单:
            arc = 组 if 相对 is None else (组 + "/" + 相对.replace("\\", "/"))
            z.write(路径, arc)
            记录.append({"path": arc, "size": os.path.getsize(路径), "sha256": sha(路径)})
        z.writestr("_manifest.json", json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"),
                                                 "files": 记录}, ensure_ascii=False, indent=2))
    print(f"打好：{包}")
    print(f"文件 {len(记录)} 个，总大小 {os.path.getsize(包)/1e6:.1f} MB")
    return 0


def 校验(包):
    with zipfile.ZipFile(包) as z:
        坏 = z.testzip()
        if 坏:
            print("坏了：", 坏)
            return 1
        man = json.loads(z.read("_manifest.json").decode("utf-8"))
        import hashlib as _h
        不对 = 0
        for f in man["files"]:
            data = z.read(f["path"])
            if _h.sha256(data).hexdigest() != f["sha256"]:
                不对 += 1
                print("对不上：", f["path"])
    print(f"校验完成：{len(man['files'])} 个文件，{不对} 个不对")
    return 0 if 不对 == 0 else 1


def 列表():
    目录 = 默认输出
    if not os.path.isdir(目录):
        print("还没有包")
        return 0
    包们 = sorted(f for f in os.listdir(目录) if f.endswith(".zip"))
    for f in 包们:
        p = os.path.join(目录, f)
        print(f"{f}  {os.path.getsize(p)/1e6:.1f} MB")
    if not 包们:
        print("还没有包")
    return 0


def 还原(包):
    if not os.path.exists(包):
        print("找不到这个包")
        return 1
    备份 = time.strftime("还原前-%Y%m%d-%H%M%S")
    临时 = os.path.join(os.path.dirname(os.path.abspath(包)), 备份)
    os.makedirs(临时, exist_ok=True)

    对应 = {
        "本子": os.path.join(DSH, "my-life"),
        "人设": os.path.join(DSH, "browser-sessions", "AGENTS.md"),
        "角色卡": os.path.join(DSH, "personas"),
        "预设": os.path.join(DSH, ".agent-presets"),
        "归档配置": os.path.join(配置档, "node_modules", "dsh-rofm", "config.json"),
    }
    with zipfile.ZipFile(包) as z:
        名字们 = z.namelist()
        for 组, 目标 in 对应.items():
            有 = [n for n in 名字们 if n == 组 or n.startswith(组 + "/") or n.startswith(组 + "\\")]
            if not 有:
                continue
            # 先把旧的挪走，别直接覆盖
            if os.path.exists(目标):
                shutil.move(目标, os.path.join(临时, 组))
            for n in 有:
                相对 = n[len(组):].lstrip("/\\")
                if not 相对:
                    # 单个文件那一档
                    data = z.read(n)
                    os.makedirs(os.path.dirname(目标), exist_ok=True)
                    open(目标, "wb").write(data)
                    continue
                目的 = os.path.join(目标, 相对)
                os.makedirs(os.path.dirname(目的), exist_ok=True)
                open(目的, "wb").write(z.read(n))
    print("还原完了；旧的东西挪到了：", 临时)
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    命令 = sys.argv[1]
    if 命令 == "打包":
        return 打包(sys.argv[2] if len(sys.argv) > 2 else None)
    if 命令 == "列表":
        return 列表()
    if 命令 == "校验" and len(sys.argv) > 2:
        return 校验(sys.argv[2])
    if 命令 == "还原" and len(sys.argv) > 2:
        return 还原(sys.argv[2])
    print("看不懂这个命令")
    return 1


if __name__ == "__main__":
    sys.exit(main())
