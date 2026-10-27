using System.Globalization;

namespace Rooms;

/// <summary>One line per room, sorted by name: its reservations for the day, or "free".</summary>
public static class Agenda
{
    public static string Render(Scheduler scheduler, DateOnly day)
    {
        var lines = new List<string> { $"Agenda for {day.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)}" };
        foreach (var room in scheduler.Rooms)
        {
            var items = scheduler.ReservationsFor(room.Name, day)
                .Select(r => $"{Time(r.Slot.Start)}-{Time(r.Slot.End)} {r.Organizer} ({r.Attendees})")
                .ToList();
            lines.Add($"{room.Name}: {(items.Count == 0 ? "free" : string.Join(", ", items))}");
        }
        return string.Join("\n", lines);
    }

    private static string Time(DateTime t) => t.ToString("HH:mm", CultureInfo.InvariantCulture);
}
