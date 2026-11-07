# Firmware TrackerLoRa

[Torna al progetto](../README.md) · [Client Python](../Client/README.md)

## Firmware e librerie

Lo sketch è in `Tracker.ino`. Usa il core Arduino-Pico RP2040 e le librerie RadioLib, TinyGPSPlus e Adafruit SSD1306, con le relative dipendenze.

Imposta `TRACKER_ROLE` in `Config.h`: `0` per TX con anemometro, `1` per RX (predefinito), `2` per RX con anemometro locale per taratura in auto. Le tre configurazioni usano lo stesso progetto `Tracker.ino`. Nella configurazione della scheda RX assegna 1 MB alla partizione filesystem LittleFS, mantenendo la stessa dimensione nei successivi caricamenti. Il GPS usa UART a 9600 baud. La seriale USB del client usa 115200 baud.

Il progetto usa moduli separati per radio, GPS, display, logger e anemometro. `Tracker.ino` contiene avvio e ciclo principale, mentre `Config.h` raccoglie ruolo, pin e parametri.

Il TX acquisisce l'anemometro su A1/GP27 e applica `max(0, 16,8 × (V − 0,021))` m/s. Ogni 3 secondi invia il vento a risoluzione 0,01 m/s e la tensione a risoluzione 1 mV, anche senza fix GPS. Al primo avvio, in assenza di una misura recente o con ADC saturo, il vento viene segnalato come mancante. Il display TX mostra il vento locale e l'esito dell'invio.

L'RX mostra `conteggio/vento` e il segnale 0–9 a destra. Il CSV radio aggiunge `wind_ms` e `wind_volts` alle colonne esistenti. I pacchetti dei firmware precedenti rimangono leggibili e producono campi vento vuoti. Sul display `--` indica vento mancante o collegamento scaduto.

### Calibrazione anemometro

Nelle configurazioni 0 e 2 collega l'uscita analogica a A1/GP27 (pin fisico 32), con massa comune e segnale entro 0–3,3 V. Il firmware acquisisce a intervalli di 10 ms e produce una media ogni secondo. Nella configurazione 2 il pulsante GP17 avvia e ferma una sessione anche senza LoRa o PC.

Il CSV di calibrazione salva ADC medio/minimo/massimo, numero di campioni, durata della finestra, tensione, velocità anemometro provvisoria, velocità GPS in km/h e m/s, età dei dati, coordinate, quota, HDOP, satelliti, UTC quando valido e contatore PPS. I dati GPS mancanti rimangono vuoti. Le colonne radio riportano l'ultimo pacchetto e la sua età, senza determinare la cadenza di acquisizione.

Le colonne finali `tx_wind_ms` e `tx_wind_volts` del CSV di calibrazione riportano il vento remoto quando disponibile. Le colonne `volts` e `wind_ms_provisional` continuano a descrivere il sensore locale su RX.

La conversione provvisoria è `max(0, 16,8 × (V − 0,021))` m/s. La pendenza deriva dai tratti stabili dei giri del 7 novembre 2026, mentre 0,021 V è il riferimento a riposo osservato sull'RX con il sensore fermo e il collegamento definitivo. Pendenza, zero e riferimento ADC nominale di 3,3 V sono in `Config.h`. Il CSV conserva i valori grezzi per ricalcolare la taratura dopo la prova.

Sul display la seconda riga mostra `conteggio/vento` con il vento arrotondato in m/s e il segnale 0–9 a destra. Sotto compaiono vento con due decimali, velocità GPS, stato fix, satelliti e volt. `FLR REC` indica una registrazione attiva.

Per scaricare una sessione usa `LIST` e `GET /session0001.csv` dalla seriale USB a 115200 baud. I CSV delle configurazioni 1 e 2 hanno intestazioni differenti e condividono la numerazione dei file. Il client Python legge sia le registrazioni radio sia quelle dell'anemometro.

La configurazione radio nello sketch è 869,525 MHz, banda 125 kHz, SF9, CR 4/5, CRC a 2 byte e potenza impostata a 14 dBm. TX e RX devono usare gli stessi parametri radio.

## Collegamenti elettrici

La tabella riporta i numeri GPIO **GP** usati dallo sketch. Le connessioni del display e della radio sono uguali su TX e RX.

