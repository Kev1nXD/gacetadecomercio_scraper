import random
from datetime import datetime

import tzlocal
from pathlib import Path
from typing import Tuple
from urllib.parse import quote

import scrapy
from scrapy.exceptions import CloseSpider
from scrapy.http import JsonRequest


class PublicationsSpider(scrapy.Spider):
    name = "publications"
    allowed_domains = ["servicios.seprec.gob.bo"]
    base_url = "https://servicios.seprec.gob.bo/api/"

    def __init__(self, output_mode="csv", output_dir=None, max_pages=None, max_sleep=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if output_mode not in ("csv", "files"):
            raise ValueError("output_mode must be 'csv' or 'files'")
        self.output_mode = output_mode
        self.output_dir = output_dir
        self.publication_ids = set()
        try:
            self.max_pages = int(max_pages) if max_pages is not None else None
        except (TypeError, ValueError) as e:
            raise ValueError("max_pages must be a positive integer") from e
        if self.max_pages is not None and self.max_pages < 1:
            raise ValueError("max_pages must be a positive integer")

        try:
            self.max_sleep = int(max_sleep) if max_sleep is not None else None
        except (TypeError, ValueError) as e:
            raise ValueError("max_sleep must be a positive integer") from e
        if self.max_sleep is not None and self.max_sleep < 1:
            raise ValueError("max_sleep must be a positive integer")

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if spider.max_sleep is not None:
            if spider.max_sleep < crawler.settings.getint("RATE_LIMIT_MIN_DELAY", 1):
                raise ValueError("max_sleep must be at least RATE_LIMIT_MIN_DELAY")
            crawler.settings.set("RATE_LIMIT_MAX_DELAY", spider.max_sleep, priority="cmdline")
        timestamp = datetime.now(tzlocal.get_localzone()).strftime("%Y%m%d_%H%M%S_%f")
        base_dir = Path(spider.output_dir or crawler.settings["OUTPUT_DIR"]).expanduser().resolve()
        run_dir = base_dir / timestamp
        crawler.settings.set("OUTPUT_DIR", run_dir, priority="cmdline")
        if spider.output_mode == "files":
            feeds = {}
        elif crawler.settings.getpriority("FEEDS") < 40:
            feeds = {
                (run_dir / f"publications_{timestamp}.csv").as_uri(): {
                    "format": "csv", "overwrite": False, "store_empty": False,
                },
            }
        else:
            feeds = crawler.settings["FEEDS"]
        crawler.settings.set("FEEDS", feeds, priority="cmdline")
        return spider

    @staticmethod
    def get_random_user_agent() -> Tuple[str, str]:
        major = random.randint(130, 155)
        version = f"{major}.0.{random.randint(6000, 8500)}.{random.randint(0, 250)}"
        user_agent = (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{version} Safari/537.36"
        )
        return user_agent, major

    def get_headers(self) -> dict:
        user_agent, major = self.get_random_user_agent()
        return {
          'accept': 'application/json, text/plain, */*',
          'accept-language': 'uk,en-US;q=0.9,en;q=0.8',
          'cache-control': 'no-cache',
          'content-type': 'application/json',
          'origin': 'https://gacetadecomercio.gob.bo',
          'pragma': 'no-cache',
          'priority': 'u=1, i',
          'referer': 'https://gacetadecomercio.gob.bo/',
          'sec-ch-ua': f'"Google Chrome";v="{major}", "Chromium";v="{major}", "Not(A:Brand";v="24"',
          'sec-ch-ua-mobile': '?0',
          'sec-ch-ua-platform': '"Windows"',
          'sec-fetch-dest': 'empty',
          'sec-fetch-mode': 'cors',
          'sec-fetch-site': 'cross-site',
          'sec-fetch-storage-access': 'active',
          'user-agent': user_agent
        }

    async def start(self):
        yield JsonRequest(
            self.base_url + "publicaciones/catalogos/lista", data={"codigo": ""},
            headers=self.get_headers(),
            callback=self.parse_catalog, errback=self.request_failed,
        )

    def read_response(self, response) -> dict:
        try:
            body = response.json()
        except ValueError as e:
            self.logger.error("Expected JSON from %s status code %s", response.url, response.status)
            raise CloseSpider("non_json_response") from e
        if response.status not in (200, 201) or body.get("finalizado") is False:
            self.logger.error("API error at %s: %s", response.url, body.get("mensaje"))
            raise CloseSpider("api_error")
        return body["datos"]

    def parse_catalog(self, response):
        for entry in self.read_response(response):
            yield self.publications_request(entry["codigoParametrica"])

    def publications_request(self, publication_type_id, page=1, retrieved=0, previous_ids=()):
        return JsonRequest(
            self.base_url + "publicaciones",
            data={
                "fechaInicial": "", "fecha": "", "fechaFinal": "", "categoria": "",
                "texto": "", "razonSocial": "", "tipoPublicacion": publication_type_id,
                "matricula": "", "resumen": "", "limite": 100, "pagina": page,
            },
            headers=self.get_headers(),
            callback=self.parse_publications,
            errback=self.request_failed,
            cb_kwargs={
                "publication_type_id": publication_type_id,
                "page": page,
                "retrieved": retrieved,
                "previous_ids": previous_ids,
            },
        )

    def parse_publications(self, response, publication_type_id, page, retrieved, previous_ids):
        data = self.read_response(response)
        rows, total = data["filas"], int(data["total"])
        if not rows and retrieved < total:
            raise CloseSpider("premature_empty_page")
        ids = tuple(row["id"] for row in rows)
        if ids and ids == previous_ids:
            raise CloseSpider("repeated_page")
        for row in rows:
            publication_id = str(row["id"])
            if publication_id not in self.publication_ids:
                self.publication_ids.add(publication_id)
                self.crawler.stats.inc_value("publications/found")
                yield self.publication_request(row)
        retrieved += len(rows)
        if retrieved < total and (self.max_pages is None or page < self.max_pages):
            yield self.publications_request(publication_type_id, page + 1, retrieved, ids)

    def publication_request(self, publication):
        publication_id = quote(str(publication["id"]), safe="")
        return JsonRequest(
            self.base_url + f"publicaciones/{publication_id}",
            headers=self.get_headers(),
            callback=self.parse_publication,
            errback=self.request_failed,
            cb_kwargs={"publication": publication},
        )

    def parse_publication(self, response, publication):
        details = self.read_response(response)
        empresa = publication["empresa"] or {}
        company_name, registration_number = empresa.get('razonSocial', ''), empresa.get('matricula', '')
        yield {
            "company_name": company_name,
            "registration_number": registration_number,
            "document_base64": details.get("documento"),
            "publication_text": details.get("textoCompleto"),
        }

    def request_failed(self, failure):
        self.logger.error("Request failed: %s (%s)", failure.request.url, failure.getErrorMessage())
        raise CloseSpider("request_failed")

    def closed(self, reason):
        stats = self.crawler.stats
        found = stats.get_value("publications/found", 0)
        saved = stats.get_value("publications/saved", 0)
        self.logger.info(
            "Collection summary: found=%d, saved=%d, not_saved=%d, files_saved=%d, "
            "reason=%s, max_pages=%s",
            found, saved, found - saved, stats.get_value("publications/files_saved", 0),
            reason, self.max_pages if self.max_pages is not None else "unlimited",
        )
