#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
test_dir="$repo_dir/firmware/tests"
idf_dir=${IDF_PATH:-/Users/mj/esp/esp-idf}
output=${TMPDIR:-/private/tmp}/racesense_network_contract_host_test

cc -std=c11 -D_POSIX_C_SOURCE=200809L \
  -I"$test_dir/host_stubs" \
  -I"$repo_dir/firmware/components/network/include" \
  -I"$idf_dir/components/json/cJSON" \
  "$test_dir/network_contract_host_test.c" \
  "$repo_dir/firmware/components/network/network_contract.c" \
  "$idf_dir/components/json/cJSON/cJSON.c" \
  -lm -o "$output"

"$output"
