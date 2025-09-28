## 需求
爬取 https://www.linovel.net/ 的全部小说

## 网站分析

### 列表页请求

小说列表页为 https://www.linovel.net/cat/-1.html

请求:
curl 'https://www.linovel.net/cat/-1.html?page=1' \
  -H 'accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7' \
  -H 'accept-language: zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6' \
  -b 'kotori=bf999de59eb255025562c9162ef873a4; Hm_lvt_fa984679f78b2f9a0cff33b19d5d265f=1758953659; HMACCOUNT=E0B31916854FB3F2; Hm_lpvt_fa984679f78b2f9a0cff33b19d5d265f=1758953669' \
  -H 'priority: u=0, i' \
  -H 'referer: https://www.linovel.net/cat/-1.html' \
  -H 'sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Microsoft Edge";v="140"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "Windows"' \
  -H 'sec-fetch-dest: document' \
  -H 'sec-fetch-mode: navigate' \
  -H 'sec-fetch-site: same-origin' \
  -H 'sec-fetch-user: ?1' \
  -H 'upgrade-insecure-requests: 1' \
  -H 'user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0'

返回html

.storage/list1.html

翻页请求:
curl 'https://www.linovel.net/cat/-1.html?page=2' \
  -H 'accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7' \
  -H 'accept-language: zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6' \
  -b 'kotori=bf999de59eb255025562c9162ef873a4; Hm_lvt_fa984679f78b2f9a0cff33b19d5d265f=1758953659; HMACCOUNT=E0B31916854FB3F2; Hm_lpvt_fa984679f78b2f9a0cff33b19d5d265f=1758953832' \
  -H 'priority: u=0, i' \
  -H 'referer: https://www.linovel.net/cat/-1.html?page=1' \
  -H 'sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Microsoft Edge";v="140"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "Windows"' \
  -H 'sec-fetch-dest: document' \
  -H 'sec-fetch-mode: navigate' \
  -H 'sec-fetch-site: same-origin' \
  -H 'sec-fetch-user: ?1' \
  -H 'upgrade-insecure-requests: 1' \
  -H 'user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0'

page增加,返回值html中 //ul[@class="pagination"]/li[position()=last()-1]/a/text() 为总页数,遍历请求,爬取全部小说

### 返回值解析:

//div[@class='rank-book-list'] 为小说列表,列表中的每个小说为//div[@class='rank-book']

//div[@class='rank-book'] 小说容器中的 //div[@class='book-draw'] 小说基本信息,//div[@class='rank-book-mask'] 小说最新章节信息

//div[@class='rank-book-mask'] 小说最新章节信息中的 //a[@class='book-mask-left']/@href 小说最新章节页跳转url

//div[@class='rank-book-mask'] 小说最新章节信息中的 //a[@class='book-mask-left']/div[@class='vol-name'] 小说最新卷名

//div[@class='rank-book-mask'] 小说最新章节信息中的 //a[@class='book-mask-left']/div[@class='vol-intro'] 小说最新卷选段

//div[@class='rank-book-mask'] 小说最新章节信息中的 //a[@class='book-mask-right']/ul/li 中为小说最近的几个章节信息,//a/@href 章节跳转url,//a/p 章节名,//a/div[@class='new-vol'] 为最新章节标识

//div[@class='book-draw'] 小说基本信息中的 //div[@class='book-cover']/img/@src 小说封面

//div[@class='book-draw'] 小说基本信息中的 //a[@class='book-box']/div[@class='book-info']/a/@href 小说详情页 text为小说名

//div[@class='book-draw'] 小说基本信息中的 //a[@class='book-box']/div[@class='book-info']/div[@class='book-tags']/a/@href 小说标签跳转url

//div[@class='book-draw'] 小说基本信息中的 //a[@class='book-box']/div[@class='book-info']/div[@class='book-tags']/a/@text 小说标签

//div[@class='book-draw'] 小说基本信息中的 //a[@class='book-box']/div[@class='book-info']/div[@class='book-intro'] 小说简介

//div[@class='book-draw'] 小说基本信息中的 //a[@class='book-box']/div[@class='book-info']/div[@class='book-extra'] 小说作者和更新时间 中间使用 | 分隔


