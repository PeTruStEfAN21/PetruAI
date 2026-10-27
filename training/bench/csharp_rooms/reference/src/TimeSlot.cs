namespace Rooms;

/// <summary>A half-open interval [Start, End): a slot ending at 10:00 does not overlap one starting at 10:00.</summary>
public sealed record TimeSlot
{
    public TimeSlot(DateTime start, DateTime end)
    {
        if (end <= start)
        {
            throw new ArgumentException("a slot must end after it starts");
        }
        Start = start;
        End = end;
    }

    public DateTime Start { get; }
    public DateTime End { get; }
    public TimeSpan Duration => End - Start;

    public bool Overlaps(TimeSlot other) => Start < other.End && other.Start < End;

    public TimeSlot ShiftedBy(TimeSpan offset) => new(Start + offset, End + offset);
}
