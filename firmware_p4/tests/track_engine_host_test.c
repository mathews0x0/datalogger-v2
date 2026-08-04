#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "track_engine.h"

static track_event_t s_events[8];
static int s_event_count;

static void on_event(const track_event_t *event, void *ctx)
{
    (void)ctx;
    assert(event != NULL);
    assert(s_event_count < (int)(sizeof(s_events) / sizeof(s_events[0])));
    s_events[s_event_count++] = *event;
}

static void write_track_file(const char *path)
{
    FILE *file = fopen(path, "w");
    assert(file != NULL);
    fputs("{"
          "\"name\":\"Host Replay Circuit\","
          "\"start_line\":{\"lat\":12.000000,\"lon\":77.000000,\"radius_m\":8,\"heading\":90},"
          "\"sectors\":["
              "{\"end_lat\":12.000000,\"end_lon\":77.000200,\"radius_m\":8},"
              "{\"end_lat\":12.000000,\"end_lon\":77.000400,\"radius_m\":8}"
          "],"
          "\"tbl\":{\"lap_time\":20.0,\"sectors\":[10.0,10.0]},"
          "\"device_layout\":{"
              "\"polyline\":[{\"x\":0,\"y\":500},{\"x\":1000,\"y\":500}],"
              "\"start_marker\":{\"x\":0,\"y\":500},"
              "\"sector_markers\":[{\"x\":500,\"y\":500,\"sector_index\":1}],"
              "\"bounds\":{\"min_lat\":11.9,\"max_lat\":12.1,\"min_lon\":76.9,\"max_lon\":77.1}"
          "}"
          "}", file);
    fclose(file);
}

int main(void)
{
    const char *path = "/private/tmp/racesense_track_engine_host_test.json";
    write_track_file(path);

    assert(track_engine_init() == ESP_OK);
    assert(track_engine_set_event_cb(on_event, NULL) == ESP_OK);
    assert(track_engine_load_track(path) == ESP_OK);
    assert(strcmp(track_engine_get_track_name(), "Host Replay Circuit") == 0);
    track_display_layout_t layout = {0};
    assert(track_engine_get_display_layout(&layout));
    assert(layout.polyline_count == 2);
    assert(layout.has_start_marker);
    assert(layout.sector_marker_count == 1);
    assert(layout.sector_count == 2);
    assert(layout.tbl_lap_time == 20.0f);
    assert(layout.tbl_sector_times[1] == 10.0f);

    /* Approach and cross the start line eastbound. */
    track_engine_update_gps(12.000000, 76.999800, 0);
    track_engine_update_gps(12.000000, 77.000000, 1000);
    assert(s_event_count == 1);
    assert(s_events[0].type == TRACK_EVT_FOUND);
    assert(track_engine_is_track_found());

    /* Cross S1, then repeat the same point to simulate GPS jitter. */
    track_engine_update_gps(12.000000, 77.000200, 11500);
    assert(s_event_count == 2);
    assert(s_events[1].type == TRACK_EVT_SECTOR);
    assert(s_events[1].sector_index == 0);
    assert(s_events[1].tbl_time == 10.0f);
    assert(s_events[1].sub_type == TRACK_EVT_SECTOR_NEUTRAL);
    track_engine_update_gps(12.000000, 77.000200, 11600);
    assert(s_event_count == 2);

    /* Cross S2 and complete the lap at 21.1 seconds: slower than the TBL. */
    track_engine_update_gps(12.000000, 77.000400, 22100);
    assert(s_event_count == 3);
    assert(s_events[2].type == TRACK_EVT_LAP);
    assert(s_events[2].lap_time == 21.1f);
    assert(s_events[2].sub_type == TRACK_EVT_SECTOR_SLOW);
    assert(track_engine_get_lap_count() == 1);
    assert(track_engine_get_current_lap_number() == 2);

    char lap_time[16];
    track_engine_get_current_lap_time(23000, lap_time, sizeof(lap_time));
    assert(strcmp(lap_time, "0.900") == 0);

    /* Invalid coordinates are ignored and cannot create timing events. */
    track_engine_update_gps(100.0, 77.0, 23000);
    track_engine_update_gps(0.0, 0.0, 24000);
    assert(s_event_count == 3);

    track_engine_reset_session();
    assert(!track_engine_is_track_found());
    assert(track_engine_get_current_lap_number() == 0);

    puts("track_engine_host_test: PASS");
    return 0;
}
