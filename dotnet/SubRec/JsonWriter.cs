// Minimal JSON writer for Candidate lists. Key order mirrors the Python dict
// built in backend/csvimport.py detect_recurring(); floats are printed like
// Python repr (integral doubles keep a trailing ".0") so consumers parsing the
// JSON get the exact same values as from the Python path.
using System.Globalization;
using System.Text;

namespace SubRec;

public static class JsonWriter
{
    public static string Dump(IReadOnlyList<Candidate> candidates)
    {
        var sb = new StringBuilder("[");
        for (int i = 0; i < candidates.Count; i++)
        {
            if (i > 0) sb.Append(',');
            var c = candidates[i];
            sb.Append('{')
              .Append("\"name\":").Append(Str(c.Name)).Append(',')
              .Append("\"description\":").Append(Str(c.Description)).Append(',')
              .Append("\"amount\":").Append(Num(c.Amount)).Append(',')
              .Append("\"currency\":").Append(Str(c.Currency)).Append(',')
              .Append("\"cycle\":").Append(Str(c.Cycle)).Append(',')
              .Append("\"custom_days\":").Append(c.CustomDays.HasValue ? c.CustomDays.Value.ToString(CultureInfo.InvariantCulture) : "null").Append(',')
              .Append("\"next_due_date\":").Append(Str(c.NextDueDate)).Append(',')
              .Append("\"occurrences\":").Append(c.Occurrences).Append(',')
              .Append("\"period_days\":").Append(c.PeriodDays).Append(',')
              .Append("\"first_date\":").Append(Str(c.FirstDate)).Append(',')
              .Append("\"last_date\":").Append(Str(c.LastDate))
              .Append('}');
        }
        return sb.Append(']').ToString();
    }

    private static string Num(double v)
    {
        if (Math.Floor(v) == v && Math.Abs(v) < 1e15)
            return v.ToString("0.0", CultureInfo.InvariantCulture);  // 10 -> "10.0" (Python repr)
        return v.ToString("R", CultureInfo.InvariantCulture);
    }

    private static string Str(string s)
    {
        var sb = new StringBuilder("\"");
        foreach (var ch in s)
        {
            switch (ch)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                case '\b': sb.Append("\\b"); break;
                case '\f': sb.Append("\\f"); break;
                default:
                    if (ch < ' ') sb.Append("\\u").Append(((int)ch).ToString("x4"));
                    else sb.Append(ch);
                    break;
            }
        }
        return sb.Append('"').ToString();
    }
}
