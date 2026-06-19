import json

log_path = r'C:\Users\Windows\.gemini\antigravity-ide\brain\4e6134ae-2b16-43be-b499-3e4283c6ced1\.system_generated\logs\transcript.jsonl'

with open(log_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for line in lines[-50:]:
    try:
        data = json.loads(line)
        if data.get('type') in ['USER_INPUT', 'PLANNER_RESPONSE']:
            print(f"\n--- {data['type']} ---")
            print(data.get('content', ''))
    except Exception as e:
        pass
