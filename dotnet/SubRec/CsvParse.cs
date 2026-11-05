// Port of backend/csvimport.py parse_csv() and its date/amount helpers.
// Behaviour-identical to the Python path (golden parity tests compare both).
using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace SubRec;

public static partial class CsvParse
{
    private static readonly string[] DateHints = { "date", "дата" };
    private static readonly string[] DescHints = { "description", "опис", "призначен", "detail", "merchant", "payee", "найменув" };
    private static readonly string[] AmtHints = { "amount", "сума", "sum", "value", "debit", "credit" };

    private static readonly Regex TimestampRe =
        new(@"^(\d{4}-\d{2}-\d{2})[ T]", RegexOptions.Compiled);
    private static readonly Regex DmyMonthFirst = new(@"^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})$", RegexOptions.Compiled);
    private static readonly Regex MdyMonthFirst = new(@"^([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})$", RegexOptions.Compiled);
    private static readonly Regex NegRe = new(@"^-|-\s*$|^\(.*\)$", RegexOptions.Compiled);
    private static readonly Regex CurrencyNoise = new(@"(?i)(uah|usd|eur|грн|₴|\$|€|£)", RegexOptions.Compiled);
    private static readonly Regex NumericOnly = new(@"^[\d.,]+$", RegexOptions.Compiled);

    private static readonly Dictionary<string, int> MonthNames = new(StringComparer.Ordinal)
    {
        ["jan"] = 1, ["feb"] = 2, ["mar"] = 3, ["apr"] = 4, ["may"] = 5, ["jun"] = 6,
        ["jul"] = 7, ["aug"] = 8, ["sep"] = 9, ["oct"] = 10, ["nov"] = 11, ["dec"] = 12,
    };

    // Lenient strptime-equivalents: Python %d/%m accept 1-2 unpadded digits.
    // Group indexes are 1-based (Groups[0] is the whole match in .NET).
    private static readonly (Regex Re, int YearIdx, int MonthIdx, int DayIdx)[] DateFormats =
    {
        (new(@"^(\d{4})-(\d{1,2})-(\d{1,2})$", RegexOptions.Compiled), 1, 2, 3),   // %Y-%m-%d
        (new(@"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", RegexOptions.Compiled), 3, 2, 1), // %d.%m.%Y
        (new(@"^(\d{1,2})/(\d{1,2})/(\d{4})$", RegexOptions.Compiled), 3, 2, 1),   // %d/%m/%Y (day-first wins ties, EU statements)
        (new(@"^(\d{1,2})/(\d{1,2})/(\d{4})$", RegexOptions.Compiled), 3, 1, 2),   // %m/%d/%Y
        (new(@"^(\d{1,2})-(\d{1,2})-(\d{4})$", RegexOptions.Compiled), 3, 2, 1),   // %d-%m-%Y
        (new(@"^(\d{4})\.(\d{1,2})\.(\d{1,2})$", RegexOptions.Compiled), 1, 2, 3), // %Y.%m.%d
        (new(@"^(\d{4})/(\d{1,2})/(\d{1,2})$", RegexOptions.Compiled), 1, 2, 3),   // %Y/%m/%d
    };

