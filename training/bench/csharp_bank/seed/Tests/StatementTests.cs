using Bank;
using Xunit;

namespace Bank.Tests;

public class StatementTests
{
    [Fact]
    public void RendersAStatementForAPeriod()
    {
        var ledger = new Ledger();
        var a = ledger.Open("Ana").Id;
        var b = ledger.Open("Bogdan").Id;
        ledger.Deposit(a, 200m, new DateOnly(2026, 10, 30));
        ledger.Deposit(a, 100m, new DateOnly(2026, 11, 1));
        ledger.Transfer(a, b, 50.5m, new DateOnly(2026, 11, 3));
        ledger.Withdraw(a, 1000m - 750.5m, new DateOnly(2026, 11, 4));
        ledger.Deposit(a, 1m, new DateOnly(2026, 12, 1));

        var text = Statement.Render(ledger, a, new DateOnly(2026, 11, 1), new DateOnly(2026, 11, 30));

        var expected = string.Join("\n",
            "Statement for ACC-0001 (Ana), 2026-11-01 to 2026-11-30",
            "Opening balance: 200.00",
            "2026-11-01  Deposit                    +100.00    300.00",
            "2026-11-03  Transfer to ACC-0002        -50.50    249.50",
            "2026-11-04  Withdrawal                 -249.50      0.00",
            "Closing balance: 0.00");
        Assert.Equal(expected, text);
    }

    [Fact]
    public void EmptyPeriodShowsOnlyBalances()
    {
        var ledger = new Ledger();
        var a = ledger.Open("Ana", overdraftLimit: 20m).Id;
        ledger.Withdraw(a, 12.3m, new DateOnly(2026, 1, 5));
        var text = Statement.Render(ledger, a, new DateOnly(2026, 2, 1), new DateOnly(2026, 2, 28));
        Assert.Equal(string.Join("\n",
            "Statement for ACC-0001 (Ana), 2026-02-01 to 2026-02-28",
            "Opening balance: -12.30",
            "Closing balance: -12.30"), text);
    }

    [Fact]
    public void RejectsAnInvertedPeriod()
    {
        var ledger = new Ledger();
        var a = ledger.Open("Ana").Id;
        Assert.Throws<ArgumentException>(() =>
            Statement.Render(ledger, a, new DateOnly(2026, 2, 1), new DateOnly(2026, 1, 1)));
    }
}
