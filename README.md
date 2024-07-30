# AndroidDataMining

获取 Google Play 和 F-Droid 平台的 App 信息和源代码。

## Google Play

step 1 `python gh_crawler.py`

通过Github GraphQL API获取满足初步筛选条件`language:Java/Kotlin，pushed>2017-01-01，star>10` repos

step 2 `python filter_googleplay_download.py`

筛选出repos中README中的Google Play应用链接，本地部署 [facundoolano/google-play-api](https://github.com/facundoolano/google-play-api) 第三方工具获取应用在Google Play上的下载量等信息，保留下载量大于1k的应用`more_than_1k_repos.txt`。

step 3 `bash mine_code.sh`

将repos clone到本地，得到源代码。

## F-Droid

step 1 `python fd_crawler.py`

通过F-Droid API获取当前在F-Droid平台上活跃的应用信息，筛选出可通过git clone获取源代码的项目`fdroid-github-repos.txt`。

step 2 `bash mine_code.sh`

将repos clone到本地，得到源代码。
