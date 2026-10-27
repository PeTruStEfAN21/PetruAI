namespace Bank;

public sealed class Ledger
{
    private readonly Dictionary<string, Account> _accounts = new();
    private int _next = 1;

    public Account Open(string owner, decimal overdraftLimit = 0m)
    {
        if (string.IsNullOrWhiteSpace(owner))
        {
            throw new ArgumentException("owner must not be empty", nameof(owner));
        }
        ArgumentOutOfRangeException.ThrowIfNegative(overdraftLimit);
        var account = new Account($"ACC-{_next++:D4}", owner.Trim(), overdraftLimit);
        _accounts.Add(account.Id, account);
        return account;
    }

    public Account Get(string id) =>
        _accounts.TryGetValue(id, out var account) ? account : throw new BankException($"unknown account {id}");

    public IReadOnlyList<Transaction> History(string id) => Get(id).History;

    public IEnumerable<Account> Accounts => _accounts.Values.OrderBy(a => a.Id, StringComparer.Ordinal);

    public void Deposit(string id, decimal amount, DateOnly day)
    {
        RequirePositive(amount);
        Open(id, out var account);
        account.Post(day, TransactionKind.Deposit, amount, "Deposit");
    }

    public void Withdraw(string id, decimal amount, DateOnly day)
    {
        RequirePositive(amount);
        Open(id, out var account);
        RequireFunds(account, amount);
        account.Post(day, TransactionKind.Withdrawal, -amount, "Withdrawal");
    }

    public void Transfer(string fromId, string toId, decimal amount, DateOnly day)
    {
        RequirePositive(amount);
        if (fromId == toId)
        {
            throw new BankException("cannot transfer to the same account");
        }
        Open(fromId, out var from);
        Open(toId, out var to);
        RequireFunds(from, amount);
        from.Post(day, TransactionKind.TransferOut, -amount, $"Transfer to {to.Id}");
        to.Post(day, TransactionKind.TransferIn, amount, $"Transfer from {from.Id}");
    }

    public void Close(string id)
    {
        Open(id, out var account);
        if (account.Balance != 0m)
        {
            throw new BankException($"account {id} has a non-zero balance");
        }
        account.IsClosed = true;
    }

    /// <summary>Pays interest to open accounts in credit and charges the fee to those in overdraft; returns the interest paid.</summary>
    public decimal ApplyMonthlyInterest(DateOnly day, decimal annualRatePercent)
    {
        decimal paid = 0m;
        foreach (var account in Accounts.Where(a => !a.IsClosed))
        {
            if (account.Balance < 0)
            {
                account.Post(day, TransactionKind.Fee, -InterestPolicy.OverdraftFee, "Overdraft fee");
                continue;
            }
            var interest = InterestPolicy.MonthlyInterest(account.Balance, annualRatePercent);
            if (interest > 0)
            {
                account.Post(day, TransactionKind.Interest, interest, "Interest");
                paid += interest;
            }
        }
        return paid;
    }

    private void Open(string id, out Account account)
    {
        account = Get(id);
        if (account.IsClosed)
        {
            throw new BankException($"account {id} is closed");
        }
    }

    private static void RequirePositive(decimal amount) =>
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(amount);

    private static void RequireFunds(Account account, decimal amount)
    {
        if (!account.CanWithdraw(amount))
        {
            throw new BankException($"insufficient funds in {account.Id}");
        }
    }
}
