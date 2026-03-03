import sqlite3
import os
import hashlib
import time

db_path = 'C:/Users/20731/.openclaw/memory/main.sqlite'
memory_dir = 'C:/Users/20731/.openclaw/workspace/memory'

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 获取所有md文件
files = [f for f in os.listdir(memory_dir) if f.endswith('.md')]
print(f'找到 {len(files)} 个memory文件')

for filename in files:
    filepath = os.path.join(memory_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 计算hash
    file_hash = hashlib.md5(content.encode()).hexdigest()
    
    # 检查是否已存在
    c.execute('SELECT hash FROM chunks WHERE path = ?', (filename,))
    existing = c.fetchone()
    
    if existing and existing[0] == file_hash:
        print(f'Skipping {filename} (unchanged)')
        continue
    
    # 删除旧数据
    c.execute('DELETE FROM chunks WHERE path = ?', (filename,))
    
    # 插入新chunk (将整个文件作为一个chunk)
    chunk_id = f"{filename}:{int(time.time())}"
    c.execute('''INSERT INTO chunks (id, path, source, start_line, end_line, hash, model, text, embedding, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (chunk_id, filename, 'memory', 1, len(content.split('\n')), file_hash, '', content, '', int(time.time())))
    
    print(f'Indexed: {filename} ({len(content)} chars)')

conn.commit()

# 验证
c.execute('SELECT COUNT(*) FROM chunks')
print(f'\n总chunks: {c.fetchone()[0]}')

conn.close()
print('索引创建完成!')
