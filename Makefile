# EdgeFlow ESP32 firmware helpers (host-side).
# These targets call ./scripts/idf which sources ESP-IDF for the single command.

ESP_PORT ?= /dev/ttyACM0
ESP_BAUD ?= 460800
ESP_TARGET ?= esp32s3
PROJ ?= esp32/model_client
IDF ?= ./scripts/idf

.PHONY: fw-target fw-build fw-flash fw-monitor fw-menuconfig fw-clean

fw-target:
	$(IDF) -C $(PROJ) set-target $(ESP_TARGET)

fw-build: fw-target
	$(IDF) -C $(PROJ) build

fw-flash: fw-target
	$(IDF) -C $(PROJ) -p $(ESP_PORT) -b $(ESP_BAUD) build flash

fw-monitor:
	$(IDF) -C $(PROJ) -p $(ESP_PORT) -b $(ESP_BAUD) monitor

fw-menuconfig: fw-target
	$(IDF) -C $(PROJ) menuconfig

fw-clean:
	$(IDF) -C $(PROJ) fullclean
