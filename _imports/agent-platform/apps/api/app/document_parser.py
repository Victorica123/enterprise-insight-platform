from io import BytesIO
from pathlib import Path
import re
import unicodedata


SUPPORTED_EXTENSIONS = (".txt", ".md", ".pdf")


def is_supported_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS


def parse_document(filename: str, raw: bytes) -> str:
    extension = Path(filename).suffix.lower()

    if extension in {".txt", ".md"}:
        return parse_text(raw)

    if extension == ".pdf":
        return parse_pdf(raw)

    supported = ", ".join(SUPPORTED_EXTENSIONS)
    raise ValueError(f"Only {supported} files are supported.")


def parse_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Text file must be UTF-8 encoded.") from exc


def parse_pdf(raw: bytes) -> str:
    errors: list[str] = []

    try:
        return parse_pdf_with_pymupdf(raw)
    except ImportError:
        errors.append("PyMuPDF is not installed.")
    except ValueError as exc:
        raise exc
    except Exception as exc:
        errors.append(f"PyMuPDF failed: {exc}")

    try:
        return parse_pdf_with_pypdf(raw)
    except ImportError:
        errors.append("pypdf is not installed.")
    except ValueError as exc:
        raise exc
    except Exception as exc:
        errors.append(f"pypdf failed: {exc}")

    raise RuntimeError(
        "PDF support requires PyMuPDF or pypdf. Please run pip install -r requirements.txt. "
        + " ".join(errors)
    )


def parse_pdf_with_pymupdf(raw: bytes) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise ImportError("PyMuPDF is not installed.") from exc

    try:
        with fitz.open(stream=raw, filetype="pdf") as document:
            pages = []
            for page_index, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                if text:
                    pages.append(f"[PDF page {page_index}]\n{clean_extracted_text(text)}")
    except Exception as exc:
        raise ValueError("PDF could not be parsed. Please check whether the file is valid or encrypted.") from exc

    text = "\n\n".join(pages)
    if not text.strip():
        raise ValueError("No readable text was found in the PDF.")

    return text


def parse_pdf_with_pypdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError("pypdf is not installed.") from exc

    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError("PDF is encrypted and cannot be parsed.")

        pages = []
        for page_index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"[PDF page {page_index}]\n{clean_extracted_text(text)}")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF could not be parsed. Please check whether the file is valid or encrypted.") from exc

    text = "\n\n".join(pages)
    if not text.strip():
        raise ValueError("No readable text was found in the PDF.")

    return text


def clean_extracted_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = add_breaks_before_common_fields(normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)

    lines = [line.strip() for line in normalized.split("\n")]
    merged_lines: list[str] = []

    for line in lines:
        if not line:
            if merged_lines and merged_lines[-1]:
                merged_lines.append("")
            continue

        if should_merge_with_previous(merged_lines, line):
            merged_lines[-1] = merged_lines[-1] + line
        else:
            merged_lines.append(line)

    return "\n".join(merged_lines).strip()


def should_merge_with_previous(lines: list[str], current_line: str) -> bool:
    if not lines or not lines[-1]:
        return False

    previous_line = lines[-1]
    sentence_endings = "。！？；：.!?;:"
    if previous_line.endswith(tuple(sentence_endings)):
        return False

    if looks_like_heading(previous_line) or looks_like_heading(current_line):
        return False

    return contains_cjk(previous_line) or contains_cjk(current_line)


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def looks_like_heading(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) <= 20 and stripped.endswith(("：", ":")):
        return True

    return bool(re.match(r"^(第[一二三四五六七八九十\d]+[章节条]|[一二三四五六七八九十\d]+[、.．])", stripped))


def add_breaks_before_common_fields(text: str) -> str:
    fields = [
        "客户",
        "项目",
        "原计划交付日期",
        "调整后交付日期",
        "项目负责人",
        "延期原因",
        "合同风险",
        "建议动作",
    ]

    result = text
    for field in fields:
        result = re.sub(rf"(?<!\n)({field}\s*[:：])", r"\n\1", result)

    return result
