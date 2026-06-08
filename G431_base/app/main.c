#include "config.h"
#include "stm32g4_sys.h"
#include "stm32g4_systick.h"
#include "stm32g4_gpio.h"
#include "stm32g4_uart.h"
#include "stm32g4_utils.h"
#include "bsp_servo.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>

/* ============================================================
 *  TRI DE RESISTANCES — pilote par le PC via UART2 (115200)
 *
 *  Le PC (Flask + Claude Vision) identifie la resistance et
 *  envoie une commande sur UART2 :
 *      "SORT:1K\r\n"      -> bac 1 kOhm
 *      "SORT:10K\r\n"     -> bac 10 kOhm
 *      "SORT:REJECT\r\n"  -> bac rebut
 *
 *  Sequence executee a chaque commande :
 *    1. SERVO_CARROUSEL (PA9) tourne a l'angle du bon bac
 *       => le bac correspondant se place sous la trappe
 *    2. SERVO_TRAPPE (PA10) s'abaisse => la resistance tombe
 *    3. la trappe se referme
 *    4. le carrousel revient a la position initiale (HOME)
 *
 *  La carte renvoie "ACK:1K" / "ACK:10K" / "ACK:REJECT".
 * ============================================================ */

/* ---- Affectation des servos ---- */
#define SERVO_CARROUSEL   SERVO_2   /* PA9  : oriente le bon bac sous la trappe */
#define SERVO_TRAPPE      SERVO_3   /* PA10 : trappe qui s'abaisse pour lacher   */

/* ---- Angles du carrousel : servo 360 deg (DS3225 360) ----
 * Portee 360 deg configuree dans bsp_servo.c (SERVO_2 : 500-2500 us).
 * 3 bacs a 90 / 180 / 270 deg, position initiale a 0 deg.
 */
#define CARR_1K       90.0f         /* bac 1 kOhm  sous la trappe ( 90 deg) */
#define CARR_10K     180.0f         /* bac 10 kOhm sous la trappe (180 deg) */
#define CARR_REBUT   270.0f         /* bac rebut   sous la trappe (270 deg) */
#define CARR_HOME      0.0f         /* position initiale (repos)  (  0 deg) */

/* ---- Angles de la trappe (A AJUSTER mecaniquement) ---- */
#define TRAP_FERMEE   90.0f         /* trappe fermee : retient la resistance */
#define TRAP_OUVERTE  20.0f         /* trappe abaissee : la resistance tombe */

/* ---- Temporisations (ms) ---- */
#define T_ROTATION   700            /* attente positionnement du bac     */
#define T_CHUTE      600            /* attente chute de la resistance    */
#define T_FERMETURE  250            /* attente fermeture trappe          */
#define T_RETOUR     700            /* attente retour carrousel au HOME  */


static void write_LED(bool b)
{
    HAL_GPIO_WritePin(LED_GREEN_GPIO, LED_GREEN_PIN, b);
}

/* Execute le cycle complet de tri pour un angle de bac donne. */
static void cycle_tri(float angle_bac, const char *nom)
{
    write_LED(true);

    /* 1. amener le bon bac sous la trappe */
    BSP_SERVO_set_angle(SERVO_CARROUSEL, angle_bac);
    HAL_Delay(T_ROTATION);

    /* 2. abaisser la trappe -> la resistance tombe dans le bac */
    BSP_SERVO_set_angle(SERVO_TRAPPE, TRAP_OUVERTE);
    HAL_Delay(T_CHUTE);

    /* 3. refermer la trappe */
    BSP_SERVO_set_angle(SERVO_TRAPPE, TRAP_FERMEE);
    HAL_Delay(T_FERMETURE);

    /* 4. retour du carrousel a la position initiale */
    BSP_SERVO_set_angle(SERVO_CARROUSEL, CARR_HOME);
    HAL_Delay(T_RETOUR);

    write_LED(false);
    printf("ACK:%s\r\n", nom);
}

/* Interprete une ligne de commande recue du PC. */
static void traite_commande(const char *cmd)
{
    if      (strcmp(cmd, "SORT:1K")     == 0) cycle_tri(CARR_1K,    "1K");
    else if (strcmp(cmd, "SORT:10K")    == 0) cycle_tri(CARR_10K,   "10K");
    else if (strcmp(cmd, "SORT:REJECT") == 0) cycle_tri(CARR_REBUT, "REJECT");
    else if (strcmp(cmd, "PING")        == 0) printf("PONG\r\n");

    /* ---- Mode reglage en direct (pour trouver les bons angles) ---- */
    else if (strncmp(cmd, "TRAP:", 5) == 0) {     /* ex: TRAP:0  -> trappe a 0 deg */
        float a = (float)atoi(cmd + 5);
        BSP_SERVO_set_angle(SERVO_TRAPPE, a);
        printf("TRAP=%d\r\n", (int)a);
    }
    else if (strncmp(cmd, "CARR:", 5) == 0) {     /* ex: CARR:180 -> carrousel a 180 deg */
        float a = (float)atoi(cmd + 5);
        BSP_SERVO_set_angle(SERVO_CARROUSEL, a);
        printf("CARR=%d\r\n", (int)a);
    }

    else                                      printf("ERR:UNKNOWN:%s\r\n", cmd);
}


int main(void)
{
    HAL_Init();
    BSP_GPIO_enable();
    BSP_UART_init(UART2_ID, 115200);
    BSP_SYS_set_std_usart(UART2_ID, UART2_ID, UART2_ID);
    BSP_GPIO_pin_config(LED_GREEN_GPIO, LED_GREEN_PIN,
                        GPIO_MODE_OUTPUT_PP, GPIO_NOPULL,
                        GPIO_SPEED_FREQ_HIGH, GPIO_NO_AF);

    BSP_SERVO_init();

    /* ---- Position initiale : carrousel au HOME, trappe fermee ---- */
    BSP_SERVO_set_angle(SERVO_TRAPPE,    TRAP_FERMEE);
    BSP_SERVO_set_angle(SERVO_CARROUSEL, CARR_HOME);
    write_LED(false);

    HAL_Delay(300);
    printf("STM32:READY\r\n");
    printf("Tri resistances : SORT:1K / SORT:10K / SORT:REJECT\r\n");
    printf("Carrousel=SERVO_2(PA9)  Trappe=SERVO_3(PA10)\r\n");

    /* ============================================================
     *  Boucle de reception : lit les commandes ligne par ligne
     * ============================================================ */
    char    buf[32];
    uint8_t n = 0;

    while (1)
    {
        if (BSP_UART_data_ready(UART2_ID))
        {
            char c = (char)BSP_UART_get_next_byte(UART2_ID);

            if (c == '\n' || c == '\r')
            {
                if (n > 0)
                {
                    buf[n] = '\0';
                    traite_commande(buf);
                    n = 0;
                }
            }
            else if (n < sizeof(buf) - 1)
            {
                buf[n++] = c;
            }
        }
    }
}
