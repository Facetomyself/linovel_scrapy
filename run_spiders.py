#!/usr/bin/env python3
"""
小说爬虫启动脚本
支持断点续爬和多种运行模式
"""

import os
import sys
import argparse
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 确保从项目目录运行
project_dir = os.path.dirname(os.path.abspath(__file__))
if os.getcwd() != project_dir:
    os.chdir(project_dir)
    sys.path.insert(0, project_dir)

def run_novel_list_spider(max_pages=None, start_page=1):
    """运行小说列表爬虫"""
    settings = get_project_settings()
    process = CrawlerProcess(settings)

    spider_args = {}
    if max_pages:
        spider_args['max_pages'] = max_pages
        spider_args['start_page'] = start_page

    process.crawl('novel_list', **spider_args)
    process.start()

def run_novel_detail_spider(book_ids=None):
    """运行小说详情爬虫"""
    settings = get_project_settings()
    process = CrawlerProcess(settings)

    spider_args = {}
    if book_ids:
        spider_args['book_ids'] = book_ids

    process.crawl('novel_detail', **spider_args)
    process.start()

def run_novel_comment_spider(book_ids=None):
    """运行小说评论爬虫"""
    settings = get_project_settings()
    process = CrawlerProcess(settings)

    spider_args = {}
    if book_ids:
        spider_args['book_ids'] = book_ids

    process.crawl('novel_comment', **spider_args)
    process.start()

def run_all_spiders(max_pages=None, book_ids=None):
    """运行所有爬虫"""
    settings = get_project_settings()
    process = CrawlerProcess(settings)

    if book_ids:
        # 如果指定了book_ids，运行所有爬虫
        spider_args_list = {}
        if max_pages:
            spider_args_list['max_pages'] = max_pages

        spider_args_detail = {'book_ids': book_ids}
        spider_args_comment = {'book_ids': book_ids}

        process.crawl('novel_list', **spider_args_list)
        process.crawl('novel_detail', **spider_args_detail)
        process.crawl('novel_comment', **spider_args_comment)
    else:
        # 如果没有指定book_ids，运行列表爬虫（它会自动触发详情页和评论页的爬取）
        spider_args_list = {}
        if max_pages:
            spider_args_list['max_pages'] = max_pages

        process.crawl('novel_list', **spider_args_list)

    process.start()

def main():
    parser = argparse.ArgumentParser(description='小说爬虫启动脚本')
    parser.add_argument('spider', choices=['list', 'detail', 'comment', 'all'],
                       help='要运行的爬虫类型')
    parser.add_argument('--max-pages', type=int, help='列表爬虫最大页数')
    parser.add_argument('--start-page', type=int, default=1, help='列表爬虫起始页数')
    parser.add_argument('--book-ids', help='指定书籍ID，多个用逗号分隔')

    args = parser.parse_args()

    print(f"启动爬虫: {args.spider}")
    if args.max_pages:
        print(f"最大页数: {args.max_pages}")
    if args.start_page > 1:
        print(f"起始页数: {args.start_page}")
    if args.book_ids:
        print(f"指定书籍ID: {args.book_ids}")

    try:
        if args.spider == 'list':
            run_novel_list_spider(args.max_pages, args.start_page)
        elif args.spider == 'detail':
            run_novel_detail_spider(args.book_ids)
        elif args.spider == 'comment':
            run_novel_comment_spider(args.book_ids)
        elif args.spider == 'all':
            run_all_spiders(args.max_pages, args.book_ids)
    except KeyboardInterrupt:
        print("\n爬虫被用户中断")
    except Exception as e:
        print(f"爬虫运行出错: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
