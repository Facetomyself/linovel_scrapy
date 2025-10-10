#!/usr/bin/env python3
"""
一键清理数据脚本（破坏性操作）

功能：
- MySQL 数据清空：支持 TRUNCATE 和 DROP DATABASE
- Redis 清理：支持 FLUSHDB 或按前缀删除 crawl_status/url_cache
- 本地断点状态清理：storage/state 与 storage/jobs

用法示例：
  # 仅清空业务表并清理 Redis 相关键（推荐）
  python reset_data.py --truncate --clear-redis --clear-local --yes

  # 彻底重置数据库（删除并重新创建），并清空 Redis 整库（极度危险）
  python reset_data.py --drop-db --flush-redis --clear-local --yes

说明：
- 通过 .env 读取连接信息（MySQL/Redis）
- 需要 --yes 参数确认后才会执行
"""

import argparse
import os
import shutil
import sys
import pymysql
import redis
from dotenv import load_dotenv


def parse_args():
    p = argparse.ArgumentParser(description='破坏性数据清理（谨慎使用）')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--truncate', action='store_true', help='TRUNCATE 业务表清空（保留数据库）')
    g.add_argument('--drop-db', action='store_true', help='DROP DATABASE 并重新创建（最危险）')

    p.add_argument('--clear-redis', action='store_true', help='按前缀删除 Redis 键（crawl_status:* 与 url_cache:*）')
    p.add_argument('--flush-redis', action='store_true', help='Redis FLUSHDB（整库清空，最危险）')
    p.add_argument('--clear-local', action='store_true', help='清理 storage/state 与 storage/jobs')
    p.add_argument('--yes', action='store_true', help='确认执行，否则仅打印将要执行的操作')
    return p.parse_args()


def get_mysql_conn():
    return pymysql.connect(
        host=os.getenv('mysql_host'),
        port=int(os.getenv('mysql_port', 3306)),
        user=os.getenv('mysql_user'),
        password=os.getenv('mysql_password'),
        database=os.getenv('mysql_database'),
        charset='utf8mb4'
    )


def drop_and_recreate_database(db_name: str):
    """删除并重建数据库（使用不指定 database 的连接）"""
    mysql_config = dict(
        host=os.getenv('mysql_host'),
        port=int(os.getenv('mysql_port', 3306)),
        user=os.getenv('mysql_user'),
        password=os.getenv('mysql_password'),
        charset='utf8mb4'
    )
    conn = pymysql.connect(**mysql_config)
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
    cur.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.commit()
    cur.close()
    conn.close()


def truncate_tables(conn):
    """清空业务表，处理外键顺序并暂时关闭约束"""
    cur = conn.cursor()
    cur.execute('SET FOREIGN_KEY_CHECKS=0')
    # 先删子表，再删父表，最后状态表
    for tbl in ['novel_chapters', 'novel_volumes', 'novel_comments', 'novels', 'crawl_status']:
        try:
            cur.execute(f'TRUNCATE TABLE {tbl}')
        except Exception as e:
            print(f'[WARN] TRUNCATE {tbl} 失败: {e}')
    cur.execute('SET FOREIGN_KEY_CHECKS=1')
    conn.commit()
    cur.close()


def clear_redis(prefix_only: bool):
    password = os.getenv('redis_password') or None
    username = os.getenv('redis_username') or None
    client = redis.Redis(
        host=os.getenv('redis_host'),
        port=int(os.getenv('redis_port', 6379)),
        password=password,
        username=username,
        decode_responses=True
    )
    client.ping()
    if prefix_only:
        patterns = ['crawl_status:*', 'url_cache:*']
        total = 0
        for pat in patterns:
            for key in client.scan_iter(pat):
                client.delete(key)
                total += 1
        print(f'[OK] 已删除 Redis 键（按前缀）：{total} 个')
    else:
        client.flushdb()
        print('[OK] 已执行 Redis FLUSHDB（整库清空）')


def clear_local_state():
    for path in ['storage/state', 'storage/jobs']:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            os.makedirs(path, exist_ok=True)
            print(f'[OK] 已清理本地目录并重建：{path}')


def main():
    load_dotenv('.env')
    args = parse_args()

    db_name = os.getenv('mysql_database')
    print('将执行以下操作:')
    if args.truncate:
        print('- TRUNCATE MySQL 业务表（保留数据库与结构）')
    if args.drop_db:
        print(f'- DROP 并重建数据库 `{db_name}`')
    if args.flush_redis:
        print('- Redis FLUSHDB（整库清空）')
    elif args.clear_redis:
        print('- 按前缀删除 Redis 键：crawl_status:*, url_cache:*')
    if args.clear_local:
        print('- 清理本地断点状态：storage/state 与 storage/jobs')

    if not args.yes:
        print('\n未提供 --yes，已模拟展示。若要执行，请追加 --yes')
        return 0

    # MySQL 部分
    if args.drop_db:
        drop_and_recreate_database(db_name)
        print(f'[OK] 已重置数据库：{db_name}')
    elif args.truncate:
        conn = get_mysql_conn()
        truncate_tables(conn)
        conn.close()
        print('[OK] 已清空业务表')

    # Redis 部分
    if args.flush_redis:
        clear_redis(prefix_only=False)
    elif args.clear_redis:
        clear_redis(prefix_only=True)

    # 本地断点状态
    if args.clear_local:
        clear_local_state()

    print('\n清理完成')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n已取消')
        sys.exit(130)
