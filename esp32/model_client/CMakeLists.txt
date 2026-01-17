cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(model_client)
spiffs_create_partition_image(model spiffs_image FLASH_IN_PROJECT)
