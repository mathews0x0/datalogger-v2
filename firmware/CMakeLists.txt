# RaceSense Native Firmware
# Primary target: Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3
# Framework: ESP-IDF v5.x
# Architecture: Native C/FreeRTOS (build from scratch)

cmake_minimum_required(VERSION 3.16)

# One RaceSense Mark number is shared by the server and device firmware.
# Fail configuration rather than silently emitting an unrelated identity.
set(RACESENSE_VERSION_FILE "${CMAKE_CURRENT_SOURCE_DIR}/../server/VERSION")
if(NOT EXISTS "${RACESENSE_VERSION_FILE}")
    message(FATAL_ERROR "Missing shared Mark number: ${RACESENSE_VERSION_FILE}")
endif()
file(READ "${RACESENSE_VERSION_FILE}" RACESENSE_MARK)
string(STRIP "${RACESENSE_MARK}" RACESENSE_MARK)
if(NOT RACESENSE_MARK MATCHES "^[0-9]+$")
    message(FATAL_ERROR "RaceSense Mark number must be numeric: '${RACESENSE_MARK}'")
endif()
set(PROJECT_VER "Mark ${RACESENSE_MARK}")

# Include component directories
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_SOURCE_DIR}/components"
)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(racesense)
