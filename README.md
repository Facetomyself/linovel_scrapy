# Linovel小说爬虫

基于Scrapy的小说网站爬虫，支持异步爬取、断点续爬和数据持久化。

## 功能特性

- 多线程异步爬取（默认4线程，可配置）
- 自动创建数据库表结构
- Redis缓存支持，提升性能
- 智能断点续爬机制
- MySQL数据持久化存储
- 完整的小说信息爬取（基础信息、卷信息、章节URL）
- 评论数据爬取和存储
- 实时监控和统计功能
- 生产级别的错误处理和重试机制

## 系统架构

### 核心组件

- **Spider模块**：`novel_list`、`novel_detail`、`novel_comment` 三个专用爬虫
- **Pipeline模块**：数据库操作和数据持久化
- **Middleware模块**：断点续爬控制和请求过滤
- **监控模块**：统计脚本和状态追踪

### 技术特点

- **并发安全**：线程锁保护数据库操作，支持高并发
- **智能缓存**：Redis + 数据库双重缓存策略
- **容错机制**：自动重试、连接重连、状态恢复
- **可观测性**：详细日志、进度统计、性能监控

## 环境要求

- Python 3.8+
- MySQL 5.7+
- Redis 5.0+
- 网络连接（访问目标网站）

## 快速开始

### 1. 安装依赖

**推荐使用 uv（现代Python包管理器）：**

```bash
# 安装uv (如果还没有安装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 进入项目目录并同步依赖（自动创建虚拟环境）
cd linovel_crawler
uv sync

# 激活虚拟环境（可选，uv通常会自动管理）
source .venv/bin/activate  # Linux/macOS
# 或者在Windows上: .venv\Scripts\activate
```

**或者使用传统的pip方式：**

```bash
# 创建虚拟环境
cd linovel_crawler
python -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # Linux/macOS
# 或者在Windows上: .venv\Scripts\activate

# 安装依赖
pip install scrapy pymysql redis python-dotenv
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件并配置数据库连接信息：

```env
# 目标网站基础URL
base_url = https://www.linovel.net/

# MySQL数据库配置
mysql_host = mysql_host
mysql_port = mysql_port
mysql_user = mysql_user
mysql_password = mysql_password
mysql_database = mysql_database

# Redis缓存配置
redis_host = redis_host
redis_port = redis_port
redis_password = redis_password
```

### 3. 测试数据库连接

```bash
python test_db.py
```

## 数据库设计

爬虫会自动创建以下表结构：

### novels表 - 小说基本信息

| 字段名 | 类型 | 说明 |
|--------|------|------|
| book_id | VARCHAR(20) PRIMARY KEY | 小说ID |
| title | VARCHAR(255) NOT NULL | 小说标题 |
| cover_url | TEXT | 封面图片URL |
| author | VARCHAR(100) | 作者 |
| intro | TEXT | 简介 |
| tags | JSON | 标签列表 |
| word_count | INT | 字数统计 |
| popularity | INT | 热度 |
| favorites | INT | 收藏数 |
| status | VARCHAR(20) | 连载状态 |
| sign_status | VARCHAR(50) | 签约状态 |
| last_update | DATETIME | 最后更新时间 |
| detail_url | TEXT | 详情页URL |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

```sql
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
    last_update DATETIME,
    detail_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### novel_volumes表 - 小说卷信息

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INT AUTO_INCREMENT PRIMARY KEY | 主键ID |
| book_id | VARCHAR(20) NOT NULL | 关联小说ID |
| volume_index | INT NOT NULL | 卷序号 |
| volume_title | VARCHAR(255) | 卷标题 |
| volume_word_count | INT | 卷字数 |
| volume_desc | TEXT | 卷描述 |
| created_at | TIMESTAMP | 创建时间 |

