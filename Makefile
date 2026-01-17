ESP_PORT ?= /dev/ttyACM0
ESP_BAUD ?= 460800

IDF  := ./scripts/idf
PROJ := esp32/model_client

.PHONY: fw-target fw-build fw-flash fw-monitor

fw-target:
	$(IDF) -C $(PROJ) set-target esp32s3

fw-build: fw-target
	$(IDF) -C $(PROJ) build

fw-flash: fw-target
	$(IDF) -C $(PROJ) -p $(ESP_PORT) -b $(ESP_BAUD) build flash

fw-monitor:
	$(IDF) -C $(PROJ) -p $(ESP_PORT) -b $(ESP_BAUD) monitor
