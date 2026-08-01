idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    PRIV_REQUIRES
        bsp
        drivers
        storage
        sensors
        ui
        network
        track_engine
        imu_calibration
        feedback
)
