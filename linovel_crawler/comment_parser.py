"""
评论数据解析工具模块

提供独立的评论解析功能，避免Spider间的直接耦合。
"""

import json
import scrapy
from datetime import datetime


class CommentParser:
    """评论解析器"""

    def __init__(self, base_url):
        self.base_url = base_url

    def parse_comments(self, response, spider):
        """
        解析评论API响应

        Args:
            response: Scrapy响应对象
            spider: 调用该方法的Spider实例

        Yields:
            NovelCommentItem: 评论数据项
        """
        from linovel_crawler.items import NovelCommentItem, CrawlStatusItem

        book_id = response.meta['book_id']
        page = response.meta['page']

        try:
            yield spider.update_crawl_status('novel_comment', 'comment_page', f"{book_id}_{page}", 'processing')

            data = json.loads(response.text)

            if 'items' not in data:
                spider.logger.info(f"没有评论数据 (book_id: {book_id}, page: {page})")
                yield spider.update_crawl_status('novel_comment', 'comment_page', f"{book_id}_{page}", 'completed')
                return

            comments = data['items']
            has_more_pages = False

            for comment_data in comments:
                comment_item = NovelCommentItem()
                comment_item['book_id'] = book_id
                comment_item['comment_id'] = str(comment_data.get('id'))
                comment_item['user_name'] = comment_data.get('author', {}).get('nick', '')
                comment_item['content'] = comment_data.get('content', '').strip()

                create_time = comment_data.get('date')
                if create_time:
                    comment_item['create_time'] = datetime.fromtimestamp(create_time)

                comment_item['like_count'] = int(comment_data.get('like', 0))

                if comment_item.get('comment_id') and comment_item.get('content'):
                    yield comment_item

            total_comments = data.get('count', 0)
            page_size = 15
            max_pages = (total_comments + page_size - 1) // page_size

            if page < max_pages:
                has_more_pages = True
                next_page = page + 1
                yield scrapy.Request(
                    f"{self.base_url}/comment/items?type=book&tid={book_id}&pageSize=15&page={next_page}",
                    callback=lambda r: self.parse_comments(r, spider),
                    meta={'book_id': book_id, 'page': next_page},
                    headers={
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                        'X-Requested-With': 'XMLHttpRequest',
                    }
                )

            yield spider.update_crawl_status('novel_comment', 'comment_page', f"{book_id}_{page}", 'completed')

            if not has_more_pages:
                # 标记书籍级别的完成状态（用于统计目的）
                yield spider.update_crawl_status('novel_comment', 'book_comments', book_id, 'completed')

        except Exception as e:
            spider.logger.error(f"解析评论失败 (book_id: {book_id}, page: {page}): {e}")
            # 发送失败状态，Pipeline会自动处理重试计数
            yield spider.update_crawl_status('novel_comment', 'comment_page', f"{book_id}_{page}", 'failed')
