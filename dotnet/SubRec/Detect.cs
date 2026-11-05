// Port of backend/csvimport.py detect_recurring() + backend/schedule.py
// add_months/add_years. Must stay behaviour-identical to the Python path:
// golden parity tests (tests/test_native_parity.py) compare both outputs.
//
// Pipeline: raw CSV -> ParseCsv() -> List<Txn> -> DetectRecurring() ->
// candidates for the user to confirm. The heuristic groups transactions by a
// normalized description (digits and punctuation stripped, so
// "NETFLIX.COM 8812" and "NETFLIX.COM 9931" group together), then checks that
// consecutive-transaction gaps are all within +/-2 days of one known period
// (7 / 14 / 30 / 31 / 365) and the amounts are near-identical.
// Calendar-honest intervals (28/30/31 for a monthly charge) therefore still
// match, but a skipped month (a 60-day gap) breaks the group.
using System.Globalization;
using System.Text;

namespace SubRec;

public readonly record struct Txn(DateOnly Date, string Description, double Amount, string Currency);

public static class Detect
{
    public static readonly int[] KnownPeriods = { 7, 14, 30, 31, 365 };
    public const int DateTolerance = 2;        // days a real-world gap may deviate
    public const double AmountTolerance = 0.05; // relative spread allowed inside one group
    public const int MinOccurrences = 3;

    // Python str.upper() expands a few single chars into several; char-wise
    // ToUpperInvariant does not. Map the common ones so grouping keys match.
    private static readonly (char From, string To)[] UpperExpand =
    {
        ('ß', "SS"), ('ﬁ', "FI"), ('ﬂ', "FL"), ('ﬀ', "FF"), ('ﬃ', "FFI"),
        ('ﬄ', "FFL"), ('ſ', "S"), ('Ǉ', "LJ"), ('Ǌ', "NJ"), ('ǅ', "Dz"),
    };

    /// <summary>Grouping key: uppercase, digits/punctuation dropped, spaces collapsed.</summary>
    public static string NormalizeDescription(string desc)
    {
        var upper = ExpandUpper(desc.ToUpperInvariant());
        var sb = new StringBuilder(upper.Length);
        foreach (var ch in upper)
        {
            bool keep = (ch >= 'A' && ch <= 'Z')
                        || (ch >= '\u0410' && ch <= '\u042F')   // А-Я
                        || ch == '\u0406' || ch == '\u0407'     // І Ї
                        || ch == '\u0404' || ch == '\u0490'     // Є Ґ
                        || ch == ' ';
            sb.Append(keep ? ch : ' ');
        }
        // collapse whitespace runs, trim (same as re.sub(r"\s+", " ", ...) + strip)
        var parts = sb.ToString().Split(' ', StringSplitOptions.RemoveEmptyEntries);
        return string.Join(' ', parts);
    }

    private static string ExpandUpper(string s)
    {
        foreach (var (from, to) in UpperExpand)
        {
            if (s.Contains(from))
                s = s.Replace(from.ToString(), to);
        }
        return s;
    }

