#ifndef __SYSTEM_STATUS_MQH__
#define __SYSTEM_STATUS_MQH__

#property strict

#include <SYSTEM_Export.mqh>

#define SYSTEM_PROTOCOL_SCHEMA_VERSION "1.0.0"
#define SYSTEM_EA_VERSION "1.0.0"
#define SYSTEM_STATUS_FILENAME_TEMPLATE "status_%s.json"

string SYSTEM_GetProtocolSchemaVersion()
{
   return SYSTEM_PROTOCOL_SCHEMA_VERSION;
}

string SYSTEM_GetEaVersion()
{
   return SYSTEM_EA_VERSION;
}

string SYSTEM_FormatJsonBoolean(const bool value)
{
   return value ? "true" : "false";
}

string SYSTEM_FormatJsonNumber(const double value, const int digits)
{
   return DoubleToString(value, digits);
}

string SYSTEM_EscapeJsonString(const string value)
{
   string escaped = value;
   StringReplace(escaped, "\\", "\\\\");
   StringReplace(escaped, "\"", "\\\"");
   return escaped;
}

string SYSTEM_BuildStatusFilePath(const string account_id)
{
   string filename = StringFormat(SYSTEM_STATUS_FILENAME_TEMPLATE, account_id);
   return SYSTEM_JoinPath(SYSTEM_BuildAccountDir(account_id), filename);
}

string SYSTEM_BuildStatusJson(
   const string account_id,
   const bool connected,
   const bool trade_allowed,
   const double balance,
   const double equity,
   const double margin_free,
   const string last_error
)
{
   string timestamp_utc = SYSTEM_FormatTimeUtc(TimeCurrent());
   string json = "{\n";
   json = json + "  \"account_id\": \"" + SYSTEM_EscapeJsonString(account_id) + "\",\n";
   json = json + "  \"balance\": " + SYSTEM_FormatJsonNumber(balance, 2) + ",\n";
   json = json + "  \"connected\": " + SYSTEM_FormatJsonBoolean(connected) + ",\n";
   json = json + "  \"ea_version\": \"" + SYSTEM_EscapeJsonString(SYSTEM_GetEaVersion()) + "\",\n";
   json = json + "  \"equity\": " + SYSTEM_FormatJsonNumber(equity, 2) + ",\n";
   json = json + "  \"margin_free\": " + SYSTEM_FormatJsonNumber(margin_free, 2) + ",\n";
   json = json + "  \"schema_version\": \"" + SYSTEM_EscapeJsonString(SYSTEM_GetProtocolSchemaVersion()) + "\",\n";
   json = json + "  \"timestamp_utc\": \"" + timestamp_utc + "\",\n";
   json = json + "  \"trade_allowed\": " + SYSTEM_FormatJsonBoolean(trade_allowed);
   if(StringLen(last_error) > 0)
      json = json + ",\n  \"last_error\": \"" + SYSTEM_EscapeJsonString(last_error) + "\"";
   json = json + "\n}\n";
   return json;
}

string SYSTEM_BuildStatusJsonFromAccount(const string account_id)
{
   return SYSTEM_BuildStatusJson(
      account_id,
      IsConnected(),
      IsTradeAllowed(),
      AccountBalance(),
      AccountEquity(),
      AccountFreeMargin(),
      ""
   );
}

bool SYSTEM_ExportStatus(const string account_id)
{
   if(StringLen(account_id) == 0)
      return false;
   if(!SYSTEM_EnsureAccountDirectories(account_id))
      return false;

   string path = SYSTEM_BuildStatusFilePath(account_id);
   string payload = SYSTEM_BuildStatusJsonFromAccount(account_id);
   return SYSTEM_AtomicWriteText(path, payload);
}

bool SYSTEM_ExportStatusWithLastError(const string account_id, const string last_error)
{
   if(StringLen(account_id) == 0)
      return false;
   if(!SYSTEM_EnsureAccountDirectories(account_id))
      return false;

   string path = SYSTEM_BuildStatusFilePath(account_id);
   string payload = SYSTEM_BuildStatusJson(
      account_id,
      IsConnected(),
      IsTradeAllowed(),
      AccountBalance(),
      AccountEquity(),
      AccountFreeMargin(),
      last_error
   );
   return SYSTEM_AtomicWriteText(path, payload);
}

bool SYSTEM_StatusPerformsAnalysis()
{
   return false;
}

#endif
