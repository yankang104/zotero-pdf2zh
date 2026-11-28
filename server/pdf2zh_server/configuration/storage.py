import os
import shutil
import threading

import toml

from pdf2zh_server.engines.next_runtime.deepseek import (
    validate_winexe_runtime_if_selected,
)
from pdf2zh_server.providers.catalog import (
    pdf2zh_next_config_map,
    pdf2zh_next_custom_service_engine,
    pdf2zh_next_service_aliases,
)
from pdf2zh_server.providers.deepseek_options import (
    is_deepseek_thinking_model,
    normalize_deepseek_extra_data,
    remove_stale_thinking_fields,
)
from pdf2zh_server.providers.openai_options import validate_openai_none
from pdf2zh_server.providers.relay_options import normalize_relay_options
from pdf2zh_server.providers.relay_patch import (
    bind_relay_target,
    describe_relay_options,
)

pdf2zh_next = "pdf2zh_next"

CONFIG_FILE_LOCK = threading.RLock()

_OPENAI_SEND_TEMPERATURE_ALIAS = "openai_send_temperature"

_OPENAI_SEND_TEMPERATURE_UPSTREAM = "openai_send_temprature"

_TRUE_VALUES = {"true", "1", "yes", "on"}

_FALSE_VALUES = {"false", "0", "no", "off"}

_CLEARED_PLACEHOLDERS = {"", "null", "none"}


def _normalize_openai_send_temperature_key(values):
    """Map this project's old spelling to pdf2zh_next's compatibility key."""
    if not isinstance(values, dict):
        return
    if (
        _OPENAI_SEND_TEMPERATURE_ALIAS in values
        and _OPENAI_SEND_TEMPERATURE_UPSTREAM not in values
    ):
        values[_OPENAI_SEND_TEMPERATURE_UPSTREAM] = values[
            _OPENAI_SEND_TEMPERATURE_ALIAS
        ]
    values.pop(_OPENAI_SEND_TEMPERATURE_ALIAS, None)


def _safe_log_value(key, value):
    name = str(key or "").lower()
    if any(token in name for token in ("key", "token", "secret", "password", "auth")):
        raw = str(value or "")
        if not raw:
            return ""
        return ("*" * 8 + raw[-4:]) if len(raw) > 4 else ("*" * len(raw))
    return value


def resolve_pdf2zh_next_service(service):
    return pdf2zh_next_service_aliases.get(service, service)


def _is_cleared_value(value):
    if not isinstance(value, str):
        return True
    text = value.strip()
    return not text or text.lower() in _CLEARED_PLACEHOLDERS


def clear_saved_credential(config_file, service):
    """清除配置文件里某个服务保存的 API Key。

    请求里不带 llm_api 时 server 会复用配置文件上次保存的 Key；插件删除某条
    LLM API 配置后调用这里，把该服务残留在 config.toml 里的 Key
    改回占位值，避免用户以为已删除却仍在扣费。
    返回 True 表示确实清掉了一个非空 Key。
    """
    with CONFIG_FILE_LOCK:
        return _clear_saved_credential(config_file, service)


def _clear_saved_credential(config_file, service):
    if not config_file or not os.path.exists(config_file):
        return False
    service = resolve_pdf2zh_next_service(service)
    config_map = pdf2zh_next_config_map.get(service) or {}
    mapped_key = config_map.get("apiKey")
    if not mapped_key:
        return False

    with open(config_file, "r", encoding="utf-8") as f:
        config = toml.load(f)
    container = config.get(f"{service}_detail")
    placeholder = "null"

    if not isinstance(container, dict) or _is_cleared_value(container.get(mapped_key)):
        return False

    container[mapped_key] = placeholder
    with open(config_file, "w", encoding="utf-8") as f:
        toml.dump(config, f)
    print(f"🧹 已清除 pdf2zh_next 配置中 {service} 保存的密钥 ({mapped_key})")
    return True


def _is_pdf2zh_next_bool_extra_key(key):
    name = str(key or "")
    return (
        name.endswith("_enable_json_mode")
        or name.endswith("_send_temprature")
        or name.endswith("_send_temperature")
        or name.endswith("_send_reasoning_effort")
        or name.endswith("_enable_thinking")
        or name.endswith("_send_enable_thinking_param")
    )


