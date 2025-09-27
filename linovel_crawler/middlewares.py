# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from scrapy import signals
from scrapy.exceptions import IgnoreRequest
import os

# useful for handling different item types with a single interface
from itemadapter import ItemAdapter


class ResumeCrawlerMiddleware:
    """断点续爬中间件"""

    def __init__(self):
        self.pipelines = {}  # 按spider名称存储pipeline引用

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(s.spider_closed, signal=signals.spider_closed)
        return s

    def spider_opened(self, spider):
        """Spider启动时获取pipeline引用"""
        try:
            # 通过crawler.engine.scraper获取pipelines
            if hasattr(spider.crawler, 'engine') and hasattr(spider.crawler.engine, 'scraper'):
                scraper = spider.crawler.engine.scraper
                # 尝试不同的方式获取pipelines
                if hasattr(scraper, 'pipelines'):
                    pipelines = scraper.pipelines
                elif hasattr(scraper, 'slot') and hasattr(scraper.slot, 'pipeline'):
                    pipelines = [scraper.slot.pipeline]
                else:
                    # 最后尝试，直接从crawler的pipelines配置中获取
                    from scrapy.utils.misc import load_object
                    pipelines = []
                    for pipeline_path in spider.crawler.settings.get('ITEM_PIPELINES', {}):
                        try:
                            pipeline_class = load_object(pipeline_path)
                            pipeline_instance = pipeline_class()
                            pipelines.append(pipeline_instance)
                        except:
                            pass

                # 找到DatabasePipeline
                for pipeline in pipelines:
                    if hasattr(pipeline, 'get_crawl_status'):
                        self.pipelines[spider.name] = pipeline
                        spider.logger.info(f"ResumeCrawlerMiddleware: 成功获取 {spider.name} 的pipeline引用")
                        break

        except Exception as e:
            spider.logger.warning(f"ResumeCrawlerMiddleware: 获取pipeline引用失败: {e}")

    def spider_closed(self, spider):
        """Spider关闭时清理"""
        if spider.name in self.pipelines:
            del self.pipelines[spider.name]

    def process_spider_output(self, response, result, spider):
        """处理Spider输出，过滤重复请求"""
        for item_or_request in result:
            # 如果是Request对象，检查是否应该跳过
            if hasattr(item_or_request, 'url') and hasattr(item_or_request, 'callback'):
                should_skip = self.should_skip_request(item_or_request, spider)
                if should_skip:
                    spider.logger.info(f"跳过已处理的请求: {item_or_request.url}")
                    # 缓存已处理的URL，提升性能
                    pipeline = self.pipelines.get(spider.name)
                    if pipeline:
                        pipeline.cache_url(item_or_request.url)
                    continue
            yield item_or_request

    def should_skip_request(self, request, spider):
        """判断是否应该跳过请求"""
        try:
            # 从已存储的pipelines中获取对应spider的pipeline
            pipeline = self.pipelines.get(spider.name)
            if not pipeline:
                return False

            # 检查pipeline是否已经初始化（有数据库连接）
            if not hasattr(pipeline, 'connection') or pipeline.connection is None:
                return False

            # 从URL中提取标识符
            url = request.url
            max_retry_count = spider.crawler.settings.get('RESUME_MAX_RETRY_COUNT', 3)

            # 首先检查Redis缓存，如果已缓存则直接跳过
            if pipeline.is_url_cached(url):
                spider.logger.debug(f"URL已在缓存中，跳过: {url}")
                return True

            # 根据Spider类型和URL判断状态类型
            if spider.name == 'novel_list':
                # 列表页请求
                if 'cat/-1.html?page=' in url:
                    page = url.split('page=')[-1].split('&')[0]
                    status, retry_count = pipeline.get_crawl_status('novel_list', 'list_page', page)

                    # 如果已完成，跳过
                    if status == 'completed':
                        return True

                    # 如果重试次数超过限制，跳过
                    if status == 'failed' and retry_count >= max_retry_count:
                        spider.logger.warning(f"列表页 {page} 重试次数超过限制 ({retry_count}/{max_retry_count})，跳过")
                        return True

                    # 允许重试或继续处理
                    return False

            elif spider.name == 'novel_detail':
                # 详情页请求
                if '/book/' in url and '.html' in url:
                    book_id = url.split('/book/')[-1].split('.html')[0]
                    status, retry_count = pipeline.get_crawl_status('novel_detail', 'detail_page', book_id)

                    # 如果已完成，跳过
                    if status == 'completed':
                        return True

                    # 如果重试次数超过限制，跳过
                    if status == 'failed' and retry_count >= max_retry_count:
                        spider.logger.warning(f"详情页 {book_id} 重试次数超过限制 ({retry_count}/{max_retry_count})，跳过")
                        return True

                    # 允许重试或继续处理
                    return False

            elif spider.name == 'novel_comment':
                # 评论页请求
                if '/comment/items?' in url and 'tid=' in url:
                    book_id = url.split('tid=')[-1].split('&')[0]
                    page = url.split('page=')[-1].split('&')[0] if 'page=' in url else '1'
                    status, retry_count = pipeline.get_crawl_status('novel_comment', 'comment_page', f"{book_id}_{page}")

                    # 如果已完成，跳过
                    if status == 'completed':
                        return True

                    # 如果重试次数超过限制，跳过
                    if status == 'failed' and retry_count >= max_retry_count:
                        spider.logger.warning(f"评论页 {book_id}_{page} 重试次数超过限制 ({retry_count}/{max_retry_count})，跳过")
                        return True

                    # 允许重试或继续处理
                    return False

        except Exception as e:
            # 静默处理错误，不输出警告，因为这在初始化阶段是正常的
            pass

        return False


class LinovelCrawlerSpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    async def process_start(self, start):
        # Called with an async iterator over the spider start() method or the
        # maching method of an earlier spider middleware.
        async for item_or_request in start:
            yield item_or_request

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class LinovelCrawlerDownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)
