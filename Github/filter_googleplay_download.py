import json
import re
import time
import requests

headers = {"Authorization": "Bearer <Github_API_KEY>"}  # updated token
filted_repos = set()


def run_query(owner, repo):
    query = f"""
    {{
      repository(owner: "{owner}", name: "{repo}") {{
        object(expression: "HEAD:README.md") {{
          ... on Blob {{
            text
          }}
        }}
      }}
    }}
    """
    attempts = 0
    while attempts < 6:
        try:
            request = requests.post('https://api.github.com/graphql', json={'query': query}, headers=headers)
            content = request.json()
            if request.status_code == 200:
                if content.get('data'):
                    repository = content['data'].get('repository')
                    if repository:
                        obj = repository.get('object')
                        if obj and obj.get('text'):
                            return obj['text']
                return None
            else:
                attempts += 1
                if 'message' in content and 'wait' in content['message']:
                    time.sleep(120)
        except Exception as e:
            attempts += 1
            print("Error fetching README:", e)
            time.sleep(120)
    print("Error fetching README:", content)
    return None


def extract_owner_repo(link):
    parts = link.strip().split('/')
    if len(parts) > 2:
        return parts[-2], parts[-1]
    return None, None


def extract_google_play_id(readme_content: str):
    pattern = r"https://play\.google\.com/store/apps/details\?id=[\w\.]+"
    link = re.search(pattern, readme_content)
    if link:
        pattern_id = r'id=([a-zA-Z0-9._]+)'
        google_id = re.search(pattern_id, link.group())
        if google_id:
            return google_id.group(1)
    return None


def get_app_info(link, app_id, app_content):
    name = app_content.get('title', '')
    description = app_content.get('description', '')
    latest_version = app_content.get('version', '')
    package_name = app_content.get('appId', '')
    categories = app_content.get('genre', '')
    app_info = {
        'id': app_id,
        'name': name,
        'version': latest_version,
        'description': description,
        'packageName': package_name,
        'sourceCode': link,
        'categories': categories
    }
    return app_info


def extract_apps_info():
    apps_info = []
    app_id = 1
    with open('google_play_more_1k_repos.txt', 'r') as f:
        lines = f.readlines()
    for line in lines:
        link = line.strip().split()[0]
        owner, repo = extract_owner_repo(link)
        readme = run_query(owner, repo)
        if readme:
            google_id = extract_google_play_id(readme)
            if google_id:
                request = requests.request("GET", f"http://localhost:3000/api/apps/{google_id}")
                app_content = request.json()
                apps_info.append(get_app_info(link.strip(), app_id, app_content))
                app_id += 1
    output_data = {'appsInfo': apps_info}
    with open('google_play_apps_info.json', 'w') as f:
        json.dump(output_data, f, indent=4, ensure_ascii=False)


if __name__ == '__main__':
    with open('java-top-repos.txt', 'r') as f:
        lines = f.readlines()
    for line in lines:
        owner, repo = extract_owner_repo(line)
        readme = run_query(owner, repo)
        if readme:
            google_id = extract_google_play_id(readme)
            if google_id:
                res = requests.request("GET", f"http://localhost:3000/api/apps/{google_id}")
                content = res.json()
                if 'minInstalls' in content and content['minInstalls'] >= 1000:
                    filted_repos.add((f"{line.strip()}", content['maxInstalls']))
                else:
                    print(line, content)
    with open(f'java_more_than_1k_repos.txt', 'w') as f:
        for repo, maxInstalls in sorted(filted_repos, key=lambda e: e[1], reverse=True):
            f.write(f'{repo} {maxInstalls}\n')
