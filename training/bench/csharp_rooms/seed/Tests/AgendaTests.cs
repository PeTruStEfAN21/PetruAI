using Rooms;
using Xunit;

namespace Rooms.Tests;

public class AgendaTests
{
    [Fact]
    public void RendersEveryRoomForTheDay()
    {
        var day = new DateOnly(2026, 11, 2);
        TimeSlot at(int h1, int m1, int h2, int m2) =>
            new(day.ToDateTime(new TimeOnly(h1, m1)), day.ToDateTime(new TimeOnly(h2, m2)));
        var s = new Scheduler();
        s.AddRoom("Bolt", 4);
        s.AddRoom("Atlas", 8);
        s.AddRoom("Comet", 12);
        s.Book("Atlas", "bob", at(13, 0, 14, 30), 2);
        s.Book("Atlas", "ana", at(9, 0, 10, 0), 4);
        s.Book("Comet", "eve", at(8, 0, 20, 0), 12);
        var tomorrow = day.AddDays(1);
        s.Book("Bolt", "dan", new TimeSlot(tomorrow.ToDateTime(new TimeOnly(9, 0)), tomorrow.ToDateTime(new TimeOnly(10, 0))), 1);

        Assert.Equal(string.Join("\n",
            "Agenda for 2026-11-02",
            "Atlas: 09:00-10:00 ana (4), 13:00-14:30 bob (2)",
            "Bolt: free",
            "Comet: 08:00-20:00 eve (12)"), Agenda.Render(s, day));
    }
}
