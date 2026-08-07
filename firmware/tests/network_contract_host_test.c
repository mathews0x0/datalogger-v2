#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "network_contract.h"

int main(void)
{
    char url[256];
    assert(network_contract_build_url("https://racesense.in",
                                     NETWORK_ENDPOINT_DEVICE_PING,
                                     url, sizeof(url)) == ESP_OK);
    assert(strcmp(url, "https://racesense.in/api/device/ping") == 0);

    assert(network_contract_build_url("https://racesense.in/api/upload/",
                                     NETWORK_ENDPOINT_UPLOAD_BATCH,
                                     url, sizeof(url)) == ESP_OK);
    assert(strcmp(url, "https://racesense.in/api/upload/batch") == 0);

    char encoded[128];
    assert(network_contract_url_encode("sess 01+test.csv", encoded,
                                      sizeof(encoded)) == ESP_OK);
    assert(strcmp(encoded, "sess%2001%2Btest.csv") == 0);

    const char *response =
        "{\"active_track\":{"
        "\"track_name\":\"Contract Circuit\","
        "\"start_line\":{\"lat\":12.0,\"lon\":77.0,\"radius_m\":20},"
        "\"sectors\":[{\"end_lat\":12.0,\"end_lon\":77.001,\"radius_m\":15}],"
        "\"tbl\":{\"sectors\":[12.5]},"
        "\"sector_count\":1,"
        "\"device_layout\":{\"polyline\":[]}}}";
    char payload[2048];
    assert(network_contract_extract_active_track(response, strlen(response),
                                                 payload, sizeof(payload)) == ESP_OK);
    assert(strstr(payload, "Contract Circuit") != NULL);
    assert(strstr(payload, "device_layout") != NULL);
    assert(strstr(payload, "sector_count") != NULL);

    assert(network_contract_extract_active_track(
               "{\"active_track\":null}", 23, payload, sizeof(payload)) == ESP_ERR_NOT_FOUND);
    assert(network_contract_extract_active_track(
               "{\"active_track\":{\"track_name\":\"bad\",\"start_line\":{\"lat\":99,\"lon\":77},\"sectors\":[]}}",
               strlen("{\"active_track\":{\"track_name\":\"bad\",\"start_line\":{\"lat\":99,\"lon\":77},\"sectors\":[]}}"),
               payload, sizeof(payload)) == ESP_ERR_INVALID_ARG);

    puts("network_contract_host_test: PASS");
    return 0;
}
