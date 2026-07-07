#property copyright "SYSTEM"
#property link      "https://github.com/voldis1994/VS_READER_ENGINE_V2"
#property version   "1.00"
#property strict

#include <SYSTEM_Export.mqh>

datetime g_last_exported_bar_time = 0;

int OnInit()
{
   if(Period() != PERIOD_M1)
   {
      Print("SYSTEM_EA requires M1 timeframe");
      return INIT_FAILED;
   }

   if(!SYSTEM_InitPaths())
   {
      Print("SYSTEM path initialization failed");
      return INIT_FAILED;
   }

   return INIT_SUCCEEDED;
}

void OnTick()
{
   if(!SYSTEM_IsNewM1Bar(Symbol(), g_last_exported_bar_time))
      return;

   string account_id = IntegerToString(AccountNumber());
   if(!SYSTEM_ExportMarketAndSensor(account_id, Symbol(), MagicNumber))
   {
      Print("SYSTEM export failed for ", Symbol(), " magic=", MagicNumber);
      return;
   }

   g_last_exported_bar_time = iTime(Symbol(), PERIOD_M1, 0);
}

void OnDeinit(const int reason)
{
}
