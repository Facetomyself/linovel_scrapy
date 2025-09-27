#!/usr/bin/env python3
"""
爬虫统计和监控脚本
"""

import os
from dotenv import load_dotenv
from pymysql import connect
from datetime import datetime, timedelta

# 加载环境变量
load_dotenv()

def get_crawler_stats():
    """获取爬虫统计信息"""
    try:
        mysql_config = {
            'host': os.getenv('mysql_host'),
            'port': int(os.getenv('mysql_port', 3306)),
            'user': os.getenv('mysql_user'),
            'password': os.getenv('mysql_password'),
            'database': os.getenv('mysql_database'),
            'charset': 'utf8mb4'
        }

        connection = connect(**mysql_config)
        cursor = connection.cursor()

        print("爬虫统计报告")
        print("=" * 60)

        # 1. 数据总量统计
        print("\n数据总量统计:")
        tables = ['novels', 'novel_volumes', 'novel_chapters', 'novel_comments']
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   {table}: {count:,} 条记录")

        # 2. 爬取状态统计
        print("\n爬取状态统计:")
        cursor.execute("""
            SELECT spider_name, status, COUNT(*) as count
            FROM crawl_status
            GROUP BY spider_name, status
            ORDER BY spider_name, status
        """)

        status_stats = cursor.fetchall()
        current_spider = None
        for spider_name, status, count in status_stats:
            if spider_name != current_spider:
                if current_spider:
                    print()
                print(f"   {spider_name}:")
                current_spider = spider_name
            status_text = {
                'pending': '待处理',
                'processing': '处理中',
                'completed': '已完成',
                'failed': '已失败'
            }.get(status, f'{status}')
            print(f"     {status_text}: {count:,}")

        # 3. 失败统计和重试分析
        print("\n失败和重试统计:")
        cursor.execute("""
            SELECT spider_name, status_type, COUNT(*) as failed_count,
                   AVG(retry_count) as avg_retries, MAX(retry_count) as max_retries
            FROM crawl_status
            WHERE status = 'failed'
            GROUP BY spider_name, status_type
            ORDER BY failed_count DESC
        """)

        failed_stats = cursor.fetchall()
        if failed_stats:
            for spider_name, status_type, failed_count, avg_retries, max_retries in failed_stats:
                print(f"   {spider_name} - {status_type}:")
                print(f"     失败次数: {failed_count:,}")
                print(f"     平均重试: {avg_retries:.1f} 次")
                print(f"     最大重试: {max_retries:.1f} 次")
        else:
            print("   暂无失败记录")

        # 4. 最近活动统计
        print("\n最近活动统计:")
        # 最近1小时
        one_hour_ago = datetime.now() - timedelta(hours=1)
        cursor.execute("""
            SELECT COUNT(*) FROM crawl_status
            WHERE last_update >= %s
        """, (one_hour_ago,))
        recent_count = cursor.fetchone()[0]
        print(f"   最近1小时更新: {recent_count:,} 条")

        # 最近24小时
        one_day_ago = datetime.now() - timedelta(days=1)
        cursor.execute("""
            SELECT COUNT(*) FROM crawl_status
            WHERE last_update >= %s
        """, (one_day_ago,))
        day_count = cursor.fetchone()[0]
        print(f"   最近24小时更新: {day_count:,} 条")

        # 5. 进度估算
        print("\n爬取进度估算:")

        # 列表页完成情况
        cursor.execute("""
            SELECT
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                COUNT(*) as total
            FROM crawl_status
            WHERE spider_name = 'novel_list' AND status_type = 'list_page'
        """)
        list_result = cursor.fetchone()
        if list_result and list_result[1] > 0:
            completed_pages = list_result[0] or 0
            total_pages = list_result[1]
            progress = (completed_pages / total_pages) * 100
            print(f"   列表页进度: {progress:.1f}% ({completed_pages}/{total_pages})")
        # 小说详情完成情况
        cursor.execute("""
            SELECT
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                COUNT(*) as total
            FROM crawl_status
            WHERE spider_name = 'novel_detail' AND status_type = 'detail_page'
        """)
        detail_result = cursor.fetchone()
        if detail_result and detail_result[1] > 0:
            completed_details = detail_result[0] or 0
            total_details = detail_result[1]
            progress = (completed_details / total_details) * 100
            print(f"   详情页进度: {progress:.1f}% ({completed_details}/{total_details})")
        # 评论完成情况
        cursor.execute("""
            SELECT
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                COUNT(*) as total
            FROM crawl_status
            WHERE spider_name = 'novel_comment' AND status_type = 'comment_page'
        """)
        comment_result = cursor.fetchone()
        if comment_result and comment_result[1] > 0:
            completed_comments = comment_result[0] or 0
            total_comments = comment_result[1]
            progress = (completed_comments / total_comments) * 100
            print(f"   评论页进度: {progress:.1f}% ({completed_comments}/{total_comments})")
        cursor.close()
        connection.close()

        print("\n统计报告生成完成！")

    except Exception as e:
        print(f"获取统计信息失败: {e}")

def get_failed_items_details():
    """获取失败项目的详细信息"""
    try:
        mysql_config = {
            'host': os.getenv('mysql_host'),
            'port': int(os.getenv('mysql_port', 3306)),
            'user': os.getenv('mysql_user'),
            'password': os.getenv('mysql_password'),
            'database': os.getenv('mysql_database'),
            'charset': 'utf8mb4'
        }

        connection = connect(**mysql_config)
        cursor = connection.cursor()

        print("\n失败项目详情 (最近10条):")
        print("-" * 60)

        cursor.execute("""
            SELECT spider_name, status_type, identifier, retry_count, last_update
            FROM crawl_status
            WHERE status = 'failed'
            ORDER BY last_update DESC
            LIMIT 10
        """)

        failed_items = cursor.fetchall()
        if failed_items:
            for spider_name, status_type, identifier, retry_count, last_update in failed_items:
                print(f"   {spider_name} | {status_type} | {identifier} | 重试{retry_count}次 | {last_update}")
        else:
            print("   无失败项目")

        cursor.close()
        connection.close()

    except Exception as e:
        print(f"获取失败详情失败: {e}")

if __name__ == '__main__':
    get_crawler_stats()
    get_failed_items_details()
