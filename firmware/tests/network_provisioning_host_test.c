#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "network_provisioning.h"

static network_device_config_t saved_config(void)
{
    network_device_config_t cfg = {0};
    strcpy(cfg.api_url, "https://racesense.in");
    strcpy(cfg.password, "old-pass");
    return cfg;
}

int main(void)
{
    network_device_config_t saved = saved_config();
    network_device_config_t candidate = {0};
    network_provisioning_source_t source = NETWORK_PROVISIONING_NONE;

    assert(network_provisioning_parse_request(
               "GET",
               "/setup?ssid=Pit%20Hotspot&pass=p%26ss%2B1&token=rsk_1234&api_url=https%3A%2F%2Fracesense.in%2Fapi%2Fupload",
               NULL, &saved, &candidate, &source) == ESP_OK);
    assert(source == NETWORK_PROVISIONING_MAGIC_LINK);
    assert(strcmp(candidate.ssid, "Pit Hotspot") == 0);
    assert(strcmp(candidate.password, "p&ss+1") == 0);
    assert(strcmp(candidate.token, "rsk_1234") == 0);
    assert(strcmp(candidate.api_url, "https://racesense.in/api/upload") == 0);

    memset(&candidate, 0, sizeof(candidate));
    assert(network_provisioning_parse_request(
               "POST", "/setup",
               "ssid=Home+WiFi&password=secret&token=rsk_form&api_url=https%3A%2F%2Fracesense.in",
               &saved, &candidate, &source) == ESP_OK);
    assert(source == NETWORK_PROVISIONING_FORM);
    assert(strcmp(candidate.ssid, "Home WiFi") == 0);
    assert(strcmp(candidate.password, "secret") == 0);
    assert(strcmp(candidate.token, "rsk_form") == 0);

    assert(network_provisioning_parse_request(
               "GET", "/setup", NULL, &saved, &candidate, &source) == ESP_ERR_NOT_FOUND);
    assert(network_provisioning_parse_request(
               "GET", "/setup?ssid=wifi&token=bad&api_url=https%3A%2F%2Fracesense.in",
               NULL, &saved, &candidate, &source) == ESP_ERR_INVALID_ARG);
    assert(network_provisioning_parse_request(
               "POST", "/setup",
               "ssid=wifi%0Aevil&password=x&token=rsk_bad&api_url=https%3A%2F%2Fracesense.in",
               &saved, &candidate, &source) == ESP_ERR_INVALID_ARG);

    puts("network_provisioning_host_test: PASS");
    return 0;
}
