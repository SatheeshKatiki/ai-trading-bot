import json

log_path = r'C:\Users\Windows\.gemini\antigravity-ide\brain\4e6134ae-2b16-43be-b499-3e4283c6ced1\.system_generated\logs\transcript.jsonl'

with open(log_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

user_inputs = []
for line in lines:
    try:
        data = json.loads(line)
        if data.get('type') == 'USER_INPUT':
            user_inputs.append(data.get('content', ''))
    except Exception as e:
        pass

if user_inputs:
    print(f"\n--- LAST USER INPUT ---")
    print(user_inputs[-1])
