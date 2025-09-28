import scrapy
import re
import os
from urllib.parse import urljoin
from linovel_crawler.items import NovelItem, NovelVolumeItem, NovelChapterItem, CrawlStatusItem


class NovelListSpider(scrapy.Spider):
    name = "novel_list"
    allowed_domains = ["linovel.net"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = os.getenv('base_url', 'https://www.linovel.net')

    def start_requests(self):
        """开始请求，检查断点续爬"""
        start_page = getattr(self, 'start_page', 1)
        max_pages = getattr(self, 'max_pages', None)

        # 检查是否需要获取总页数
        if not max_pages:
            yield scrapy.Request(
                f"{self.base_url}/cat/-1.html?page=1",
                callback=self.parse_total_pages,
                meta={'page': 1}
            )
        else:
            # 如果指定了最大页数，直接开始爬取
            # 状态检查由ResumeCrawlerMiddleware处理
            for page in range(start_page, max_pages + 1):
                yield scrapy.Request(
                    f"{self.base_url}/cat/-1.html?page={page}",
                    callback=self.parse_list_page,
                    meta={'page': page},
                    dont_filter=True  # 不同页码的URL参数不同，必须允许重复请求
                )

    def parse_total_pages(self, response):
        """解析总页数"""
        try:
            # XPath: //ul[@class="pagination"]/li[position()=last()-1]/a/text()
            total_pages_element = response.xpath('//ul[@class="pagination"]/li[position()=last()-1]/a/text()').get()
            if total_pages_element:
                total_pages = int(total_pages_element.strip())
                self.logger.info(f"总页数: {total_pages}")

                # 生成所有页面的请求
                for page in range(1, total_pages + 1):
                    yield scrapy.Request(
                        f"{self.base_url}/cat/-1.html?page={page}",
                        callback=self.parse_list_page,
                        meta={'page': page},
                        dont_filter=True
                    )
            else:
                # 获取默认最大页数配置，如果无法解析总页数则使用保守的默认值
                default_max_pages = self.crawler.settings.get('DEFAULT_MAX_PAGES', 10)
                self.logger.warning(f"无法获取总页数，使用默认最大页数: {default_max_pages}")
                for page in range(1, default_max_pages + 1):
                    yield scrapy.Request(
                        f"{self.base_url}/cat/-1.html?page={page}",
                        callback=self.parse_list_page,
                        meta={'page': page},
                        dont_filter=True
                    )

        except Exception as e:
            self.logger.error(f"解析总页数失败: {e}")

    def parse_list_page(self, response):
        """解析列表页面"""
        page = response.meta['page']

        try:
            # yield processing状态
            yield self.update_crawl_status('novel_list', 'list_page', str(page), 'processing')

            # XPath: //div[@class='rank-book-list'] 为小说列表
            # XPath: //div[@class='rank-book'] 为单个小说
            novels = response.xpath('//div[@class="rank-book-list"]//div[@class="rank-book"]')

            for novel in novels:
                novel_item = NovelItem()

                # XPath: //div[@class='book-draw'] 小说基本信息中的 //div[@class='book-info']/a/@href 小说详情页 text为小说名
                detail_link = novel.xpath('.//div[@class="book-draw"]//div[@class="book-info"]/a/@href').get()
                if detail_link:
                    novel_item['detail_url'] = urljoin(self.base_url, detail_link)
                    novel_item['title'] = novel.xpath('.//div[@class="book-draw"]//div[@class="book-info"]/a/text()').get()

                    # 提取book_id
                    book_id_match = re.search(r'/book/(\d+)\.html', novel_item['detail_url'])
                    if book_id_match:
                        novel_item['book_id'] = book_id_match.group(1)

                        # 生成详情页请求（状态检查在pipeline中处理）
                        yield scrapy.Request(
                            novel_item['detail_url'],
                            callback=self.parse_novel_detail,
                            meta={'book_id': novel_item['book_id']},
                            dont_filter=True
                        )

                # XPath: //div[@class='book-cover']/img/@src 小说封面
                cover_url = novel.xpath('.//div[@class="book-cover"]/img/@src').get()
                if cover_url:
                    novel_item['cover_url'] = urljoin(self.base_url, cover_url)

                # XPath: //div[@class='book-tags']/a[@class='book-tag']/text() 小说标签
                tags = novel.xpath('.//div[@class="book-tags"]/a[@class="book-tag"]/text()').extract()
                novel_item['tags'] = [tag.strip() for tag in tags if tag.strip()]

                # XPath: //div[@class='book-info']/div[@class='book-intro'] 小说简介
                intro = novel.xpath('.//div[@class="book-info"]/div[@class="book-intro"]/text()').get()
                if intro:
                    novel_item['intro'] = intro.strip()

                # XPath: //div[@class='book-info']/div[@class='book-extra'] 小说作者和更新时间
                extra_info = novel.xpath('.//div[@class="book-info"]/div[@class="book-extra"]/text()').get()
                if extra_info:
                    # 格式通常为 "作者 | 更新时间"
                    parts = extra_info.split('|')
                    if len(parts) >= 2:
                        novel_item['author'] = parts[0].strip()
                        novel_item['last_update'] = parts[1].strip()

                # XPath: //div[@class='rank-book-mask'] 小说最新章节信息
                latest_chapter_info = novel.xpath('.//div[@class="rank-book-mask"]')

                if latest_chapter_info:
                    # 这里可以提取最新章节信息，但暂时不需要具体内容

                    yield novel_item

            # 标记页面为已完成
            yield self.update_crawl_status('novel_list', 'list_page', str(page), 'completed')

        except Exception as e:
            self.logger.error(f"解析列表页面失败 (page {page}): {e}")
            # 发送失败状态，Pipeline会自动处理重试计数
            yield self.update_crawl_status('novel_list', 'list_page', str(page), 'failed')

    def parse_novel_detail(self, response):
        """解析小说详情页 - 获取卷和章节信息"""
        book_id = response.meta['book_id']

        try:
            # 标记详情页处理开始
            yield self.update_crawl_status('novel_detail', 'detail_page', book_id, 'processing')

            # 解析小说详细信息
            novel_item = NovelItem()
            novel_item['book_id'] = book_id

            # 尝试从详情页提取标题
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
                    # 清理标题，去掉网站名称等
                    title = title.strip()
                    if ' - ' in title:
                        title = title.split(' - ')[0]
                    if ' | ' in title:
                        title = title.split(' | ')[0]
                    # 处理页面title格式：书名_轻小说_作者_轻之文库
                    if '_轻小说_' in title and '_轻之文库' in title:
                        parts = title.split('_轻小说_')
                        if len(parts) >= 2:
                            title = parts[0].strip()  # 只取书名部分
                    # 最后的清理
                    title = title.replace('_轻之文库', '').strip()
                    if len(title) > 0 and title != '轻小说文库' and title != '轻之文库':
                        novel_item['title'] = title
                        break

            # 从页面中提取详细信息
            book_data = response.xpath('//div[@class="book-data"]')
            if book_data:
                spans = book_data.xpath('.//span')
                if len(spans) >= 4:
                    # 字数
                    word_count_text = spans[0].xpath('text()').get()
                    if word_count_text:
                        word_match = re.search(r'(\d+)', word_count_text)
                        novel_item['word_count'] = int(word_match.group(1)) if word_match else None

                    # 热度
                    popularity_text = spans[1].xpath('text()').get()
                    if popularity_text:
                        pop_match = re.search(r'(\d+)', popularity_text)
                        novel_item['popularity'] = int(pop_match.group(1)) if pop_match else None

                    # 收藏数
                    favorites_text = spans[2].xpath('text()').get()
                    if favorites_text:
                        fav_match = re.search(r'(\d+)', favorites_text)
                        novel_item['favorites'] = int(fav_match.group(1)) if fav_match else None

                    # 连载状态
                    status_text = spans[3].xpath('text()').get()
                    if status_text:
                        novel_item['status'] = status_text.strip()

            # 签约状态
            sign_info = response.xpath('//div[@class="book-sign-wrp"]')
            if sign_info:
                sign_status = sign_info.xpath('.//div[@class="book-sign"]/text()').get()
                if sign_status:
                    novel_item['sign_status'] = sign_status.strip()

                # 更新时间
                update_time = sign_info.xpath('.//div[@class="book-last-update"]/text()').get()
                if update_time:
                    update_time = update_time.strip()
                    # 清理"更新于"前缀，转换为标准datetime格式
                    if update_time.startswith('更新于'):
                        update_time = update_time.replace('更新于', '').strip()
                    novel_item['last_update'] = update_time

            # 如果有详细信息且标题存在，保存小说信息
            if novel_item.get('title') and any([novel_item.get('word_count'), novel_item.get('popularity'),
                   novel_item.get('favorites'), novel_item.get('status'),
                   novel_item.get('sign_status'), novel_item.get('last_update')]):
                yield novel_item

            # 解析卷和章节信息
            yield from self.parse_chapters(response, book_id)

            # 标记详情页处理完成
            yield self.update_crawl_status('novel_detail', 'detail_page', book_id, 'completed')

            # 同时触发评论Spider的第一个请求
            yield scrapy.Request(
                f"{self.base_url}/comment/items?type=book&tid={book_id}&pageSize=15&page=1",
                callback=self.parse_comments,
                meta={'book_id': book_id, 'page': 1},
                dont_filter=True,
                headers={
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                    'X-Requested-With': 'XMLHttpRequest',
                }
            )

        except Exception as e:
            self.logger.error(f"处理小说详情失败 (book_id: {book_id}): {e}")
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

                    # 只有当必要字段存在时才yield
                    if chapter_item.get('chapter_url') and chapter_item.get('chapter_title'):
                        yield chapter_item

        except Exception as e:
            self.logger.error(f"解析章节列表失败 (book_id: {book_id}): {e}")

    def parse_comments(self, response):
        """解析评论数据"""
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
