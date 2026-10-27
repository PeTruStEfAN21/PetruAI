using Rooms;
using Xunit;

namespace Rooms.Tests;

public class SchedulerTests
{
    static readonly DateOnly Monday = new(2026, 11, 2);

    static TimeSlot At(DateOnly day, int startHour, int startMinute, int endHour, int endMinute) =>
        new(day.ToDateTime(new TimeOnly(startHour, startMinute)), day.ToDateTime(new TimeOnly(endHour, endMinute)));

    static Scheduler WithRooms()
    {
        var s = new Scheduler();
        s.AddRoom("Atlas", capacity: 8);
        s.AddRoom("Bolt", capacity: 4);
        s.AddRoom("Comet", capacity: 12);
        return s;
    }

    [Fact]
    public void TimeSlotsValidateAndOverlapHalfOpen()
    {
        Assert.Throws<ArgumentException>(() => At(Monday, 10, 0, 10, 0));
        var a = At(Monday, 9, 0, 10, 0);
        Assert.True(a.Overlaps(At(Monday, 9, 30, 11, 0)));
        Assert.False(a.Overlaps(At(Monday, 10, 0, 11, 0)));
        Assert.Equal(TimeSpan.FromHours(1), a.Duration);
    }

    [Fact]
    public void RoomsAreValidated()
    {
        var s = WithRooms();
        Assert.Throws<ArgumentException>(() => s.AddRoom("Atlas", 3));
        Assert.Throws<ArgumentOutOfRangeException>(() => s.AddRoom("Dot", 0));
        var ex = Assert.Throws<BookingException>(() => s.Book("Zed", "ana", At(Monday, 9, 0, 10, 0), 1));
        Assert.Equal("unknown room Zed", ex.Message);
    }

    [Fact]
    public void BookingAndConflicts()
    {
        var s = WithRooms();
        var r1 = s.Book("Atlas", "ana", At(Monday, 10, 0, 11, 0), 6);
        Assert.Equal("R1", r1.Id);
        Assert.Equal("Atlas", r1.Room);
        Assert.Null(r1.SeriesId);
        var ex = Assert.Throws<BookingException>(() => s.Book("Atlas", "bob", At(Monday, 10, 30, 12, 0), 2));
        Assert.Equal("room Atlas is taken from 10:00 to 11:00 by R1", ex.Message);
        Assert.Equal("R2", s.Book("Atlas", "bob", At(Monday, 11, 0, 12, 0), 2).Id);
        Assert.Equal("R3", s.Book("Bolt", "bob", At(Monday, 10, 30, 12, 0), 2).Id);
    }

    [Fact]
    public void CapacityAndOpeningHours()
    {
        var s = WithRooms();
        var big = Assert.Throws<BookingException>(() => s.Book("Bolt", "ana", At(Monday, 9, 0, 10, 0), 5));
        Assert.Equal("room Bolt holds 4 people, 5 requested", big.Message);
        Assert.Throws<ArgumentOutOfRangeException>(() => s.Book("Bolt", "ana", At(Monday, 9, 0, 10, 0), 0));
        var early = Assert.Throws<BookingException>(() => s.Book("Bolt", "ana", At(Monday, 7, 30, 9, 0), 2));
        Assert.Equal("bookings must be between 08:00 and 20:00 on one day", early.Message);
        Assert.Throws<BookingException>(() => s.Book("Bolt", "ana", At(Monday, 19, 0, 20, 30), 2));
        var overnight = new TimeSlot(Monday.ToDateTime(new TimeOnly(19, 0)), Monday.AddDays(1).ToDateTime(new TimeOnly(9, 0)));
        Assert.Throws<BookingException>(() => s.Book("Bolt", "ana", overnight, 2));
        s.Book("Bolt", "ana", At(Monday, 8, 0, 20, 0), 2);
    }

