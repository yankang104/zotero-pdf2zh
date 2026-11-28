"""Translation and PDF-operation workflows, independent of HTTP and UI."""

import base64
import os
import shutil
import threading
import uuid
from datetime import datetime

from pdf2zh_server.configuration.request import Config
from pdf2zh_server.configuration.storage import detect_saved_credential_reuse
from pdf2zh_server.engines import next as next_engine
from pdf2zh_server.errors import classify_exception, exception_payload
from pdf2zh_server.pdf.outputs import (
    canonicalize_pdf2zh_next_dual,
    get_dual_mode,
    get_filename_after_process,
    get_filetype,
    get_filetype_after_crop,
)
from pdf2zh_server.tasks.progress import engine_tail_for_error
from pdf2zh_server.tasks.workspace import JobWorkspace

pdf2zh_next = "pdf2zh_next"
wenyi = "wenyi"


class TranslationService:
    def __init__(self, options, paths, task_manager, env_manager, cropper, wenyi=None):
        self.options = options
        self.paths = paths
        self.tasks = task_manager
        self.env_manager = env_manager
        self.cropper = cropper
        self.wenyi = wenyi

    @staticmethod
    def _safe_upload_filename(raw_name):
        if not isinstance(raw_name, str):
            raise ValueError("Invalid PDF filename")
        name = raw_name.strip()
        if (
            not name
            or name in {".", ".."}
            or "/" in name
            or ("\\" in name)
            or (os.path.basename(name) != name)
        ):
            raise ValueError("Invalid PDF filename")
        if not name.lower().endswith(".pdf"):
            raise ValueError("Only PDF uploads are accepted")
        return name

    def process_request(self, data, task_id=None):
        if not isinstance(data, dict):
            raise ValueError("Invalid JSON request")
        config = Config(data)
        if config.engine == pdf2zh_next:
            detect_saved_credential_reuse(
                config, self.paths.config_paths[pdf2zh_next]
            )
        file_name = self._safe_upload_filename(data.get("fileName"))
        file_content = data.get("fileContent", "")
        if not isinstance(file_content, str):
            raise ValueError("Invalid PDF content")
        if file_content.startswith("data:application/pdf;base64,"):
            file_content = file_content[len("data:application/pdf;base64,") :]
        try:
            decoded = base64.b64decode(file_content)
        except Exception as exc:
            raise ValueError(f"Invalid PDF content: {exc}") from exc
        if config.engine == wenyi:
            if task_id is None:
                raise ValueError(
                    "Wenyi v1 supports translation only, not crop or compare operations"
                )
            input_path = self.wenyi.workspace(task_id) / file_name
            input_path.write_bytes(decoded)
            return input_path, config

        workspace = JobWorkspace(str(self.paths.output))
        config.job_workspace = workspace
        try:
            input_path = workspace.upload(file_name, decoded)
        except Exception:
            workspace.cleanup()
            raise
        return (input_path, config)

    def _existing_output_files(self, paths):
        existing = []
        for path in paths or []:
            if path and os.path.exists(path):
                existing.append(os.path.abspath(path))
        return existing

    def _success_files_payload(self, paths, workspace=None):
        existing = self._existing_output_files(paths)
        if workspace is not None:
            existing = workspace.publish(existing)
        return {
            "status": "success",
            "fileList": [os.path.basename(p) for p in existing],
            "outputDir": os.path.abspath(str(self.paths.output)),
            "filePaths": existing,
        }

    def _success_files_response(self, paths, workspace=None):
        return (self._success_files_payload(paths, workspace), 200)

    @staticmethod
    def _cleanup_workspace(workspace):
        if workspace is not None:
            try:
                workspace.cleanup()
            except Exception as exc:
                print(f"⚠️ 无法清理任务临时目录: {exc}")

    def _build_task_info(
        self, task_id, input_path, config, engine, start_time, status="开始处理"
    ):
        output_types = []
        if config.mono:
            output_types.append("mono")
        if config.dual:
            output_types.append("dual")
        if config.mono_cut:
            output_types.append("mono-cut")
        if config.dual_cut:
            output_types.append("dual-cut")
        if config.compare:
            output_types.append("compare")
        if config.crop_compare:
            output_types.append("crop-compare")
        config_summary = {
            "sourceLang": config.sourceLang,
            "targetLang": config.targetLang,
            "outputTypes": output_types,
        }
        config_summary["qps"] = config.qps
        config_summary["dualMode"] = config.dual_mode
        config_summary["noWatermark"] = config.no_watermark
        config_summary["ocr"] = config.ocr or config.auto_ocr
        config_summary["poolSize"] = config.pool_size
        if config.skip_last_pages and config.skip_last_pages > 0:
            config_summary["skipLastPages"] = config.skip_last_pages
        if config.no_watermark:
            config_summary["noWatermark"] = config.no_watermark
        model_name = config.llm_api.get("model", "")
        service = config.service
        if not model_name:
            if service == "siliconflowfree":
                model_name = "siliconflowfree (免费服务)"
            elif service == "bing":
                model_name = "Bing 翻译"
            elif service == "google":
                model_name = "Google 翻译"
            else:
                model_name = f"{service} (默认模型)"
        task_record = {
            "taskId": task_id,
            "active": True,
            "finished": False,
            "fileName": os.path.basename(input_path),
            "engine": engine,
            "service": getattr(config, "custom_service", None) or config.service,
            "modelName": model_name,
            "startTime": start_time.isoformat(),
            "progress": 0,
            "status": status,
            "message": "正在初始化...",
            "config": config_summary,
            "warnings": list(getattr(config, "warnings", []) or []),
        }
        if engine == wenyi:
            self.tasks.register_stopper(task_id, self.wenyi.close)
        return task_record

    def _start_accepted_job(
        self, task_id, task_info, worker, context, workspace=None, async_job=False
    ):
        raw_worker = worker

        def worker():
            try:
                return raw_worker()
            finally:
                self._cleanup_workspace(workspace)

        self.tasks.add_task(task_id, task_info)
        if async_job:

            def run():
                try:
                    worker()
                except Exception as exc:
                    classified = classify_exception(exc)
                    user_msg = str(exc)
                    if classified.get("errorCode") != "UNKNOWN_ERROR":
                        raw_tail = engine_tail_for_error(3).strip()
                        user_msg = f"💡 {classified['userMessage']}\n(建议: {classified.get('hint', '')})"
                        if raw_tail:
                            user_msg += f"\n\n[引擎错误] {raw_tail}"
                        print(
                            f"💡 [Zotero PDF2zh Server] 错误解读: [{classified['errorCode']}] {classified['userMessage']}"
                        )
                    self.tasks.complete_task(
                        task_id, "failed", user_msg, error=str(exc)
                    )
                    exception_payload(exc, context=context)

            threading.Thread(target=run, daemon=True).start()
            payload = {"status": "accepted", "taskId": task_id}
            warnings = task_info.get("warnings")
            if warnings:
                payload["warnings"] = warnings
            return (payload, 200)
        print(
            f"ℹ️ [Zotero PDF2zh Server] 旧插件协议：同步等待完成后返回 fileList ({context})"
        )
        try:
            payload = worker() or {}
            if payload.get("status") == "error":
                return (payload, 500)
            if payload.get("status") != "success":
                return (
                    {
                        "status": "error",
                        "message": payload.get("message")
                        or "操作失败，请查看详细日志。",
                    },
                    500,
                )
            return (payload, 200)
        except Exception as exc:
            self.tasks.complete_task(task_id, "failed", str(exc), error=str(exc))
            return self._handle_exception(exc, context=context)

    def _complete_job_files(self, task_id, paths, message, workspace=None):
        payload = self._success_files_payload(paths, workspace)
        if not payload["fileList"]:
            self.tasks.complete_task(
                task_id, "failed", "操作失败，请查看详细日志。", error="无文件生成"
            )
            return {"status": "error", "message": "操作失败，请查看详细日志。"}
        self.tasks.complete_task(
            task_id,
            "success",
            message,
            file_list=payload["fileList"],
            file_paths=payload["filePaths"],
            output_dir=payload["outputDir"],
            result=payload,
        )
        return payload

    def translate(self, data, async_job=False):
        task_id = str(uuid.uuid4())
        start_time = datetime.now()
        config = None
        handed_off = False
        try:
            input_path, config = self.process_request(data, task_id=task_id)
            infile_type = get_filetype(input_path)
            engine = config.engine
            engine = config.engine
            task_info = self._build_task_info(
                task_id, input_path, config, engine, start_time, status="开始翻译"
            )
            if infile_type != "origin":
                return (
                    {
                        "status": "error",
                        "message": "Input file must be an original PDF file.",
                    },
                    400,
                )
            response = self._start_accepted_job(
                task_id,
                task_info,
                lambda: self._execute_translate_job(
                    task_id, input_path, config, engine
                ),
                "/translate",
                workspace=getattr(config, "job_workspace", None),
                async_job=async_job,
            )
            handed_off = True
            return response
        except Exception as e:
            self.tasks.complete_task(task_id, "failed", str(e), error=str(e))
            return self._handle_exception(e, context="/translate")
        finally:
            if not handed_off:
                self._cleanup_workspace(getattr(config, "job_workspace", None))

    def _execute_translate_job(self, task_id, input_path, config, engine):

        def addFileList(fileList, filePath):
            if os.path.exists(filePath):
                fileList.append(filePath)

        if engine == wenyi:
            def on_progress(updates):
                self.tasks.update_task(task_id, updates)

            fileList = self.wenyi.translate(
                input_path, config, task_id, on_progress
            )
        elif engine == pdf2zh_next:
            print("🔍 [Zotero PDF2zh Server] PDF2zh_next 开始翻译文件...")
            if config.mono_cut or config.mono:
                config.no_mono = False
            if config.dual or config.dual_cut or config.crop_compare or config.compare:
                config.no_dual = False
            if config.no_dual and config.no_mono:
                raise ValueError(
                    "⚠️ [Zotero PDF2zh Server] pdf2zh_next 引擎至少需要生成 mono 或 dual 文件, 请检查 no_dual 和 no_mono 配置项"
                )
            fileList = []
            retList = self.run_engine(input_path, config, task_id)
            if config.no_mono:
                dual_path = retList[0]
            elif config.no_dual:
                mono_path = retList[0]
                fileList.append(mono_path)
            else:
                mono_path, dual_path = (retList[0], retList[1])
                fileList.append(mono_path)
            primary_dual_path = None
            LR_dual_path = None
            TB_dual_path = None
            if not config.no_dual:
                primary_dual_path = canonicalize_pdf2zh_next_dual(
                    dual_path, config.dual_mode, self.cropper
                )
                if config.dual_mode == "LR":
                    LR_dual_path = primary_dual_path
                    if config.dual_cut or config.crop_compare:
                        _, TB_dual_path = self.cropper.pdf_dual_mode(
                            primary_dual_path, "LR", "TB"
                        )
                else:
                    TB_dual_path = primary_dual_path
                if config.dual:
                    fileList.append(primary_dual_path)
            if config.mono_cut:
                mono_cut_path = get_filename_after_process(
                    mono_path, "mono-cut", engine
                )
                self.cropper.crop_pdf(
                    config, mono_path, "mono", mono_cut_path, "mono-cut"
                )
                addFileList(fileList, mono_cut_path)
            if config.dual_cut:
                if not TB_dual_path:
                    raise ValueError("dual-cut 需要 TB dual 输入，但未能准备该布局。")
                dual_cut_path = get_filename_after_process(
                    TB_dual_path, "dual-cut", engine
                )
                self.cropper.crop_pdf(
                    config, TB_dual_path, "dual", dual_cut_path, "dual-cut"
                )
                addFileList(fileList, dual_cut_path)
            if config.crop_compare:
                if not TB_dual_path:
                    raise ValueError(
                        "crop-compare 需要 TB dual 输入，但未能准备该布局。"
                    )
                crop_compare_path = get_filename_after_process(
                    TB_dual_path, "crop-compare", engine
                )
                self.cropper.crop_pdf(
                    config, TB_dual_path, "dual", crop_compare_path, "crop-compare"
                )
                addFileList(fileList, crop_compare_path)
            if config.compare:
                if config.dual_mode == "LR":
                    if not LR_dual_path:
                        raise ValueError(
                            "compare 需要 LR dual 输入，但未能准备该布局。"
                        )
                    compare_path = get_filename_after_process(
                        LR_dual_path, "compare", engine
                    )
                    if os.path.exists(compare_path):
                        os.remove(compare_path)
                    shutil.copyfile(LR_dual_path, compare_path)
                    addFileList(fileList, compare_path)
                else:
                    if not TB_dual_path:
                        raise ValueError(
                            "compare 需要 TB dual 输入，但未能准备该布局。"
                        )
                    compare_path = get_filename_after_process(
                        TB_dual_path, "compare", engine
                    )
                    self.cropper.merge_pdf(TB_dual_path, compare_path)
                    addFileList(fileList, compare_path)
        else:
            raise ValueError(f"Unsupported translation engine: {engine}")
        existing = [p for p in fileList if os.path.exists(p)]
        missing = [p for p in fileList if not os.path.exists(p)]
        for m in missing:
            print(f"⚠️ 期望生成但不存在: {m}")
        for f in existing:
            size = os.path.getsize(f)
            print(
                f"🐲 翻译成功, 生成文件: {f}, 大小为: {size / 1024.0 / 1024.0:.2f} MB"
            )
        if not existing:
            self.tasks.complete_task(
                task_id, "failed", "操作失败，请查看详细日志。", error="无文件生成"
            )
            return {"status": "error", "message": "操作失败，请查看详细日志。"}
        payload = self._success_files_payload(
            existing, getattr(config, "job_workspace", None)
        )
        self.tasks.complete_task(
            task_id,
            "success",
            f"成功生成 {len(existing)} 个文件",
            file_list=payload["fileList"],
            file_paths=payload["filePaths"],
            output_dir=payload["outputDir"],
            result=payload,
        )
        return payload

    def _handle_exception(self, exc, status_code=500, context=None):
        return (exception_payload(exc, context=context), status_code)

    def crop(self, data):
        config = None
        try:
            input_path, config = self.process_request(data)
            infile_type = get_filetype(input_path)
            source_path = input_path
            if (
                infile_type == "dual"
                and get_dual_mode(input_path, config.dual_mode) == "LR"
            ):
                _, source_path = self.cropper.pdf_dual_mode(input_path, "LR", "TB")
            new_type = get_filetype_after_crop(input_path)
            if new_type == "unknown":
                return (
                    {
                        "status": "error",
                        "errorType": "InvalidPDFOperation",
                        "message": f"当前 PDF 类型 {infile_type} 不能再次执行裁剪。请选择原文、mono 或 dual 文件。",
                    },
                    400,
                )
            new_path = get_filename_after_process(input_path, new_type, config.engine)
            self.cropper.crop_pdf(config, source_path, infile_type, new_path, new_type)
            print(
                f"🔍 [Zotero PDF2zh Server] 开始裁剪文件: {source_path}, {infile_type}, 裁剪类型: {new_type}, {new_path}"
            )
            if os.path.exists(new_path):
                return self._success_files_response(
                    [new_path], getattr(config, "job_workspace", None)
                )
            return (
                {"status": "error", "message": f"Crop failed: {new_path} not found"},
                500,
            )
        except Exception as e:
            return self._handle_exception(e, context="/crop")
        finally:
            self._cleanup_workspace(getattr(config, "job_workspace", None))

    def crop_compare(self, data, async_job=False):
        task_id = str(uuid.uuid4())
        start_time = datetime.now()
        config = None
        handed_off = False
        try:
            input_path, config = self.process_request(data)
            infile_type = get_filetype(input_path)
            engine = config.engine
            if infile_type == "crop-compare":
                return (
                    {
                        "status": "error",
                        "errorType": "InvalidPDFOperation",
                        "message": "该 PDF 已经是“裁剪后双语对照”结果，无需再次执行 crop-compare。请选择原文或 dual 附件。",
                    },
                    409,
                )
            if infile_type not in {"origin", "dual", "dual-cut"}:
                return (
                    {
                        "status": "error",
                        "errorType": "InvalidPDFOperation",
                        "message": f"当前 PDF 类型 {infile_type} 不能执行 crop-compare。请选择原文、dual 或 dual-cut 文件。",
                    },
                    400,
                )
            task_info = self._build_task_info(
                task_id, input_path, config, engine, start_time, status="开始处理"
            )
            response = self._start_accepted_job(
                task_id,
                task_info,
                lambda: self._execute_crop_compare_job(
                    task_id, input_path, config, engine, infile_type
                ),
                "/crop-compare",
                workspace=getattr(config, "job_workspace", None),
                async_job=async_job,
            )
            handed_off = True
            return response
        except Exception as e:
            self.tasks.complete_task(task_id, "failed", str(e), error=str(e))
            return self._handle_exception(e, context="/crop-compare")
        finally:
            if not handed_off:
                self._cleanup_workspace(getattr(config, "job_workspace", None))

    def _execute_crop_compare_job(
        self, task_id, input_path, config, engine, infile_type
    ):
        if infile_type == "origin":
            config.dual_mode = "TB"
            config.no_dual = False
            config.no_mono = True
            fileList = self.run_engine(input_path, config, task_id)
            input_path = fileList[0]
            if not os.path.exists(input_path):
                raise FileNotFoundError(f"Dual file not found: {input_path}")
        infile_type = get_filetype(input_path)
        if infile_type == "dual-cut":
            new_path = get_filename_after_process(input_path, "crop-compare", engine)
            self.cropper.merge_pdf(input_path, new_path)
        elif infile_type == "dual":
            source_path = input_path
            if get_dual_mode(input_path, config.dual_mode) == "LR":
                _, source_path = self.cropper.pdf_dual_mode(input_path, "LR", "TB")
            new_path = get_filename_after_process(input_path, "crop-compare", engine)
            self.cropper.crop_pdf(config, source_path, "dual", new_path, "crop-compare")
        else:
            raise ValueError(
                f"当前 PDF 类型 {infile_type} 不能执行 crop-compare。请选择原文、dual 或 dual-cut 文件。"
            )
        if not os.path.exists(new_path):
            raise RuntimeError(f"Crop-compare failed: {new_path} not found")
        fileName = os.path.basename(new_path)
        size = os.path.getsize(new_path)
        print(
            f"🐲 双语对照成功(裁剪后拼接), 生成文件: {fileName}, 大小为: {size / 1024.0 / 1024.0:.2f} MB"
        )
        return self._complete_job_files(
            task_id,
            [new_path],
            f"成功生成 {fileName}",
            workspace=getattr(config, "job_workspace", None),
        )

    def compare(self, data, async_job=False):
        task_id = str(uuid.uuid4())
        start_time = datetime.now()
        config = None
        handed_off = False
        try:
            input_path, config = self.process_request(data)
            infile_type = get_filetype(input_path)
            engine = config.engine
            if infile_type == "compare":
                return (
                    {
                        "status": "error",
                        "errorType": "InvalidPDFOperation",
                        "message": "该 PDF 已经是双语对照结果，无需再次执行 compare。请选择原文或 dual 附件。",
                    },
                    409,
                )
            if infile_type not in {"origin", "dual"}:
                return (
                    {
                        "status": "error",
                        "errorType": "InvalidPDFOperation",
                        "message": f"当前 PDF 类型 {infile_type} 不能执行 compare。请选择原文或 dual 文件。",
                    },
                    400,
                )
            task_info = self._build_task_info(
                task_id, input_path, config, engine, start_time, status="开始处理"
            )
            response = self._start_accepted_job(
                task_id,
                task_info,
                lambda: self._execute_compare_job(
                    task_id, input_path, config, engine, infile_type
                ),
                "/compare",
                workspace=getattr(config, "job_workspace", None),
                async_job=async_job,
            )
            handed_off = True
            return response
        except Exception as e:
            self.tasks.complete_task(task_id, "failed", str(e), error=str(e))
            return self._handle_exception(e, context="/compare")
        finally:
            if not handed_off:
                self._cleanup_workspace(getattr(config, "job_workspace", None))

    def _execute_compare_job(self, task_id, input_path, config, engine, infile_type):
        if infile_type == "origin":
            config.dual_mode = "LR"
            config.no_dual = False
            config.no_mono = True
            fileList = self.run_engine(input_path, config, task_id)
            dual_path = fileList[0]
            if not os.path.exists(dual_path):
                raise FileNotFoundError(f"Dual file not found: {dual_path}")
            new_path = get_filename_after_process(input_path, "compare", engine)
            if os.path.exists(new_path):
                os.remove(new_path)
            os.rename(dual_path, new_path)
            fileName = os.path.basename(new_path)
            print(
                f"🐲 双语对照成功, 生成文件: {fileName}, 大小为: {os.path.getsize(new_path) / 1024.0 / 1024.0:.2f} MB"
            )
            return self._complete_job_files(
                task_id,
                [new_path],
                f"成功生成 {fileName}",
                workspace=getattr(config, "job_workspace", None),
            )
        infile_type = get_filetype(input_path)
        if infile_type != "dual":
            raise ValueError(
                f"当前 PDF 类型 {infile_type} 不能执行 compare。请选择原文或 dual 文件。"
            )
        new_path = get_filename_after_process(input_path, "compare", engine)
        if get_dual_mode(input_path, config.dual_mode) == "LR":
            if os.path.exists(new_path):
                os.remove(new_path)
            shutil.copyfile(input_path, new_path)
        else:
            self.cropper.merge_pdf(input_path, new_path)
        if not os.path.exists(new_path):
            raise RuntimeError(f"Compare failed: {new_path} not found")
        fileName = os.path.basename(new_path)
        print(
            f"🐲 双语对照成功, 生成文件: {fileName}, 大小为: {os.path.getsize(new_path) / 1024.0 / 1024.0:.2f} MB"
        )
        return self._complete_job_files(
            task_id,
            [new_path],
            f"成功生成 {fileName}",
            workspace=getattr(config, "job_workspace", None),
        )

    def run_engine(self, input_path, config, task_id=None):
        workspace = getattr(config, "job_workspace", None)
        owns_workspace = workspace is None
        if owns_workspace:
            workspace = JobWorkspace(self.paths.output)
            config.job_workspace = workspace
        try:
            if owns_workspace:
                input_path = workspace.copy_input(input_path)
            paths = next_engine.translate(
                input_path,
                config,
                task_id,
                self.options,
                self.env_manager,
                self.paths,
                on_progress=lambda updates: self.tasks.update_task(task_id, updates),
            )
            if getattr(config, "save_auto_extracted_glossary", False):
                workspace.publish(workspace.output_dir.glob("*.csv"))
            return workspace.publish(paths) if owns_workspace else paths
        finally:
            if owns_workspace:
                self._cleanup_workspace(workspace)
                config.job_workspace = None
