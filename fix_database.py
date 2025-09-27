#!/usr/bin/env python3
"""
修复数据库字段类型
"""

import os
from dotenv import load_dotenv
from pymysql import connect

# 加载环境变量
load_dotenv()

def fix_database_schema():
    """修复数据库表结构"""
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

        print("开始修复数据库表结构...")

        # 修改novels表的last_update字段类型
        try:
            cursor.execute("""
                ALTER TABLE novels
                MODIFY COLUMN last_update VARCHAR(50)
            """)
            print("✓ novels.last_update 字段类型已修改为 VARCHAR(50)")
        except Exception as e:
            print(f"修改novels.last_update字段失败: {e}")

        # 检查其他可能需要修复的字段
        # 查看当前表结构
        cursor.execute("DESCRIBE novels")
        columns = cursor.fetchall()
        print("\n当前novels表结构:")
        for col in columns:
            print(f"  {col[0]}: {col[1]}")

        connection.commit()
        cursor.close()
        connection.close()

        print("\n数据库修复完成！")

    except Exception as e:
        print(f"数据库修复失败: {e}")

if __name__ == '__main__':
    fix_database_schema()
