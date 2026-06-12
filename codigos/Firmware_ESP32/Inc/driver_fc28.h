#ifndef DRIVER_FC28_H
#define DRIVER_FC28_H

#include "esp_err.h"
#include <stdint.h>

void driver_fc28_iniciar(void);
esp_err_t driver_fc28_leer_porcentaje(uint8_t *humedad_suelo);

#endif