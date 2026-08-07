#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "storage.h"

int main(void)
{
    const storage_fault_t faults[] = {
        STORAGE_FAULT_NONE,
        STORAGE_FAULT_NOT_READY,
        STORAGE_FAULT_OPEN,
        STORAGE_FAULT_WRITE,
        STORAGE_FAULT_FLUSH,
        STORAGE_FAULT_CLOSE,
        STORAGE_FAULT_CAPACITY,
        STORAGE_FAULT_DRAIN_TIMEOUT,
    };

    for (size_t i = 0; i < sizeof(faults) / sizeof(faults[0]); ++i) {
        const char *name = storage_fault_name(faults[i]);
        assert(name != NULL);
        assert(name[0] != '\0');
    }

    assert(strcmp(storage_fault_name(STORAGE_FAULT_WRITE),
                  "STORAGE WRITE FAILED") == 0);
    assert(strcmp(storage_fault_name(STORAGE_FAULT_FLUSH),
                  "STORAGE FLUSH FAILED") == 0);
    assert(strcmp(storage_fault_name(STORAGE_FAULT_CAPACITY),
                  "STORAGE FULL") == 0);
    assert(strcmp(storage_fault_name((storage_fault_t)99),
                  "STORAGE ERROR") == 0);

    puts("storage_fault_host_test: PASS");
    return 0;
}