| Dispositivo | Segnale del modulo | GPIO del Pico | Note |
| --- | --- | --- | --- |
| OLED SSD1306 I²C | SDA | GP4 | Prima coppia cercata dal firmware |
| OLED SSD1306 I²C | SCL | GP5 | Prima coppia cercata dal firmware |
| OLED SSD1306 I²C | SDA / SCL | GP6 / GP7 | Coppia alternativa, rilevata automaticamente |
| GPS sul ricevitore RX | TX del GPS | GP1 | RX UART del Pico |
| GPS sul ricevitore RX | RX del GPS | GP0 | TX UART del Pico |
| GPS sul trasmettitore TX | TX del GPS | GP9 | RX UART del Pico |
| GPS sul trasmettitore TX | RX del GPS | GP8 | TX UART del Pico |
| GPS sul ricevitore RX | PPS | GP16 | Ingresso con pull-down, diagnostica impulsi |
| Radio SX1262 | SCK | GP10 | SPI1 |
| Radio SX1262 | MOSI | GP11 | Uscita dati dal Pico |
| Radio SX1262 | MISO | GP12 | Ingresso dati al Pico |
| Radio SX1262 | NSS / CS | GP3 | Selezione radio |
| Radio SX1262 | DIO1 | GP20 | Interrupt ricezione |
| Radio SX1262 | RESET | GP15 | Reset radio |
| Radio SX1262 | BUSY | GP2 | Stato radio |
| Pulsante REC sul RX | Un terminale | GP17 | Ingresso con pull-up interno |
| Pulsante REC sul RX | Altro terminale | GND | Pulsante normalmente aperto |
| Anemometro sul TX o sull'RX da taratura | Uscita analogica | GP27 / A1 | Pin fisico 32, segnale 0–3,3 V, massa comune |

Collega le masse di Pico, display, GPS e radio a GND comune. I segnali GPIO del Pico lavorano a 3,3 V. Per VCC/VIN dei moduli usa l'alimentazione prevista dal rispettivo breakout e segnali compatibili con il Pico. Il cablaggio di alimentazione dipende dal modello dei moduli utilizzati.

Il display è cercato agli indirizzi I²C 0x3C e 0x3D. Il firmware prova GP4/GP5 e poi GP6/GP7.


## Registrazione e memoria

Il pulsante GP17 avvia REC e una seconda pressione chiude il CSV in LittleFS. I file vengono numerati come `/session0001.csv`. Il firmware RX usa una partizione filesystem da 1 MB. Mantieni la stessa dimensione nei successivi caricamenti per conservare la disposizione della memoria.

La seriale USB espone questi comandi a 115200 baud, terminati da invio.

| Comando | Risposta e funzione |
| --- | --- |
| `STATUS` | Stato REC, con `# recording=0` o `# recording=1` |
| `LIST` | Nomi e dimensioni delle registrazioni, seguito da `# END LIST` |
| `GET /session0001.csv` | CSV tra `# BEGIN CSV` e `# END CSV` |
| `MEM` | Capacità totale e byte occupati, con `# MEM totale occupati` |
| `CHECK /session0001.csv` | Percorso, dimensione e checksum CRC32 del file |
| `DEL /session0001.csv CRC DIMENSIONE` | Elimina il file se contenuto e dimensione coincidono con quelli attesi |

STATUS è disponibile anche durante REC. Gli altri comandi richiedono REC fermo e un filesystem disponibile. DEL accetta solo i percorsi delle registrazioni, verifica nuovamente il contenuto prima della cancellazione e restituisce `# DELETED /session0001.csv` in caso di successo. Il client usa questi controlli per cancellare solo dopo aver verificato una copia locale e chiesto conferma.

## Moduli del firmware

| File | Funzione |
| --- | --- |
| `Tracker.ino` | Inizializzazione e ciclo principale |
| `Config.h` | Ruolo, GPIO, parametri radio e anemometro |
| `Tracker.h`, `TrackerState.cpp` | Dichiarazioni e stato condiviso |
| `Radio.cpp` | Trasmissione, ricezione e formato dei pacchetti |
| `Gps.cpp` | Lettura GPS e diagnostica |
| `Display.cpp` | Interfaccia OLED |
| `Logger.cpp` | Pulsante REC, LittleFS e comandi seriali |
| `Anemometer.cpp` | Acquisizione analogica e registrazioni di taratura |

Per consultare le registrazioni e gestire la memoria dal portatile segui la [guida del client](../Client/README.md).
