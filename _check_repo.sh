#!/bin/bash
# source this snippet from other scripts to check they are called from the correct part of the repo.

if [[ ! -d "src" && ! -d "packages" ]]; then
  echo "This script needs to be run in the repo root."
  exit 1
fi