    public static DateOnly? ParseDate(string value)
    {
        var v = value.Trim().Trim('"').Trim('\'');
        // Timestamps ('2024-06-01 10:30:44', '2024-06-01T10:30'): keep the date part.
        var m = TimestampRe.Match(v);
        if (m.Success)
            v = m.Groups[1].Value;
        foreach (var (re, yi, mi, di) in DateFormats)
        {
            m = re.Match(v);
            if (!m.Success)
                continue;
            if (TryDate(int.Parse(m.Groups[yi].Value, CultureInfo.InvariantCulture),
                        int.Parse(m.Groups[mi].Value, CultureInfo.InvariantCulture),
                        int.Parse(m.Groups[di].Value, CultureInfo.InvariantCulture),
                        out var d))
                return d;
        }
        m = DmyMonthFirst.Match(v);   // 01 Jun 2024
        if (m.Success && MonthNames.TryGetValue(m.Groups[2].Value.ToLowerInvariant(), out var mon))
        {
            if (TryDate(int.Parse(m.Groups[3].Value, CultureInfo.InvariantCulture), mon,
                        int.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture), out var d))
                return d;
        }
        m = MdyMonthFirst.Match(v);   // Jun 1, 2024
        if (m.Success && MonthNames.TryGetValue(m.Groups[1].Value.ToLowerInvariant(), out mon))
        {
            if (TryDate(int.Parse(m.Groups[3].Value, CultureInfo.InvariantCulture), mon,
                        int.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture), out var d))
                return d;
        }
        return null;
    }

    private static bool TryDate(int year, int month, int day, out DateOnly d)
    {
        if (year is >= 1 and <= 9999 && month is >= 1 and <= 12 && day is >= 1 and <= 31
            && DateOnly.TryParseExact($"{year:D4}-{month:D2}-{day:D2}", "yyyy-MM-dd",
                                      CultureInfo.InvariantCulture, DateTimeStyles.None, out d))
            return true;
        d = default;
        return false;
    }

    public static double? ParseAmount(string raw)
    {
        var s = raw.Trim().Trim('"').Trim('\'');
        bool neg = NegRe.IsMatch(s);
        s = CurrencyNoise.Replace(s, "");
        s = s.Replace("\u00a0", "").Replace(" ", "").Trim('(', ')', '+', '-');
        if (!NumericOnly.IsMatch(s))
            return null;
        if (s.Contains(',') && s.Contains('.'))
        {
            // The right-most separator is the decimal one; the other is thousands.
            char dec = s.LastIndexOf(',') > s.LastIndexOf('.') ? ',' : '.';
            s = s.Replace(dec == '.' ? "," : ".", "");
            s = s.Replace(dec, '.');
        }
        else if (s.Contains(','))
        {
            s = s.Replace(",", ".");   // EU decimal comma: "1234,56"
        }
        if (!double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var value))
            return null;
        return neg ? -value : value;
    }

    private static char SniffDelimiter(string sampleLine)
    {
        var counts = new Dictionary<char, int>();
        foreach (var d in new[] { ',', ';', '\t', '|' })
            counts[d] = sampleLine.Count(c => c == d);
        char best = counts.Keys.First();
        foreach (var kv in counts)
            if (kv.Value > counts[best])
                best = kv.Key;
        return counts[best] > 0 ? best : ',';
    }

    private static bool LooksLikeHeader(IReadOnlyList<string> cells)
    {
        var joined = string.Join("|", cells.Select(c => c.Trim().ToLowerInvariant()));
        int hits = 0;
        foreach (var hints in new[] { DateHints, DescHints, AmtHints })
            if (hints.Any(h => joined.Contains(h)))
                hits++;
        return hits >= 2;
    }

    // Python csv.reader applied per line: RFC4180-style quoted fields.
    private static List<string> ParseLine(string line, char delim)
    {
        var fields = new List<string>();
        var sb = new StringBuilder();
        bool inQuotes = false;
        int i = 0;
        while (i < line.Length)
        {
            char c = line[i];
            if (inQuotes)
            {
                if (c == '"')
                {
                    if (i + 1 < line.Length && line[i + 1] == '"') { sb.Append('"'); i += 2; }
                    else { inQuotes = false; i++; }
                }
                else { sb.Append(c); i++; }
            }
            else if (c == '"' && sb.Length == 0) { inQuotes = true; i++; }
            else if (c == delim)
            {
                fields.Add(sb.ToString());
                sb.Clear();
                i++;
            }
            else { sb.Append(c); i++; }
        }
        fields.Add(sb.ToString());
        return fields;
    }

    private static readonly char[] LineSeps = { '\n', '\r', '\u000b', '\u000c', '\u0085', '\u2028', '\u2029' };

    /// <summary>Parse a bank/CSV statement into (date, description, amount) rows.
    /// Auto-detects the delimiter, an optional header row, the date format and
    /// the amount format (EU decimal commas, currency symbols, negatives).
    /// Raises FormatException when the file does not contain a usable statement.</summary>
    public static List<Txn> ParseCsv(string text, bool canonical = false)
    {
        text = text.TrimStart('\ufeff');
        var lines = text.Split(LineSeps).Where(ln => ln.Length > 0).ToList();
        if (lines.Count < 2)
            throw new FormatException("CSV needs at least 2 non-empty lines");
        char delim = SniffDelimiter(lines[0]);
        var rows = lines.Select(ln => ParseLine(ln, delim)).ToList();

        int colDate = -1, colDesc = -1, colAmt = -1, colCcy = -1;
        int start = 0;
        if (canonical)
        {
            // native_accel feeds the CLI in fixed order (with an explicit
            // currency column, unlike the generic Python header guessing).
            colDate = 0; colDesc = 1; colAmt = 2; colCcy = 3;
            start = 1;
        }
        else if (LooksLikeHeader(rows[0]))
        {
            var header = rows[0].Select(c => c.Trim().ToLowerInvariant()).ToList();
            for (int i = 0; i < header.Count; i++)
            {
                var h = header[i];
                if (colDate < 0 && DateHints.Any(k => h.Contains(k))) colDate = i;
                else if (colDesc < 0 && DescHints.Any(k => h.Contains(k))) colDesc = i;
                else if (colAmt < 0 && AmtHints.Any(k => h.Contains(k))) colAmt = i;
            }
            start = 1;
        }
        if (colDate < 0 || colAmt < 0)
        {
            var body = rows.Skip(start).ToList();
            (var dateHits, var numHits) = ColumnScores(body);
            if (colDate < 0)
            {
                colDate = ArgMax(dateHits);
                if (dateHits[colDate] == 0)
                    throw new FormatException("no date column found");
            }
            if (colAmt < 0)
            {
                // Amount = most numeric column that is not the date column.
                var order = Enumerable.Range(0, numHits.Length)
                    .OrderBy(i => -numHits[i]);   // stable, like Python sorted()
                colAmt = order.FirstOrDefault(i => i != colDate && numHits[i] > 0, -1);
                if (colAmt < 0)
                    throw new FormatException("no amount column found");
            }
            if (colDesc < 0)
            {
                int width = body.Max(r => r.Count);
                var widths = new int[width];
                foreach (var r in body)
                    for (int i = 0; i < r.Count; i++)
                        widths[i] = Math.Max(widths[i], r[i].Length);
                int best = -1, bestW = -1;
                for (int i = 0; i < width; i++)
                {
                    if (i == colDate || i == colAmt) continue;
                    if (widths[i] > bestW) { best = i; bestW = widths[i]; }
                }
                colDesc = best;   // -1 = none found
            }
        }

        int maxCol = Math.Max(colDate, colAmt);
        var txns = new List<Txn>();
        for (int ri = start; ri < rows.Count; ri++)
        {
            var row = rows[ri];
            if (row.Count <= maxCol)
                continue;
            var d = ParseDate(row[colDate]);
            var amt = ParseAmount(row[colAmt]);
            if (d is null || amt is null)
                continue;
            string desc = colDesc >= 0 && colDesc < row.Count ? row[colDesc].Trim() : "";
            string ccy = colCcy >= 0 && colCcy < row.Count ? row[colCcy].Trim().ToUpperInvariant() : "USD";
            if (!FullMatchAsciiUpper(ccy))
                ccy = "USD";
            txns.Add(new Txn(d.Value, desc, amt.Value, ccy));
        }
        if (txns.Count == 0)
            throw new FormatException("no parsable (date, amount) rows in CSV");
        return txns;
    }

    private static bool FullMatchAsciiUpper(string s)
        => s.Length == 3 && s.All(c => c >= 'A' && c <= 'Z');

    /// <summary>Score each column: how many values parse as a date / a number.</summary>
    private static (int[] DateHits, int[] NumHits) ColumnScores(List<List<string>> rows)
    {
        int n = rows.Max(r => r.Count);
        var dateHits = new int[n];
        var numHits = new int[n];
        foreach (var row in rows)
        {
            for (int i = 0; i < row.Count; i++)
            {
                if (ParseDate(row[i]).HasValue)
                    dateHits[i]++;
                if (ParseAmount(row[i]).HasValue)
                    numHits[i]++;
            }
        }
        return (dateHits, numHits);
    }

    private static int ArgMax(int[] xs)
    {
        int best = 0;
        for (int i = 1; i < xs.Length; i++)
            if (xs[i] > xs[best])
                best = i;
        return best;
    }
}
