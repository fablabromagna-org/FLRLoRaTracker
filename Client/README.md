# Client TrackerLoRa per Windows

[Torna al progetto](../README.md) · [Firmware e collegamenti](../Tracker/README.md)

## Installazione del client

Collega l'RX via USB e chiudi il monitor seriale Arduino per liberare la porta COM. Installa Python per Windows con Tkinter, quindi esegui dalla cartella principale del progetto.

```powershell
cd Client
py -m pip install -r requirements.txt
py tracker_client.py
```

Con un solo dispositivo USB disponibile il client propone la sua COM. Con più dispositivi scegli la porta del ricevitore RX. Una porta TX viene riconosciuta dal relativo output seriale e segnalata.

## Mappa e ricezione in tempo reale

L'interfaccia raggruppa i comandi in Ricevitore e Sessioni lanciate da PC e mostra il logo FabLab Romagna in alto a destra. La vista live mostra segnale e progressivo TX, mentre la consultazione delle sessioni usa un riepilogo compatto del percorso. La legenda resta visibile sopra la mappa.

Premi **Connetti** per monitorare l'RX. Il riepilogo superiore mostra la distanza RX–TX, lo stato GPS e il progressivo TX in grande sulla destra. La distanza viene mostrata in metri o chilometri quando è disponibile.

La vista live mostra anche **Batteria RX** e **Batteria TX** in volt. La tensione RX si aggiorna dalla diagnostica locale anche durante le pause radio, mentre la tensione TX arriva nei pacchetti LoRa. Un valore mancante o non valido appare come `n/d`. Una misura non aggiornata viene indicata come `dato precedente`. La soglia TX segue il timeout del collegamento, normalmente 9 secondi. Le letture presenti nei CSV scaricati non modificano gli indicatori live.

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
- **SESSIONI** permette di scegliere un GPX nella cartella `sessioni` e aprirne la mappa.

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

Premi **Connetti** nel gruppo Ricevitore per collegare l'RX e passare alla vista live. Il pulsante **REGISTRAZIONI**, nello stesso gruppo, scarica tutte le registrazioni del Pico e apre l'elenco dei CSV sul PC per scegliere quello da visualizzare. Se REC è attivo, il download richiesto attende la fine della registrazione. Il client confronta dimensione e checksum con le copie locali e scarica solo registrazioni nuove o cambiate. Nel gruppo **Sessioni lanciate da PC**, il pulsante **SESSIONI** apre i GPX salvati nella cartella sessioni.

La cartella `Registrazioni` contiene i CSV originali scaricati. Quando apri una registrazione, il client genera gli export GPX e SVG e mostra la mappa interna. Il client verifica dimensione e checksum quando supportato dal firmware e ripete fino a tre volte i trasferimenti non validi. I trasferimenti interrotti restano come file `.part` e possono essere ripetuti.

Dopo la sincronizzazione, **REGISTRAZIONI** apre l'elenco dei CSV sul PC per scegliere quello da consultare. Sessioni e registrazioni si visualizzano nella mappa principale, con tratti colorati e dettagli al clic. Il pulsante LIVE riporta alla ricezione e al centraggio sulla posizione RX. Durante la consultazione, la raccolta dei dati in arrivo continua.

Il nuovo CSV contiene numero progressivo, RSSI, SNR, qualità, stato GPS TX, coordinate TX, distanza e, quando disponibili, coordinate e altitudine RX. L'header `quality_0_9` identifica la scala aggiornata. Le precedenti letture su scala 1–10 vengono convertite sottraendo uno.

Il client legge anche le registrazioni dell'anemometro con header `sample_ms`. In questo formato il percorso usa il GPS RX e i dettagli includono velocità GPS e vento provvisorio. L'orario UTC GPS viene usato quando disponibile. I campioni senza fix restano nel CSV originale e vengono esclusi dalla mappa.

I vecchi CSV del Pico contengono solo le coordinate TX. La mappa li identifica come percorso TX. Per ricostruire il percorso RX serve una registrazione creata con lo sketch aggiornato. I CSV radio precedenti contengono solo tempi relativi all'avvio del Pico. In assenza di UTC valido, gli export li rappresentano a partire dal 1 gennaio 1970 e il riepilogo segnala che data e ora reali non sono disponibili.

## Consultazione del percorso