    /// <summary>Median like Python statistics.median (float division for even n).</summary>
    private static double Median(double[] xs)
    {
        var sorted = (double[])xs.Clone();
        Array.Sort(sorted);
        int n = sorted.Length;
        return n % 2 == 1 ? sorted[n / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0;
    }

    private static int? PickPeriod(double medianGap)
    {
        int best = KnownPeriods[0];
        double bestDist = Math.Abs(best - medianGap);
        for (int i = 1; i < KnownPeriods.Length; i++)
        {
            double d = Math.Abs(KnownPeriods[i] - medianGap);
            if (d < bestDist) { best = KnownPeriods[i]; bestDist = d; }
        }
        return bestDist <= DateTolerance ? best : null;
    }

    // --- calendar math (port of backend/schedule.py) --------------------------

    /// <summary>Same calendar day clamped to the month's real length (Jan 31 -> Feb 28).</summary>
    private static DateOnly Clamp(int year, int month, int day)
    {
        int last = DateTime.DaysInMonth(year, month);
        return new DateOnly(year, month, Math.Min(day, last));
    }

    /// <summary>d + n months; day clamps to month length but stays anchored (Jan 31 -> Feb 28 -> Mar 31).</summary>
    private static DateOnly AddMonths(DateOnly d, int n, int anchorDay)
    {
        int monthIndex = d.Month - 1 + n;
        int year = d.Year + monthIndex / 12;
        int month = monthIndex % 12 + 1;
        return Clamp(year, month, anchorDay);
    }

    /// <summary>d + n years; Feb 29 clamps to Feb 28 on non-leap years, anchor restores it.</summary>
    private static DateOnly AddYears(DateOnly d, int n, int anchorDay)
        => Clamp(d.Year + n, d.Month, anchorDay);

    private static DateOnly NextDue(DateOnly last, int period, out string cycle, out int? customDays)
    {
        if (period == 30 || period == 31)
        {
            cycle = "monthly";
            customDays = null;
            return AddMonths(last, 1, last.Day);
        }
        if (period == 365)
        {
            cycle = "yearly";
            customDays = null;
            return AddYears(last, 1, last.Day);
        }
        cycle = "custom";
        customDays = period;
        return last.AddDays(period);
    }

    private static bool FullMatchAsciiUpper(string s)
    {
        return s.Length == 3 && s.All(c => c >= 'A' && c <= 'Z');
    }

    // --- detection -------------------------------------------------------------

    /// <summary>Find repeating charges -> confirmation candidates (sorted by amount).</summary>
    public static List<Candidate> DetectRecurring(
        IReadOnlyList<Txn> txns, int minOccurrences = MinOccurrences, int tol = DateTolerance)
    {
        // Group by normalized description, preserving first-occurrence order
        // (Python dict insertion order).
        var index = new Dictionary<string, int>(StringComparer.Ordinal);
        var groups = new List<List<Txn>>();
        foreach (var t in txns)
        {
            var key = NormalizeDescription(t.Description);
            if (!index.TryGetValue(key, out var gi))
            {
                gi = groups.Count;
                index[key] = gi;
                groups.Add(new List<Txn>());
            }
            groups[gi].Add(t);
        }

        var candidates = new List<Candidate>();
        foreach (var group in groups)
        {
            if (group.Count < minOccurrences)
                continue;
            // stable sort by date (Python list.sort is stable)
            var ordered = group.OrderBy(t => t.Date).ToList();

            var gaps = new double[ordered.Count - 1];
            for (int i = 0; i < gaps.Length; i++)
                gaps[i] = ordered[i + 1].Date.DayNumber - ordered[i].Date.DayNumber;

            int? period = PickPeriod(Median(gaps));
            // Calendar-honest intervals: a monthly charge may gap 28/30/31 days,
            // so each gap may match ANY known period within the tolerance, while
            // the median still picks the labelling period (30 vs 31 etc.).
            if (period is null ||
                !gaps.All(g => KnownPeriods.Any(p => Math.Abs(g - p) <= tol)))
                continue;

            var amounts = ordered.Select(t => Math.Abs(t.Amount)).ToArray();
            double medAmount = Median(amounts);
            double spread = amounts.Max() - amounts.Min();
            if (spread > Math.Max(0.02, AmountTolerance * medAmount))
                continue;

            // most frequent raw label / currency; ties keep first-encountered order
            string description = MostCommon(ordered.Select(t => t.Description.Trim()).ToList());
            string ccy = MostCommon(ordered.Select(t => t.Currency).ToList()).ToUpperInvariant();
            if (!FullMatchAsciiUpper(ccy))
                ccy = "USD";

            var nextDue = NextDue(ordered[^1].Date, period.Value, out var cycle, out var customDays);

            candidates.Add(new Candidate(
                Name: description.Length > 60 ? description[..60] : description,
                Description: description,
                Amount: Math.Round(medAmount, 2),
                Currency: ccy,
                Cycle: cycle,
                CustomDays: customDays,
                NextDueDate: nextDue.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                Occurrences: group.Count,
                PeriodDays: period.Value,
                FirstDate: ordered[0].Date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                LastDate: ordered[^1].Date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)));
        }
        // stable sort by descending amount (Python sorted(..., key=-amount))
        return candidates.OrderByDescending(c => c.Amount).ToList();
    }

    private static string MostCommon(IReadOnlyList<string> values)
    {
        var seen = new List<string>();
        var counts = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (var v in values)
        {
            if (!counts.TryGetValue(v, out var c))
            {
                seen.Add(v);
                c = 0;
            }
            counts[v] = c + 1;
        }
        string best = seen[0];
        int bestCount = 0;
        foreach (var v in seen)
        {
            int c = counts[v];
            if (c > bestCount) { best = v; bestCount = c; }
        }
        return best;
    }
}

public readonly record struct Candidate(
    string Name, string Description, double Amount, string Currency,
    string Cycle, int? CustomDays, string NextDueDate,
    int Occurrences, int PeriodDays, string FirstDate, string LastDate);
