//+------------------------------------------------------------------+
//| XT_Aggressivo50.mq5                                              |
//| Conto piccolo (es. 50 EUR, meglio se conto CENT), profilo        |
//| AGGRESSIVO con anti-martingala.                                  |
//| Strategie (le uniche positive in tutti i test 2013-2026):        |
//|  1 Asian fade EURCHF  (H1, Bollinger 20 / 2,5 nelle ore 00-08)   |
//|  2 Z-score fade EURGBP (D1, media 50, ingresso |z| > 1,5)        |
//| Size: rischio base x moltiplicatore. Dopo ogni trade vinto il    |
//| moltiplicatore sale (x1,5, max 3), dopo una perdita torna a 1.   |
//| Freni: obiettivo (es. raddoppio) -> chiude e si ferma;           |
//| soglia di perdita -> chiude e si ferma; dopo N giorni non apre   |
//| piu' nuovi trade.                                                |
//| Backtest 2013-2026 (aggr50.py): ~1,7 trade al mese; dopo 60      |
//| giorni da 50 EUR risultato mediano 52 EUR, 10% peggiori 41 EUR,  |
//| 10% migliori 66 EUR. Provarlo prima in demo.                     |
//| Orari = ora del SERVER (tipicamente GMT+2/+3).                   |
//| Mettere l'EA su UN solo grafico (qualsiasi simbolo / timeframe). |
//+------------------------------------------------------------------+
#property copyright "xtrading"
#property version   "1.00"
#property description "Asian fade EURCHF + Z-score fade EURGBP, profilo aggressivo con anti-martingala"

#include <Trade/Trade.mqh>

input group "=== Rischio aggressivo ==="
input double InpRiskBasePct     = 10.0;  // Rischio base per trade (% del capitale INIZIALE)
input double InpWinMult         = 1.5;   // Dopo un trade vinto il moltiplicatore viene moltiplicato per questo
input double InpMaxMult         = 3.0;   // Moltiplicatore massimo (10% x 3 = 30% di rischio su un trade)
input double InpInitialBalance  = 0;     // Capitale iniziale (0 = saldo al primo avvio)
input double InpMinLotTolerance = 2.0;   // Salta il trade se il lotto minimo rischia piu' di X volte il previsto

input group "=== Freni ==="
input double InpTargetPct   = 100.0;  // Obiettivo: chiude tutto e si ferma a +X% (100 = raddoppio)
input double InpFloorPct    = 60.0;   // Soglia di perdita: chiude tutto e si ferma a -X% dal capitale iniziale
input int    InpMaxDays     = 60;     // Dopo X giorni dall'avvio non apre piu' trade (chiude quelli aperti alla loro uscita)
input double InpDailyStopPct = 0.0;   // Stop giornaliero opzionale in % del capitale iniziale (0 = spento)

input group "=== Simboli e parametri ==="
input string InpSymAsian     = "EURCHF";  // Simbolo Asian fade (nome del broker, es. EURCHFc su conti cent)
input string InpSymZ         = "EURGBP";  // Simbolo Z-score fade (nome del broker)
input double InpAsianK       = 2.5;       // Asian fade: deviazioni standard
input int    InpAsianN       = 20;        // Asian fade: periodo Bollinger (H1)
input int    InpAsianFrom    = 0;         // Asian fade: prima ora server di ingresso (inclusa)
input int    InpAsianTo      = 8;         // Asian fade: ultima ora server di ingresso (esclusa)
input int    InpAsianExitH   = 10;        // Asian fade: uscita forzata dalle ore server
input double InpAsianStopATR = 6.0;       // Asian fade: stop = X * ATR(14) H1
input int    InpZN           = 50;        // Z-score: periodo media (D1)
input double InpZIn          = 1.5;       // Z-score: soglia di ingresso
input double InpZStopATR     = 2.0;       // Z-score: stop = X * ATR(14) D1
input int    InpZMaxDays     = 15;        // Z-score: giorni massimi di permanenza

input group "=== Varie ==="
input long   InpMagicBase = 990000;       // Magic base (strategia N = base + N)
input int    InpTimerSec  = 10;           // Frequenza controllo (secondi)

