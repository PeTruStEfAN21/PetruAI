namespace Rooms;

/// <summary>Rooms can be booked from 08:00 to 20:00, within a single day.</summary>
public static class OpeningHours
{
    public static readonly TimeOnly Opens = new(8, 0);
    public static readonly TimeOnly Closes = new(20, 0);

    public static TimeSlot Of(DateOnly day) => new(day.ToDateTime(Opens), day.ToDateTime(Closes));

    public static bool Contains(TimeSlot slot)
    {
        var day = DateOnly.FromDateTime(slot.Start);
        var open = Of(day);
        return slot.Start >= open.Start && slot.End <= open.End;
    }
}
