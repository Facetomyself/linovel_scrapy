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
        """解析评论JSON数据"""
        book_id = response.meta['book_id']
        page = response.meta['page']

        try:
            # yield processing状态
            yield self.update_crawl_status('novel_comment', 'comment_page', f"{book_id}_{page}", 'processing')

            # 解析JSON响应
            try:
                data = json.loads(response.text)
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON解析失败 (book_id: {book_id}, page: {page}): {e}")
                return

            # 检查是否有评论数据
            if 'items' not in data:
                self.logger.info(f"没有评论数据 (book_id: {book_id}, page: {page})")
                # 标记为已完成
                yield self.update_crawl_status('novel_comment', 'comment_page', f"{book_id}_{page}", 'completed')
                return

            comments = data['items']
            has_more_pages = False

            for comment_data in comments:
                comment_item = NovelCommentItem()
                comment_item['book_id'] = book_id

                # 提取评论ID
                comment_id = comment_data.get('id')
                if comment_id:
                    comment_item['comment_id'] = str(comment_id)

                # 用户名 - 从author字段获取
                author_info = comment_data.get('author', {})
                if isinstance(author_info, dict):
                    comment_item['user_name'] = author_info.get('nick', '')

                # 评论内容
                content = comment_data.get('content', '')
                if content:
                    comment_item['content'] = content.strip()

                # 创建时间 - date字段是时间戳
                create_time = comment_data.get('date')
                if create_time:
                    try:
                        # 时间戳格式
                        if isinstance(create_time, (int, float)):
                            comment_item['create_time'] = datetime.fromtimestamp(create_time)
                        else:
                            comment_item['create_time'] = create_time
                    except Exception as e:
                        self.logger.warning(f"时间解析失败: {create_time} - {e}")
                        comment_item['create_time'] = None

                # 点赞数 - like字段
                like_count = comment_data.get('like', 0)
                comment_item['like_count'] = int(like_count) if like_count else 0

                # 只有当必要字段存在时才yield
                if comment_item.get('comment_id') and comment_item.get('content'):
                    yield comment_item

            # 检查是否还有更多页面 - API返回的总评论数
            total_comments = data.get('count', 0)
            page_size = 15  # API默认每页15条
            max_pages = (total_comments + page_size - 1) // page_size  # 向上取整

            if page < max_pages:
                has_more_pages = True
                next_page = page + 1

                # 生成下一页请求（状态检查在pipeline中处理）
                yield scrapy.Request(
                    f"{self.base_url}/comment/items?type=book&tid={book_id}&pageSize=15&page={next_page}",
                    callback=self.parse_comments,
                    meta={'book_id': book_id, 'page': next_page},
                    dont_filter=True,
                    headers={
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                        'X-Requested-With': 'XMLHttpRequest',
                    }
                )

            # 标记当前页面为已完成
            yield self.update_crawl_status('novel_comment', 'comment_page', f"{book_id}_{page}", 'completed')

            # 如果没有更多页面，也标记书籍级别的完成状态（用于统计目的）
            if not has_more_pages:
                yield self.update_crawl_status('novel_comment', 'book_comments', book_id, 'completed')

        except Exception as e:
            self.logger.error(f"解析评论失败 (book_id: {book_id}, page: {page}): {e}")
            # 获取当前重试次数并增加
            _, current_retry_count = self.get_crawl_status('novel_comment', 'comment_page', f"{book_id}_{page}")
            new_retry_count = current_retry_count + 1
            yield self.update_crawl_status('novel_comment', 'comment_page', f"{book_id}_{page}", 'failed', new_retry_count)

    def get_crawl_status(self, spider_name, status_type, identifier):
        """获取爬取状态"""
        # 在Spider中无法直接访问pipeline，需要通过其他方式
        # 这里返回默认值，实际的状态检查在pipeline中处理
        return 'pending', 0

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
