# SubRec — нативний акселератор детекції повторюваних платежів

C# (.NET 10) CLI-порт рушія `backend/csvimport.py` (`parse_csv` +
`detect_recurring`). Читає виписку CSV зі stdin, пише JSON-кандидатів у
stdout. Поведінково ідентичний Python-шляху — це перевіряють golden/fuzz
порівняння в `tests/test_native_parity.py`.

## Збірка

```bash
dotnet publish dotnet/SubRec -c Release -o dotnet/publish
# -> dotnet/publish/SubRec.exe (self-contained, ~70 MB, без інстальованого .NET)
```

## Використання

```bash
./dotnet/publish/SubRec.exe < statement.csv > candidates.json
./dotnet/publish/SubRec.exe --min-occurrences 3 --tolerance 2 < statement.csv
```

Коди виходу: `0` — успіх, `1` — невідомий аргумент, `2` — виписка не
розпарсилась (повідомлення у stderr).

## Інтеграція з subwatch

Python-бекенд сам знаходить exe (спершу `SUBWATCH_NATIVE`, потім
`dotnet/publish/SubRec.exe`), і використовує його у `backend/native_accel.py`;
якщо exe немає або він впав — тихо повертається на Python-шлях.
`SUBWATCH_NATIVE=off` примусово вимикає нативний шлях.
