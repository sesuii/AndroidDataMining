# -*- coding: utf-8 -*-
"""
Provides a mechanism for identifying projects on GitHub
"""
import argparse
import os
import sys
import time
import typing as t
from datetime import datetime, timedelta

import attr
import requests
from loguru import logger

RESULTS_PER_PAGE: int = 100
MAX_PAGES_PER_QUERY: int = 10
MAX_RESULTS_PER_QUERY: int = RESULTS_PER_PAGE * MAX_PAGES_PER_QUERY
MIN_FILE_SIZE: int = 1
MAX_FILE_SIZE: int = 50_000_000
NUM_REPOS = 250_000
MIN_STARS = 10
LANGUAGE = "python"


@attr.s(auto_attribs=True)
class Credentials:
    user: str
    token: str = attr.ib(repr=False)
    next_usable_at: datetime = attr.ib(default=datetime.min)

    @classmethod
    def from_line(cls, line: str) -> "Credentials":
        user, token = line.strip().split(":", 2)
        return Credentials(user, token)

    @classmethod
    def load_all_from_file(cls, filename: str) -> t.List["Credentials"]:
        with open(filename, "r") as fh:
            return [cls.from_line(line) for line in fh]


@attr.s
class GitHubCodeSearch:
    """Provides a wrapper around the GitHub API that handles multiple API
    keys without exposing implementation details to the client."""
    _credential_pool: t.List[Credentials] = attr.ib()
    _session: requests.Session = attr.ib(init=False)
    _per_request_delay: float = attr.ib(default=1.0)
    _per_request_delay_increment: float = attr.ib(default=0.0)

    @staticmethod
    def for_credentials_file(filename: str) -> "GitHubCodeSearch":
        credential_pool = Credentials.load_all_from_file(filename)
        logger.info(f"using GitHub credentials: {credential_pool}")
        return GitHubCodeSearch(credential_pool)

    def __attrs_post_init__(self) -> None:
        self._session = requests.Session()
        self._session.headers["accept"] = "application/vnd.github.v3+json"

    def _get(self, url: str, **kwargs: t.Any) -> requests.Response:
        # before making a request, we wait for a small period of time to avoid
        # spamming the GitHub API with too many requests and getting a 403
        time.sleep(self._per_request_delay)

        # wait until we can use the credentials at the front of the queue
        auth = self._credential_pool[0]
        time_now = datetime.now()
        if auth.next_usable_at > time_now:
            wait_time = (auth.next_usable_at - time_now).total_seconds() + 1
            time.sleep(wait_time)

        response: requests.Response = self._session.get(
            url,
            **kwargs,
            auth=(auth.user, auth.token),
        )

        if response.status_code == 403:
            # sometimes GitHub gets angry before we've exceed our API rate limits
            # if so, we back off for the specified wait period and try again
            if "retry-after" in response.headers:
                wait_time = int(response.headers["retry-after"])
                logger.debug(f"403: retry-after expires after {wait_time} secs")
                time.sleep(wait_time + 1)

                # we also increment our per-request delay to avoid the same issue
                # happening again
                self._per_request_delay += self._per_request_delay_increment
                logger.debug("incremented per-request delay: "
                             f"{self._per_request_delay:.3f} secs")

                return self._get(url, **kwargs)

            # check if we've hit the primary API rate limit for the current API key
            contains_ratelimit = "x-ratelimit-remaining" in response.headers
            if contains_ratelimit and response.headers["x-ratelimit-remaining"] == 0:
                logger.debug(f"exhausted API credentials: {auth}")
                self._credential_pool.pop(0)
                auth.next_usable_at = datetime.utcfromtimestamp(int(response.headers["x-ratelimit-reset"]))
                self._credential_pool.append(auth)
                logger.debug(f"switching to API credentials: {self._credential_pool[0]}")
                return self._get(url, **kwargs)

            # check if we've hit a secondary API rate limit for the current API key
            jsn = response.json()
            if jsn[
                "documentation_url"] == "https://docs.github.com/en/free-pro-team@latest/rest/overview/resources-in-the-rest-api#secondary-rate-limits":  # noqa: E501
                logger.debug(f"hit secondary API rate limit: {auth}")
                self._credential_pool.pop(0)
                auth.next_usable_at = datetime.now() + timedelta(seconds=60)
                self._credential_pool.append(auth)
                logger.debug(f"switching to API credentials: {self._credential_pool[0]}")
                return self._get(url, **kwargs)

            # unhandled 403
            logger.error(f"Unexpected 403 response: {response.headers}\nJSON: {response.json()}")
            raise Exception("Unexpected 403 response")

        return response

    def _run_constrained_query(
            self,
            query: str,
            num_results: int,
    ) -> t.Iterator[t.Dict[str, t.Any]]:
        """Obtains the results for a constrained query."""
        logger.debug(f"fetching {num_results} expected results for constrained query: {query}")
        params = {
            "q": query,
            "per_page": RESULTS_PER_PAGE,
        }

        num_pages = num_results // RESULTS_PER_PAGE
        assert num_pages <= MAX_PAGES_PER_QUERY

        for page in range(1, num_pages + 1):
            params["page"] = str(page)
            response = self._get("https://api.github.com/search/repositories", params=params)
            assert response.status_code == 200
            yield from response.json()["items"]

        logger.debug(f"fetched {num_results} expected results for constrained query: {query}")

    def _compute_number_of_results(self, query: str) -> int:
        """Determines the number of results for a given query."""
        response = self._get("https://api.github.com/search/repositories", params={"q": query})
        return response.json()["total_count"]

    def inspect_content(self, repo_url: str, file_path: str):
        response = self._get(f"{repo_url}/contents/{file_path}")
        response = requests.get(response.json()["download_url"])
        return response.content

    def _search_interval(
            self,
            query: str,
            min_file_size: int,
            max_file_size: int,
    ) -> t.Iterator[t.Dict[str, t.Any]]:
        # TODO we could exploit search ordering to double MAX_RESULTS_PER_QUERY
        interval_size = max_file_size - min_file_size + 1
        constrained_query = f"{query} size:{min_file_size}..{max_file_size}"

        # number of results within interval
        num_results = self._compute_number_of_results(constrained_query)
        logger.debug(
            f"found {num_results} results for constrained query: {constrained_query}",
        )

        has_too_many_results = num_results > MAX_RESULTS_PER_QUERY
        is_smallest_interval = interval_size == 1

        # neato: we can fetch the complete results for the query
        if not has_too_many_results:
            yield from self._run_constrained_query(constrained_query, num_results)

        # we have too many results, but we can divide the interval
        elif not is_smallest_interval:
            logger.debug(f"interval is too large ({num_results} > {MAX_RESULTS_PER_QUERY})")

            left_interval: t.Tuple[int, int]
            right_interval: t.Tuple[int, int]

            if interval_size == 2:
                left_interval = (min_file_size, min_file_size)
                right_interval = (max_file_size, max_file_size)
            else:
                interval_midpoint = min_file_size + (interval_size // 2)
                left_interval = (min_file_size, interval_midpoint)
                right_interval = (interval_midpoint + 1, max_file_size)

            logger.debug(f"divided interval: {left_interval}, {right_interval}")

            logger.debug(f"collecting results for left interval: {left_interval}")
            yield from self._search_interval(query, *left_interval)

            logger.debug(f"collecting results for right interval: {right_interval}")
            yield from self._search_interval(query, *right_interval)

        # interval is as small as possible, but we have more than the maximum number
        # of results -- we just have to lose some results :-(
        else:
            num_lost_results = num_results - MAX_RESULTS_PER_QUERY
            logger.debug(
                f"cannot shrink interval further: {constrained_query} "
                f"[lost {num_lost_results} of {num_results} results]",
            )
            yield from self._run_constrained_query(constrained_query, MAX_RESULTS_PER_QUERY)

    def search(
            self,
            query: str,
            min_file_size: int = MIN_FILE_SIZE,
            max_file_size: int = MAX_FILE_SIZE,
    ) -> t.Iterator[t.Dict[str, t.Any]]:
        """

        Returns
        -------
        t.Iterator[t.Dict[str, t.Any]]
            An iterator over each of the individual code search matches
        """
        num_results = 0
        logger.info(f"executing query [{query}]")
        for result in self._search_interval(query, min_file_size, max_file_size):
            num_results += 1
            yield result
        logger.info(f"executed query [{query}] (found {num_results} results)")


@attr.s
class GitHubRepoFinder:
    """
    Uses the code search functionality.
    """
    _api: GitHubCodeSearch = attr.ib()
    _min_file_size: int = attr.ib(default=MIN_FILE_SIZE)
    _max_file_size: int = attr.ib(default=MAX_FILE_SIZE)

    def _repos_for_query(self, query: str) -> t.Iterator[str]:
        repos: t.Set[str] = set()
        for result in self._api.search(
                query=query,
                min_file_size=self._min_file_size,
                max_file_size=self._max_file_size,
        ):
            repo_url = result["html_url"]
            # contents = self._api.inspect_content(result["repository"]["url"], result["path"]).decode()
            if repo_url not in repos:
                repos.add(repo_url)
                yield repo_url, result["stargazers_count"]

    def run(self) -> t.Iterator[str]:
        num_results = 0
        query = f"language:{LANGUAGE} pushed:>2020-01-01 stars:>{MIN_STARS}"
        for repo_url, stars in self._repos_for_query(query):
            num_results += 1
            yield repo_url, stars
        logger.debug(f"found a total of {num_results} repositories via GitHub")


def _setup_logging(log_to_file: str) -> None:
    # disable default logging
    logger.remove()

    # log to stderr
    log_format = "<green>[{time:YYYY-MM-DD HH:mm:ss}]</green> <b>{level}:</b> {message}"
    logger.add(sys.stderr, colorize=True, format=log_format, level="DEBUG")

    # log to file
    logger.add(log_to_file, format=log_format, mode="w")

    logger.enable("rosanatomy")


def main() -> None:
    parser = argparse.ArgumentParser("Obtains a list of ROS projects from GitHub")
    parser.add_argument(
        "--github-auth",
        default="auth.txt",
        help=("the name of a plaintext file containing a colon-delimited "
              "GitHub username and personal access token."),
    )
    parser.add_argument(
        "--output",
        default=f"{LANGUAGE}_repos.txt",
        help="the name of the file to which discovered repos should be written",
    )
    parser.add_argument(
        "--log-filename",
        default="repo-finder-{time}.log",
        help="the name of the file to which logs should be written",
    )
    parser.add_argument(
        "--github-min-file-size",
        type=int,
        default=MIN_FILE_SIZE,
        help="the minimum file size to use when searching GitHub",
    )
    parser.add_argument(
        "--github-max-file-size",
        type=int,
        default=MAX_FILE_SIZE,
        help="the maximum file size to use when searching GitHub",
    )
    args = parser.parse_args()

    _setup_logging(args.log_filename)

    try:
        github_api = GitHubCodeSearch.for_credentials_file(args.github_auth)
    except FileNotFoundError:
        print(f"FATAL ERROR: unable to locate GitHub credentials file [{args.github_auth}]")
        sys.exit(1)

    # ensure that we can write to the given output file before we embark
    # on the expensive process of mining
    output_filename = args.output
    logger.info(f"repo URLs will be written to {output_filename}")

    # maintain track of all unique URLs
    repo_urls: t.Set[str] = set()

    # if the output file already exists, keep track of the unique URLs that
    # we've already discovered
    if os.path.isfile(output_filename):
        logger.info(f"loading known URLs from existing output file: {output_filename}")
        with open(output_filename, "r") as fh:
            repo_urls.update(url.strip() for url in fh.readlines())
        logger.info(f"loaded {len(repo_urls)} URLs from existing output file: {output_filename}")

    with open(output_filename, "a") as fh:
        github_finder = GitHubRepoFinder(
            api=github_api,
            min_file_size=args.github_min_file_size,
            max_file_size=args.github_max_file_size,
        )
        for url, stars in github_finder.run():
            if url not in repo_urls:
                repo_urls.add(url)
                logger.debug(f"found new repository: {url} (stars: {stars})")
                fh.write(f"{url}\t:{stars}\n")

            if len(repo_urls) > NUM_REPOS:
                break


main()
