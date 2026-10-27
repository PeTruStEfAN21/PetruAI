using Bank;
using Xunit;

namespace Bank.Tests;

public class LedgerTests
{
    static readonly DateOnly Day = new(2026, 11, 2);

    [Fact]
    public void OpensAccountsWithSequentialIds()
    {
        var ledger = new Ledger();
        var a = ledger.Open("Ana");
        var b = ledger.Open("Bogdan", overdraftLimit: 50m);
        Assert.Equal("ACC-0001", a.Id);
        Assert.Equal("ACC-0002", b.Id);
        Assert.Equal("Bogdan", ledger.Get(b.Id).Owner);
        Assert.Equal(0m, a.Balance);
        Assert.Equal(50m, b.OverdraftLimit);
        Assert.Throws<ArgumentException>(() => ledger.Open(" "));
        Assert.Throws<ArgumentOutOfRangeException>(() => ledger.Open("X", overdraftLimit: -1m));
        var ex = Assert.Throws<BankException>(() => ledger.Get("ACC-0099"));
        Assert.Equal("unknown account ACC-0099", ex.Message);
    }

    [Fact]
    public void DepositsAndWithdrawals()
    {
        var ledger = new Ledger();
        var id = ledger.Open("Ana").Id;
        ledger.Deposit(id, 100m, Day);
        ledger.Withdraw(id, 30.25m, Day);
        Assert.Equal(69.75m, ledger.Get(id).Balance);
        Assert.Throws<ArgumentOutOfRangeException>(() => ledger.Deposit(id, 0m, Day));
        Assert.Throws<ArgumentOutOfRangeException>(() => ledger.Withdraw(id, -5m, Day));
        var ex = Assert.Throws<BankException>(() => ledger.Withdraw(id, 70m, Day));
        Assert.Equal("insufficient funds in ACC-0001", ex.Message);
        Assert.Equal(69.75m, ledger.Get(id).Balance);
    }

    [Fact]
    public void OverdraftAllowsANegativeBalanceUpToTheLimit()
    {
        var ledger = new Ledger();
        var id = ledger.Open("Ana", overdraftLimit: 100m).Id;
        ledger.Withdraw(id, 100m, Day);
        Assert.Equal(-100m, ledger.Get(id).Balance);
        Assert.Throws<BankException>(() => ledger.Withdraw(id, 0.01m, Day));
    }

    [Fact]
    public void TransfersMoveMoneyAtomically()
    {
        var ledger = new Ledger();
        var a = ledger.Open("Ana").Id;
        var b = ledger.Open("Bogdan").Id;
        ledger.Deposit(a, 50m, Day);
        ledger.Transfer(a, b, 20m, Day);
        Assert.Equal(30m, ledger.Get(a).Balance);
        Assert.Equal(20m, ledger.Get(b).Balance);
        Assert.Throws<BankException>(() => ledger.Transfer(a, b, 31m, Day));
        Assert.Equal(30m, ledger.Get(a).Balance);
        Assert.Equal(20m, ledger.Get(b).Balance);
        var same = Assert.Throws<BankException>(() => ledger.Transfer(a, a, 1m, Day));
        Assert.Equal("cannot transfer to the same account", same.Message);
        Assert.Throws<BankException>(() => ledger.Transfer(a, "ACC-0404", 1m, Day));
        Assert.Equal(30m, ledger.Get(a).Balance);
    }

    [Fact]
    public void HistoryRecordsEveryMovementWithTheBalanceAfter()
    {
        var ledger = new Ledger();
        var a = ledger.Open("Ana").Id;
        var b = ledger.Open("Bogdan").Id;
        ledger.Deposit(a, 100m, Day);
        ledger.Transfer(a, b, 40m, Day.AddDays(1));
        ledger.Withdraw(b, 15m, Day.AddDays(2));
        var history = ledger.History(a);
        Assert.Equal(new[] { TransactionKind.Deposit, TransactionKind.TransferOut }, history.Select(t => t.Kind));
        Assert.Equal(new[] { 100m, -40m }, history.Select(t => t.Amount));
        Assert.Equal(new[] { 100m, 60m }, history.Select(t => t.BalanceAfter));
        Assert.Equal("Transfer to ACC-0002", history[1].Description);
        var other = ledger.History(b);
        Assert.Equal("Transfer from ACC-0001", other[0].Description);
        Assert.Equal(Day.AddDays(2), other[1].Day);
        Assert.Equal(25m, other[1].BalanceAfter);
    }

    [Fact]
    public void MonthlyInterestAndOverdraftFees()
    {
        var ledger = new Ledger();
        var saver = ledger.Open("Ana").Id;
        var borrower = ledger.Open("Bogdan", overdraftLimit: 100m).Id;
        var empty = ledger.Open("Carmen").Id;
        ledger.Deposit(saver, 1000m, Day);
        ledger.Withdraw(borrower, 10m, Day);
        var paid = ledger.ApplyMonthlyInterest(Day.AddDays(28), annualRatePercent: 3m);
        Assert.Equal(2.5m, paid);
        Assert.Equal(1002.5m, ledger.Get(saver).Balance);
        Assert.Equal(-15m, ledger.Get(borrower).Balance);
        Assert.Equal(0m, ledger.Get(empty).Balance);
        Assert.Equal(TransactionKind.Interest, ledger.History(saver)[^1].Kind);
        Assert.Equal(TransactionKind.Fee, ledger.History(borrower)[^1].Kind);
        Assert.Empty(ledger.History(empty));
    }

    [Fact]
    public void InterestIsRoundedToCents()
    {
        var ledger = new Ledger();
        var id = ledger.Open("Ana").Id;
        ledger.Deposit(id, 333.33m, Day);
        Assert.Equal(0.69m, ledger.ApplyMonthlyInterest(Day, annualRatePercent: 2.5m));
    }

    [Fact]
    public void ClosedAccountsRefuseEverything()
    {
        var ledger = new Ledger();
        var id = ledger.Open("Ana").Id;
        ledger.Deposit(id, 5m, Day);
        var notEmpty = Assert.Throws<BankException>(() => ledger.Close(id));
        Assert.Equal("account ACC-0001 has a non-zero balance", notEmpty.Message);
        ledger.Withdraw(id, 5m, Day);
        ledger.Close(id);
        Assert.True(ledger.Get(id).IsClosed);
        var closed = Assert.Throws<BankException>(() => ledger.Deposit(id, 1m, Day));
        Assert.Equal("account ACC-0001 is closed", closed.Message);
        var other = ledger.Open("Bogdan").Id;
        ledger.Deposit(other, 10m, Day);
        Assert.Throws<BankException>(() => ledger.Transfer(other, id, 1m, Day));
        Assert.Equal(10m, ledger.Get(other).Balance);
        Assert.Equal(0.04m, ledger.ApplyMonthlyInterest(Day, 5m)); // only the open account earns interest
    }
}
