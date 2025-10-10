#!/usr/bin/env python3
"""
检查Redis缓存中的数据
"""

import os
import redis
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def check_redis_cache():
    try:
        # 连接Redis（支持密码与ACL用户名，可选）
        redis_password = os.getenv('redis_password') or None
        redis_username = os.getenv('redis_username') or None
        redis_client = redis.Redis(
            host=os.getenv('redis_host', 'localhost'),
            port=int(os.getenv('redis_port', 6379)),
            password=redis_password,
            username=redis_username,
            decode_responses=True
        )

        # 检查连接
        redis_client.ping()
        print("Redis连接成功")

        # 查找所有crawl_status开头的键
        keys = redis_client.keys("crawl_status:*")
        print(f"找到 {len(keys)} 个crawl_status缓存键")

        if keys:
            print("\n前10个缓存键:")
            for key in keys[:10]:
                value = redis_client.get(key)
                print(f"  {key}: {value}")

            # 统计不同状态的数量
            status_count = {}
            for key in keys:
                value = redis_client.get(key)
                status_count[value] = status_count.get(value, 0) + 1

            print(f"\n状态分布:")
            for status, count in status_count.items():
                print(f"  {status}: {count} 个")

        # 检查不同spider的缓存
        print("\n不同Spider的缓存分布:")
        for spider in ['novel_list', 'novel_detail', 'novel_comment']:
            spider_keys = redis_client.keys(f"crawl_status:{spider}:*")
            print(f"  {spider}: {len(spider_keys)} 个缓存键")

        # 检查具体的缓存键
        test_keys = [
            'crawl_status:novel_list:list_page:1',
            'crawl_status:novel_detail:detail_page:100818',
            'crawl_status:novel_comment:comment_page:100007_1'
        ]

        print(f"\n关键缓存键检查:")
        for key in test_keys:
            value = redis_client.get(key)
            print(f"  {key}: {value}")

        else:
            print("没有找到crawl_status缓存键")

    except Exception as e:
        print(f"检查失败: {e}")

if __name__ == "__main__":
    check_redis_cache()
