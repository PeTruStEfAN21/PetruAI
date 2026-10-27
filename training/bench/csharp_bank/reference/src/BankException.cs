namespace Bank;

/// <summary>An operation the bank refuses: unknown or closed accounts, missing funds.</summary>
public class BankException : Exception
{
    public BankException(string message) : base(message) { }
}
