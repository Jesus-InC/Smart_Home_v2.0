#ifndef DRIVER_DHT22_H
#define DRIVER_DHT22_H

#include "esp_err.h"

typedef struct {
    float temperatura;
    float humedad_ambiente;
} lectura_dht22_t;

void driver_dht22_iniciar(void);
esp_err_t driver_dht22_leer(lectura_dht22_t *lectura);

#endif