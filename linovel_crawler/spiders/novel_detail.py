import scrapy
import re
import os
from urllib.parse import urljoin
from datetime import datetime
from linovel_crawler.items import NovelItem, NovelVolumeItem, NovelChapterItem, CrawlStatusItem


class NovelDetailSpider(scrapy.Spider):
    name = "novel_detail"
    allowed_domains = ["linovel.net"]
    custom_settings = {
        'JOBDIR': 'storage/jobs/novel_detail',
        'SCHEDULER_PERSIST': True,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = os.getenv('base_url', 'https://www.linovel.net')

    def _iter_start_requests(self):
        """公共起始请求生成器，供 start() 与 start_requests() 复用"""
        book_ids = getattr(self, 'book_ids', None)
        if book_ids:
            for book_id in book_ids.split(','):
                yield scrapy.Request(
                    f"{self.base_url}/book/{book_id.strip()}.html",
                    callback=self.parse_detail,
                    meta={'book_id': book_id.strip()}
                )
        else:
            # 如果没有指定book_ids，输出提示
            self.logger.info("未指定book_ids参数，将不爬取任何详情页")

    def start_requests(self):
        """兼容低版本Scrapy的启动入口"""
        yield from self._iter_start_requests()

    async def start(self):
        """Scrapy 2.13+ 推荐的异步启动入口"""
        for req in self._iter_start_requests():
            yield req

    def query_pending_books(self):
        """查询待处理的书籍"""
        # 这个方法会在实际运行时通过pipeline调用数据库
        pass

    def parse_detail(self, response):
        """解析小说详情页"""
        book_id = response.meta['book_id']

        try:
            # yield processing状态
            yield self.update_crawl_status('novel_detail', 'detail_page', book_id, 'processing')

            # 创建小说基本信息item（如果需要更新）
            novel_item = NovelItem()
            novel_item['book_id'] = book_id
            novel_item['detail_url'] = response.url

            # 解析标题（与列表爬虫逻辑一致，尽量健壮）
            title_selectors = [
                '//title/text()',
                '//meta[@property="og:title"]/@content',
                '//h1[@class="book-title"]/text()',
                '//div[@class="book-title"]/h1/text()',
                '//h1/text()'
            ]
            for selector in title_selectors:
                title = response.xpath(selector).get()
                if title:
                    title = title.strip()
                    if ' - ' in title:
                        title = title.split(' - ')[0]
                    if ' | ' in title:
                        title = title.split(' | ')[0]
                    if '_轻小说_' in title and '_轻之文库' in title:
                        parts = title.split('_轻小说_')
                        if len(parts) >= 2:
                            title = parts[0].strip()
                    title = title.replace('_轻之文库', '').strip()
                    if len(title) > 0 and title not in ('轻小说文库', '轻之文库'):
                        novel_item['title'] = title
                        break

            # XPath: //div[@class='book-data'] 为小说基本数据
            book_data = response.xpath('//div[@class="book-data"]')
            if book_data:
                spans = book_data.xpath('.//span')
                if len(spans) >= 4:
                    # 依次为：字数、热度、收藏、连载状态
                    word_count_text = spans[0].xpath('text()').get()
                    if word_count_text:
                        # 提取数字部分，如 "123456字" -> 123456
                        word_match = re.search(r'(\d+)', word_count_text)
                        novel_item['word_count'] = int(word_match.group(1)) if word_match else None

                    popularity_text = spans[1].xpath('text()').get()
                    if popularity_text:
                        pop_match = re.search(r'(\d+)', popularity_text)
                        novel_item['popularity'] = int(pop_match.group(1)) if pop_match else None

                    favorites_text = spans[2].xpath('text()').get()
                    if favorites_text:
                        fav_match = re.search(r'(\d+)', favorites_text)
                        novel_item['favorites'] = int(fav_match.group(1)) if fav_match else None

                    status_text = spans[3].xpath('text()').get()
                    if status_text:
                        novel_item['status'] = status_text.strip()

            # XPath: //div[@class='book-sign-wrp'] 小说签约信息
            sign_info = response.xpath('//div[@class="book-sign-wrp"]')
            if sign_info:
                # 小说签约状态
                sign_status = sign_info.xpath('.//div[@class="book-sign"]/text()').get()
                if sign_status:
                    novel_item['sign_status'] = sign_status.strip()

                # 小说更新时间
                update_time = sign_info.xpath('.//div[@class="book-last-update"]/text()').get()
                if update_time:
                    novel_item['last_update'] = update_time.strip()

            # 如果有新信息，yield小说item
            if any([novel_item.get('title'), novel_item.get('word_count'), novel_item.get('popularity'),
                   novel_item.get('favorites'), novel_item.get('status'),
                   novel_item.get('sign_status'), novel_item.get('last_update'), novel_item.get('detail_url')]):
                yield novel_item

            # 解析章节列表
            yield from self.parse_chapters(response, book_id)

            # 标记为已完成
            yield self.update_crawl_status('novel_detail', 'detail_page', book_id, 'completed')

        except Exception as e:
            self.logger.error(f"解析小说详情失败 (book_id: {book_id}): {e}")
            # 发送失败状态，Pipeline会自动处理重试计数
            yield self.update_crawl_status('novel_detail', 'detail_page', book_id, 'failed')

    def parse_chapters(self, response, book_id):
        """解析章节列表"""
        try:
            # XPath: //div[@class='section-list'] 为小说章节列表
            section_list = response.xpath('//div[@class="section-list"]')
            self.logger.info(f"book_id {book_id}: 找到 {len(section_list)} 个section-list")

            if not section_list:
                self.logger.warning(f"book_id {book_id}: 未找到section-list")
                return

            # XPath: //div[@class='section-list']/div[@class='section'] 为小说卷章节列表
            sections = section_list.xpath('.//div[@class="section"]')
            self.logger.info(f"book_id {book_id}: 找到 {len(sections)} 个section")

            for section_index, section in enumerate(sections, 1):
                self.logger.debug(f"book_id {book_id}: 处理section {section_index}")
                # 解析卷信息
                volume_item = NovelVolumeItem()
                volume_item['book_id'] = book_id
                volume_item['volume_index'] = section_index

                # XPath: //div[@class='section-list']/div[@class='section']/div[@class='volume-info'] 为卷信息区域
                volume_info = section.xpath('.//div[@class="volume-info"]')

                if volume_info:
                    # 卷标题
                    volume_title_elem = volume_info.xpath('.//h2[@class="volume-title"]/a/text()').get()
                    if volume_title_elem:
                        volume_item['volume_title'] = volume_title_elem.strip()

                    # 卷字数信息
                    volume_hint = volume_info.xpath('.//div[@class="volume-hint"]/text()').get()
                    if volume_hint:
                        word_match = re.search(r'(\d+)', volume_hint)
                        if word_match:
                            volume_item['volume_word_count'] = int(word_match.group(1))

                    # 卷描述内容
                    volume_desc_elem = volume_info.xpath('.//div[@class="volume-desc"]//div[@class="text-content-actual"]')
                    if volume_desc_elem:
                        desc_parts = volume_desc_elem.xpath('.//text()').extract()
                        if desc_parts:
                            volume_item['volume_desc'] = ''.join(desc_parts).strip()

                    yield volume_item

                # 解析章节列表
                # XPath: //div[@class='section']/div[@class='chapter']/a
                chapters = section.xpath('.//div[@class="chapter"]/a')
                self.logger.debug(f"book_id {book_id}: section {section_index} 找到 {len(chapters)} 个章节")

                for chapter in chapters:
                    chapter_item = NovelChapterItem()
                    chapter_item['book_id'] = book_id
                    chapter_item['volume_index'] = section_index

                    # 章节URL
                    chapter_url = chapter.xpath('@href').get()
                    if chapter_url:
                        chapter_item['chapter_url'] = urljoin(self.base_url, chapter_url)

                    # 章节标题
                    chapter_title = chapter.xpath('text()').get()
                    if chapter_title:
                        chapter_item['chapter_title'] = chapter_title.strip()

                    if chapter_item.get('chapter_url') and chapter_item.get('chapter_title'):
                        yield chapter_item

        except Exception as e:
            self.logger.error(f"解析章节列表失败 (book_id: {book_id}): {e}")


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
