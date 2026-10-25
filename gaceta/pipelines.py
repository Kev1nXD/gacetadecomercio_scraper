import base64
import binascii
import logging
import re
from pathlib import Path


logger = logging.getLogger(__name__)


class PublicationFilesPipeline:
    def __init__(self, output_dir, stats):
        self.output_dir = Path(output_dir)
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings["OUTPUT_DIR"], crawler.stats)

    def process_item(self, item):
        document = item.pop("document_base64")
        text = item.pop("publication_text")
        company = self.filename_part(item.get("company_name"), "unknown_company", 45)
        registration = self.filename_part(item.get("registration_number"), "unknown_registration", 20)
        filename = f"{company}_{registration}"
        files = []
        if document:
            try:
                content = base64.b64decode("".join(document.split()), validate=True)
            except (ValueError, binascii.Error):
                logger.error("Invalid PDF Base64 for publication %s", filename)
                self.stats.inc_value("publications/invalid_pdf")
            else:
                if content.startswith(b"%PDF-"):
                    files.append(self.save("files", filename + ".pdf", content))
                else:
                    logger.error("Document is not a PDF for publication %s", filename)
                    self.stats.inc_value("publications/invalid_pdf")
        if text:
            files.append(self.save("files", filename + ".txt", text.encode("utf-8")))
        if not files:
            logger.error("No document or full text for publication %s", filename)
        if files:
            self.stats.inc_value("publications/saved")
        else:
            self.stats.inc_value("publications/missing_content")
        item["file_name"] = ";".join(files)
        item["collection_status"] = "complete" if files else "missing_content"
        return item

    @staticmethod
    def filename_part(value, fallback, length):
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or ""))
        value = re.sub(r"\s+", " ", value).strip(" ._")[:length].rstrip(" .")
        return value or fallback

    def save(self, directory, filename, content):
        relative = Path(directory) / filename
        target = self.output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        index = 2
        while target.exists():
            target = self.output_dir / relative.with_name(f"{relative.stem}_{index}{relative.suffix}")
            index += 1
        relative = target.relative_to(self.output_dir)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
        self.stats.inc_value("publications/files_saved")
        return relative.as_posix()
