using System.Globalization;

namespace Bank;

/// <summary>A plain-text account statement for an inclusive date range.</summary>
public static class Statement
{
    private static readonly CultureInfo Invariant = CultureInfo.InvariantCulture;

    public static string Render(Ledger ledger, string accountId, DateOnly from, DateOnly to)
    {
        if (to < from)
        {
            throw new ArgumentException("the period ends before it starts");
        }
        var account = ledger.Get(accountId);
        var before = account.History.LastOrDefault(t => t.Day < from);
        var opening = before?.BalanceAfter ?? 0m;
        var inPeriod = account.History.Where(t => t.Day >= from && t.Day <= to).ToList();
        var closing = inPeriod.Count > 0 ? inPeriod[^1].BalanceAfter : opening;

        var lines = new List<string>
        {
            $"Statement for {account.Id} ({account.Owner}), {Date(from)} to {Date(to)}",
            $"Opening balance: {Money(opening)}",
        };
        lines.AddRange(inPeriod.Select(t =>
            $"{Date(t.Day)}  {t.Description,-24}{t.Amount.ToString("+0.00;-0.00", Invariant),10}{Money(t.BalanceAfter),10}"));
        lines.Add($"Closing balance: {Money(closing)}");
        return string.Join("\n", lines);
    }

    private static string Date(DateOnly day) => day.ToString("yyyy-MM-dd", Invariant);

    private static string Money(decimal value) => value.ToString("0.00", Invariant);
}
