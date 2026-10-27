namespace Bank;

public sealed class Account
{
    private readonly List<Transaction> _history = new();

    internal Account(string id, string owner, decimal overdraftLimit)
    {
        Id = id;
        Owner = owner;
        OverdraftLimit = overdraftLimit;
    }

    public string Id { get; }
    public string Owner { get; }
    public decimal OverdraftLimit { get; }
    public decimal Balance { get; private set; }
    public bool IsClosed { get; internal set; }

    public IReadOnlyList<Transaction> History => _history;

    internal bool CanWithdraw(decimal amount) => Balance - amount >= -OverdraftLimit;

    internal void Post(DateOnly day, TransactionKind kind, decimal signedAmount, string description)
    {
        Balance += signedAmount;
        _history.Add(new Transaction(day, kind, signedAmount, Balance, description));
    }
}
