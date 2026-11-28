"""Command-line startup and existing interactive maintenance workflow."""

import argparse
import os
import socket
import sys

from pdf2zh_server.application import ServerApplication
from pdf2zh_server.configuration.migration import prepare_config_files
from pdf2zh_server.environment.discovery import (
    ENGINE_ENV_NAMES,
    find_existing_environment,
    format_versions,
    pdf2zh_next_meets_minimum,
    read_versions,
)
from pdf2zh_server.paths import ServerPaths
from pdf2zh_server.source_update import (
    check_for_updates,
    fetch_and_show_notices,
    perform_update_optimized,
)

pdf2zh_next = "pdf2zh_next"
venv = "venv"
PORT = 8890
default_env_tool = "auto"
enable_venv = True
paths = ServerPaths()
root_path = str(paths.root)
output_folder = str(paths.output)
config_path = paths.config_paths
venv_name = ENGINE_ENV_NAMES.copy()
update_log = "自定义中转新增明确入口、保存状态和一键选用；翻译任务独立配置与文件；拒绝截断响应；隔离正文与术语中转及缓存。请同时更新插件和 Server。"


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ("yes", "true", "t", "1", "y"):
        return True
    elif v.lower() in ("no", "false", "f", "0", "n"):
        return False
    else:
        raise argparse.ArgumentTypeError("Boolean value expected.")


def prepare_path():
    os.makedirs(output_folder, exist_ok=True)
    prepare_config_files(config_path)


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Server bind host; use 0.0.0.0 only when remote access is intentionally required",
    )
    parser.add_argument(
        "--port", type=int, default=PORT, help="Port to run the server on"
    )
    parser.add_argument(
        "--enable_venv", type=str2bool, default=enable_venv, help="脚本自动开启虚拟环境"
    )
    parser.add_argument(
        "--env_tool",
        choices=["auto", "uv", "conda"],
        default=default_env_tool,
        help="环境管理工具；auto 会沿用已有 uv/conda，新环境优先 uv",
    )
    parser.add_argument(
        "--check_update", type=str2bool, default=True, help="启动时检查更新"
    )
    parser.add_argument(
        "--update_source",
        type=str,
        default="gitee",
        help="优先更新源 gitee 或 github；失败时自动尝试另一个源",
    )
    parser.add_argument(
        "--debug", type=str2bool, default=False, help="Enable debug mode"
    )
    parser.add_argument(
        "--enable_winexe",
        type=str2bool,
        default=False,
        help="使用pdf2zh_next Windows可执行文件运行脚本, 仅限Windows系统",
    )
    parser.add_argument(
        "--enable_mirror",
        type=str2bool,
        default=True,
        help="启用下载镜像加速, 仅限中国大陆用户",
    )
    parser.add_argument(
        "--mirror_source",
        type=str,
        default="https://mirrors.ustc.edu.cn/pypi/simple",
        help="自定义您的PyPI镜像源, 仅限中国大陆用户",
    )
    parser.add_argument(
        "--winexe_path",
        type=str,
        default="./pdf2zh-v2.6.3-BabelDOC-v0.5.7-win64/pdf2zh/pdf2zh.exe",
        help="Windows可执行文件的路径",
    )
    parser.add_argument(
        "--winexe_attach_console",
        type=str2bool,
        default=True,
        help="Winexe模式是否尝试附着父控制台显示实时日志 (默认True)",
    )
    parser.add_argument(
        "--skip_install", type=str2bool, default=False, help="跳过虚拟环境中的安装"
    )
    parser.add_argument(
        "--wenyi-python",
        default=None,
        help="Python with wenyi-cli installed; bypass the dedicated environment and use an external bridge",
    )
    parser.add_argument(
        "--wenyi-data-dir",
        default=None,
        help="Persistent plugin Wenyi data root (or ZOTERO_WENYI_DATA_DIR)",
    )
    parser.add_argument(
        "--wenyi-cache-dir",
        default=None,
        help="Managed bridge asset cache (default: <Wenyi data root>/cache; or ZOTERO_WENYI_CACHE_DIR)",
    )
    parser.add_argument(
        "--wenyi-bridge-url",
        default=None,
        help="Use an external bridge instead of starting one in the Wenyi environment",
    )
    parser.add_argument(
        "--wenyi-timeout",
        type=float,
        default=10800,
        help="Wenyi process timeout in seconds",
    )
    return parser.parse_args(argv)