```sql
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### novel_chapters表 - 小说章节信息

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INT AUTO_INCREMENT PRIMARY KEY | 主键ID |
| book_id | VARCHAR(20) NOT NULL | 关联小说ID |
| volume_index | INT | 所属卷序号 |
| chapter_url | TEXT NOT NULL | 章节URL |
| chapter_title | VARCHAR(500) | 章节标题 |
| created_at | TIMESTAMP | 创建时间 |

```sql
CREATE TABLE IF NOT EXISTS novel_chapters (
    id INT AUTO_INCREMENT PRIMARY KEY,
    book_id VARCHAR(20) NOT NULL,
    volume_index INT,
    chapter_url TEXT NOT NULL,
    chapter_title VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_chapter_url (chapter_url(500)),
    FOREIGN KEY (book_id) REFERENCES novels(book_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### novel_comments表 - 评论数据

| 字段名 | 类型 | 说明 |
|--------|------|------|
| comment_id | VARCHAR(50) PRIMARY KEY | 评论ID |
| book_id | VARCHAR(20) NOT NULL | 关联小说ID |
| user_name | VARCHAR(100) | 用户名 |
| content | TEXT | 评论内容 |
| create_time | DATETIME | 创建时间 |
| like_count | INT DEFAULT 0 | 点赞数 |
| created_at | TIMESTAMP | 创建时间 |

```sql
CREATE TABLE IF NOT EXISTS novel_comments (
    comment_id VARCHAR(50) PRIMARY KEY,
    book_id VARCHAR(20) NOT NULL,
    user_name VARCHAR(100),
    content TEXT,
    create_time DATETIME,
    like_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(book_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### crawl_status表 - 爬取状态跟踪

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INT AUTO_INCREMENT PRIMARY KEY | 主键ID |
| spider_name | VARCHAR(50) NOT NULL | Spider名称 |
| status_type | VARCHAR(50) NOT NULL | 状态类型 |
| identifier | VARCHAR(100) NOT NULL | 标识符 |
| status | VARCHAR(20) DEFAULT 'pending' | 状态 |
| last_update | TIMESTAMP | 最后更新时间 |
| retry_count | INT DEFAULT 0 | 重试次数 |

```sql
CREATE TABLE IF NOT EXISTS crawl_status (
    id INT AUTO_INCREMENT PRIMARY KEY,
    spider_name VARCHAR(50) NOT NULL,
    status_type VARCHAR(50) NOT NULL,
    identifier VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    retry_count INT DEFAULT 0,
    UNIQUE KEY unique_status (spider_name, status_type, identifier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

## 使用方法

### 基本用法

#### 1. 爬取小说列表
```bash
# 使用uv运行（推荐）
uv run python run_spiders.py list --max-pages 10

# 或直接使用python（如果已激活虚拟环境）
python run_spiders.py list --max-pages 10

# 从指定页面开始爬取
uv run python run_spiders.py list --start-page 5 --max-pages 20
```

#### 2. 爬取小说详情
```bash
# 爬取指定小说的详细信息和章节列表
uv run python run_spiders.py detail --book-ids 100818,100007
```

#### 3. 爬取评论数据
```bash
# 爬取指定小说的评论
uv run python run_spiders.py comment --book-ids 100818
```

#### 4. 完整流程爬取
```bash
# 运行完整的爬取流程（列表 -> 详情 -> 评论）
uv run python run_spiders.py all --max-pages 5
```

### 高级用法

#### 断点续爬
系统会自动记录爬取状态，支持断点续爬：

```bash
# 第一次运行
uv run python run_spiders.py all --max-pages 100

# 如果中途中断，重新运行会自动从断点继续
uv run python run_spiders.py all --max-pages 100
```

#### 监控统计
```bash
# 查看爬取统计信息
uv run python crawler_stats.py

# 检查数据库中的数据
uv run python check_data.py
```

## 断点续爬机制

### 工作原理

1. **状态记录**：每次爬取前记录任务状态为 `processing`
2. **进度跟踪**：使用 `crawl_status` 表跟踪每个页面的爬取状态
3. **智能跳过**：检查已完成的页面，自动跳过重复请求
4. **失败重试**：对失败的任务自动重试，最多3次
5. **缓存加速**：Redis缓存已处理的URL，提升性能

### 重试策略

- **网络错误**：自动重试，最多3次
- **解析错误**：记录失败状态，可手动重新处理
- **连接超时**：指数退避重试策略

## 监控和统计

### 统计信息

运行 `python crawler_stats.py` 可查看：

- 数据总量统计（各表记录数）
- 爬取状态分布（进行中、已完成、已失败）
- 失败率分析和重试统计
- 最近活动情况
- 总体进度估算

### 日志监控

系统会生成详细的日志文件：

```
logs/scrapy.log  # 主日志文件
```

日志包含：
- 请求和响应的详细信息
- 错误信息和堆栈跟踪
- 性能统计和进度信息
- 数据库操作记录

## 性能优化

### 已实现的优化

#### 1. 并发控制
- 线程安全的数据库操作
- 智能请求调度和延迟控制
- 连接池管理

#### 2. 缓存策略
- Redis缓存已完成的URL
- 双重检查机制（缓存 + 数据库）
- 自动缓存更新

#### 3. 错误处理
- 自动重试机制
- 连接重连功能
- 状态恢复机制

### 性能参数配置

在 `settings.py` 中可调整：

```python
# 并发设置
CONCURRENT_REQUESTS = 4                    # 总并发数
CONCURRENT_REQUESTS_PER_DOMAIN = 2         # 每域名并发数

# 延迟设置
DOWNLOAD_DELAY = 0.1                       # 请求间隔

# 重试设置
RETRY_ENABLED = True                       # 启用重试
RETRY_TIMES = 3                           # 最大重试次数
RESUME_MAX_RETRY_COUNT = 3                # 断点续爬最大重试数
```

## 注意事项

### 使用建议

1. **首次运行**：建议从小量数据开始测试
2. **监控资源**：注意数据库和Redis的资源使用情况
3. **网络稳定**：确保网络连接稳定，避免频繁重试
4. **定期清理**：可定期清理旧的日志文件

### 安全考虑

1. **配置安全**：敏感信息通过环境变量配置，不写入代码
2. **请求频率**：设置合理的请求延迟，避免对目标网站造成压力
3. **数据合规**：确保爬取行为符合网站使用条款和法律法规

## 故障排除

### 常见问题

#### 数据库连接失败
```
错误：数据库连接失败
```
**解决方案**：
- 检查MySQL服务是否运行：`systemctl status mysql`
- 验证环境变量配置
- 检查网络连接和防火墙设置

#### Redis连接失败
```
警告：Redis连接失败，将禁用Redis缓存
```
**解决方案**：
- 检查Redis服务状态
- 验证Redis配置和密码
- 注意：Redis失败不会影响基本功能，只会降低性能

#### 爬取被拦截
```
错误：请求被拒绝或返回异常状态码
```
**解决方案**：
- 检查User-Agent配置
- 增加请求延迟：调整 `DOWNLOAD_DELAY`
- 检查目标网站是否有更新
- 考虑更换IP地址或使用代理

#### 数据解析失败
```
错误：XPath匹配失败或数据格式异常
```
**解决方案**：
- 检查网站结构是否变更
- 查看详细日志定位问题
- 更新XPath表达式

### 调试技巧

1. **启用调试日志**：
   ```python
   # 在settings.py中设置
   LOG_LEVEL = 'DEBUG'
   ```

2. **单步测试**：
   ```bash
   # 先测试列表爬虫
   uv run python run_spiders.py list --max-pages 1

   # 再测试详情爬虫
   uv run python run_spiders.py detail --book-ids 100818
   ```

3. **数据验证**：
   ```bash
   # 检查爬取的数据
   uv run python check_data.py
   uv run python crawler_stats.py
   ```

## 技术栈

- **框架**：Scrapy 2.x
- **包管理**：uv（现代化Python包管理器）
- **数据库**：MySQL 5.7+ / PyMySQL
- **缓存**：Redis 5.0+ / redis-py
- **配置**：python-dotenv
- **并发**：threading.Lock（线程安全）

## 更新日志

### v2.1.0 (2025-09-27)
- 迁移到现代化的包管理：uv + pyproject.toml
- 优化虚拟环境管理流程
- 更新文档以支持uv工作流
- 添加.uvignore配置文件

### v2.0.0 (2025-09-27)
- 重构系统架构，实现生产级稳定性
- 添加完整的断点续爬机制
- 实现Redis缓存优化
- 添加监控和统计功能
- 优化并发安全和错误处理

### v1.0.0 (初始版本)
- 基础爬虫功能实现
- 支持小说列表、详情、评论爬取
- MySQL数据存储

## 贡献指南

欢迎提交Issue和Pull Request来改进这个项目。

## 许可证

本项目仅供学习和研究使用，请遵守相关法律法规和网站使用条款。
