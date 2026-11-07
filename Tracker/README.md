# Firmware TrackerLoRa

[Torna al progetto](../README.md) · [Client Python](../Client/README.md)

## Firmware e librerie

Lo sketch è in `Tracker.ino`. Usa il core Arduino-Pico RP2040 e le librerie RadioLib, TinyGPSPlus e Adafruit SSD1306, con le relative dipendenze.

Imposta `TRACKER_ROLE` in `Config.h`: `0` per TX con anemometro, `1` per RX (predefinito), `2` per RX con anemometro locale per taratura in auto. Le tre configurazioni usano lo stesso progetto `Tracker.ino`. Nella configurazione della scheda RX assegna 1 MB alla partizione filesystem LittleFS, mantenendo la stessa dimensione nei successivi caricamenti. Il GPS usa UART a 9600 baud. La seriale USB del client usa 115200 baud.

Il progetto usa moduli separati per radio, GPS, display, logger e anemometro. `Tracker.ino` contiene avvio e ciclo principale, mentre `Config.h` raccoglie ruolo, pin e parametri.

### TX su Waveshare RP2040-LoRa-HF

Per la scheda con radio integrata imposta `TRACKER_ROLE=0` in `Config.h` e `TRACKER_HARDWARE=1` in `Hardware.h`. Il valore hardware `0` mantiene il cablaggio del Pico con shield. Le tre configurazioni funzionali rimangono TX, RX e RX da taratura; il profilo integrato è predisposto per il TX.

La RP2040-LoRa deve essere la versione HF, compatibile con la frequenza di progetto 869,525 MHz. Si compila con lo stesso core Arduino-Pico e scheda Raspberry Pi Pico, flash 2 MB. Il sorgente Waveshare conferma TCXO a 1,7 V, DIO2 come controllo RF e GP17 alto a riposo/RX, basso in TX. Il firmware gestisce GP17 con la tabella RF di RadioLib.

| Segnale radio | Pico con shield | RP2040-LoRa-HF |
| --- | --- | --- |
| SCK, SPI1 | GP10 | GP14 |
| MOSI, SPI1 | GP11 | GP15 |
| MISO, SPI1 | GP12 | GP24 |
| CS | GP3 | GP13 |
| RESET | GP15 | GP23 |
| DIO1 | GP20 | GP16 |
| BUSY | GP2 | GP18 |
| Selettore RF esterno | Gestito dallo shield | GP17, attivo basso in TX |

Sulla scheda integrata collega l'anemometro a GP27/ADC1, il GPS con TX GPS → GP9 e RX GPS → GP8, e l'OLED con SDA → GP4 e SCL → GP5. La coppia OLED GP6/GP7 è supportata come sul dispositivo precedente. Usa i numeri GPIO riportati sulla nuova scheda, la cui disposizione fisica differisce dal Pico a 40 pin. Collega le masse e mantieni i segnali entro 3,3 V.

La scheda integrata usa un regolatore ME6217 e richiede un progetto di alimentazione batteria dedicato. Il partitore BATTERY_AD e il caricatore MCP73831 appartengono allo shield del kit precedente. Nel profilo integrato `kBatteryMonitorEnabled` è quindi disabilitato e il TX trasmette batteria mancante. Per misurarla, realizza un partitore esterno su GP26 e abilita la misura in `Config.h`, impostando il rapporto effettivo.

