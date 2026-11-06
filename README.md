# Client TrackerLoRa per Windows

1. Sul ricevitore carica lo sketch aggiornato con `kTransmitter = false`. Il TX può mantenere il firmware attuale.
2. Collega l'RX via USB e chiudi il monitor seriale Arduino per liberare la COM.
3. Con Python per Windows (con Tkinter), dalla cartella del progetto esegui:

   ```powershell
   py -m pip install -r requirements.txt
   py tracker_client.py
   ```

4. Seleziona la COM e premi **START**. **PAUSA** sospende la registrazione e **START** la riprende nello stesso file. **STOP** termina la sessione e salva gli export. Anche la chiusura della finestra salva la sessione.

La mappa live usa OpenStreetMap e richiede Internet per la cartografia. RX e percorso sono blu, TX è rosso, i pacchetti sono arancioni. Clicca un puntino per leggere progressivo TX, qualità del segnale e altitudine RX. Il primo pacchetto con fix RX recente crea un punto anche da fermo. I successivi richiedono almeno 3 metri di spostamento dall'ultimo puntino e, se disponibile, una velocità di almeno 1 km/h.

Ogni sessione crea tre file nella cartella `sessioni`:

- **.log** contiene i byte ricevuti dalla seriale durante la registrazione, comprese le righe diagnostiche.
- **.gpx** contiene il tragitto RX in segmenti separati dalle pause e i puntini come waypoint. Si può importare in un visualizzatore GPX con cartografia offline.
- **.svg** si apre in un browser senza Internet e mostra il tragitto e i puntini su sfondo neutro. Passa il mouse su un puntino per leggere i dettagli.

I log del firmware precedente contengono le coordinate TX. Per registrare il percorso RX serve lo sketch aggiornato sul ricevitore.
