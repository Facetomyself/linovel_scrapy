# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from scrapy import signals, Request
from scrapy.exceptions import IgnoreRequest
import os

# useful for handling different item types with a single interface
from itemadapter import ItemAdapter


class ResumeCrawlerMiddleware:
    """断点续爬中间件

    改进点：
    - 预加载已完成状态到内存集合，作为Redis不可用时的本地快速判断。
    - 通过本地文件存储（LocalStateStore）在无DB/Redis时也能跨运行跳过已完成任务。
    - 修正原先未使用的 pipelines 字段逻辑，按 spider 维护独立的 pipeline 和状态。
    """

    def __init__(self):
        # 每个 spider 维护独立的 pipeline、内存完成集和本地状态存储
        self.pipelines = {}
        self.completed_map = {}  # spider.name -> set(keys)
        self.local_state = {}    # spider.name -> LocalStateStore
        # 达到重试上限而需要跳过的键集合（仅内存，按 spider 隔离）
        self.retry_skip_map = {}

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(s.spider_closed, signal=signals.spider_closed)
        return s

    def spider_opened(self, spider):
        """Spider启动时预加载状态到内存和Redis（如可用），并加载本地状态文件作为兜底。"""
        # 初始化本地状态存储
        try:
            from linovel_crawler.state_store import LocalStateStore
            state_path = os.path.join('storage', 'state', f'{spider.name}_status.json')
            store = LocalStateStore(state_path)
            store.load()
            self.local_state[spider.name] = store
            self.completed_map[spider.name] = store.snapshot()
            spider.logger.info(f"ResumeCrawlerMiddleware: 已加载本地状态 {len(self.completed_map[spider.name])} 条")
        except Exception as e:
            spider.logger.warning(f"ResumeCrawlerMiddleware: 加载本地状态失败: {e}")
            self.completed_map[spider.name] = set()

        # 连接数据库以预加载更多的已完成状态（如连接失败则忽略）
        pipeline = None
        try:
            from linovel_crawler.pipelines import DatabasePipeline
            pipeline = DatabasePipeline()
            pipeline.open_spider(spider)
            self.pipelines[spider.name] = pipeline

            # 从数据库预加载完成状态到内存，并尽量写入Redis以加速
            self._preload_completed_status(pipeline, spider)
            spider.logger.info(f"ResumeCrawlerMiddleware: {spider.name} 已预加载完成状态")
        except Exception as e:
            spider.logger.warning(f"ResumeCrawlerMiddleware: 预加载数据库状态失败: {e}")
            # 不抛出异常，允许仅依赖本地状态继续

    def _preload_completed_status(self, pipeline, spider):
        """预加载已完成的状态到内存集合，同时可写入Redis缓存。"""
        try:
            completed_status = pipeline._execute_with_lock(lambda: self._query_completed_status(pipeline))
            if completed_status:
                mem_set = self.completed_map.get(spider.name) or set()
                # 写入内存集合
                keys = []
                for record_spider, status_type, identifier in completed_status:
                    cache_key = f"crawl_status:{record_spider}:{status_type}:{identifier}"
                    mem_set.add(cache_key)
                    keys.append(cache_key)
                self.completed_map[spider.name] = mem_set

                # 尝试写入Redis（可选）
                try:
                    if pipeline.redis_client:
                        for k in keys:
                            pipeline.redis_client.set(k, "completed", ex=86400)
                except Exception as cache_error:
                    spider.logger.warning(f"ResumeCrawlerMiddleware: 写入Redis缓存失败: {cache_error}")

                # 合并到本地状态，并持久化一次
                try:
                    store = self.local_state.get(spider.name)
                    if store:
                        store.extend_completed(keys)
                        store.save()
                except Exception as e:
                    spider.logger.warning(f"ResumeCrawlerMiddleware: 本地状态持久化失败: {e}")

                spider.logger.info(f"ResumeCrawlerMiddleware: 预加载 {len(keys)} 个完成状态")
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
        """Spider关闭时持久化本地状态并清理资源"""
        try:
            store = self.local_state.get(spider.name)
            if store:
                # 将内存中的完成集落盘
                mem = self.completed_map.get(spider.name)
                if mem is not None:
                    store.extend_completed(mem)
                store.save()
        except Exception as e:
            spider.logger.warning(f"ResumeCrawlerMiddleware: 关闭时保存本地状态失败: {e}")

        # 关闭并清理pipeline
        pipeline = self.pipelines.pop(spider.name, None)
        if pipeline:
            try:
                pipeline.close_spider(spider)
            except Exception:
                pass

    async def process_spider_output(self, response, result, spider):
        """处理Spider输出，过滤重复请求并动态更新本地完成状态（支持异步输出）"""
        async for item_or_request in result:
            # 1) 状态项：在本地状态中标记完成，便于同一运行内和跨运行跳过
            try:
                item_name = type(item_or_request).__name__
            except Exception:
                item_name = ''

            if item_name == 'CrawlStatusItem':
                try:
                    status = item_or_request.get('status')
                    if status == 'completed':
                        key = f"crawl_status:{item_or_request.get('spider_name')}:{item_or_request.get('status_type')}:{item_or_request.get('identifier')}"
                        # 更新内存集合
                        mem = self.completed_map.get(spider.name)
                        if mem is not None:
                            mem.add(key)
                        else:
                            self.completed_map[spider.name] = {key}
                        # 延迟到关闭时统一保存，避免频繁IO
                except Exception as e:
                    spider.logger.debug(f"ResumeCrawlerMiddleware: 更新本地完成状态失败: {e}")
                # 无论如何，状态项继续传递给后续Pipeline处理
                yield item_or_request
                continue

            # 2) 请求对象：判断是否应跳过
            if isinstance(item_or_request, Request):
                if self.should_skip_request(item_or_request, spider):
                    spider.logger.info(f"跳过已处理的请求: {item_or_request.url}")
                    pipeline = self.pipelines.get(spider.name)
                    if pipeline:
                        try:
                            pipeline.cache_url(item_or_request.url)
                        except Exception:
                            pass
                    continue

            yield item_or_request

    def should_skip_request(self, request, spider):
        """判断是否应该跳过请求：优先检查内存/本地状态，随后可用则检查Redis。"""
        try:
            url = request.url

            # 计算与该请求对应的完成状态键
            cache_key = self._get_cache_key(url, spider)

            # 0) 重试上限跳过集（仅内存）
            if cache_key:
                retry_set = self.retry_skip_map.get(spider.name)
                if retry_set and cache_key in retry_set:
                    return True

            # 1) 先查内存集合（最快速、无需外部依赖）
            if cache_key:
                mem = self.completed_map.get(spider.name)
                if mem and cache_key in mem:
                    return True

                # 2) 再查本地存储（如果尚未在内存中）
                store = self.local_state.get(spider.name)
                if store and store.is_completed(cache_key):
                    # 同步回内存，加速后续判断
                    mem = self.completed_map.setdefault(spider.name, set())
                    mem.add(cache_key)
                    return True

            # 3) 可选：如果Redis可用，检查Redis缓存
            pipeline = self.pipelines.get(spider.name)
            if cache_key and pipeline and getattr(pipeline, 'redis_client', None):
                try:
                    cached_status = pipeline.redis_client.get(cache_key)
                    if cached_status:
                        status_str = cached_status.decode() if isinstance(cached_status, bytes) else cached_status
                        if status_str == "completed":
                            # 同步回内存/本地
                            self.completed_map.setdefault(spider.name, set()).add(cache_key)
                            return True
                except Exception as cache_error:
                    spider.logger.debug(f"读取Redis缓存失败: {cache_key} - {cache_error}")

            # 3.5) 数据库重试阈值判断：超过上限则跳过
            if cache_key and pipeline and getattr(pipeline, 'connection', None):
                parsed = self._parse_cache_key(cache_key)
                if parsed:
                    p_spider, status_type, identifier = parsed
                    try:
                        status, retry_count = pipeline.get_crawl_status(p_spider, status_type, identifier)
                        max_retry = spider.crawler.settings.getint('RESUME_MAX_RETRY_COUNT', 3)
                        if status == 'failed' and retry_count >= max_retry:
                            self.retry_skip_map.setdefault(spider.name, set()).add(cache_key)
                            spider.logger.info(f"跳过已达重试上限的请求: {url} (retry={retry_count}, max={max_retry})")
                            return True
                    except Exception as e:
                        spider.logger.debug(f"查询重试状态失败: {cache_key} - {e}")

            # 4) URL级别的短期缓存（仅作为性能优化）
            if pipeline and hasattr(pipeline, 'is_url_cached') and pipeline.is_url_cached(url):
                return True

            return False
        except Exception as e:
            spider.logger.debug(f"ResumeCrawlerMiddleware: 检查请求状态失败: {e}")
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

    def _parse_cache_key(self, cache_key):
        """将缓存键解析为 (spider_name, status_type, identifier)"""
        try:
            parts = cache_key.split(':', 3)
            if len(parts) == 4 and parts[0] == 'crawl_status':
                return parts[1], parts[2], parts[3]
        except Exception:
            pass
        return None

    async def process_start(self, start):
        """在起始阶段也进行跳过判断，避免已完成任务的首个请求重复发出"""
        async for item_or_request in start:
            if isinstance(item_or_request, Request):
                cb = getattr(item_or_request, 'callback', None)
                spider = getattr(cb, '__self__', None)
                if spider and self.should_skip_request(item_or_request, spider):
                    try:
                        spider.logger.info(f"跳过已处理的起始请求: {item_or_request.url}")
                        pipeline = self.pipelines.get(spider.name)
                        if pipeline:
                            pipeline.cache_url(item_or_request.url)
                    except Exception:
                        pass
                    continue
            yield item_or_request


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

    async def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an (async) iterable of Request, or item objects.
        async for i in result:
            yield i

    async def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        return None

    async def process_start(self, start):
        # Called with an async iterator over the spider start() method or the
        # matching method of an earlier spider middleware.
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

    async def process_spider_output(self, response, result, spider):
        """处理Spider输出，过滤重复请求（支持异步输出）"""
        async for item in result:
            if isinstance(item, Request):  # 这是Request对象
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
