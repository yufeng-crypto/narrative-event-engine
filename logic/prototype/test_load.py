# Test script to verify role loading
import sys
import os

# Add prototype path
sys.path.insert(0, os.path.dirname(__file__))

# Import the function
exec(open('main.py', encoding='utf-8').read().split('# ============= GUI')[0] + '''
# Test loading
roles = load_npc_roles('C:/Users/20731/.openclaw/workspace/logic/roles')
for role_id, role in roles.items():
    print(f'{role_id}: {role["name"]} -> axes: {role["axes"]}')
''')
