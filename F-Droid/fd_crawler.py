import json
import os

input_file_path = 'fdroid_index_v2.json'
output_file_path = 'fdroid_index_v2_beautified.json'
output_txt_path = 'fdroid-github-repos.txt'


def beautify_json(input_file_path, output_file_path):
    try:
        with open(input_file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        with open(output_file_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
        print(f"file_after_beautified: {output_file_path}")
    except Exception as e:
        print(f"error: {e}")


def extract_and_save_source_codes(input_json_path, output_txt_path):
    try:
        with open(input_json_path, 'r', encoding='utf-8') as file:
            data = json.load(file)

        with open(output_txt_path, 'w', encoding='utf-8') as file:
            for app_key in data['packages']:
                source_code_url = data['packages'][app_key]['metadata'].get('sourceCode', None)
                if source_code_url and "git" in source_code_url:
                    file.write(source_code_url + '\n')

        print(f"Github Links 已写入 {output_txt_path}")
    except Exception as e:
        print(f"error: {e}")


if __name__ == '__main__':
    os.system('curl https://f-droid.org/repo/index-v2.json -o fdroid_index_v2.json')
    beautify_json(input_file_path, output_file_path)
    extract_and_save_source_codes(output_file_path, output_txt_path)
