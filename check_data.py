#!/usr/bin/env python3
"""
检查数据库中的数据
"""

import os
from dotenv import load_dotenv
from pymysql import connect

# 加载环境变量
load_dotenv()

def check_database_data():
    """检查数据库中的数据"""
    try:
        # 连接数据库
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

        # 检查各个表的数据量
        tables = ['novels', 'novel_volumes', 'novel_chapters', 'novel_comments', 'crawl_status']

        print("数据库数据检查:")
        print("=" * 50)

        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"{table}: {count} 条记录")

            # 显示最新的几条记录作为示例
            if count > 0:
                if table == 'novels':
                    cursor.execute(f"SELECT book_id, title FROM {table} ORDER BY created_at DESC LIMIT 3")
                    rows = cursor.fetchall()
                    for row in rows:
                        print(f"     - {row[0]}: {row[1][:30]}...")
                elif table == 'novel_chapters':
                    cursor.execute(f"SELECT book_id, chapter_title FROM {table} ORDER BY created_at DESC LIMIT 3")
                    rows = cursor.fetchall()
                    for row in rows:
                        print(f"     - {row[0]}: {row[1][:30] if row[1] else 'N/A'}...")
                elif table == 'crawl_status':
                    cursor.execute(f"SELECT spider_name, status_type, status FROM {table} ORDER BY last_update DESC LIMIT 5")
                    rows = cursor.fetchall()
                    for row in rows:
                        print(f"     - {row[0]} {row[1]}: {row[2]}")

        cursor.close()
        connection.close()

        print("\n数据检查完成！")

    except Exception as e:
        print(f"检查失败: {e}")

if __name__ == '__main__':
    check_database_data()
