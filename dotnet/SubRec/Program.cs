// SubRec CLI: stdin CSV -> stdout JSON candidates.
// Faithful port of backend/csvimport.py (parse_csv + detect_recurring) used as
// a native accelerator for the Python subwatch backend. See dotnet/README.md.
//
//   SubRec [--min-occurrences N] [--tolerance DAYS] < statement.csv > candidates.json
//
// Exit codes: 0 = ok, 1 = bad usage, 2 = unusable statement.
using System.Globalization;
using System.Text;
using SubRec;

if (args.Contains("--help") || args.Contains("-h"))
{
    Console.Error.WriteLine(
        """
        SubRec — recurring-payment detection (subwatch native accelerator)

        Usage: SubRec [--min-occurrences N] [--tolerance DAYS] < statement.csv

        Reads a bank statement CSV from stdin (UTF-8), auto-detects the
        delimiter/header/date/amount formats, finds recurring payments and
        writes a JSON array of confirmation candidates to stdout.
        """);
    return 0;
}

int minOcc = Detect.MinOccurrences;
int tol = Detect.DateTolerance;
bool canonical = false;
for (int i = 0; i < args.Length - 1; i++)
{
    switch (args[i])
    {
        case "--min-occurrences": minOcc = int.Parse(args[i + 1], CultureInfo.InvariantCulture); i++; break;
        case "--tolerance": tol = int.Parse(args[i + 1], CultureInfo.InvariantCulture); i++; break;
        default:
            Console.Error.WriteLine($"error: unknown argument {args[i]}");
            return 1;
    }
}
if (args.Contains("--canonical"))
    canonical = true;
if (args.Length % 2 == 1)
{
    Console.Error.WriteLine("error: missing value for the last argument");
    return 1;
}

string input;
using (var reader = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false)))
    input = reader.ReadToEnd();

List<Txn> txns;
try
{
    txns = CsvParse.ParseCsv(input, canonical);
}
catch (FormatException ex)
{
    Console.Error.WriteLine($"error: {ex.Message}");
    return 2;
}

var candidates = Detect.DetectRecurring(txns, minOcc, tol);
using (var stdout = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true })
    stdout.Write("{\"rows\":" + txns.Count + ",\"candidates\":" + JsonWriter.Dump(candidates) + "}");
return 0;
