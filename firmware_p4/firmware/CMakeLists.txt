# RaceSense ESP32-P4 Firmware
# Target: Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3
# Framework: ESP-IDF v5.x
# Architecture: Native C/FreeRTOS (build from scratch)

cmake_minimum_required(VERSION 3.16)

# Include component directories
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_SOURCE_DIR}/components"
)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(racesense_p4)