CTrade trade;
double   g_initial = 0, g_dayRef = 0, g_mult = 1.0;
datetime g_day = 0, g_haltDay = 0, g_start = 0;
bool     g_haltAll = false;
datetime g_lastH1 = 0, g_lastD1 = 0;
string   g_symA = "", g_symZ = "";

string   GV(string n) { return "XTA50_" + IntegerToString(InpMagicBase) + "_" + n; }
long     Magic(int s) { return InpMagicBase + s; }
bool     IsOur(long m) { return m == Magic(1) || m == Magic(2); }
datetime Today() { return TimeCurrent() - (TimeCurrent() % 86400); }
bool     Expired() { return InpMaxDays > 0 && TimeCurrent() - g_start > (datetime)InpMaxDays * 86400; }
bool     NoNewTrades() { return g_haltAll || g_haltDay == Today() || Expired(); }

bool FindPos(string sym, long magic, ulong &ticket)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == sym && PositionGetInteger(POSITION_MAGIC) == magic) { ticket = t; return true; }
     }
   return false;
  }

// --- indicatori (serie: 0 = barra in corso, 1 = ultima chiusa)
double ATRWilder(const MqlRates &r[], int n, int shift)
  {
   int total = ArraySize(r); double a = 0; bool init = false;
   for(int i = total - 1; i >= shift; i--)
     {
      double tr = r[i].high - r[i].low;
      if(i + 1 < total) { double pc = r[i + 1].close; tr = MathMax(tr, MathMax(MathAbs(r[i].high - pc), MathAbs(r[i].low - pc))); }
      if(!init) { a = tr; init = true; } else a += (tr - a) / n;
     }
   return a;
  }
double Mean(const MqlRates &r[], int n, int shift)
  { double s = 0; for(int i = shift; i < shift + n; i++) s += r[i].close; return s / n; }
double Std(const MqlRates &r[], int n, int shift)
  { double m = Mean(r, n, shift), s = 0; for(int i = shift; i < shift + n; i++) s += MathPow(r[i].close - m, 2); return MathSqrt(s / (n - 1)); }

// --- dimensionamento
double LotsForRisk(string sym, double stopDist, double riskMoney, bool &ok)
  {
   ok = false;
   double tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE_LOSS); if(tv <= 0) tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE), step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), vmax = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(tv <= 0 || ts <= 0 || step <= 0 || stopDist <= 0) return 0;
   double lossPerLot = stopDist / ts * tv;
   double lots = MathFloor(riskMoney / lossPerLot / step) * step;
   if(lots < vmin)
     {
      if(vmin * lossPerLot > riskMoney * InpMinLotTolerance)
        { PrintFormat("XTA50: %s saltato, il lotto minimo rischia %.2f contro %.2f previsti. Serve un conto cent/micro.", sym, vmin * lossPerLot, riskMoney); return 0; }
      lots = vmin;
     }
   lots = MathMin(lots, vmax);
   ok = true;
   return NormalizeDouble(lots, (int)MathMax(0, MathCeil(-MathLog10(step) - 1e-9)));
  }

bool Open(int strat, string sym, int dir, double stopDist, string tag)
  {
   if(NoNewTrades()) return false;
   double riskMoney = g_initial * InpRiskBasePct / 100.0 * g_mult;
   bool ok; double lots = LotsForRisk(sym, stopDist, riskMoney, ok);
   if(!ok) return false;
   int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double px = dir > 0 ? SymbolInfoDouble(sym, SYMBOL_ASK) : SymbolInfoDouble(sym, SYMBOL_BID);
   double sl = NormalizeDouble(px - dir * stopDist, dg);
   trade.SetExpertMagicNumber(Magic(strat)); trade.SetTypeFillingBySymbol(sym); trade.SetDeviationInPoints(30);
   bool res = dir > 0 ? trade.Buy(lots, sym, 0, sl, 0, tag) : trade.Sell(lots, sym, 0, sl, 0, tag);
   if(!res || (trade.ResultRetcode() != TRADE_RETCODE_DONE && trade.ResultRetcode() != TRADE_RETCODE_PLACED))
     { PrintFormat("XTA50: errore apertura %s: %d %s", tag, trade.ResultRetcode(), trade.ResultRetcodeDescription()); return false; }
   PrintFormat("XTA50: aperto %s %s lotti=%.2f rischio=%.2f (x%.2f) SL=%s", tag, dir > 0 ? "BUY" : "SELL", lots, riskMoney, g_mult, DoubleToString(sl, dg));
   return true;
  }

