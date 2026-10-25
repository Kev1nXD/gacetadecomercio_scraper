from pathlib import Path


BOT_NAME = "gaceta"
SPIDER_MODULES = ["gaceta.spiders"]
NEWSPIDER_MODULE = "gaceta.spiders"

CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_TIMEOUT = 30
DOWNLOAD_DELAY = 0
DOWNLOAD_DELAY_JITTER = 0
RETRY_TIMES = 3

AUTOTHROTTLE_ENABLED = False

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
FEED_EXPORT_ENCODING = "utf-8-sig"
FEEDS = {
    OUTPUT_DIR.as_uri() + "/publications_%(batch_time)s.csv": {
        "format": "csv",
        "overwrite": False,
        "store_empty": False,
    },
}

RATE_LIMIT_MIN_DELAY = 1
RATE_LIMIT_MAX_DELAY = 5
RATE_LIMIT_BACKOFF = 30
RATE_LIMIT_MAX_BACKOFF = 60
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": None,
    "gaceta.middlewares.RateLimitMiddleware": 550,
}

ITEM_PIPELINES = {"gaceta.pipelines.PublicationFilesPipeline": 300}
FEED_EXPORT_FIELDS = ["company_name", "registration_number", "file_name"]
