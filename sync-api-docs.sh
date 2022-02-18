#! /usr/bin/env bash
# Copyright (C) 2022 Sebastian Pipping <sebastian@pipping.org>
# Licensed under the MIT license

require_clean_git() {
    git diff --quiet || exit 1
    git diff --cached --quiet || exit 1
}

PS4='# '
set -x

set -e

abstargetdir="$(dirname "$0")"/doc/api/latest
[[ ${abstargetdir:0:1} != / ]] && abstargetdir="${PWD}/${abstargetdir}"

require_clean_git

[[ -d "${abstargetdir}" ]] && git rm -r "${abstargetdir}"

# Build fresh docs from libexpat Git master
abstempdir="$(mktemp -d)"
absversionfile="$(mktemp)"
(
    cd "${abstempdir}"
    git clone https://github.com/libexpat/libexpat.git
    cd libexpat
    git describe --tags | sed -E 's,R_(.+)_(.+)_(.+),\1.\2.\3,' | tee "${absversionfile}"
)
files_to_copy=(
    ok.min.css
    reference.html
    style.css
)
mkdir -p "${abstargetdir}"
( cd "${abstempdir}"/libexpat/expat/doc/ && cp -v "${files_to_copy[@]}" "${abstargetdir}" )
mv -v "${abstargetdir}"/{reference,index}.html 
rm -Rf "${abstempdir}"

git add "${abstargetdir}"
git ci -m "API docs: Update to version $(cat "${absversionfile}")"
