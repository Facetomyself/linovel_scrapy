# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

import os
import json
import pymysql
import redis
from datetime import datetime
from urllib.parse import urlparse
import logging
from threading import Lock
from linovel_crawler.items import CrawlStatusItem

logger = logging.getLogger(__name__)


class DatabasePipeline:
    def __init__(self):
        # 加载环境变量
        self.mysql_config = {
            'host': os.getenv('mysql_host'),
            'port': int(os.getenv('mysql_port', 3306)),
            'user': os.getenv('mysql_user'),
            'password': os.getenv('mysql_password'),
            'database': os.getenv('mysql_database'),
            'charset': 'utf8mb4'
        }

        # 兼容带密码与无密码的Redis配置；空字符串视为未设置
        redis_password = os.getenv('redis_password')
        if not redis_password:
            redis_password = None

        # 可选：Redis ACL 用户名
        redis_username = os.getenv('redis_username')
        if not redis_username:
            redis_username = None

        self.redis_config = {
            'host': os.getenv('redis_host'),
            'port': int(os.getenv('redis_port', 6379)),
            'password': redis_password,
            'username': redis_username,
            'decode_responses': True
        }

        # 数据库连接和锁
        self.connection = None
        self.connection_lock = Lock()
        self.redis_client = None

    def _execute_with_lock(self, operation_func, *args, **kwargs):
        """使用锁安全地执行数据库操作"""
        with self.connection_lock:
            if self.connection is None:
                logger.warning("数据库连接不存在，无法执行操作")
                return None
            try:
                return operation_func(*args, **kwargs)
            except pymysql.Error as e:
                logger.error(f"数据库操作失败: {e}")
                # 尝试重连
                try:
                    self.connection.ping(reconnect=True)
                    return operation_func(*args, **kwargs)
                except Exception as reconnect_error:
                    logger.error(f"数据库重连失败: {reconnect_error}")
                    return None

    def open_spider(self, spider):
        """Spider启动时初始化数据库连接"""
        try:
            # 连接MySQL（不指定数据库）
            mysql_config_no_db = self.mysql_config.copy()
            mysql_config_no_db.pop('database', None)

            temp_connection = pymysql.connect(**mysql_config_no_db)

            # 创建数据库，转义数据库名防止注入
            db_name = os.getenv('mysql_database')
            if not db_name:
                raise ValueError("mysql_database环境变量未设置")

            # 验证和转义数据库名（只允许字母、数字、下划线）
            import re
            if not re.match(r'^[a-zA-Z0-9_]+$', db_name):
                raise ValueError(f"数据库名包含非法字符: {db_name}")

            with temp_connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                logger.info(f"数据库 `{db_name}` 创建成功")

            temp_connection.close()

            # 连接到指定数据库
            self.connection = pymysql.connect(**self.mysql_config)
            logger.info("MySQL连接成功")

            # 连接Redis
            try:
                self.redis_client = redis.Redis(**self.redis_config)
                self.redis_client.ping()
                logger.info("Redis连接成功")
            except Exception as e:
                logger.warning(f"Redis连接失败，将禁用Redis缓存: {e}")
                self.redis_client = None

            # 创建表结构
            self.create_tables()

            # 保存spider引用，用于状态检查
            self.current_spider = spider

        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    def close_spider(self, spider):
        """Spider关闭时关闭连接"""
        if self.connection:
            self.connection.close()
        if self.redis_client:
            try:
                self.redis_client.close()
            except:
                pass

    def create_tables(self):
        """自动创建数据库表"""
        with self.connection.cursor() as cursor:
            # 小说基本信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS novels (
                    book_id VARCHAR(20) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    cover_url TEXT,
                    author VARCHAR(100),
                    intro TEXT,
                    tags JSON,
                    word_count INT,
                    popularity INT,
                    favorites INT,
                    status VARCHAR(20),
                    sign_status VARCHAR(50),
                    last_update VARCHAR(50),
                    detail_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # 小说卷信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS novel_volumes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    book_id VARCHAR(20) NOT NULL,
                    volume_index INT NOT NULL,
                    volume_title VARCHAR(255),
                    volume_word_count INT,
                    volume_desc TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_book_volume (book_id, volume_index),
                    FOREIGN KEY (book_id) REFERENCES novels(book_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # 小说章节信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS novel_chapters (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    book_id VARCHAR(20) NOT NULL,
                    volume_index INT,
                    chapter_url TEXT NOT NULL,
                    chapter_title VARCHAR(500),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_chapter_url (chapter_url(500)),
                    FOREIGN KEY (book_id) REFERENCES novels(book_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # 小说评论表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS novel_comments (
                    comment_id VARCHAR(50) PRIMARY KEY,
                    book_id VARCHAR(20) NOT NULL,
                    user_name VARCHAR(100),
                    content TEXT,
                    create_time DATETIME,
                    like_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (book_id) REFERENCES novels(book_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # 爬取状态表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS crawl_status (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    spider_name VARCHAR(50) NOT NULL,
                    status_type VARCHAR(50) NOT NULL,
                    identifier VARCHAR(100) NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    retry_count INT DEFAULT 0,
                    UNIQUE KEY unique_status (spider_name, status_type, identifier)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            self.connection.commit()
            logger.info("数据库表检查/创建完成")

    def process_item(self, item, spider):
        """处理不同的item类型"""
        try:
            logger.debug(f"处理item: {type(item).__name__}, spider: {spider.name}")

            # 检查item类型 - 使用更可靠的方法
            item_class_name = type(item).__name__

            if item_class_name == 'NovelItem':
                # NovelItem
                logger.debug(f"保存小说: {item.get('book_id')} - {item.get('title')[:30] if item.get('title') else 'N/A'}")
                self.save_novel(item)
            elif item_class_name == 'NovelVolumeItem':
                # NovelVolumeItem
                logger.debug(f"保存小说卷: {item.get('book_id')} - {item.get('volume_index')}")
                self.save_novel_volume(item)
            elif item_class_name == 'NovelChapterItem':
                # NovelChapterItem
                logger.debug(f"保存小说章节: {item.get('book_id')} - {item.get('chapter_title')[:30] if item.get('chapter_title') else 'N/A'}")
                self.save_novel_chapter(item)
            elif item_class_name == 'NovelCommentItem':
                # NovelCommentItem
                logger.debug(f"保存评论: {item.get('comment_id')}")
                self.save_novel_comment(item)
            elif item_class_name == 'CrawlStatusItem':
                # CrawlStatusItem
                logger.debug(f"保存爬取状态: {item.get('spider_name')} - {item.get('status_type')} - {item.get('identifier')}")
                self.save_crawl_status(item)
            else:
                logger.warning(f"未知的item类型: {item_class_name}, item内容: {dict(item)}")

            return item

        except Exception as e:
            logger.error(f"处理item失败: {e}, item类型: {type(item)}, item内容: {item}")
            raise

    def save_novel(self, item):
        """保存小说基本信息"""
        with self.connection.cursor() as cursor:
            sql = """
                INSERT INTO novels (
                    book_id, title, cover_url, author, intro, tags,
                    word_count, popularity, favorites, status,
                    sign_status, last_update, detail_url
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title=COALESCE(VALUES(title), title),
                    cover_url=COALESCE(VALUES(cover_url), cover_url),
                    author=COALESCE(VALUES(author), author),
                    intro=COALESCE(VALUES(intro), intro),
                    tags=COALESCE(VALUES(tags), tags),
                    word_count=COALESCE(VALUES(word_count), word_count),
                    popularity=COALESCE(VALUES(popularity), popularity),
                    favorites=COALESCE(VALUES(favorites), favorites),
                    status=COALESCE(VALUES(status), status),
                    sign_status=COALESCE(VALUES(sign_status), sign_status),
                    last_update=COALESCE(VALUES(last_update), last_update),
                    detail_url=COALESCE(VALUES(detail_url), detail_url)
            """
            # 避免用缺失字段覆盖已有值：仅当 item 含有该字段时才写入；否则传 None 以触发 COALESCE 使用旧值
            tags_val = item.get('tags') if 'tags' in item else None
            tags_json = json.dumps(tags_val) if tags_val is not None else None
            cursor.execute(sql, (
                item.get('book_id'),
                item.get('title') if 'title' in item else None,
                item.get('cover_url') if 'cover_url' in item else None,
                item.get('author') if 'author' in item else None,
                item.get('intro') if 'intro' in item else None,
                tags_json,
                item.get('word_count') if 'word_count' in item else None,
                item.get('popularity') if 'popularity' in item else None,
                item.get('favorites') if 'favorites' in item else None,
                item.get('status') if 'status' in item else None,
                item.get('sign_status') if 'sign_status' in item else None,
                item.get('last_update') if 'last_update' in item else None,
                item.get('detail_url') if 'detail_url' in item else None
            ))
            self.connection.commit()
            logger.debug(f"小说保存成功: {item.get('book_id')} - {cursor.rowcount}行受影响")

    def save_novel_volume(self, item):
        """保存小说卷信息"""
        with self.connection.cursor() as cursor:
            sql = """
                INSERT INTO novel_volumes (
                    book_id, volume_index, volume_title, volume_word_count, volume_desc
                ) VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    volume_title=VALUES(volume_title),
                    volume_word_count=VALUES(volume_word_count),
                    volume_desc=VALUES(volume_desc)
            """
            cursor.execute(sql, (
                item.get('book_id'), item.get('volume_index'), item.get('volume_title'),
                item.get('volume_word_count'), item.get('volume_desc')
            ))
            self.connection.commit()

    def save_novel_chapter(self, item):
        """保存小说章节信息"""
        with self.connection.cursor() as cursor:
            sql = """
                INSERT INTO novel_chapters (
                    book_id, volume_index, chapter_url, chapter_title
                ) VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    chapter_title=VALUES(chapter_title)
            """
            cursor.execute(sql, (
                item.get('book_id'), item.get('volume_index'),
                item.get('chapter_url'), item.get('chapter_title')
            ))
            self.connection.commit()

    def save_novel_comment(self, item):
        """保存小说评论"""
        with self.connection.cursor() as cursor:
            sql = """
                INSERT INTO novel_comments (
                    comment_id, book_id, user_name, content, create_time, like_count
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    content=VALUES(content), like_count=VALUES(like_count)
            """
            cursor.execute(sql, (
                item.get('comment_id'), item.get('book_id'), item.get('user_name'),
                item.get('content'), item.get('create_time'), item.get('like_count')
            ))
            self.connection.commit()

    def save_crawl_status(self, item):
        """保存爬取状态"""
        def _save_status():
            with self.connection.cursor() as cursor:
                spider_name = item.get('spider_name')
                status_type = item.get('status_type')
                identifier = item.get('identifier')
                status = item.get('status')

                # 如果是失败状态，自动查询现有重试次数并自增
                retry_count = item.get('retry_count', 0)
                if status == 'failed':
                    # 查询现有记录的retry_count
                    cursor.execute("""
                        SELECT retry_count FROM crawl_status
                        WHERE spider_name=%s AND status_type=%s AND identifier=%s
                    """, (spider_name, status_type, identifier))
                    result = cursor.fetchone()
                    existing_retry_count = result[0] if result else 0
                    retry_count = existing_retry_count + 1

                sql = """
                    INSERT INTO crawl_status (
                        spider_name, status_type, identifier, status, retry_count
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        status=VALUES(status), retry_count=VALUES(retry_count)
                """
                cursor.execute(sql, (
                    spider_name, status_type, identifier, status, retry_count
                ))
                self.connection.commit()
                logger.debug(f"状态保存成功: {spider_name}-{status_type}-{identifier} -> {status} (重试:{retry_count})")

        self._execute_with_lock(_save_status)

    def get_crawl_status(self, spider_name, status_type, identifier):
        """获取爬取状态"""
        def _get_status():
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT status, retry_count FROM crawl_status
                    WHERE spider_name=%s AND status_type=%s AND identifier=%s
                """, (spider_name, status_type, identifier))
                result = cursor.fetchone()
                return result if result else ('pending', 0)

        return self._execute_with_lock(_get_status) or ('pending', 0)

    def update_crawl_status(self, spider_name, status_type, identifier, status, retry_count=0):
        """更新爬取状态"""
        item = CrawlStatusItem()
        item['spider_name'] = spider_name
        item['status_type'] = status_type
        item['identifier'] = identifier
        item['status'] = status
        item['retry_count'] = retry_count
        self.save_crawl_status(item)

    def is_url_cached(self, url, expire_time=3600):
        """检查URL是否已缓存"""
        if not self.redis_client:
            return False
        try:
            cache_key = f"url_cache:{url}"
            return bool(self.redis_client.exists(cache_key))
        except:
            return False

    def cache_url(self, url, expire_time=3600):
        """缓存URL"""
        if not self.redis_client:
            return
        try:
            cache_key = f"url_cache:{url}"
            self.redis_client.setex(cache_key, expire_time, "1")
        except:
            pass
