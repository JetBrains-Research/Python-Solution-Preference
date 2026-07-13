import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
old = 'sqlite:///community.db'
new = f'sqlite:///{os.path.join(BASE_DIR, "community.db")}'
with open('config.py', 'r') as f:
    content = f.read()
content = content.replace('sqlite:///community.db', new)
with open('config.py', 'w') as f:
    f.write(content)
print('Config updated to absolute path')
