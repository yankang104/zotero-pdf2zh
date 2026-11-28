"""Resolve the execution service while retaining a custom provider's name."""

from pdf2zh_server.providers.catalog import (
    is_known_pdf2zh_next_service,
    pdf2zh_next_custom_service_engine,
)


def resolve_provider_route(engine, service, llm_api):
    """Return (execution_service, custom_provider_name) for a saved selection.

    Built-in services keep their existing alias handling. Custom provider names
    use the OpenAI-compatible engine; their API format remains in extraData for
    the request modules to process.
    """
    uses_custom_provider = (
        engine == "pdf2zh_next"
        and not is_known_pdf2zh_next_service(service)
        and llm_api.get("service") == service
        and str(llm_api.get("apiUrl") or "").strip()
    )
    if uses_custom_provider:
        return pdf2zh_next_custom_service_engine, service
    return service, None
