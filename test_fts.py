import sqlite3
import os

# 连接主索引数据库
db_path = 'C:/Users/20731/.openclaw/memory/main.sqlite'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# 检查现有表结构
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print('现有表:', tables)

# 创建 FTS5 虚拟表（如果不存在）
try:
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content, source, chunk_id)")
    print('FTS表创建成功')
except Exception as e:
    print('FTS表创建失败:', e)

# 读取一个memory文件测试
memory_file = 'C:/Users/20731/.openclaw/workspace/memory/2026-03-02.md'
if os.path.exists(memory_file):
    with open(memory_file, 'r', encoding='utf-8') as f:
        content = f.read()[:500]
    c.execute('INSERT INTO memory_fts VALUES (?, ?, ?)', (content, 'test', 1))
    conn.commit()
    print('测试数据插入成功')
    
    # 测试搜索
    result = c.execute("SELECT chunk_id FROM memory_fts WHERE memory_fts MATCH '六轴'").fetchall()
    print('搜索结果:', result)

conn.close()