I dettagli elettrici sono documentati nella [wiki Waveshare](https://www.waveshare.com/wiki/RP2040-LoRa) e nello [schema RP2040-LoRa](https://files.waveshare.com/wiki/RP2040-LoRa/Rp2040-lora-sch.pdf).

### Batterie del kit Waveshare

Le colonne finali `tx_battery_v` e `rx_battery_v` dei CSV riportano le tensioni delle due batterie. Il TX trasmette la propria misura via LoRa; l'RX misura la propria batteria anche nei record GPS locali durante le pause radio. I CSV di calibrazione includono gli stessi due campi. I pacchetti dei firmware precedenti producono un campo TX vuoto.

La lettura usa GP26/A0 e il partitore BATTERY_AD dello schema Waveshare (R17=200 kΩ, R18=100 kΩ, R19=0 Ω), con rapporto configurabile `kBatteryDividerRatio = 3`. Queste resistenze sono indicate come opzionali nello schema. Verifica la dotazione della scheda e confronta una lettura con un multimetro prima di usare le tensioni per valutare l'autonomia. Se la misura ricostruita è fuori 2,5–4,35 V, il campo resta vuoto e la diagnostica seriale mostra `battery_v=unavailable` con il valore ADC grezzo.

Le misure riportano la tensione del nodo batteria. La tensione varia con il carico e la ricarica USB.

Il circuito è documentato nello [schema Waveshare Pico-LoRa-SX1262](https://files.waveshare.com/upload/d/d8/Pico-LoRa-SX1262_Sch.pdf).

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
| `Hardware.h` | Pin radio e selezione Pico con shield oppure RP2040-LoRa-HF |
| `Tracker.h`, `TrackerState.cpp` | Dichiarazioni e stato condiviso |
| `Radio.cpp` | Trasmissione, ricezione e formato dei pacchetti |
| `Gps.cpp` | Lettura GPS e diagnostica |
| `Display.cpp` | Interfaccia OLED |
| `Logger.cpp` | Pulsante REC, LittleFS e comandi seriali |
| `LinkAlerts.cpp` | LED RGB e beeper opzionali per lo stato del collegamento |
| `Anemometer.cpp` | Acquisizione analogica e registrazioni di taratura |

Per consultare le registrazioni e gestire la memoria dal portatile segui la [guida del client](../Client/README.md).

## Traccia GPS autonoma sul ricevitore

Durante REC, il ruolo RX normale salva un campione GPS locale ogni secondo, anche quando non arriva LoRa. I pacchetti radio continuano a essere registrati al momento della ricezione. Il CSV distingue le righe con la colonna `record_type`, che vale `gps` o `radio`, e aggiunge `utc` quando il GPS fornisce data e ora valide.

Le righe GPS autonome lasciano vuoti i dati radio. Quando manca un fix recente, rimangono vuote anche le coordinate. Il client ricostruisce il percorso dai fix validi e colora in grigio i tratti senza una misura radio recente. Il ruolo 2 conserva la propria acquisizione ogni secondo del GPS e dell'anemometro.

## LED RGB e beeper opzionali

Gli avvisi sono predisposti per un LED RGB a catodo comune e un piezo passivo compatibile con un'uscita logica a 3,3 V. Le opzioni `kRgbEnabled` e `kBeeperEnabled` in Config.h sono inizialmente `false`. Impostale a `true` dopo aver collegato i componenti.

| Componente | GPIO RX | Collegamento previsto |
| --- | --- | --- |
| LED rosso | GP18 | Anodo rosso attraverso una resistenza dedicata, per esempio 470 Ω |
| LED verde | GP19 | Anodo verde attraverso una resistenza dedicata |
| LED blu | GP21 | Anodo blu attraverso una resistenza dedicata |
| LED RGB | GND | Catodo comune |
| Piezo passivo | GP22 | Ingresso del piezo compatibile o del suo circuito di pilotaggio |
| Piezo / circuito di pilotaggio | GND | Massa comune |

Un modulo RGB ad anodo comune richiede polarità invertita rispetto a questa configurazione. Per un buzzer amplificato o alimentato a tensione diversa serve un circuito di pilotaggio adeguato al suo modello.

Il LED mostra verde per 6–9, giallo per 2–5 e rosso per 0–1. Prima del primo pacchetto lampeggia blu. Dopo la perdita del collegamento lampeggia rosso. Il timeout corrisponde ad almeno tre intervalli attesi fra i pacchetti, normalmente 9 secondi con TX ogni 3 secondi.

Il beeper emette due suoni brevi alla perdita del collegamento e uno più acuto alla ripresa. Gli avvisi sono emessi al cambio di stato e non richiedono attese bloccanti. Il generatore usa le funzioni tone del [core Arduino-Pico](https://arduino-pico.readthedocs.io/en/stable/digital.html).
