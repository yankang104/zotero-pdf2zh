"""PDF product types, layouts and output naming."""

import os

pdf2zh_next = "pdf2zh_next"


PRODUCT_SUFFIXES = (
    ("-mono-cut.pdf", "mono-cut"),
    (".mono-cut.pdf", "mono-cut"),
    ("-dual-cut.pdf", "dual-cut"),
    (".dual-cut.pdf", "dual-cut"),
    ("-crop-compare.pdf", "crop-compare"),
    (".crop-compare.pdf", "crop-compare"),
    ("-compare.pdf", "compare"),
    (".compare.pdf", "compare"),
    ("-cut.pdf", "origin-cut"),
    (".cut.pdf", "origin-cut"),
    ("-mono.pdf", "mono"),
    (".mono.pdf", "mono"),
    ("-dual.pdf", "dual"),
    (".dual.pdf", "dual"),
    (".lr_dual.pdf", "dual"),
    (".tb_dual.pdf", "dual"),
)


def get_filetype(path):
    name = os.path.basename(str(path)).lower()
    for suffix, filetype in PRODUCT_SUFFIXES:
        if name.endswith(suffix):
            return filetype
    return "origin"


def get_dual_mode(path, fallback="TB"):
    name = os.path.basename(str(path))
    if name.endswith(".LR_dual.pdf"):
        return "LR"
    if name.endswith(".TB_dual.pdf"):
        return "TB"
    mode = str(fallback or "TB").upper()
    return mode if mode in {"LR", "TB"} else "TB"


def canonicalize_pdf2zh_next_dual(dual_path, mode, cropper):
    if not dual_path or not os.path.exists(dual_path):
        raise FileNotFoundError(f"Dual file not found: {dual_path}")
    mode = "LR" if str(mode).upper() == "LR" else "TB"
    path = str(dual_path)
    if path.endswith(".LR_dual.pdf") or path.endswith(".TB_dual.pdf"):
        current = get_dual_mode(path)
        if current == mode:
            return path
        lr_path, tb_path = cropper.pdf_dual_mode(path, current, mode)
        return lr_path if mode == "LR" else tb_path
    if path.endswith(".dual.pdf"):
        target = path[: -len(".dual.pdf")] + f".{mode}_dual.pdf"
    else:
        target = (
            path[:-4] + f".{mode}_dual.pdf"
            if path.endswith(".pdf")
            else path + f".{mode}_dual.pdf"
        )
    if os.path.exists(target):
        os.remove(target)
    os.replace(path, target)
    return target


def get_filetype_after_crop(path):
    filetype = get_filetype(path)
    print(f"🔍 [Zotero PDF2zh Server] 获取文件类型: {filetype} from {path}")
    if filetype == "origin":
        return "origin-cut"
    if filetype == "mono":
        return "mono-cut"
    if filetype == "dual":
        return "dual-cut"
    return "unknown"


def get_filetype_after_crop_compare(path):
    filetype = get_filetype(path)
    if filetype in {"origin", "dual", "dual-cut"}:
        return "crop-compare"
    return "unknown"


def get_filetype_after_compare(path):
    filetype = get_filetype(path)
    if filetype in {"origin", "dual"}:
        return "compare"
    return "unknown"


def get_filename_after_process(inpath, outtype, engine):
    inpath = str(inpath)
    intype = get_filetype(inpath)
    if intype == "dual":
        for suffix in (".LR_dual.pdf", ".TB_dual.pdf"):
            if inpath.endswith(suffix):
                base = inpath[: -len(suffix)]
                return base + (
                    f"-{outtype}.pdf"
                    if engine != pdf2zh_next
                    else f".{outtype}.pdf"
                )
    if engine != pdf2zh_next:
        if intype == "origin":
            if outtype == "origin-cut":
                return os.path.splitext(inpath)[0] + "-cut.pdf"
            return os.path.splitext(inpath)[0] + f"-{outtype}.pdf"
        return inpath.replace(f"{intype}.pdf", f"{outtype}.pdf")
    if intype == "origin":
        if outtype == "origin-cut":
            return os.path.splitext(inpath)[0] + ".cut.pdf"
        return os.path.splitext(inpath)[0] + f".{outtype}.pdf"
    return inpath.replace(f"{intype}.pdf", f"{outtype}.pdf")
