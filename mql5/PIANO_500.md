# Piano "500 EUR in 30 giorni"

| Strada | Probabilita' 500 EUR in 30 gg | Rischio |
|---|---|---|
| Conto personale 100 EUR, rischio 100% a trade | ~22% (teorico; leva non consentita in UE) | 41% perde tutto |
| Conto personale 100 EUR, rischio 10% | 0% | risultato tipico ~105 EUR |
| Prop challenge 1 fase 10k + conto finanziato +5% | fase in 30 gg ~11%; poi +5% sul finanziato | si perde solo la quota (~50-100 EUR) |

Passi:
1. Prova gratuita / demo con `presets/prop_1fase_10k.set` su `XT_Aggressivo50.mq5` (compilare in MetaEditor).
2. Challenge 1 fase con regole uguali o piu' larghe (target <= 6%, giornaliera >= 3%, totale >= 6%, nessun limite di tempo).
3. Superata la fase: `presets/funded_500.set` sul conto finanziato, si ferma a +5% (500 su 10.000) per il pagamento.
Nota: il successo entro 30 giorni non e' probabile; senza limite di tempo le probabilita' salgono (~47% entro 1 anno).
