#include "storage.h"

const char *storage_fault_name(storage_fault_t fault)
{
    switch (fault) {
        case STORAGE_FAULT_NONE:          return "NO STORAGE FAULT";
        case STORAGE_FAULT_NOT_READY:    return "STORAGE NOT READY";
        case STORAGE_FAULT_OPEN:         return "SESSION OPEN FAILED";
        case STORAGE_FAULT_WRITE:        return "STORAGE WRITE FAILED";
        case STORAGE_FAULT_FLUSH:        return "STORAGE FLUSH FAILED";
        case STORAGE_FAULT_CLOSE:        return "SESSION CLOSE FAILED";
        case STORAGE_FAULT_CAPACITY:     return "STORAGE FULL";
        case STORAGE_FAULT_DRAIN_TIMEOUT:return "STORAGE DRAIN TIMEOUT";
        default:                         return "STORAGE ERROR";
    }
}
