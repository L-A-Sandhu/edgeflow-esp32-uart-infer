\
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <inttypes.h>
#include <stdarg.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_err.h"
#include "esp_spiffs.h"
#include "esp_heap_caps.h"
#include "esp_task_wdt.h"

#include "driver/uart.h"

#define DISABLE_TASK_WDT 1

// UART protocol (UART0)
static const uint8_t MAGIC_META[4] = {'M','E','T','A'};
static const uint8_t MAGIC_INFR[4] = {'I','N','F','R'};
static const uint8_t MAGIC_INFO[4] = {'I','N','F','O'};
static const uint8_t MAGIC_PRED[4] = {'P','R','E','D'};

// Debug UART (UART1) - optional, does not interfere with UART0 protocol
#define DBG_UART UART_NUM_1
#define DBG_TX_PIN 17
#define DBG_RX_PIN 18
#define DBG_BAUD 115200

static void dbg_init(void) {
    uart_config_t cfg = {
        .baud_rate = DBG_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    uart_param_config(DBG_UART, &cfg);
    uart_set_pin(DBG_UART, DBG_TX_PIN, DBG_RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    uart_driver_install(DBG_UART, 4096, 0, 0, NULL, 0);
}

static void dbg_printf(const char *fmt, ...) {
    char buf[256];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    if (n > 0) uart_write_bytes(DBG_UART, buf, n);
}

// Model bin header
typedef struct __attribute__((packed)) {
    uint8_t magic[4];   // "LST0"
    uint16_t T;
    uint16_t F;
    uint16_t H;
    uint16_t hidden;
    uint32_t reserved;
} model_hdr_t;

typedef struct {
    model_hdr_t hdr;
    float *buf;     // contiguous buffer
    float *W_ih;    // (4h, F)
    float *W_hh;    // (4h, h)
    float *b;       // (4h)
    float *W_fc;    // (H, h)
    float *b_fc;    // (H)
    float *x_tmp;   // (T*F)
    float *y_tmp;   // (H)
} model_t;

static model_t g = {0};

static inline float sigmoidf_fast(float x) {
    if (x >= 0.0f) {
        float z = expf(-x);
        return 1.0f / (1.0f + z);
    } else {
        float z = expf(x);
        return z / (1.0f + z);
    }
}

static esp_err_t mount_model_spiffs(void) {
    esp_vfs_spiffs_conf_t conf = {
        .base_path = "/model",
        .partition_label = "model",
        .max_files = 5,
        .format_if_mount_failed = true,
    };
    return esp_vfs_spiffs_register(&conf);
}

static esp_err_t load_model_bin(const char *path) {
    dbg_printf("[DBG] load_model_bin path=%s\r\n", path);

    FILE *f = fopen(path, "rb");
    if (!f) {
        dbg_printf("[ERR] fopen failed\r\n");
        return ESP_FAIL;
    }

    model_hdr_t hdr;
    if (fread(&hdr, 1, sizeof(hdr), f) != sizeof(hdr)) {
        dbg_printf("[ERR] read header failed\r\n");
        fclose(f);
        return ESP_FAIL;
    }
    if (memcmp(hdr.magic, "LST0", 4) != 0) {
        dbg_printf("[ERR] bad magic\r\n");
        fclose(f);
        return ESP_FAIL;
    }

    const int T = hdr.T, F = hdr.F, H = hdr.H, h = hdr.hidden;
    const int gates = 4 * h;

    size_t n_wih = (size_t)gates * (size_t)F;
    size_t n_whh = (size_t)gates * (size_t)h;
    size_t n_b   = (size_t)gates;
    size_t n_fcw = (size_t)H * (size_t)h;
    size_t n_fcb = (size_t)H;
    size_t total = n_wih + n_whh + n_b + n_fcw + n_fcb;

    dbg_printf("[DBG] hdr T=%d F=%d H=%d h=%d total_floats=%u\r\n", T, F, H, h, (unsigned)total);

    float *buf = (float *)heap_caps_malloc(total * sizeof(float), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buf) buf = (float *)heap_caps_malloc(total * sizeof(float), MALLOC_CAP_8BIT);
    if (!buf) {
        dbg_printf("[ERR] malloc model buffer failed\r\n");
        fclose(f);
        return ESP_ERR_NO_MEM;
    }

    size_t got = fread(buf, sizeof(float), total, f);
    fclose(f);
    if (got != total) {
        dbg_printf("[ERR] short read got=%u need=%u\r\n", (unsigned)got, (unsigned)total);
        heap_caps_free(buf);
        return ESP_FAIL;
    }

    g.hdr = hdr;
    g.buf = buf;
    size_t off = 0;
    g.W_ih = g.buf + off; off += n_wih;
    g.W_hh = g.buf + off; off += n_whh;
    g.b    = g.buf + off; off += n_b;
    g.W_fc = g.buf + off; off += n_fcw;
    g.b_fc = g.buf + off; off += n_fcb;

    g.x_tmp = (float *)heap_caps_malloc((size_t)T * (size_t)F * sizeof(float), MALLOC_CAP_8BIT);
    g.y_tmp = (float *)heap_caps_malloc((size_t)H * sizeof(float), MALLOC_CAP_8BIT);
    if (!g.x_tmp || !g.y_tmp) {
        dbg_printf("[ERR] malloc io buffers failed\r\n");
        if (g.x_tmp) heap_caps_free(g.x_tmp);
        if (g.y_tmp) heap_caps_free(g.y_tmp);
        heap_caps_free(g.buf);
        memset(&g, 0, sizeof(g));
        return ESP_ERR_NO_MEM;
    }

    dbg_printf("[DBG] model loaded ok\r\n");
    return ESP_OK;
}

static void lstm_infer_one(const float *x_TF, float *y_H) {
    const int T = g.hdr.T, F = g.hdr.F, H = g.hdr.H, h = g.hdr.hidden;
    const int gates = 4 * h;

    float *hvec = (float *)alloca((size_t)h * sizeof(float));
    float *cvec = (float *)alloca((size_t)h * sizeof(float));
    float *gpre = (float *)alloca((size_t)gates * sizeof(float));
    memset(hvec, 0, (size_t)h * sizeof(float));
    memset(cvec, 0, (size_t)h * sizeof(float));

    for (int t = 0; t < T; ++t) {
        const float *xt = x_TF + (size_t)t * (size_t)F;

        for (int i = 0; i < gates; ++i) {
            float s = g.b[i];
            const float *wih = g.W_ih + (size_t)i * (size_t)F;
            for (int j = 0; j < F; ++j) s += wih[j] * xt[j];

            const float *whh = g.W_hh + (size_t)i * (size_t)h;
            for (int j = 0; j < h; ++j) s += whh[j] * hvec[j];

            gpre[i] = s;
        }

        for (int k = 0; k < h; ++k) {
            float i_gate = sigmoidf_fast(gpre[k]);
            float f_gate = sigmoidf_fast(gpre[h + k]);
            float g_gate = tanhf(gpre[2*h + k]);
            float o_gate = sigmoidf_fast(gpre[3*h + k]);

            float c = f_gate * cvec[k] + i_gate * g_gate;
            cvec[k] = c;
            hvec[k] = o_gate * tanhf(c);
        }

        if ((t & 3) == 0) vTaskDelay(1);
    }

    for (int out = 0; out < H; ++out) {
        float s = g.b_fc[out];
        const float *w = g.W_fc + (size_t)out * (size_t)h;
        for (int j = 0; j < h; ++j) s += w[j] * hvec[j];
        y_H[out] = s;
    }
}

static int read_exact(int uart_num, uint8_t *buf, int n, int timeout_ms) {
    int got = 0;
    while (got < n) {
        int r = uart_read_bytes(uart_num, buf + got, n - got, pdMS_TO_TICKS(timeout_ms));
        if (r <= 0) return got;
        got += r;
    }
    return got;
}

static void write_all(int uart_num, const uint8_t *buf, int n) {
    int sent = 0;
    while (sent < n) {
        int w = uart_write_bytes(uart_num, (const char *)(buf + sent), n - sent);
        if (w > 0) sent += w;
    }
}

static void uart_rpc_task(void *arg) {
    const int uart_num = UART_NUM_0;
    dbg_printf("[DBG] uart_rpc_task start on UART0\r\n");

    uint8_t win[4] = {0};
    while (1) {
        uint8_t b;
        int r = uart_read_bytes(uart_num, &b, 1, pdMS_TO_TICKS(1000));
        if (r <= 0) continue;

        win[0] = win[1]; win[1] = win[2]; win[2] = win[3]; win[3] = b;

        if (memcmp(win, MAGIC_META, 4) == 0) {
            dbg_printf("[DBG] META received\r\n");
            uint8_t out[12];
            memcpy(out, MAGIC_INFO, 4);
            uint16_t T = g.hdr.T, F = g.hdr.F, H = g.hdr.H, h = g.hdr.hidden;
            memcpy(out + 4,  &T, 2);
            memcpy(out + 6,  &F, 2);
            memcpy(out + 8,  &H, 2);
            memcpy(out + 10, &h, 2);
            write_all(uart_num, out, sizeof(out));
        } else if (memcmp(win, MAGIC_INFR, 4) == 0) {
            uint32_t n_floats = 0;
            if (read_exact(uart_num, (uint8_t *)&n_floats, 4, 2000) != 4) {
                dbg_printf("[ERR] INFR read n_floats timeout\r\n");
                continue;
            }

            const uint32_t expect = (uint32_t)g.hdr.T * (uint32_t)g.hdr.F;
            if (n_floats != expect) {
                dbg_printf("[ERR] INFR wrong size got=%u expect=%u\r\n", (unsigned)n_floats, (unsigned)expect);
                uint8_t out[8];
                memcpy(out, MAGIC_PRED, 4);
                uint32_t zero = 0;
                memcpy(out + 4, &zero, 4);
                write_all(uart_num, out, sizeof(out));
                continue;
            }

            const int bytes = (int)(n_floats * sizeof(float));
            if (read_exact(uart_num, (uint8_t *)g.x_tmp, bytes, 5000) != bytes) {
                dbg_printf("[ERR] INFR payload timeout bytes=%d\r\n", bytes);
                continue;
            }

            lstm_infer_one(g.x_tmp, g.y_tmp);

            write_all(uart_num, MAGIC_PRED, 4);
            uint32_t H = (uint32_t)g.hdr.H;
            write_all(uart_num, (uint8_t *)&H, 4);
            write_all(uart_num, (uint8_t *)g.y_tmp, (int)(H * sizeof(float)));
        }
    }
}

static void uart0_init(void) {
    uart_config_t cfg = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    uart_param_config(UART_NUM_0, &cfg);
    uart_driver_install(UART_NUM_0, 4096, 0, 0, NULL, 0);
}

void app_main(void) {
    dbg_init();
    dbg_printf("[DBG] boot\r\n");

#if DISABLE_TASK_WDT
    esp_task_wdt_deinit();
    dbg_printf("[DBG] task_wdt disabled\r\n");
#endif

    uart0_init();

    dbg_printf("[DBG] mounting spiffs\r\n");
    if (mount_model_spiffs() != ESP_OK) {
        dbg_printf("[ERR] spiffs mount failed\r\n");
        while (1) vTaskDelay(pdMS_TO_TICKS(1000));
    }

    if (load_model_bin("/model/model_fp32.bin") != ESP_OK) {
        dbg_printf("[ERR] model load failed\r\n");
        while (1) vTaskDelay(pdMS_TO_TICKS(1000));
    }

    xTaskCreatePinnedToCore(uart_rpc_task, "uart_rpc", 8192, NULL, 5, NULL, 1);
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}
