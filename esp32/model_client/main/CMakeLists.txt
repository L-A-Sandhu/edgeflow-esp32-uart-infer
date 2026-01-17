idf_component_register(
  SRCS "main.c"
  INCLUDE_DIRS "."
  REQUIRES spiffs esp_timer esp_driver_uart
)