void ClosePos(ulong t, string why)
  {
   if(trade.PositionClose(t)) PrintFormat("XTA50: chiuso %I64u (%s)", t, why);
   else PrintFormat("XTA50: errore chiusura %I64u: %d", t, trade.ResultRetcode());
  }

void CloseAllOurs(string why)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     { ulong t = PositionGetTicket(i); if(t != 0 && IsOur(PositionGetInteger(POSITION_MAGIC))) ClosePos(t, why); }
  }

// --- anti-martingala: aggiorna il moltiplicatore a ogni trade chiuso
void OnTradeTransaction(const MqlTradeTransaction &tr, const MqlTradeRequest &req, const MqlTradeResult &res)
  {
   if(tr.type != TRADE_TRANSACTION_DEAL_ADD || tr.deal == 0) return;
   if(!HistoryDealSelect(tr.deal)) return;
   if(!IsOur(HistoryDealGetInteger(tr.deal, DEAL_MAGIC))) return;
   if(HistoryDealGetInteger(tr.deal, DEAL_ENTRY) != DEAL_ENTRY_OUT) return;
   double pl = HistoryDealGetDouble(tr.deal, DEAL_PROFIT) + HistoryDealGetDouble(tr.deal, DEAL_COMMISSION) + HistoryDealGetDouble(tr.deal, DEAL_SWAP);
   g_mult = pl > 0 ? MathMin(g_mult * InpWinMult, InpMaxMult) : 1.0;
   GlobalVariableSet(GV("mult"), g_mult);
   PrintFormat("XTA50: trade chiuso %+.2f, moltiplicatore ora x%.2f", pl, g_mult);
  }

// --- freni
void CheckGuards()
  {
   double bal = AccountInfoDouble(ACCOUNT_BALANCE), eq = AccountInfoDouble(ACCOUNT_EQUITY);
   datetime d = Today();
   if(d != g_day) { g_day = d; g_dayRef = MathMax(bal, eq); }
   if(g_haltAll) return;
   if(InpTargetPct > 0 && eq >= g_initial * (1.0 + InpTargetPct / 100.0))
     { CloseAllOurs("obiettivo"); g_haltAll = true; GlobalVariableSet(GV("haltall"), 1); Print("XTA50: OBIETTIVO RAGGIUNTO, tutto chiuso, EA fermo"); return; }
   if(InpFloorPct > 0 && eq <= g_initial * (1.0 - InpFloorPct / 100.0))
     { CloseAllOurs("soglia di perdita"); g_haltAll = true; GlobalVariableSet(GV("haltall"), 1); Print("XTA50: SOGLIA DI PERDITA, tutto chiuso, EA fermo"); return; }
   if(InpDailyStopPct > 0 && g_haltDay != d && eq <= g_dayRef - g_initial * InpDailyStopPct / 100.0)
     { CloseAllOurs("stop giornaliero"); g_haltDay = d; Print("XTA50: stop giornaliero fino a domani"); }
  }

// --- 1: Asian fade su ogni nuova barra H1
void AsianFade()
  {
   if(g_symA == "") return;
   datetime t0 = iTime(g_symA, PERIOD_H1, 0);
   if(t0 == 0 || t0 == g_lastH1) return;
   g_lastH1 = t0;
   MqlRates r[]; ArraySetAsSeries(r, true);
   if(CopyRates(g_symA, PERIOD_H1, 0, 200, r) < 200) return;
   double m = Mean(r, InpAsianN, 1), sd = Std(r, InpAsianN, 1), c = r[1].close;
   MqlDateTime dt; TimeToStruct(r[1].time, dt);
   ulong tk;
   if(FindPos(g_symA, Magic(1), tk))
     {
      long type = PositionGetInteger(POSITION_TYPE);
      if(dt.hour >= InpAsianExitH || (type == POSITION_TYPE_BUY && c >= m) || (type == POSITION_TYPE_SELL && c <= m))
         ClosePos(tk, "Asian fade: media o fine sessione");
      else return;
     }
   if(dt.hour >= InpAsianFrom && dt.hour < InpAsianTo)
     {
      double stop = InpAsianStopATR * ATRWilder(r, 14, 1);
      if(c < m - InpAsianK * sd) Open(1, g_symA, +1, stop, "XTA50_AsianFade");
      else if(c > m + InpAsianK * sd) Open(1, g_symA, -1, stop, "XTA50_AsianFade");
     }
  }

