# FLRLoRaTracker

Tracker LoRa con due Raspberry Pi Pico, GPS, radio SX1262 e display OLED SSD1306. Il TX trasmette la posizione e un numero progressivo. L'RX mostra la qualità del collegamento e può registrare i pacchetti nella propria memoria flash. Il client Python per Windows legge l'RX via USB, mostra la mappa e scarica le registrazioni.

## Firmware e librerie

Lo sketch è in `Tracker/Tracker.ino`. Usa il core Arduino-Pico RP2040 e le librerie RadioLib, TinyGPSPlus e Adafruit SSD1306, con le relative dipendenze.

Imposta `kTransmitter = true` per il TX e `kTransmitter = false` per l'RX. Nella configurazione della scheda RX assegna spazio alla partizione filesystem LittleFS per le registrazioni. Il GPS usa UART a 9600 baud. La seriale USB del client usa 115200 baud.

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

Collega le masse di Pico, display, GPS e radio a GND comune. I segnali GPIO del Pico lavorano a 3,3 V. Per VCC/VIN dei moduli usa l'alimentazione prevista dal rispettivo breakout e segnali compatibili con il Pico. Il cablaggio di alimentazione dipende dal modello dei moduli utilizzati.

Il display è cercato agli indirizzi I²C 0x3C e 0x3D. Il firmware prova GP4/GP5 e poi GP6/GP7.

## Installazione del client

Collega l'RX via USB e chiudi il monitor seriale Arduino per liberare la porta COM. Installa Python per Windows con Tkinter, quindi esegui dalla cartella principale del progetto.

```powershell
cd Client
py -m pip install -r requirements.txt
py tracker_client.py
```

Il client propone una porta USB disponibile. Controlla che sia quella del ricevitore.

## Mappa e ricezione in tempo reale

Premi **COLLEGA** per monitorare l'RX. Il riepilogo superiore mostra la distanza RX–TX, lo stato GPS e il progressivo TX in grande sulla destra. La distanza viene mostrata in metri o chilometri quando è disponibile.

La barra orizzontale indica il segnale su scala **0–9**, con il numero al centro.

| Valori | Colore |
| --- | --- |
| 6–9 | Verde |
| 2–5 | Giallo |
| 0–1 | Rosso |

La posizione RX è un punto blu sempre in primo piano, il TX è rosso e i pacchetti ricevuti sono piccoli punti arancioni. La mappa si ricentra sulla posizione RX quando cambia, mantenendo lo zoom scelto. Clicca sui puntini per leggere progressivo TX, segnale e altitudine RX.

Il primo pacchetto con fix RX recente crea un punto. I successivi richiedono almeno 3 metri di spostamento dall'ultimo punto e, se disponibile, una velocità di almeno 1 km/h. La cartografia OpenStreetMap richiede Internet. Le tessere visualizzate vengono conservate nella cache locale.

## Sessioni registrate sul PC

- **START** avvia una nuova sessione sul PC o riprende quella in pausa.
- **PAUSA** sospende la registrazione sul PC.
- **STOP** termina la sessione e salva gli export.
- **APRI SESSIONE** permette di scegliere un GPX nella cartella `sessioni` e aprirne la mappa.

Anche la chiusura della finestra salva la sessione PC. La registrazione sul Pico viene comandata dal pulsante fisico.

Ogni sessione PC crea quattro file nella cartella `sessioni`.

| Formato | Contenuto |
| --- | --- |
| .log | Byte ricevuti dalla seriale durante la registrazione, incluse le righe diagnostiche |
| .gpx | Percorso RX, segmenti separati dalle pause e pacchetti come waypoint |
| .svg | Percorso su sfondo neutro, consultabile offline in un browser |
| .html | Mappa interattiva con tracciato colorato in base al segnale |

## REC sul Pico e download

Il pulsante su GP17 avvia la registrazione sul ricevitore. Sul display compare REC. Una seconda pressione chiude e salva il file `/sessionNNNN.csv` in LittleFS.

