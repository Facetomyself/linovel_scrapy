import scrapy
import json
import os
from datetime import datetime
from urllib.parse import urljoin
from linovel_crawler.items import NovelCommentItem, CrawlStatusItem


class NovelCommentSpider(scrapy.Spider):
    name = "novel_comment"
    allowed_domains = ["linovel.net"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = os.getenv('base_url', 'https://www.linovel.net')

    def start_requests(self):
        """从参数获取待处理的book_id"""
        book_ids = getattr(self, 'book_ids', None)
        if book_ids:
            for book_id in book_ids.split(','):
                yield scrapy.Request(
                    f"{self.base_url}/comment/items?type=book&tid={book_id.strip()}&pageSize=15&page=1",
                    callback=self.parse_comments,
                    meta={'book_id': book_id.strip(), 'page': 1},
                    dont_filter=True,
                    headers={
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                        'X-Requested-With': 'XMLHttpRequest',
                    }
                )
        else:
            # 如果没有指定book_ids，输出提示
            self.logger.info("未指定book_ids参数，将不爬取任何评论")

    def query_pending_comments(self):
        """查询待处理的评论"""
        # 这个方法会在实际运行时通过pipeline调用数据库
        pass

    def parse_comments(self, response):
        """解析评论API响应"""
        from linovel_crawler.comment_parser import CommentParser

        comment_parser = CommentParser(self.base_url)
        yield from comment_parser.parse_comments(response, self)


    def update_crawl_status(self, spider_name, status_type, identifier, status, retry_count=0):
        """更新爬取状态"""
        # 通过yield CrawlStatusItem来更新状态
        status_item = CrawlStatusItem()
        status_item['spider_name'] = spider_name
        status_item['status_type'] = status_type
        status_item['identifier'] = identifier
        status_item['status'] = status
        status_item['retry_count'] = retry_count
        return status_item
