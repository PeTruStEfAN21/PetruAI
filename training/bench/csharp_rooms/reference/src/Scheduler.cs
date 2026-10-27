namespace Rooms;

public sealed class Scheduler
{
    private readonly Dictionary<string, Room> _rooms = new();
    private readonly List<Reservation> _reservations = new();
    private int _nextReservation = 1;
    private int _nextSeries = 1;

    public IEnumerable<Room> Rooms => _rooms.Values.OrderBy(r => r.Name, StringComparer.Ordinal);

    public Room AddRoom(string name, int capacity)
    {
        if (_rooms.ContainsKey(name))
        {
            throw new ArgumentException($"room {name} already exists", nameof(name));
        }
        ArgumentOutOfRangeException.ThrowIfLessThan(capacity, 1);
        var room = new Room(name, capacity);
        _rooms.Add(name, room);
        return room;
    }

    public Reservation Book(string room, string organizer, TimeSlot slot, int attendees)
    {
        Check(room, slot, attendees, _reservations);
        return Add(room, organizer, slot, attendees, null);
    }

    /// <summary>The same slot every week for `weeks` weeks; nothing is booked if any week fails.</summary>
    public IReadOnlyList<Reservation> BookWeekly(string room, string organizer, TimeSlot first, int weeks, int attendees)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(weeks, 1);
        var slots = Enumerable.Range(0, weeks).Select(w => first.ShiftedBy(TimeSpan.FromDays(7 * w))).ToList();
        foreach (var slot in slots)
        {
            Check(room, slot, attendees, _reservations);
        }
        var seriesId = $"S{_nextSeries++}";
        return slots.Select(slot => Add(room, organizer, slot, attendees, seriesId)).ToList();
    }

    public void Cancel(string reservationId)
    {
        if (_reservations.RemoveAll(r => r.Id == reservationId) == 0)
        {
            throw new BookingException($"unknown reservation {reservationId}");
        }
    }

    public int CancelSeries(string seriesId)
    {
        var removed = _reservations.RemoveAll(r => r.SeriesId == seriesId);
        return removed > 0 ? removed : throw new BookingException($"unknown series {seriesId}");
    }

    public IReadOnlyList<Reservation> ReservationsFor(string room, DateOnly day)
    {
        RoomNamed(room);
        return _reservations
            .Where(r => r.Room == room && DateOnly.FromDateTime(r.Slot.Start) == day)
            .OrderBy(r => r.Slot.Start)
            .ToList();
    }

    public IReadOnlyList<TimeSlot> FreeSlots(string room, DateOnly day, TimeSpan minLength)
    {
        var free = new List<TimeSlot>();
        var cursor = OpeningHours.Of(day).Start;
        var close = OpeningHours.Of(day).End;
        foreach (var r in ReservationsFor(room, day))
        {
            AddGap(free, cursor, r.Slot.Start, minLength);
            cursor = r.Slot.End > cursor ? r.Slot.End : cursor;
        }
        AddGap(free, cursor, close, minLength);
        return free;
    }

    /// <summary>The smallest room (then the first by name) that holds the attendees and is free for the slot.</summary>
    public string? FindRoom(TimeSlot slot, int attendees) =>
        Rooms.Where(room => room.Capacity >= attendees)
            .Where(room => !_reservations.Any(r => r.Room == room.Name && r.Slot.Overlaps(slot)))
            .OrderBy(room => room.Capacity)
            .ThenBy(room => room.Name, StringComparer.Ordinal)
            .Select(room => room.Name)
            .FirstOrDefault();

    private static void AddGap(List<TimeSlot> free, DateTime start, DateTime end, TimeSpan minLength)
    {
        if (end - start >= minLength && end > start)
        {
            free.Add(new TimeSlot(start, end));
        }
    }

    private Room RoomNamed(string name) =>
        _rooms.TryGetValue(name, out var room) ? room : throw new BookingException($"unknown room {name}");

    private void Check(string roomName, TimeSlot slot, int attendees, IEnumerable<Reservation> existing)
    {
        var room = RoomNamed(roomName);
        ArgumentOutOfRangeException.ThrowIfLessThan(attendees, 1);
        if (attendees > room.Capacity)
        {
            throw new BookingException($"room {room.Name} holds {room.Capacity} people, {attendees} requested");
        }
        if (!OpeningHours.Contains(slot))
        {
            throw new BookingException(
                $"bookings must be between {OpeningHours.Opens:HH\\:mm} and {OpeningHours.Closes:HH\\:mm} on one day");
        }
        var clash = existing.Where(r => r.Room == roomName && r.Slot.Overlaps(slot)).OrderBy(r => r.Slot.Start).FirstOrDefault();
        if (clash is not null)
        {
            throw new BookingException(
                $"room {roomName} is taken from {clash.Slot.Start:HH\\:mm} to {clash.Slot.End:HH\\:mm} by {clash.Id}");
        }
    }

    private Reservation Add(string room, string organizer, TimeSlot slot, int attendees, string? seriesId)
    {
        var reservation = new Reservation($"R{_nextReservation++}", room, organizer, slot, attendees, seriesId);
        _reservations.Add(reservation);
        return reservation;
    }
}