    [Fact]
    public void WeeklySeriesAreAllOrNothing()
    {
        var s = WithRooms();
        var series = s.BookWeekly("Atlas", "ana", At(Monday, 9, 0, 10, 0), weeks: 3, attendees: 5);
        Assert.Equal(new[] { "R1", "R2", "R3" }, series.Select(r => r.Id));
        Assert.All(series, r => Assert.Equal("S1", r.SeriesId));
        Assert.Equal(Monday.AddDays(14).ToDateTime(new TimeOnly(9, 0)), series[2].Slot.Start);

        s.Book("Bolt", "bob", At(Monday.AddDays(14), 9, 30, 10, 30), 2);
        var ex = Assert.Throws<BookingException>(() =>
            s.BookWeekly("Bolt", "bob", At(Monday, 9, 0, 10, 0), weeks: 3, attendees: 2));
        Assert.Equal("room Bolt is taken from 09:30 to 10:30 by R4", ex.Message);
        Assert.Single(s.ReservationsFor("Bolt", Monday.AddDays(14)));
        Assert.Empty(s.ReservationsFor("Bolt", Monday));
        Assert.Equal("R5", s.Book("Bolt", "bob", At(Monday, 9, 0, 10, 0), 2).Id);
        Assert.Throws<ArgumentOutOfRangeException>(() => s.BookWeekly("Bolt", "x", At(Monday, 12, 0, 13, 0), 0, 1));
    }

    [Fact]
    public void Cancelling()
    {
        var s = WithRooms();
        var one = s.Book("Atlas", "ana", At(Monday, 9, 0, 10, 0), 2);
        s.BookWeekly("Comet", "bob", At(Monday, 9, 0, 10, 0), 2, 10);
        s.Cancel(one.Id);
        Assert.Empty(s.ReservationsFor("Atlas", Monday));
        var ex = Assert.Throws<BookingException>(() => s.Cancel(one.Id));
        Assert.Equal("unknown reservation R1", ex.Message);
        Assert.Equal(2, s.CancelSeries("S1"));
        Assert.Empty(s.ReservationsFor("Comet", Monday.AddDays(7)));
        Assert.Throws<BookingException>(() => s.CancelSeries("S1"));
    }

    [Fact]
    public void ReservationsForADayAreSortedByStart()
    {
        var s = WithRooms();
        s.Book("Atlas", "c", At(Monday, 15, 0, 16, 0), 1);
        s.Book("Atlas", "a", At(Monday, 9, 0, 10, 0), 1);
        s.Book("Atlas", "x", At(Monday.AddDays(1), 9, 0, 10, 0), 1);
        Assert.Equal(new[] { "a", "c" }, s.ReservationsFor("Atlas", Monday).Select(r => r.Organizer));
    }

    [Fact]
    public void FreeSlotsAreTheGapsInOpeningHours()
    {
        var s = WithRooms();
        s.Book("Atlas", "a", At(Monday, 9, 0, 10, 0), 1);
        s.Book("Atlas", "b", At(Monday, 10, 15, 12, 0), 1);
        s.Book("Atlas", "c", At(Monday, 18, 0, 20, 0), 1);
        var free = s.FreeSlots("Atlas", Monday, TimeSpan.FromMinutes(30));
        Assert.Equal(new[] { At(Monday, 8, 0, 9, 0), At(Monday, 12, 0, 18, 0) }, free);
        Assert.Equal(new[] { At(Monday, 8, 0, 20, 0) }, s.FreeSlots("Bolt", Monday, TimeSpan.FromHours(12)));
        Assert.Empty(s.FreeSlots("Bolt", Monday, TimeSpan.FromHours(13)));
    }

    [Fact]
    public void FindRoomPicksTheSmallestFreeRoomThatFits()
    {
        var s = WithRooms();
        var slot = At(Monday, 14, 0, 15, 0);
        Assert.Equal("Bolt", s.FindRoom(slot, 3));
        Assert.Equal("Atlas", s.FindRoom(slot, 5));
        s.Book("Atlas", "a", At(Monday, 14, 30, 15, 30), 1);
        Assert.Equal("Comet", s.FindRoom(slot, 5));
        Assert.Null(s.FindRoom(slot, 13));
    }
}
