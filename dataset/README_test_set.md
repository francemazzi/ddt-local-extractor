# Dataset DDT simulati - siderurgia e lamiere

Questo pacchetto contiene 10 Documenti di Trasporto completamente sintetici, destinati esclusivamente al test di pipeline OCR ed estrazione dati.

- Tutte le aziende, le persone giuridiche, le partite IVA, gli indirizzi di contatto, le targhe e i dati commerciali sono inventati.
- Ogni pagina riporta `FAC-SIMILE - DATI FITTIZI - NON VALIDO AI FINI FISCALI`.
- I documenti 08 e 10 sono PDF immagine con resa da scansione; gli altri contengono testo PDF nativo.
- `ground_truth_ddt.json` conserva la struttura completa e annidata.
- `ground_truth_righe.csv` contiene una riga per articolo, utile per confrontare il risultato dell'estrattore.
- `DDT_simulati_siderurgia_raccolta.pdf` unisce i 10 documenti nello stesso ordine dei file numerati.

Campi coperti: numero e data DDT, mittente, destinatario, destinazione, causale, ordine/commessa, trasporto, vettore, colli, pallet, pesi, codice articolo, descrizione, unita di misura, quantita e lotto/colata.