def coerce_pdf2zh_next_extra_value(key, value):
    """Keep extraData types compatible with pdf2zh_next pydantic fields.

    The plugin always sends extraData values as strings. toml needs native
    bool/int so fields like openai_enable_json_mode=false actually work.
    Empty values are skipped by the caller; False and 0 must still be written.
    """
    if isinstance(value, bool):
        return value
    if _is_pdf2zh_next_bool_extra_key(key):
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        text = str(value).strip().lower()
        if text in _TRUE_VALUES:
            return True
        if text in _FALSE_VALUES:
            return False
        return value
    if str(key) == "num_predict":
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return value
    return value


def detect_saved_credential_reuse(config, config_file):
    """插件没有下发 API Key、但磁盘上仍保存着该服务的 Key 时给出警告。

    update_config_file() 会有意保留请求里缺省的字段（避免插件发局部配置时
    覆盖用户手改的 config.toml），副作用是：用户在插件里删掉 Key 之后，
    服务器仍会静默用磁盘上的旧 Key 去请求付费 API。这里把"实际复用了哪份
    凭据"明确告知用户，而不是让它看起来像免费服务。
    """
    if config.llm_api.get("apiKey"):
        return None
    if not config_file or not os.path.exists(config_file):
        return None

    service = resolve_pdf2zh_next_service(config.service)
    config_map = pdf2zh_next_config_map.get(service, {})
    mapped_key = config_map.get("apiKey")
    if not mapped_key:
        return None
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            saved_config = toml.load(f)
    except (OSError, ValueError):
        return None
    detail = saved_config.get(f"{service}_detail")
    saved_key = detail.get(mapped_key) if isinstance(detail, dict) else ""
    saved_key = saved_key or ""

    if not isinstance(saved_key, str):
        return None
    saved_key = saved_key.strip()
    # 手动清空时用户可能写成占位符
    if not saved_key or saved_key.lower() in ("null", "none"):
        return None

    warning = (
        f"未收到插件下发的 {service} API Key，本次翻译将复用配置文件中已保存的密钥 "
        f"({_safe_log_value('apiKey', saved_key)})，会产生费用。"
        f"如需停用，请在插件「LLM API 配置管理」中配置该服务，或修改 {config_file}。"
    )
    config.warnings.append(warning)
    print(f"⚠️ {warning}")
    return warning


def update_config_file(config, config_file, snapshot_file=None):
    # A job must snapshot the exact configuration it just persisted before
    # another request or credential deletion can change the shared file.
    with CONFIG_FILE_LOCK:
        _update_config_file(config, config_file)
        if snapshot_file is not None:
            shutil.copyfile(config_file, snapshot_file)