Con il client collegato, l'indicatore rosso **REC sul device** segue lo stato del pulsante fisico. Il comando STATUS recupera anche lo stato quando il client si collega a una registrazione già avviata.

Quando termini REC, il client propone l'elenco delle registrazioni presenti sul Pico. Puoi richiamarlo con **LEGGI PICO**. Seleziona un file e premi **SCARICA E VISUALIZZA** per salvarlo nella cartella `Registrazioni` e aprire la mappa nel browser. Il download è disponibile a registrazione device ferma.

La cartella `Registrazioni` contiene il CSV originale e gli export GPX, SVG e HTML. Il client verifica la dimensione del download prima di confermare il CSV. I trasferimenti interrotti restano come file `.part` e possono essere ripetuti.

Il pulsante **REGISTRAZIONI** riapre un CSV già scaricato. Il visualizzatore resta disponibile finché il client è aperto o finché scegli un'altra registrazione o sessione.

Il nuovo CSV contiene numero progressivo, RSSI, SNR, qualità, stato GPS TX, coordinate TX, distanza e, quando disponibili, coordinate e altitudine RX. L'header `quality_0_9` identifica la scala aggiornata. Le precedenti letture su scala 1–10 vengono convertite sottraendo uno.

I vecchi CSV del Pico contengono solo le coordinate TX. La mappa li identifica come percorso TX. Per ricostruire il percorso RX serve una registrazione creata con lo sketch aggiornato. I tempi dei CSV sono relativi all'avvio del Pico. Negli export vengono rappresentati a partire dal 1 gennaio 1970 e non indicano la data reale del giro.

## Consultazione del percorso

La mappa usa il tracciato colorato secondo le stesse soglie della barra del segnale. Il grigio indica l'assenza di una misura recente. Cliccando sulla linea si leggono i dettagli del pacchetto associato. Il colore è assegnato dalla misura più vicina entro 5 secondi dal centro temporale del tratto. Intervalli superiori a 15 secondi restano privi di misura associata.

Puoi aprire un GPX anche da terminale.

```powershell
py tracker_route.py --serve sessioni/nome-giro.gpx
```

Il comando apre un server accessibile dal solo PC e avvia il browser. Lascia aperto il terminale durante la consultazione e premi Ctrl+C quando hai finito. Il server locale gestisce le richieste della cartografia e la cache. Aprendo direttamente l'HTML come file si consulta il tracciato su sfondo neutro.

## File del progetto

```text
Tracker/
    Tracker.ino
Client/
    requirements.txt
    tracker_client.py
    tracker_map.py
    tracker_tiles.py
    tracker_route.py
    tracker_recordings.py
    sessioni/          # dati locali
    Registrazioni/    # dati locali
FLRNemo/
    TestLetturaCircuitPython/
        code.py
```

I moduli Python elencati sotto si trovano in `Client`. Sessioni e registrazioni vengono salvate rispetto alla posizione del client, anche quando viene avviato da un'altra cartella. Per usare i comandi del visualizzatore da terminale entra prima in `Client`.

- `tracker_client.py` contiene l'interfaccia desktop e la gestione seriale.
- `tracker_map.py` gestisce la mappa live e i marcatori.
- `tracker_tiles.py` gestisce connessione e cache della cartografia.
- `tracker_route.py` genera e visualizza le mappe dei percorsi.
- `tracker_recordings.py` importa i CSV del Pico.
- `FLRNemo/TestLetturaCircuitPython/code.py` contiene una prova CircuitPython per la lettura di un anemometro con display ST7735R e usa un cablaggio dedicato.

Le cartelle `sessioni` e `Registrazioni`, i log e gli ambienti Python locali sono esclusi da Git tramite `.gitignore`.

## Licenza

Il progetto include la licenza GNU AGPL-3.0 nel file LICENSE.
