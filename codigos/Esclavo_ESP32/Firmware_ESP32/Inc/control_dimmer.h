#ifndef CONTROL_DIMMER_H
#define CONTROL_DIMMER_H

#include <stdint.h>

void control_dimmer_iniciar(void);

void control_dimmer_set_nivel(uint8_t nivel);
uint8_t control_dimmer_get_nivel(void);

uint32_t control_dimmer_obtener_contador_zc(void);
uint32_t control_dimmer_obtener_frecuencia_zc(void);

#endif