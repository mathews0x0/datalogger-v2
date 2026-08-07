#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
test_dir="$repo_dir/firmware/tests"
output=${TMPDIR:-/private/tmp}/racesense_storage_fault_host_test

cc -std=c11 -Wall -Wextra -Werror \
  -I"$test_dir/host_stubs" \
  -I"$repo_dir/firmware/components/storage/include" \
  -I"$repo_dir/firmware/components/sensors/include" \
  -I"$repo_dir/firmware/components/drivers/include" \
  "$test_dir/storage_fault_host_test.c" \
  "$repo_dir/firmware/components/storage/storage_fault.c" \
  -o "$output"

"$output"
