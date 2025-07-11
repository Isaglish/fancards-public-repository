#! /usr/bin/bash

# https://devhints.io/bash cheatsheet

current_branch=$(git name-rev --name-only HEAD)

merge_branch() {
    if [[ "${current_branch}" == "dev" ]]; then
        git checkout master
        git merge dev
        git push
        git checkout dev
        echo "merged dev to master"
    else
        echo "you are currently not in branch dev"
    fi
}

alias merge=merge_branch