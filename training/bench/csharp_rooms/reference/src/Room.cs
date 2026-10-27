namespace Rooms;

public sealed record Room(string Name, int Capacity);

public sealed record Reservation(string Id, string Room, string Organizer, TimeSlot Slot, int Attendees, string? SeriesId);

public class BookingException : Exception
{
    public BookingException(string message) : base(message) { }
}
