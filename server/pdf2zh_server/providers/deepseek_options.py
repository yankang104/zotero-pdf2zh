from __future__ import annotations

from typing import Any

THINKING_MODE_FIELD = "deepseek_thinking_mode"


REASONING_EFFORT_FIELD = "deepseek_reasoning_effort"


THINKING_MODE_FLAG = "--deepseek-thinking-mode"


REASONING_EFFORT_FLAG = "--deepseek-reasoning-effort"


FLASH_PATCH_FLAG = "--zotero-deepseek-flash-patch"


DEEPSEEK_EFFORT_VALUES = ("minimal", "low", "medium", "high", "xhigh", "max", "ultra")


_RUNTIME_CAPABILITY_CACHE: dict[tuple[str, ...], bool] = {}


def is_deepseek_v4_model(model: Any) -> bool:
    return str(model or "").strip().startswith("deepseek-v4-")


def is_deepseek_flash_model(model: Any) -> bool:
    """Only the officially documented new model, never a wildcard prefix."""
    return str(model or "").strip() == "deepseek-flash"


def is_deepseek_thinking_model(model: Any) -> bool:
    return is_deepseek_v4_model(model) or is_deepseek_flash_model(model)


def resolved_thinking_mode(value: Any) -> str:
    """Treat missing/legacy empty values as disabled (no thinking)."""
    mode = str(value or "disabled").strip().lower()
    if mode in {"", "null", "none"}:
        return "disabled"
    if mode not in {"enabled", "disabled"}:
        raise ValueError("DeepSeek V4 思考模式只能是 enabled 或 disabled。")
    return mode


def thinking_runtime_policy(mode: Any, supported: bool) -> str:
    """Decide how to handle a V4 request against the actual runtime.

    - ``pass-flags``: runtime understands thinking controls; send them explicitly
    - ``strip-and-allow``: user did not enable thinking; old runtime can proceed
    - ``block``: user enabled thinking but the runtime cannot honor it
    """
    resolved = resolved_thinking_mode(mode)
    if supported:
        return "pass-flags"
    if resolved == "enabled":
        return "block"
    return "strip-and-allow"


def normalize_deepseek_extra_data(llm_api: dict, old_config: dict) -> str:
    """Normalize request-scoped DeepSeek controls and return the effective model.

    The plugin uses extraData as its generic transport. For V4 we always make
    thinking explicit so an older saved configuration cannot accidentally fall
    back to the provider's thinking default. For non-V4 models the V4-only
    fields are removed before writing the pdf2zh_next configuration.
    """
    extra_data = llm_api.get("extraData")
    if not isinstance(extra_data, dict):
        extra_data = {}
    else:
        extra_data = dict(extra_data)

    configured_model = (
        old_config.get("deepseek_detail", {}).get("deepseek_model", "")
        if isinstance(old_config.get("deepseek_detail", {}), dict)
        else ""
    )
    effective_model = str(llm_api.get("model") or configured_model or "").strip()
    if effective_model.casefold() == "deepseek-flash" and not is_deepseek_flash_model(
        effective_model
    ):
        raise ValueError(
            "DeepSeek 模型名区分大小写，请使用精确名称 deepseek-flash；"
            "为避免思考参数被忽略，本次没有发起 API 请求。"
        )

    if not is_deepseek_thinking_model(effective_model):
        extra_data.pop(THINKING_MODE_FIELD, None)
        extra_data.pop(REASONING_EFFORT_FIELD, None)
        llm_api["extraData"] = extra_data
        return effective_model

    mode = resolved_thinking_mode(extra_data.get(THINKING_MODE_FIELD))
    extra_data[THINKING_MODE_FIELD] = mode

    if mode == "enabled":
        effort = str(extra_data.get(REASONING_EFFORT_FIELD) or "high").strip().lower()
        if effort not in {"low", "high", "max"}:
            raise ValueError("DeepSeek reasoning effort 仅支持 low/high/max。")
        extra_data[REASONING_EFFORT_FIELD] = effort
    else:
        extra_data.pop(REASONING_EFFORT_FIELD, None)

    llm_api["extraData"] = extra_data
    return effective_model


def remove_stale_thinking_fields(translator: dict, effective_model: str) -> None:
    if is_deepseek_thinking_model(effective_model):
        return
    translator.pop(THINKING_MODE_FIELD, None)
    translator.pop(REASONING_EFFORT_FIELD, None)