def main(version):
    args = parse_arguments()
    print("\n===== 💡提示💡 =====")
    print("如果您遇到问题......")
    print("1️⃣ 请阅读本项目的【github主页】, 这里有最准确的信息")
    print("    · 🤖 github: https://github.com/guaguastandup/zotero-pdf2zh")
    print(
        "    · 🤖 如果国内无法访问github, 请移步: gitee: https://gitee.com/guaguastandup/zotero-pdf2zh\n"
    )
    print(
        "2️⃣ 加入zotero-pdf2zh插件QQ群: 请在 GitHub / Gitee 仓库主页查看最新群号和入群口令"
    )
    print("    · 【提问前】您需要先确保已经阅读过本项目主页的教程以及常见问题汇总")
    print(
        "    · 【提问时】您必须将本终端输出的所有信息复制到txt文件中, 并截图您的zotero插件设置, 一并发送到群里, 否则您将不会得到回复, 感谢配合!\n"
    )
    print("\n==== 🌍翻译期间请勿关闭此窗口🌍 =====\n")
    print("🚀 启动参数:", args, "\n")
    print("🏠 当前版本: ", version)
    print("🏠 当前路径: ", root_path, "\n")
    print("🔍 开始环境检查...")
    all_checks_passed = True
    print("\n--- 网络端口检查 ---")
    port = args.port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        print(f"🔍 检查端口 {port} 是否被占用...")
        if s.connect_ex(("localhost", port)) == 0:
            print(f"❌ 端口 {port} 已被占用！")
            print("\n💡 解决方案:")
            print("   1. 选择其他端口启动: python server.py --port XXXX")
            print("   2. 或在Zotero插件设置中修改Server IP端口号")
            print(f"   3. 或停止占用端口 {port} 的其他程序")
            all_checks_passed = False
        else:
            print(f"✅ 端口 {port} 可用")
    print("\n--- 目录权限检查 ---")
    required_dirs = [("translated", "翻译输出目录"), ("config", "配置文件目录")]
    for dir_name, description in required_dirs:
        dir_path = os.path.join(root_path, dir_name)
        if not os.path.exists(dir_path):
            print(f"⚠️  {description} ({dir_name}) 不存在，尝试创建...")
            try:
                os.makedirs(dir_path, exist_ok=True)
                print(f"✅ {description} 创建成功: {dir_path}")
            except Exception as e:
                print(f"❌ 无法创建 {description}: {e}")
                print(f"\n💡 解决方案:")
                print(f"   1. 手动创建 {dir_name} 文件夹")
                print(f"   2. 检查当前用户是否有创建目录的权限")
                print(f"   3. 尝试以管理员身份运行（Windows: 右键'以管理员身份运行'）")
                all_checks_passed = False
        elif not os.access(dir_path, os.W_OK):
            print(f"❌ {description} ({dir_name}) 没有写入权限！")
            print(f"\n💡 解决方案:")
            print(f"   1. 检查 {dir_name} 文件夹的权限设置")
            print(f"   2. 在Windows中: 右键文件夹 -> 属性 -> 安全 -> 编辑权限")
            print(f"   3. 在Linux/Mac中: chmod 755 {dir_path}")
            all_checks_passed = False
        else:
            print(f"✅ {description} ({dir_name}) 权限正常")
    print("\n--- Python环境检查 ---")
    print(f"🐍 Python版本: {sys.version}")
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 8):
        print(f"❌ Python版本过低！需要 Python 3.8 或更高版本")
        print(f"💡 解决方案:")
        print(f"   1. 安装 Python 3.8 或更高版本")
        print(f"   2. 从 python.org 下载最新版 Python")
        all_checks_passed = False
    else:
        print(f"✅ Python版本符合要求")
    if args.enable_venv:
        print("\n--- 虚拟环境检查 ---")
        print(f"🔧 环境管理模式: {args.env_tool}")
        if args.env_tool == "auto":
            print("💡 auto: 优先沿用已有 uv/conda；没有已有环境时优先创建 uv。")
        found = []
        for engine_name in venv_name:
            existing = find_existing_environment(engine_name, args.env_tool)
            if existing:
                tool, env_dir, python_path = existing
                found.append(engine_name)
                print(f"✅ {engine_name}: {tool} -> {env_dir}")
                try:
                    versions = read_versions(python_path, engine_name)
                    printed = format_versions(versions)
                    if printed:
                        print(f"   📦 {printed}")
                    if engine_name == pdf2zh_next and (
                        not pdf2zh_next_meets_minimum(versions.get("pdf2zh-next"))
                    ):
                        print(
                            "   ⚠️ pdf2zh_next 低于 2.9.0，DeepSeek V4 思考控制可能不可用。"
                        )
                except Exception as exc:
                    print(f"   ⚠️ 无法读取包版本: {exc}")
            else:
                print(f"ℹ️ {engine_name}: 暂无托管环境，首次使用时将自动创建。")
        if not found:
            print("💡 尚未创建翻译环境；Server 本身可以先正常启动。")
    print("\n" + "=" * 60)
    if all_checks_passed:
        print("✅ 所有检查通过！Server准备启动...")
    else:
        print("❌ 部分检查未通过，可能影响Server正常运行")
        print("\n⚠️  您可以选择:")
        print("   1. 根据上述提示修复问题后重新启动")
        print("   2. 忽略警告继续运行（可能遇到错误）")
        user_input = input("\n是否继续启动？(y/n): ").strip().lower()
        if user_input != "y":
            print("👋 已取消启动，请修复问题后重试")
            sys.exit(0)
    print("=" * 60 + "\n")
    print("💡 请保持此窗口开启，翻译期间请勿关闭\n")
    try:
        fetch_and_show_notices(version, args.update_source)
    except Exception:
        pass
    if args.check_update:
        print("🔍 开始检查 Server 更新...")
        update_info = check_for_updates(version, args.update_source)
        if update_info:
            local_v, remote_v = update_info
            print(f"🎉 发现新版本！当前版本: {local_v}, 最新版本: {remote_v}")
            try:
                answer = input("是否要立即更新? (y/n): ").lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
                print("\n无法获取用户输入，已自动取消更新。")
            if answer in ["y", "yes"]:
                perform_update_optimized(
                    root_path,
                    version,
                    expected_version=remote_v,
                    update_source=args.update_source,
                )
            else:
                print("👌 已取消 Server 源码更新。")
    prepare_path()
    translator = ServerApplication(args, version=version)
    translator.run(args.host, args.port, debug=args.debug)
