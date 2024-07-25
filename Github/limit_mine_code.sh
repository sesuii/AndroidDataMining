#!/bin/bash
source=Github
in_file=./kotlin-top-repos.txt

log_file=./log/mine_kotlin.log
exec > >(tee -a "$log_file") 2>&1

head -n 10 $in_file | while read -r line; do
    echo "$line";
    line_array=($line);
    github_link=${line_array[0]};
    name_part=$(echo $github_link | cut -d"/" -f4-6)
    name=$(echo $name_part | cut -d"/" -f2)
    org=$(echo $name_part | cut -d"/" -f1)
    DIR=./data/$source/$org
    URL="https://api.github.com/search/code?q=AndroidManifest.xml+repo:$org/$name"
    URL=${URL%$'\r'}

    if [ -d "$DIR/$name" ]; then
        echo "Directory $DIR/$name already exists. Skipping git clone."
    else
        while true; do
            status=$(curl -s -o response.json -w "%{http_code}" \
            -L -H "Accept: application/vnd.github+json" \
            -H "Authorization: Bearer <github_token>" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            "$URL")
            echo "status: $status"
            if [ "$status" = "403" ]; then
                echo "Rate limit exceeded. Sleeping for 10 seconds."
                sleep 10
            else
                break
            fi
        done
        total_count=$(cat response.json | jq '.total_count // -1')
        echo "total_count: $total_count"
        if [ "$total_count" -gt 0 ]; then
            echo "OK-AndroidManifest.xml found in $org/$name. Cloning repository."
            mkdir -p $DIR
            git clone -q --depth 1 git@github.com:$org/$name $DIR/$name
        else
            echo "AndroidManifest.xml not found in $org/$name. Skipping clone."
        fi
    fi
done