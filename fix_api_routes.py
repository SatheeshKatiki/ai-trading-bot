import os
import glob
for file_path in glob.glob('frontend/app/api/**/*.ts', recursive=True):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        new_content = content.replace('localhost:8000', '127.0.0.1:8000')
        if new_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated {file_path}")
    except Exception as e:
        print(f"Failed {file_path}: {e}")