### 详情页请求

curl 'https://www.linovel.net/book/102872.html' \
  -H 'accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7' \
  -H 'accept-language: zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6' \
  -H 'cache-control: max-age=0' \
  -b 'kotori=bf999de59eb255025562c9162ef873a4; Hm_lvt_fa984679f78b2f9a0cff33b19d5d265f=1758953659; HMACCOUNT=E0B31916854FB3F2; blendent=white; Hm_lpvt_fa984679f78b2f9a0cff33b19d5d265f=1758955853' \
  -H 'priority: u=0, i' \
  -H 'referer: https://www.linovel.net/cat/-1.html?page=2' \
  -H 'sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Microsoft Edge";v="140"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "Windows"' \
  -H 'sec-fetch-dest: document' \
  -H 'sec-fetch-mode: navigate' \
  -H 'sec-fetch-site: same-origin' \
  -H 'sec-fetch-user: ?1' \
  -H 'upgrade-insecure-requests: 1' \
  -H 'user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0'

返回html

./storage/detail.html

### 返回值解析:

//div[@class='book-data'] 为小说基本数据 包含小说字数,热度,收藏,连载状态 按顺序排列
//div[@class='book-data']/span 依次为小说字数、热度、收藏、连载状态，顺序排列
//div[@class='book-data']/span[@class='hint'] 为对应数据的标签（如“字数”、“热度”、“收藏”）
//字数、热度、收藏为纯文本或带<i>标签的文本，连载状态为最后一个span，内容如“连载中”或“已完结”

//div[@class='book-sign-wrp'] 为小说签约信息 包含小说签约状态,更新时间

//div[@class='book-sign-wrp'] 小说签约信息中 //div[@class='book-sign'] 小说签约状态
//div[@class='book-sign-wrp'] 小说签约信息中 //div[@class='book-last-update'] 小说更新时间

//div[@class='section-list'] 为小说章节列表 包含多个小说卷的章节列表 按顺序排列
//div[@class='section-list']/div[@class='section'] 为小说卷章节列表 包含卷信息和章节列表
//div[@class='section-list']/div[@class='section']/div[@class='volume-info'] 为卷信息区域
//div[@class='section-list']/div[@class='section']/div[@class='volume-info']/h2[@class='volume-title']/a 为卷标题
//div[@class='section-list']/div[@class='section']/div[@class='volume-info']/div[@class='volume-hint'] 为卷字数信息
//div[@class='section-list']/div[@class='section']/div[@class='volume-info']/div[@class='volume-desc']//div[@class='text-content-actual'] 为卷描述内容
//div[@class='section-list']/div[@class='section']/div[@class='chapter-list-wrp']/div[@class='chapter-list']//div[@class='chapter']/a/@href 为章节跳转url
//div[@class='section-list']/div[@class='section']/div[@class='chapter-list-wrp']/div[@class='chapter-list']//div[@class='chapter']/a/text() 为章节标题

### 评论接口请求:
curl 'https://www.linovel.net/comment/items?type=book&tid=102872&pageSize=15&page=1&_=1758955873569' \
  -H 'accept: application/json, text/javascript, */*; q=0.01' \
  -H 'accept-language: zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6' \
  -b 'kotori=bf999de59eb255025562c9162ef873a4; Hm_lvt_fa984679f78b2f9a0cff33b19d5d265f=1758953659; HMACCOUNT=E0B31916854FB3F2; blendent=white; Hm_lpvt_fa984679f78b2f9a0cff33b19d5d265f=1758955853' \
  -H 'priority: u=1, i' \
  -H 'referer: https://www.linovel.net/book/102872.html' \
  -H 'sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Microsoft Edge";v="140"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "Windows"' \
  -H 'sec-fetch-dest: empty' \
  -H 'sec-fetch-mode: cors' \
  -H 'sec-fetch-site: same-origin' \
  -H 'user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0' \
  -H 'x-kotori-key: bf999de59eb255025562c9162ef873a4' \
  -H 'x-requested-with: XMLHttpRequest'

### 评论返回值
./storage/comment.json