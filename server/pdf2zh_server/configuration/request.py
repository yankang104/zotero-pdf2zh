from pdf2zh_server.pdf.tables.mode import parse_table_mode, validate_table_runtime
from pdf2zh_server.providers.routing import resolve_provider_route
from pdf2zh_server.engines.wenyi.settings import (
    WENYI_MODEL,
    normalize_wenyi_options,
    wenyi_api_key,
)

pdf2zh_next = "pdf2zh_next"
wenyi = "wenyi"


def stringToBoolean(value):
    if value == "true" or value == "True" or value == True or value == 1:
        return True
    return False


class Config:
    def __init__(self, request_data):
        self.engine = request_data.get("engine", pdf2zh_next)
        if self.engine not in {pdf2zh_next, wenyi}:
            raise ValueError(f"Unsupported translation engine: {self.engine}")

        if self.engine == wenyi:
            self.service = "deepseek"
        else:
            self.service = request_data.get("next_service") or request_data.get(
                "service", "siliconflowfree"
            )
            if not self.service:
                self.service = "siliconflowfree"

        self.sourceLang = request_data.get("sourceLang", "en")
        if self.sourceLang in [None, ""] or len(self.sourceLang) < 2:
            self.sourceLang = "en"
        self.targetLang = request_data.get("targetLang", "zh-CN")
        if self.targetLang in [None, ""] or len(self.targetLang) < 2:
            self.targetLang = "zh-CN"

        self.skip_last_pages = request_data.get("skipLastPages", 0)
        try:
            self.skip_last_pages = int(self.skip_last_pages)
        except (ValueError, TypeError):
            self.skip_last_pages = 0
        if self.skip_last_pages < 0:
            self.skip_last_pages = 0

        self.qps = request_data.get("qps", 4)
        try:
            self.qps = int(self.qps)
        except (ValueError, TypeError):
            self.qps = 4
        if self.qps < 1:
            self.qps = 4

        self.pool_size = request_data.get("poolSize", 0)
        try:
            self.pool_size = int(self.pool_size)
        except (ValueError, TypeError):
            self.pool_size = 0

        # pdf2zh_next uses qps as the worker count when pool_max_workers is unset.
        # Keep 0 as "unset/follow qps" instead of the legacy qps * 10 expansion.
        if self.pool_size < 0:
            self.pool_size = 0
        if self.pool_size > 1000:
            self.pool_size = 1000

        # 如果左右留白部分裁剪太多了, 可以调整pdf_w_offset和pdf_offset_ratio, 宽边裁剪值pdf_w_offset, 窄边裁剪值pdf_w_offset/pdf_offset_ratio
        # TODO: 将裁剪的逻辑添加到zotero配置页面
        self.pdf_w_offset = int(request_data.get("pdf_w_offset", 40))
        self.pdf_h_offset = int(request_data.get("pdf_h_offset", 20))
        self.pdf_offset_ratio = float(request_data.get("pdf_offset_ratio", 5))
        self.pdf_white_margin = int(request_data.get("pdf_white_margin", 0))

        self.mono = stringToBoolean(request_data.get("mono", True))
        self.dual = stringToBoolean(
            request_data.get("dual", self.engine != wenyi)
        )
        self.mono_cut = stringToBoolean(request_data.get("mono_cut", False))
        self.dual_cut = stringToBoolean(request_data.get("dual_cut", False))
        self.crop_compare = stringToBoolean(request_data.get("crop_compare", False))
        self.compare = stringToBoolean(request_data.get("compare", False))
        self.font_family = request_data.get(
            "fontFamily", "auto"
        )  # pdf2zh_next对应的字体选择
        self.dual_mode = request_data.get("dualMode", "LR")
        self.trans_first = stringToBoolean(request_data.get("transFirst", False))
        self.ocr = stringToBoolean(request_data.get("ocr", False))
        self.auto_ocr = stringToBoolean(request_data.get("autoOcr", False))
        self.no_watermark = stringToBoolean(request_data.get("noWatermark", True))
        self.save_auto_extracted_glossary = stringToBoolean(
            request_data.get("saveGlossary", False)
        )
        self.disable_glossary = stringToBoolean(
            request_data.get("disableGlossary", False)
        )
        self.no_dual = stringToBoolean(request_data.get("noDual", False))
        self.no_mono = stringToBoolean(request_data.get("noMono", False))
        self.skip_clean = stringToBoolean(request_data.get("skipClean", False))
        self.enhance_compatibility = stringToBoolean(
            request_data.get("enhanceCompatibility", False)
        )
        self.disable_rich_text_translate = stringToBoolean(
            request_data.get("disableRichTextTranslate", False)
        )
        self.translate_table_text = stringToBoolean(
            request_data.get("translateTableText", False)
        )
        self.skip_references = stringToBoolean(request_data.get("skipReferences", False))
        self.table_mode = parse_table_mode(request_data.get("tableMode"))
        validate_table_runtime(self.table_mode, engine=self.engine)
        if self.table_mode is not None:
            self.translate_table_text = False
        self.ignore_cache = stringToBoolean(request_data.get("ignoreCache", False))
        self.only_include_translated_page = stringToBoolean(
            request_data.get("onlyIncludeTranslatedPage", False)
        )

        print("\n🔍 Config without llm_api: ", self.__dict__)

        self.warnings = []
        self.relay_options = None
        if self.engine == wenyi:
            self.wenyi_options = normalize_wenyi_options(
                request_data["wenyi"] if "wenyi" in request_data else {}
            )
            self.llm_api = {
                "model": WENYI_MODEL,
                "apiKey": wenyi_api_key(request_data.get("llm_api")),
            }
            self.custom_service = None
            return

        self.llm_api = {
            "apiKey": request_data.get("llm_api", {}).get("apiKey", ""),
            "apiUrl": request_data.get("llm_api", {}).get("apiUrl", ""),
            "model": request_data.get("llm_api", {}).get("model", ""),
            "threadnum": request_data.get("llm_api", {}).get(
                "threadNum", 8
            ),  # TODO, 为每个服务单独配置线程数, 暂时不实现
            "extraData": request_data.get("llm_api", {}).get("extraData", {}),
        }

        # 用户自己起名的服务(例如 "my-relay"): pdf2zh_next 不认识这个名字,
        # 实际交给 OpenAI 兼容引擎执行, 名字只用于在插件里区分多条配置。
        self.service, self.custom_service = resolve_provider_route(
            self.engine,
            self.service,
            request_data.get("llm_api") or {},
        )
        if self.custom_service:
            print(f"🔀 自定义服务 '{self.custom_service}' 使用 {self.service} 引擎")
