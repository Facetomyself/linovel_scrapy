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
        self.shared_pipeline = None  # 共享的pipeline实例，用于缓存检查

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(s.spider_closed, signal=signals.spider_closed)
        return s

    def spider_opened(self, spider):
        """Spider启动时预加载已完成的状态到Redis缓存"""
        try:
            # 创建一个临时的pipeline实例来访问数据库
            from linovel_crawler.pipelines import DatabasePipeline
            temp_pipeline = DatabasePipeline()

            # 初始化pipeline以建立数据库连接
            temp_pipeline.open_spider(spider)

            # 从数据库加载所有已完成的状态到Redis缓存
            self._preload_completed_status(temp_pipeline, spider)

            # 清理临时pipeline
            temp_pipeline.close_spider(spider)

            spider.logger.info(f"ResumeCrawlerMiddleware: {spider.name} 已预加载完成状态到缓存")

        except Exception as e:
            spider.logger.warning(f"ResumeCrawlerMiddleware: 预加载状态失败: {e}")

    def _preload_completed_status(self, pipeline, spider):
        """预加载已完成的状态到Redis缓存"""
        try:
            # 查询所有已完成的状态
            completed_status = pipeline._execute_with_lock(lambda: self._query_completed_status(pipeline))
            if completed_status:
                # 将状态缓存到Redis
                for record_spider, status_type, identifier in completed_status:
                    cache_key = f"crawl_status:{record_spider}:{status_type}:{identifier}"
                    pipeline.redis_client.set(cache_key, "completed", ex=86400)  # 缓存24小时
                    spider.logger.debug(f"缓存完成状态: {cache_key} = completed")

                spider.logger.info(f"ResumeCrawlerMiddleware: 预加载了 {len(completed_status)} 个完成状态")

        except Exception as e:
            spider.logger.warning(f"ResumeCrawlerMiddleware: 预加载状态查询失败: {e}")

    def _query_completed_status(self, pipeline):
        """查询数据库中的所有完成状态"""
        cursor = pipeline.connection.cursor()
        cursor.execute("""
            SELECT spider_name, status_type, identifier
            FROM crawl_status
            WHERE status = 'completed'
        """)
        return cursor.fetchall()

    def spider_closed(self, spider):
        """Spider关闭时清理"""
        if spider.name in self.pipelines:
            del self.pipelines[spider.name]

        # 清理共享的pipeline实例
        if self.shared_pipeline:
            try:
                self.shared_pipeline.close_spider(spider)
            except:
                pass
            self.shared_pipeline = None

    async def process_spider_output(self, response, result, spider):
        """处理Spider输出，过滤重复请求"""
        async for item_or_request in result:
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
        """判断是否应该跳过请求 - 直接检查Redis缓存"""
        try:
            url = request.url

            # 使用共享的pipeline实例，避免重复创建
            if self.shared_pipeline is None:
                from linovel_crawler.pipelines import DatabasePipeline
                self.shared_pipeline = DatabasePipeline()
                self.shared_pipeline.open_spider(spider)

            pipeline = self.shared_pipeline

            # 检查Redis缓存中是否有完成状态
            cache_key = self._get_cache_key(url, spider)
            if cache_key:
                try:
                    cached_status = pipeline.redis_client.get(cache_key)
                    if cached_status:
                        status_str = cached_status.decode() if isinstance(cached_status, bytes) else cached_status
                        if status_str == "completed":
                            spider.logger.info(f"跳过已完成的请求: {url}")
                            return True
                except Exception as cache_error:
                    spider.logger.warning(f"读取缓存失败: {cache_key} - {cache_error}")

            # 检查URL缓存（已处理的URL）
            if pipeline.is_url_cached(url):
                spider.logger.debug(f"跳过已处理的URL: {url}")
                return True

            spider.logger.debug(f"允许请求: {url}")
            return False

        except Exception as e:
            spider.logger.warning(f"ResumeCrawlerMiddleware: 检查请求状态失败: {e}")
            import traceback
            spider.logger.debug(f"详细错误: {traceback.format_exc()}")
            return False

    def _get_cache_key(self, url, spider):
        """根据URL生成缓存键"""
        try:
            # 列表页面
            if 'cat/-1.html?page=' in url:
                page = url.split('page=')[-1].split('&')[0]
                return f"crawl_status:novel_list:list_page:{page}"

            # 详情页面
            elif '/book/' in url and url.endswith('.html'):
                import re
                match = re.search(r'/book/(\d+)\.html', url)
                if match:
                    book_id = match.group(1)
                    return f"crawl_status:novel_detail:detail_page:{book_id}"
                else:
                    spider.logger.debug(f"详情页面URL格式异常: {url}")

            # 评论API
            elif '/comment/items' in url and 'type=book' in url:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(url)
                query = parse_qs(parsed.query)
                book_id = query.get('tid', [''])[0]
                page = query.get('page', ['1'])[0]
                if book_id:
                    return f"crawl_status:novel_comment:comment_page:{book_id}_{page}"

            return None

        except Exception as e:
            spider.logger.warning(f"生成缓存键失败: {url} - {e}")
            return None


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


class DuplicateRequestFilterMiddleware:
    """
    自定义重复请求过滤中间件

    通过自定义请求指纹生成逻辑，避免真正的重复请求，
    同时允许业务需要的参数化请求。
    """

    def __init__(self):
        self.seen_requests = set()

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_spider_output(self, response, result, spider):
        """处理Spider输出，过滤重复请求"""
        for item in result:
            if hasattr(item, 'url'):  # 这是Request对象
                # 生成自定义指纹
                fingerprint = self._get_request_fingerprint(item, spider)
                if fingerprint and fingerprint in self.seen_requests:
                    spider.logger.debug(f"过滤重复请求: {item.url} (指纹: {fingerprint[:16]}...)")
                    continue

                # 记录已处理的请求指纹
                if fingerprint:
                    self.seen_requests.add(fingerprint)

            yield item

    def _get_request_fingerprint(self, request, spider):
        """
        生成自定义请求指纹

        根据不同类型的请求生成合适的指纹，避免不必要的重复。
        """
        url = request.url

        try:
            # 对于列表页面请求：基于页码生成指纹
            if spider.name == 'novel_list' and '/cat/-1.html?page=' in url:
                page = url.split('page=')[-1].split('&')[0]
                return f"list_page_{page}"

            # 对于详情页请求：基于book_id生成指纹
            elif spider.name == 'novel_detail' and '/book/' in url:
                # 提取book_id
                import re
                match = re.search(r'/book/(\d+)\.html', url)
                if match:
                    book_id = match.group(1)
                    return f"detail_page_{book_id}"

            # 对于评论API请求：基于book_id和页码生成指纹
            elif '/comment/items' in url and 'type=book' in url:
                # 解析查询参数
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(url)
                query = parse_qs(parsed.query)

                book_id = query.get('tid', [''])[0]
                page = query.get('page', ['1'])[0]

                if book_id:
                    return f"comment_{book_id}_{page}"

            # 其他请求使用默认URL作为指纹
            else:
                return url

        except Exception as e:
            spider.logger.warning(f"生成请求指纹失败: {url} - {e}")
            return url  # 出错时使用完整URL作为指纹
