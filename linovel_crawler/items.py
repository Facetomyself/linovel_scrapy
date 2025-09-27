# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class NovelItem(scrapy.Item):
    """小说基本信息"""
    book_id = scrapy.Field()  # 小说ID
    title = scrapy.Field()  # 小说标题
    cover_url = scrapy.Field()  # 封面图片URL
    author = scrapy.Field()  # 作者
    intro = scrapy.Field()  # 简介
    tags = scrapy.Field()  # 标签列表
    word_count = scrapy.Field()  # 字数
    popularity = scrapy.Field()  # 热度
    favorites = scrapy.Field()  # 收藏数
    status = scrapy.Field()  # 连载状态
    sign_status = scrapy.Field()  # 签约状态
    last_update = scrapy.Field()  # 最后更新时间
    detail_url = scrapy.Field()  # 详情页URL


class NovelVolumeItem(scrapy.Item):
    """小说卷信息"""
    book_id = scrapy.Field()  # 小说ID
    volume_index = scrapy.Field()  # 卷序号
    volume_title = scrapy.Field()  # 卷标题
    volume_word_count = scrapy.Field()  # 卷字数
    volume_desc = scrapy.Field()  # 卷描述


class NovelChapterItem(scrapy.Item):
    """小说章节信息"""
    book_id = scrapy.Field()  # 小说ID
    volume_index = scrapy.Field()  # 所属卷序号
    chapter_url = scrapy.Field()  # 章节URL
    chapter_title = scrapy.Field()  # 章节标题


class NovelCommentItem(scrapy.Item):
    """小说评论信息"""
    book_id = scrapy.Field()  # 小说ID
    comment_id = scrapy.Field()  # 评论ID
    user_name = scrapy.Field()  # 用户名
    content = scrapy.Field()  # 评论内容
    create_time = scrapy.Field()  # 创建时间
    like_count = scrapy.Field()  # 点赞数


class CrawlStatusItem(scrapy.Item):
    """爬取状态信息"""
    spider_name = scrapy.Field()  # Spider名称
    status_type = scrapy.Field()  # 状态类型 (list_page, detail_page, comment_page)
    identifier = scrapy.Field()  # 标识符 (页码, book_id等)
    status = scrapy.Field()  # 状态 (pending, processing, completed, failed)
    last_update = scrapy.Field()  # 最后更新时间
    retry_count = scrapy.Field()  # 重试次数
