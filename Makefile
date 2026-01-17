ESP_PORT ?= /dev/ttyACM0
ESP_BAUD ?= 460800
IDF      := ./scripts/idf
PROJ     := esp32/model_client

fw-target:
	$(IDF) -C $(PROJ) set-target esp32s3

fw-flash: fw-target
	$(IDF) -C $(PROJ) -p $(ESP_PORT) -b $(ESP_BAUD) build flash

fw-monitor:
	$(IDF) -C $(PROJ) -p $(ESP_PORT) -b $(ESP_BAUD) monitor

# If you previously built before pulling this repo, your sdkconfig may still
# point to the default partition table (no 'model' SPIFFS partition). This
# target forces a clean reconfigure.
fw-reconfigure:
	rm -rf $(PROJ)/build $(PROJ)/sdkconfig $(PROJ)/sdkconfig.old
	$(IDF) -C $(PROJ) set-target esp32s3