// --- 2: Z-score fade su ogni nuova barra D1
void ZFade()
  {
   if(g_symZ == "") return;
   datetime t0 = iTime(g_symZ, PERIOD_D1, 0);
   if(t0 == 0 || t0 == g_lastD1) return;
   g_lastD1 = t0;
   MqlRates r[]; ArraySetAsSeries(r, true);
   if(CopyRates(g_symZ, PERIOD_D1, 0, 200, r) < 200) return;
   double m = Mean(r, InpZN, 1), sd = Std(r, InpZN, 1);
   if(sd <= 0) return;
   double z = (r[1].close - m) / sd;
   ulong tk;
   if(FindPos(g_symZ, Magic(2), tk))
     {
      long type = PositionGetInteger(POSITION_TYPE);
      datetime ot = (datetime)PositionGetInteger(POSITION_TIME);
      if((type == POSITION_TYPE_BUY && z > 0) || (type == POSITION_TYPE_SELL && z < 0)) ClosePos(tk, "Z-score: ritorno alla media");
      else if(iBarShift(g_symZ, PERIOD_D1, ot, false) >= InpZMaxDays) ClosePos(tk, "Z-score: tempo massimo");
      return;
     }
   double stop = InpZStopATR * ATRWilder(r, 14, 1);
   if(z < -InpZIn) Open(2, g_symZ, +1, stop, "XTA50_ZFade");
   else if(z > InpZIn) Open(2, g_symZ, -1, stop, "XTA50_ZFade");
  }

void Process()
  {
   CheckGuards();
   if(g_haltAll) return;
   AsianFade();   // le uscite vengono gestite anche dopo la scadenza dei giorni
   ZFade();
  }

int OnInit()
  {
   g_symA = SymbolSelect(InpSymAsian, true) ? InpSymAsian : "";
   g_symZ = SymbolSelect(InpSymZ, true) ? InpSymZ : "";
   if(g_symA == "") PrintFormat("XTA50: simbolo %s non trovato: Asian fade disattivata", InpSymAsian);
   if(g_symZ == "") PrintFormat("XTA50: simbolo %s non trovato: Z-score disattivata", InpSymZ);
   if(InpInitialBalance > 0) g_initial = InpInitialBalance;
   else if(GlobalVariableCheck(GV("initial"))) g_initial = GlobalVariableGet(GV("initial"));
   else g_initial = AccountInfoDouble(ACCOUNT_BALANCE);
   GlobalVariableSet(GV("initial"), g_initial);
   g_start = GlobalVariableCheck(GV("start")) ? (datetime)GlobalVariableGet(GV("start")) : TimeCurrent();
   GlobalVariableSet(GV("start"), (double)g_start);
   g_mult = GlobalVariableCheck(GV("mult")) ? GlobalVariableGet(GV("mult")) : 1.0;
   g_haltAll = GlobalVariableCheck(GV("haltall")) && GlobalVariableGet(GV("haltall")) > 0;
   if(MQLInfoInteger(MQL_TESTER))
     { g_haltAll = false; g_mult = 1.0; g_start = TimeCurrent(); g_initial = InpInitialBalance > 0 ? InpInitialBalance : AccountInfoDouble(ACCOUNT_BALANCE); }
   PrintFormat("XTA50 avviato: capitale %.2f, rischio base %.1f%% (%.2f), moltiplicatore x%.2f, obiettivo +%.0f%%, soglia -%.0f%%, durata %d giorni",
               g_initial, InpRiskBasePct, g_initial * InpRiskBasePct / 100.0, g_mult, InpTargetPct, InpFloorPct, InpMaxDays);
   if(g_haltAll) Print("XTA50: EA FERMO (obiettivo o soglia gia' raggiunti). Per ripartire cancella le variabili globali XTA50_* (F3).");
   EventSetTimer(MathMax(1, InpTimerSec));
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) { EventKillTimer(); }
void OnTimer() { Process(); }
void OnTick()  { CheckGuards(); }
//+------------------------------------------------------------------+
