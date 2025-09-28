#!/usr/bin/env python3
"""
检查crawl_status表中的数据
"""

import os
import pymysql
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def check_crawl_status():
    try:
        conn = pymysql.connect(
            host=os.getenv('mysql_host'),
            port=int(os.getenv('mysql_port', 3306)),
            user=os.getenv('mysql_user'),
            password=os.getenv('mysql_password'),
            database=os.getenv('mysql_database'),
            charset='utf8mb4'
        )

        cursor = conn.cursor()

        # 检查总记录数
        cursor.execute('SELECT COUNT(*) FROM crawl_status')
        count = cursor.fetchone()[0]
        print(f'crawl_status表中有 {count} 条记录')

        if count > 0:
            # 检查不同状态的分布
            cursor.execute('''
                SELECT status, COUNT(*) as count
                FROM crawl_status
                GROUP BY status
                ORDER BY count DESC
            ''')
            status_stats = cursor.fetchall()
            print('\n状态分布:')
            for status, cnt in status_stats:
                print(f'  {status}: {cnt} 条')

            # 检查前10条记录
            cursor.execute('SELECT spider_name, status_type, identifier, status, retry_count, last_update FROM crawl_status ORDER BY last_update DESC LIMIT 10')
            rows = cursor.fetchall()
            print('\n最近10条记录:')
            for row in rows:
                spider_name, status_type, identifier, status, retry_count, last_update = row
                print(f'  {spider_name} - {status_type} - {identifier}: {status} (重试:{retry_count})')

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"检查失败: {e}")

if __name__ == "__main__":
    check_crawl_status()