Se una vecchia sessione PC ha il GPX vuoto, il visualizzatore cerca il log con lo stesso nome e recupera le posizioni TX disponibili. Il titolo segnala che si tratta del percorso TX e che manca il GPS RX. Mantieni il file `.log` accanto al GPX per consentire questo recupero.

La mappa usa il tracciato colorato secondo le stesse soglie della barra del segnale. Il grigio indica l'assenza di una misura recente. Cliccando sulla linea si leggono i dettagli del pacchetto associato. Il colore è assegnato dalla misura più vicina entro 5 secondi dal centro temporale del tratto. Intervalli superiori a 15 secondi restano privi di misura associata.

Per visualizzare una sessione nella finestra principale usa SESSIONI o REGISTRAZIONI. Puoi aprire un GPX anche nel browser da terminale.

```powershell
py tracker_route.py --serve sessioni/nome-giro.gpx
```

Il comando apre un server accessibile dal solo PC e avvia il browser. Lascia aperto il terminale durante la consultazione e premi Ctrl+C quando hai finito. Il server locale gestisce le richieste della cartografia e la cache. Aprendo direttamente l'HTML come file si consulta il tracciato su sfondo neutro.


## Riepilogo della sessione

La legenda sopra la mappa resta visibile anche durante la consultazione. Il riepilogo mostra due righe, per esempio.

```text
Sessione del 6/11/2026 ore 16:23 - durata 32:18 - 15,59 Km
Distanza max raggiunta tra TX e RX 3,32 Km
```

L'orario deriva dai dati GPS o dai timestamp registrati ed è espresso in UTC. La durata usa lo stesso intervallo delle posizioni GPS. La lunghezza somma i tratti all'interno dei singoli segmenti del percorso, senza collegare le pause. La distanza massima RX–TX viene letta dal campo `distance_m` del CSV o del log associato. Se quella misura manca compare `n/d`.

## Gestione della memoria del Pico

Nel gruppo Ricevitore, **GESTISCI MEMORIA** mostra capacità totale, spazio occupato, spazio libero ed elenco delle registrazioni sul device. Serve il [firmware RX aggiornato](../Tracker/README.md) e REC deve essere fermo.

Seleziona uno o più file e premi **ELIMINA SELEZIONATE**. Il client confronta dimensione e checksum CRC32 con una copia CSV nella cartella `Registrazioni`. Se manca una copia identica, scaricala prima con **REGISTRAZIONI**. Dopo la verifica viene richiesta conferma della cancellazione. Il firmware ricontrolla il contenuto prima di eliminare ogni file e il client aggiorna lo spazio disponibile. Le copie sul PC restano consultabili.

## File e cartelle

Sessioni e registrazioni sono salvate accanto al client anche quando il programma viene avviato da un'altra cartella.

| File o cartella | Contenuto |
| --- | --- |
| `tracker_client.py` | Interfaccia desktop e gestione seriale |
| `tracker_map.py` | Mappa live e marcatori |
| `tracker_tiles.py` | Connessione e cache della cartografia |
| `tracker_route.py` | Lettura e visualizzazione dei percorsi, export HTML |
| `tracker_recordings.py` | Importazione dei CSV radio e anemometro |
| `tracker_memory.py` | Elenco memoria e cancellazione con verifica della copia locale |
| `requirements.txt` | Dipendenze Python |
| `sessioni/` | Sessioni avviate sul PC |
| `Registrazioni/` | CSV scaricati dal Pico ed export associati |

Le cartelle dei dati, i log e gli ambienti Python locali sono esclusi da Git tramite il `.gitignore` del progetto.

Le registrazioni RX aggiornate includono righe GPS autonome ogni secondo, con `record_type=gps`, e righe dei pacchetti con `record_type=radio`. La mappa rimane consultabile anche quando una sessione contiene soltanto GPS. I tratti senza misure radio vicine sono grigi. I CSV delle versioni precedenti restano leggibili.

Il pulsante **Connetti** diventa **Disconnetti** quando la porta è aperta. Disconnettendo, la sessione PC eventualmente attiva viene salvata. Se il cavo USB viene rimosso, il client chiude la connessione e mostra un avviso nella barra di stato; puoi ricollegarlo e premere **Connetti**. La registrazione autonoma sul Pico continua indipendentemente dalla connessione al PC.
