"""Execute one translation using the existing engine's CLI and output conventions."""

import os
import subprocess
import sys

from pypdf import PdfReader

from pdf2zh_server.configuration.storage import update_config_file
from pdf2zh_server.engines.process import execute_with_progress
from pdf2zh_server.environment.discovery import resolve_unmanaged_pdf2zh_command
from pdf2zh_server.errors import extract_value_error
from pdf2zh_server.tasks.progress import engine_tail_for_error

pdf2zh_next = "pdf2zh_next"
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
from pdf2zh_server.pdf.tables.mode import validate_table_runtime
from pdf2zh_server.providers.catalog import pdf2zh_next_service_aliases
from pdf2zh_server.providers.relay_patch import RELAY_PATCH_FLAG, write_relay_options


def translate(
    input_path, config, task_id, options, env_manager, paths, on_progress=None
):
    validate_table_runtime(
        config.table_mode,
        engine=pdf2zh_next,
        winexe=options.enable_winexe and os.path.exists(options.winexe_path),
    )
    if config.service in pdf2zh_next_service_aliases:
        config.service = pdf2zh_next_service_aliases[config.service]
    job_output = str(config.job_workspace.output_dir)
    runtime_config = str(config.job_workspace.config_dir / "config.toml")
    update_config_file(
        config, paths.config_paths[pdf2zh_next], snapshot_file=runtime_config
    )
    cmd = [
        pdf2zh_next,
        input_path,
        "--" + config.service,
        "--qps",
        str(config.qps),
        "--output",
        job_output,
        "--lang-in",
        str(config.sourceLang),
        "--lang-out",
        str(config.targetLang),
        "--config-file",
        runtime_config,
    ]
    if config.no_watermark:
        cmd.extend(["--watermark-output-mode", "no_watermark"])
    else:
        cmd.extend(["--watermark-output-mode", "watermarked"])
    if config.skip_last_pages and config.skip_last_pages > 0:
        end = len(PdfReader(input_path).pages) - config.skip_last_pages
        if end < 1:
            raise ValueError("跳过尾页后没有可翻译的页面，请减小 skip_last_pages。")
        cmd.extend(["--pages", f"{1}-{end}"])
    if config.no_dual:
        cmd.append("--no-dual")
    if config.no_mono:
        cmd.append("--no-mono")
    if config.trans_first:
        cmd.append("--dual-translate-first")
    if config.skip_clean:
        cmd.append("--skip-clean")
    if config.disable_rich_text_translate:
        cmd.append("--disable-rich-text-translate")
    if config.enhance_compatibility:
        cmd.append("--enhance-compatibility")
    if config.save_auto_extracted_glossary:
        cmd.append("--save-auto-extracted-glossary")
    if config.disable_glossary:
        cmd.append("--no-auto-extract-glossary")
    if config.dual_mode == "TB":
        cmd.append("--use-alternating-pages-dual")
    if config.translate_table_text:
        cmd.append("--translate-table-text")
    if config.table_mode is not None:
        cmd.extend(["--zotero-table-mode", config.table_mode])
    if config.relay_options:
        if options.enable_winexe and os.path.exists(options.winexe_path):
            raise ValueError(
                "自定义请求头 / 接口类型需要 Python 引擎，Windows 独立 EXE 无法加载。请关闭 --enable_winexe 后重试；本次没有发起 API 请求。"
            )
        relay_file = str(config.job_workspace.config_dir / "relay_options.json")
        write_relay_options(relay_file, config.relay_options)
        cmd.extend([RELAY_PATCH_FLAG, relay_file])
    if config.skip_references:
        if options.enable_winexe and os.path.exists(options.winexe_path):
            print("⚠️ 参考文献跳过需要 Python 引擎；Windows 独立 EXE 本次使用原生翻译。")
        else:
            cmd.append("--zotero-reference-skip")
    if config.ignore_cache:
        cmd.append("--ignore-cache")
    if config.ocr:
        cmd.append("--ocr-workaround")
    if config.auto_ocr:
        cmd.append("--auto-enable-ocr-workaround")
    if config.font_family and config.font_family in ["serif", "sans-serif", "script"]:
        cmd.extend(["--primary-font-family", config.font_family])
    if config.pool_size and config.pool_size > 1:
        cmd.extend(["--pool-max-worker", str(config.pool_size)])
    fileName = os.path.splitext(os.path.basename(input_path))[0]
    no_watermark_mono = os.path.join(
        job_output, f"{fileName}.no_watermark.{config.targetLang}.mono.pdf"
    )
    no_watermark_dual = os.path.join(
        job_output, f"{fileName}.no_watermark.{config.targetLang}.dual.pdf"
    )
    watermark_mono = os.path.join(
        job_output, f"{fileName}.{config.targetLang}.mono.pdf"
    )
    watermark_dual = os.path.join(
        job_output, f"{fileName}.{config.targetLang}.dual.pdf"
    )
    output_path = []
    if config.no_watermark:
        if not config.no_mono:
            output_path.append(no_watermark_mono)
        if not config.no_dual:
            output_path.append(no_watermark_dual)
    else:
        if not config.no_mono:
            output_path.append(watermark_mono)
        if not config.no_dual:
            output_path.append(watermark_dual)
    if options.enable_winexe and os.path.exists(options.winexe_path):
        cmd = [f"{options.winexe_path}"] + cmd[1:]
        cmd = [
            os.path.normpath(arg) if os.path.isfile(arg) or os.path.isdir(arg) else arg
            for arg in cmd
        ]
        exe_dir = os.path.dirname(options.winexe_path)
        print(f"🔧 [winexe] winexe_attach_console={options.winexe_attach_console}")
        if options.winexe_attach_console:
            print("🚀 [winexe] mode=attach-console")
            print(f"📁 [winexe] cwd={exe_dir}")
            safe_cmd = []
            for i, arg in enumerate(cmd):
                if i > 0 and any(
                    (
                        sensitive in cmd[i - 1].lower()
                        for sensitive in ["key", "token", "secret", "password"]
                    )
                ):
                    safe_cmd.append("***")
                else:
                    safe_cmd.append(arg)
            print(f"⚡ [winexe] cmd={' '.join(safe_cmd)}")
            print("🔍 [winexe] 开始执行（预期在当前终端显示实时日志）...")
            process = subprocess.Popen(
                cmd,
                shell=False,
                cwd=exe_dir,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            stderr_lines = []
            if process.stderr:
                for line in process.stderr:
                    stderr_lines.append(line)
                    sys.stderr.write(line)
                    sys.stderr.flush()
                process.stderr.close()
            return_code = process.wait()
            if return_code != 0:
                stderr_text = "".join(stderr_lines)
                value_error = extract_value_error(stderr_text)
                if value_error:
                    raise ValueError(value_error)
                print(f"❌ pdf2zh.exe 执行失败，退出码: {return_code}")
                print("   操作失败，请查看详细日志。")
                raise RuntimeError(f"pdf2zh.exe 执行失败，退出码: {return_code}")
        else:
            print("🔇 [winexe] mode=silent")
            r = subprocess.run(
                cmd,
                shell=False,
                cwd=exe_dir,
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            if r.returncode != 0:
                value_error = extract_value_error(r.stderr or "")
                if value_error:
                    raise ValueError(value_error)
                raise RuntimeError(
                    f"pdf2zh.exe 退出码 {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
                )
    elif options.enable_venv:
        execute_with_progress(
            cmd, task_id, options, env_manager, on_progress=on_progress
        )
    else:
        cmd = resolve_unmanaged_pdf2zh_command(cmd)
        execute_with_progress(cmd, task_id, options, None, on_progress=on_progress)
    existing = [p for p in output_path if os.path.exists(p)]
    for f in existing:
        size = os.path.getsize(f)
        print(
            f"🐲 pdf2zh_next 翻译成功, 生成文件: {f}, 大小为: {size / 1024.0 / 1024.0:.2f} MB"
        )
    if not existing:
        tail = engine_tail_for_error(5).strip()
        detail = f"\n\n[引擎输出尾部]\n{tail}" if tail else ""
        raise RuntimeError(f"操作失败，请查看详细日志。{detail}")
    return existing
