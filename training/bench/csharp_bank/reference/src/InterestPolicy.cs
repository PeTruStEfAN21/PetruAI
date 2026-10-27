namespace Bank;

/// <summary>Monthly interest on positive balances; a flat fee on accounts in overdraft.</summary>
public static class InterestPolicy
{
    public const decimal OverdraftFee = 5m;

    public static decimal MonthlyInterest(decimal balance, decimal annualRatePercent) =>
        balance <= 0
            ? 0m
            : Math.Round(balance * annualRatePercent / 100m / 12m, 2, MidpointRounding.AwayFromZero);
}
