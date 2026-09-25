# UniCal Monitor

Controlla la pagina [UniCal Sostegno 2025/26](https://www.unical.it/didattica/offerta-formativa/formazione-insegnanti/corsi-per-il-sostegno/sostegno-202526/) ogni 5 minuti con GitHub Actions, anche a PC spento. Notifica su Telegram quando cambiano testo o collegamenti della sezione centrale.

## Attivazione dal browser

1. Crea su GitHub un repository chiamato `unical-monitor`. Un repository pubblico con runner standard evita il consumo dei minuti inclusi per i repository privati; un repository privato tutela la visibilità del progetto ma richiede attenzione alla quota Actions. Il progetto contiene solo codice e contenuto pubblico UniCal.
2. Estrai lo ZIP. Nel repository usa **Add file → Upload files** e carica `monitor.py`, `requirements.txt`, `README.md` e la cartella `tests`. Poi usa **Add file → Create new file**, scrivi come nome `.github/workflows/monitor.yml`, copia integralmente il contenuto dell'omonimo file locale e salva sul branch principale. Questo passaggio evita di perdere la cartella nascosta `.github` durante il caricamento. Puoi caricare anche `.gitignore`.
3. In **Settings → Secrets and variables → Actions → New repository secret**, inserisci direttamente i due Secrets `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Non metterli in file, messaggi, screenshot o variabili pubbliche. Apri il tuo bot in Telegram e premi **Avvia** prima del test. Se non hai ancora un bot, crealo tramite [BotFather](https://t.me/BotFather); token e identificativo della chat restano solo nei Secrets.
4. Vai in **Actions → UniCal Monitor → Run workflow**, scegli il branch principale e lascia selezionato il messaggio di prova. Il risultato atteso è un'esecuzione verde, un messaggio Telegram e il file `.state/state.json` nel repository. Esegui nuovamente il workflow con il messaggio di prova disattivato: se la pagina non cambia, non deve arrivare un altro messaggio.

Il primo avvio invia una conferma e crea la baseline: non segnala tutti i documenti già presenti come novità. Finché i due Secrets non sono configurati, l'inizializzazione fallisce senza salvare uno stato fuorviante.

## Funzionamento

- Selettore verificato sul markup UniCal il 25 settembre 2026: `.main-body > .py-5 > .container > .row > .col-lg-8`.
- Include avvisi nelle sezioni espandibili, date, testo e URL dei documenti; esclude intestazione, navigazione, footer, script e cookie. Normalizza spazi e Unicode; ignora attributi HTML, frammenti e parametri di tracciamento noti. Conserva i parametri funzionali dei link.
- Una modifica viene confermata con una seconda lettura dopo 10 secondi. Pagina incompleta, struttura inattesa e download falliti interrompono il controllo senza modificare lo stato.
- Lo stato è versionato in `.state/state.json` sul branch principale, senza scadenza di cache o artifact. Le esecuzioni sono serializzate. Si salva solo dopo conferma Telegram; un push fallito rende il workflow rosso.
- Una scrittura di mantenimento ogni 30 giorni dà attività al repository pubblico. Controlla comunque che Actions rimanga abilitato.
- Il workflow ha solo il permesso `contents: write`, necessario per lo stato. Le credenziali Telegram sono disponibili esclusivamente nel passaggio di controllo. Il programma non stampa token, identificativo chat, risposta Telegram o eccezioni HTTP grezze.

## Limiti e gestione errori

GitHub può ritardare o saltare esecuzioni pianificate: la cadenza è nominale, non una garanzia di notifica entro 5 minuti. Nei repository pubblici le pianificazioni possono essere disabilitate dopo 60 giorni senza attività. [Documentazione GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Il monitor rileva cambiamenti della pagina e degli URL; **non scarica i PDF per riconoscere sostituzioni del loro contenuto allo stesso URL** e non visita sottopagine. Se UniCal modifica il layout, il controllo può fallire esplicitamente e il selettore va aggiornato.

In caso di timeout Telegram dopo una consegna effettiva, oppure di mancato salvataggio Git dopo l'invio, un avviso può ripetersi: si preferisce una possibile duplicazione alla perdita della notifica. Non esiste una transazione unica fra Telegram e GitHub. Il riferimento nell'avviso identifica la versione del contenuto.

Se il workflow è rosso, apri il passaggio fallito. Verifica i Secrets e che il bot sia stato avviato; per errori di push verifica che le regole del branch consentano i commit di GitHub Actions. Non cancellare lo stato per risolvere un errore ordinario. Uno stato corrotto va ripristinato dalla cronologia Git. Abilita nelle preferenze GitHub le notifiche per i workflow falliti se vuoi essere avvisato anche quando Telegram non è raggiungibile.

## Verifiche locali

Richiede Python 3.12 o superiore.

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python monitor.py --inspect-html pagina-scaricata.html
```

L'ultima modalità analizza soltanto HTML locale: non invia Telegram e non altera lo stato. I test usano un mittente simulato, verificano rilevamento avvisi/PDF, esclusione rumore, persistenza, errori di consegna, stato corrotto e riservatezza degli errori.

Le notifiche usano [Telegram Bot API / sendMessage](https://core.telegram.org/bots/api#sendmessage).
