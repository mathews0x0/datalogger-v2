#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
test_dir="$repo_dir/firmware/tests"
output=${TMPDIR:-/private/tmp}/racesense_network_provisioning_host_test

cc -std=c11 -D_POSIX_C_SOURCE=200809L \
  -I"$test_dir/host_stubs" \
  -I"$repo_dir/firmware/components/network/include" \
  "$test_dir/network_provisioning_host_test.c" \
  "$repo_dir/firmware/components/network/network_provisioning.c" \
  -o "$output"

"$output"