def _update_config_file(config, config_file):
    service = resolve_pdf2zh_next_service(config.service)
    # toml文件, 格式参考server/config/config.toml.example
    
    config_map = pdf2zh_next_config_map.get(service, {})
    if not config_map:
        print(
            f"✏️ No config_map found for service: {service}, 如果是新的服务, 请联系开发者更新config_map"
        )
        return

    with open(config_file, "r", encoding="utf-8") as f:
        old_config = toml.load(f)

    if service == "openai":
        validate_openai_none(config.llm_api, old_config)

    # Relay-only fields never reach config.toml: upstream settings
    # models do not know them. They travel in a side file instead.
    config.relay_options = None
    if service in (pdf2zh_next_custom_service_engine, "openai"):
        config.relay_options = normalize_relay_options(
            config.llm_api.get("extraData")
        )
        if config.relay_options:
            print("🔀 [自定义中转] " + describe_relay_options(config.relay_options))

    # A previous DeepSeek V4 attempt may have written 2.9-only fields.
    # For every non-DeepSeek request, scrub those fields before an older
    # runtime gets a chance to parse the shared config.toml.
    if service != "deepseek":
        old_deepseek_detail = old_config.get("deepseek_detail")
        if isinstance(old_deepseek_detail, dict):
            remove_stale_thinking_fields(old_deepseek_detail, "")

    # extraData is the generic plugin transport. DeepSeek V4 uses it to
    # carry the user's intent, but the server normalizes the values here
    # and execute.py later maps them to the exact upstream CLI flags.
    effective_deepseek_model = ""
    if service == "deepseek":
        effective_deepseek_model = normalize_deepseek_extra_data(
            config.llm_api,
            old_config,
        )
        if is_deepseek_thinking_model(effective_deepseek_model):
            extra_data = config.llm_api.get("extraData") or {}
            thinking_mode = extra_data.get("deepseek_thinking_mode", "disabled")
            # winexe bypasses execute_with_progress(), so protect that
            # execution path here. uv/conda/system runtimes are checked
            # against the exact executable immediately before launch.
            write_thinking_fields = validate_winexe_runtime_if_selected(
                config_file,
                effective_deepseek_model,
                thinking_mode=thinking_mode,
            )
            if not write_thinking_fields:
                extra_data.pop("deepseek_thinking_mode", None)
                extra_data.pop("deepseek_reasoning_effort", None)
                config.llm_api["extraData"] = extra_data

    new_config = old_config.copy()  # 我们假设config.toml文件的格式没有问题

    # Keep request-scoped pdf2zh_next options in config.toml so they work
    # even when there is no dedicated CLI wiring in server.py.
    translation_config = new_config.setdefault("translation", {})
    translation_config["pool_max_workers"] = (
        config.pool_size if config.pool_size > 0 else "null"
    )
    pdf_config = new_config.setdefault("pdf", {})
    pdf_config["only_include_translated_page"] = config.only_include_translated_page
    pdf_config["translate_table_text"] = config.translate_table_text

    translator = None
    if f"{service}_detail" in new_config:
        translator = new_config[f"{service}_detail"]
    else:
        print(f"✏️ 服务 '{service}' 在先前配置中不存在, 创建新配置")
        translator = {}
        new_config[f"{service}_detail"] = translator

    if service == "deepseek":
        remove_stale_thinking_fields(translator, effective_deepseek_model)
    elif service == "openai":
        # Older zotero-pdf2zh releases exposed the correctly spelled
        # key, while pdf2zh_next intentionally retains the historical
        # "temprature" typo. Migrate both saved TOML and persisted
        # plugin extraData without affecting OpenAI-compatible services.
        _normalize_openai_send_temperature_key(translator)
        _normalize_openai_send_temperature_key(config.llm_api.get("extraData"))

    translator_keys = ["translate_engine_type", "support_llm"]
    if "extraData" in config_map:
        for key in config_map["extraData"]:
            translator_keys.append(key)

    keys = ["apiKey", "apiUrl", "model"]
    for key in keys:
        if key in config.llm_api and key in config_map:
            value = config.llm_api[key]
            mapped_key = config_map[key]
            if value not in (None, "", [], {}):
                translator[mapped_key] = value
                translator_keys.append(mapped_key)
                if key == "apiKey":
                    print(
                        f"✏️ 更新 {key}: {mapped_key} = {'*' * 8 + value[-4:] if len(value) > 4 else '*' * len(value)}"
                    )
                else:
                    print(f"✏️ 更新 {key}: {mapped_key} = {value}")
            else:
                translator_keys.append(mapped_key)
                print(f"✏️ 跳过 {key}: {mapped_key} = {value} (empty or null)")

    # 将用户设置的extraData也进行映射, 如果存在映射关系, 则更新
    if "extraData" in config.llm_api and isinstance(
        config.llm_api["extraData"], dict
    ):
        for key, value in config.llm_api["extraData"].items():
            coerced = coerce_pdf2zh_next_extra_value(key, value)
            if coerced not in (None, "", [], {}):
                translator[key] = coerced
                translator_keys.append(key)
                print(f"✏️ 更新 extraData: {key} = {_safe_log_value(key, coerced)}")
            else:
                print(f"✏️ 跳过 extraData: {key} = {value} (empty or null)")

    # 将translator中, 所有不在translator_keys中的key删除
    print(translator.keys())
    for key in list(translator.keys()):
        if key not in translator_keys:
            del translator[key]
            print(f"✏️ 删除旧 {key}")

    if config.relay_options:
        config.relay_options = bind_relay_target(
            config.relay_options,
            base_url=translator.get(config_map.get("apiUrl", ""), ""),
            model=translator.get(config_map.get("model", ""), ""),
            api_key=translator.get(config_map.get("apiKey", ""), ""),
            service=config.custom_service or service,
        )

    with open(config_file, "w", encoding="utf-8") as f:
        toml.dump(new_config, f)
        print(f"✏️ 更新 config file: {config_file}")

    # server.py in older releases uses a legacy singular pool flag.
    # The worker count is already persisted above, so suppress that CLI path.
    config.pool_size = 0
