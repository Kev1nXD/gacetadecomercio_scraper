import sys

from scrapy.cmdline import execute


if __name__ == "__main__":
    execute(["scrapy", "crawl", "publications", *sys.argv[1:]])
