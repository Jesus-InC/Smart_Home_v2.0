/*
 * actuadores.h
 *
 *  Created on: 10 jun 2026
 *      Author: sryis
 */

#ifndef MAIN_INC_ACTUADORES_H_
#define MAIN_INC_ACTUADORES_H_


#include <stdbool.h>
#include <stdint.h>

void actuadores_iniciar(void);

void actuadores_set_foco(uint8_t nivel);
void actuadores_set_bomba(bool encender);
void actuadores_set_ventilador(bool encender, uint8_t velocidad);
void actuadores_set_alarma_visual(bool encendida);
void actuadores_motor_detener(void);
void actuadores_motor_abrir(uint8_t velocidad);
void actuadores_motor_cerrar(uint8_t velocidad);


#endif /* MAIN_INC_ACTUADORES_H_ */
