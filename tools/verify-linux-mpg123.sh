#!/bin/bash
# One bounded library-only comparison, not a full runtime build.
set -euo pipefail
if [ "$#" -ne 1 ]; then
    echo "Usage: bash verify-linux-mpg123.sh /absolute/path/libmpg123.so.0" >&2
    exit 2
fi
reference=$(readlink -f "$1")
sha256sum "$reference"
readelf -n "$reference"
readelf -d "$reference" | grep -E 'NEEDED|RPATH|RUNPATH|SONAME'
nm -D --defined-only "$reference" | grep -E 'mpg123_(distversion|version)' || true
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
cp "$reference" "$work/reference.so"
curl --fail --location --retry 2 --max-time 90 \
    https://www.mpg123.de/download/mpg123-1.31.3.tar.bz2 \
    -o "$work/mpg123-1.31.3.tar.bz2"
echo '1ca77d3a69a5ff845b7a0536f783fee554e1041139a6b978f6afe14f5814ad1a  mpg123-1.31.3.tar.bz2' \
    | (cd "$work" && sha256sum -c -)
curl --fail --location --retry 2 --max-time 90 \
    https://codeload.github.com/love2d/love-appimage-source/tar.gz/3b3d6547093ee370d8a846594ee3b85ed0cb9ae7 \
    -o "$work/recipe.tar.gz"
echo '98ef969e29d69a271a848623517d634bc6b273a501d48e780323a77bae4e95c1  recipe.tar.gz' \
    | (cd "$work" && sha256sum -c -)
docker run --rm -v "$work:/audit" ubuntu:20.04 bash -euc '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends build-essential binutils
    base=/home/runner/work/love-appimage-source/love-appimage-source
    mkdir -p "$base"
    cd "$base"
    tar -xzf /audit/recipe.tar.gz --strip-components=1
    cp /audit/mpg123-1.31.3.tar.bz2 .
    gcc --version | head -n 1
    make installdir/lib/libmpg123.so -j2 > /audit/make.log 2>&1
    built=installdir/lib/libmpg123.so.0
    readelf -n "$built"
    matched=true
    for section in .text .rodata; do
        objcopy --dump-section "$section=/audit/original$section" /audit/reference.so
        objcopy --dump-section "$section=/audit/rebuilt$section" "$built"
        sha256sum "/audit/original$section" "/audit/rebuilt$section"
        if ! cmp -s "/audit/original$section" "/audit/rebuilt$section"; then
            matched=false
        fi
    done
    if "$matched"; then
        echo "MATCH: shipped .text and .rodata equal the pinned mpg123 1.31.3 build."
        echo "Record this as source-to-code evidence, not a byte-identical whole-file rebuild."
    else
        echo "NO MATCH: version remains recipe-inferred; no alternate versions attempted."
        exit 1
    fi
'
