import requests
import sys
import time

# Insert GitHub API token here, in place of *TOKEN*.
headers = {"Authorization": "token $github_token$>"}  # updated token
# Constants & language argument.
NUM_REPOS = 100_000
MIN_STARS = 10
LANGUAGE = "kotlin" if len(sys.argv) <= 1 else sys.argv[1]


def main():
    repositories = set()  # Use a set to avoid duplicate entries across pages.
    max_stars = 1_000_000_000  # Initialize at a very high value.
    while len(repositories) < NUM_REPOS:
        new_repositories = run_query(max_stars)
        if not new_repositories:
            break
        max_stars = min([stars for _, stars in new_repositories])
        # If a query returns no new repositories, drop it.
        if len(repositories | new_repositories) == len(repositories):
            break
        repositories.update(new_repositories)
        print(f'Collected {len(repositories):,} repositories so far; lowest number of stars: {max_stars:,}')

    with open(f'{LANGUAGE}-android-top-repos.txt', 'w') as f:
        for repository, _ in sorted(repositories, key=lambda e: e[1], reverse=True):
            f.write(f'{repository}\n')


def run_query(max_stars):
    end_cursor = None  # Used to track pagination.
    repositories = set()

    while end_cursor != "":
        # Extracts non-fork, recently active repositories in the provided language, in groups of 100. Leaves
        # placeholders for maximum stars and page cursor. The former allows us to retrieve more than 1,
        # 000 repositories by repeatedly lowering the bar.
        query = f"""
		{{
		  search(query: "android language:{LANGUAGE} fork:false pushed:>2017-01-01 sort:stars stars:<{max_stars}", type: REPOSITORY, first: 100 {', after: "' + end_cursor + '"' if end_cursor else ''}) {{
			edges {{
			  node {{
				... on Repository {{
				  url
				  isPrivate
				  isDisabled
				  isLocked
				  stargazers {{
					totalCount
				  }}
				}}
			  }}
			}}
			pageInfo {{
			  hasNextPage
			  endCursor
			}}
		  }}
		}}
		"""
        print(f'  Retrieving next page; {len(repositories)} repositories in this batch so far.')
        attempts = 0
        success = False
        while attempts < 3 or success:
            request = requests.post('https://api.github.com/graphql', json={'query': query}, headers=headers)
            content = request.json()
            if 'data' not in content or 'search' not in content['data']:
                print(content)
                # If this is simply a signal to pause querying, wait two minutes.
                if 'message' in content and 'wait' in content['message']:
                    attempts += 1
                    time.sleep(120)
                else:
                    # Assume we've hit the end of the stream.
                    break
            else:
                success = True
                break
        if not success:
            break
        end_cursor = get_end_cursor(content)
        new_repositories, is_done = get_repositories(content)
        repositories.update(new_repositories)
        if len(repositories) > NUM_REPOS or is_done:
            break
    return repositories


def get_end_cursor(content):
    page_info = content['data']['search']['pageInfo']
    has_next_page = page_info['hasNextPage']
    if has_next_page:
        return page_info['endCursor']
    return ""


def get_repositories(content):
    edges = content['data']['search']['edges']
    repositories_with_stars = []
    for edge in edges:
        if edge['node']['isPrivate'] is False and edge['node']['isDisabled'] is False and edge['node'][
            'isLocked'] is False:
            repository = edge['node']['url']
            star_count = edge['node']['stargazers']['totalCount']
            if star_count < MIN_STARS:
                return repositories_with_stars, True
            repositories_with_stars.append((repository, star_count))
    return repositories_with_stars, False


if __name__ == '__main__':
    main()
