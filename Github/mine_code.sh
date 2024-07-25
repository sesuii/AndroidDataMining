#!/bin/bash
source=Github
in_file=./java-top-repos.txt

head -19000 $in_file | xargs -P32 -n1 -I% bash -c 'echo %;
line=$"%";
line_array=($line);
github_link=${line_array[0]};
source='$source';
name_part=$(echo $github_link | cut -d"/" -f4-6)
name=$(echo $name_part | cut -d"/" -f2)
org=$(echo $name_part | cut -d"/" -f1)
DIR=./data/$source/$org
if [ -d "$DIR/$name" ]; then
  echo "Directory $DIR/$name already exists. Skipping git clone."
else
  echo "github_link: $github_link"
  echo "source: $source"
  echo "Cloning $org/$name"
  mkdir -p $DIR
  echo $DIR
  git clone -q --depth 1 git@github.com:$org/$name $DIR/$name
fi'