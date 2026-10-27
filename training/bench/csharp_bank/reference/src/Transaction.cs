namespace Bank;

public enum TransactionKind
{
    Deposit,
    Withdrawal,
    TransferIn,
    TransferOut,
    Interest,
    Fee,
}

/// <summary>One movement on an account; Amount is signed, BalanceAfter is the balance once it applied.</summary>
public sealed record Transaction(
    DateOnly Day,
    TransactionKind Kind,
    decimal Amount,
    decimal BalanceAfter,
    string Description);
