import Foundation
import Testing
@testable import CampusOS

/// Real responses from GET /api/v1/spaces/?date= and POST /api/v1/spaces/bookings/
/// (Study Room A1 booked 10:00-11:30 the next day).
let spacesFixtureJSON = #"""
{
 "date": "2026-10-25",
 "dayStart": "2026-10-25T08:00:00+05:30",
 "dayEnd": "2026-10-25T20:00:00+05:30",
 "rooms": [
  {
   "id": "ROOM-101",
   "name": "Lecture Room 101, Block A",
   "kind": "classroom",
   "capacity": 60,
   "location": "Block A · 101",
   "features": [
    "Projector",
    "Microphone"
   ],
   "isBookable": false,
   "inClassNow": false,
   "freeNow": false,
   "busy": []
  },
  {
   "id": "MEET-B2",
   "name": "Meeting Room B2",
   "kind": "meeting_room",
   "capacity": 10,
   "location": "Block B · 204",
   "features": [
    "Projector",
    "Video call"
   ],
   "isBookable": true,
   "inClassNow": false,
   "freeNow": false,
   "busy": []
  },
  {
   "id": "STUDY-A1",
   "name": "Study Room A1",
   "kind": "study_room",
   "capacity": 6,
   "location": "Library · Level 1",
   "features": [
    "Whiteboard",
    "TV screen"
   ],
   "isBookable": true,
   "inClassNow": false,
   "freeNow": false,
   "busy": [
    {
     "start": "2026-10-25T04:30:00+00:00",
     "end": "2026-10-25T06:00:00+00:00",
     "mine": true,
     "bookedBy": null,
     "checkedIn": false
    }
   ]
  }
 ]
}
"""#

let roomBookingFixtureJSON = #"""
{
 "id": "95bd91c9-c1c6-4bb6-91ff-3e938a379e90",
 "roomId": "STUDY-A1",
 "roomName": "Study Room A1",
 "start": "2026-10-25T10:00:00+05:30",
 "end": "2026-10-25T11:30:00+05:30",
 "purpose": "Robot planning",
 "attendees": 3,
 "status": "active",
 "checkedInAt": null,
 "bookedBy": "Fixture Roomer",
 "username": "fixture_roomer"
}
"""#

func spacesFixture() throws -> SpaceAvailability {
    try JSONDecoder.campusOS.decode(SpaceAvailability.self, from: Data(spacesFixtureJSON.utf8))
}

func roomBookingFixture() throws -> RoomBooking {
    try JSONDecoder.campusOS.decode(RoomBooking.self, from: Data(roomBookingFixtureJSON.utf8))
}

final class FakeSpacesService: SpacesService {
    var availability: SpaceAvailability?
    var mine: [RoomBooking] = []
    var usage: [RoomUsage] = []
    var bookResult: Result<RoomBooking, Error> = .failure(APIError.badResponse)
    var updateResult: Result<RoomBooking, Error> = .failure(APIError.badResponse)
    private(set) var requestedDates: [String] = []
    private(set) var usageFetches = 0
    private(set) var booked: [(String, Date, Int, Int, String)] = []
    private(set) var cancelled: [UUID] = []
    private(set) var checkedIn: [UUID] = []

    func fetchAvailability(date: String) async throws -> SpaceAvailability {
        requestedDates.append(date)
        return availability!
    }
    func fetchMyBookings() async throws -> [RoomBooking] { mine }
    func fetchUtilization() async throws -> [RoomUsage] { usageFetches += 1; return usage }

    func book(roomId: String, start: Date, minutes: Int, attendees: Int, purpose: String) async throws -> RoomBooking {
        booked.append((roomId, start, minutes, attendees, purpose))
        return try bookResult.get()
    }

    func cancel(id: UUID) async throws -> RoomBooking { cancelled.append(id); return try updateResult.get() }
    func checkIn(id: UUID) async throws -> RoomBooking { checkedIn.append(id); return try updateResult.get() }
}

private func copy(_ booking: RoomBooking, status: RoomBooking.Status? = nil, checkedInAt: Date? = nil,
                  start: Date? = nil) -> RoomBooking {
    let begin = start ?? booking.start
    return RoomBooking(id: booking.id, roomId: booking.roomId, roomName: booking.roomName, start: begin,
                       end: begin.addingTimeInterval(booking.end.timeIntervalSince(booking.start)),
                       purpose: booking.purpose, attendees: booking.attendees, status: status ?? booking.status,
                       checkedInAt: checkedInAt ?? booking.checkedInAt, bookedBy: booking.bookedBy,
                       username: booking.username)
}

@Suite("SpacePulse models")
struct SpacesModelTests {
    @Test func decodesRealAvailability() throws {
        let availability = try spacesFixture()
        let study = try #require(availability.rooms.first { $0.id == "STUDY-A1" })
        #expect(study.kind == .studyRoom)
        #expect(study.capacity == 6)
        #expect(study.features == ["Whiteboard", "TV screen"])
        #expect(study.isBookable)
        #expect(study.busy.count == 1)
        #expect(study.busy[0].mine)
        #expect(study.busy[0].bookedBy == nil)            // students don't see who booked
        #expect(study.busy[0].end.timeIntervalSince(study.busy[0].start) == 90 * 60)
        let classroom = try #require(availability.rooms.first { $0.id == "ROOM-101" })
        #expect(classroom.kind == .classroom && !classroom.isBookable)
        #expect(availability.dayEnd.timeIntervalSince(availability.dayStart) == 12 * 3600)
    }

    @Test func decodesRealBooking() throws {
        let booking = try roomBookingFixture()
        #expect((booking.roomId, booking.attendees, booking.purpose) == ("STUDY-A1", 3, "Robot planning"))
        #expect(booking.status == .active)
        #expect(booking.checkedInAt == nil)
    }

    @Test func freeStartsSkipBusyAndPastSlots() throws {
        let availability = try spacesFixture()
        let study = try #require(availability.rooms.first { $0.id == "STUDY-A1" })
        let busy = study.busy[0]   // 10:00-11:30
        let starts = study.freeStarts(dayStart: availability.dayStart, dayEnd: availability.dayEnd,
                                      minutes: 60, now: availability.dayStart.addingTimeInterval(-60))

        #expect(starts.first == availability.dayStart)                                  // 08:00
        #expect(!starts.contains { $0 < busy.end && busy.start < $0.addingTimeInterval(3600) })
        #expect(starts.contains(busy.end))                                              // 11:30 back-to-back
        #expect(starts.last == availability.dayEnd.addingTimeInterval(-3600))          // 19:00
        let later = study.freeStarts(dayStart: availability.dayStart, dayEnd: availability.dayEnd,
                                     minutes: 60, now: busy.end)
        #expect(later.allSatisfy { $0 > busy.end })                                     // nothing in the past
    }

    @Test func checkInWindowMatchesServer() throws {
        let booking = try roomBookingFixture()
        #expect(!booking.canCheckIn(now: booking.start.addingTimeInterval(-11 * 60)))
        #expect(booking.canCheckIn(now: booking.start.addingTimeInterval(-10 * 60)))
        #expect(booking.canCheckIn(now: booking.start.addingTimeInterval(15 * 60)))
        #expect(!booking.canCheckIn(now: booking.start.addingTimeInterval(16 * 60)))
        #expect(!copy(booking, checkedInAt: booking.start).canCheckIn(now: booking.start))
        #expect(!copy(booking, status: .cancelled).canCheckIn(now: booking.start))
    }

    @Test func dayStringIsLocalCalendarDate() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "Asia/Kolkata")!
        let date = calendar.date(from: DateComponents(year: 2026, month: 3, day: 7, hour: 23, minute: 30))!
        #expect(SpacesStore.dayString(date, calendar: calendar) == "2026-03-07")
    }
}

@MainActor
@Suite("SpacesStore")
struct SpacesStoreTests {
    private let service = FakeSpacesService()

    init() throws {
        service.availability = try spacesFixture()
    }

    @Test func loadsDayBookingsAndStaffUsage() async throws {
        service.mine = [try roomBookingFixture()]
        let fixedNow = try roomBookingFixture().start.addingTimeInterval(-3600)
        let store = SpacesStore(service: service, now: { fixedNow })
        var calendar = Calendar.current
        calendar.timeZone = .current
        let day = calendar.date(from: DateComponents(year: 2026, month: 10, day: 25))!

        await store.load(day: day, staff: false)
        #expect(service.requestedDates == ["2026-10-25"])
        #expect(store.upcoming.count == 1)
        #expect(service.usageFetches == 0)

        await store.load(day: day, staff: true)
        #expect(service.usageFetches == 1)
    }

    @Test func bookingAddsAndReloadsAvailability() async throws {
        let created = try roomBookingFixture()
        service.bookResult = .success(created)
        let fixedNow = created.start.addingTimeInterval(-3600)
        let store = SpacesStore(service: service, now: { fixedNow })
        await store.load(day: Date(), staff: false)
        let room = try #require(store.availability?.rooms.first { $0.id == "STUDY-A1" })

        try await store.book(room, start: created.start, minutes: 90, attendees: 3, purpose: "  Robot planning ",
                             day: Date())

        #expect(service.booked.first?.0 == "STUDY-A1")
        #expect(service.booked.first?.4 == "Robot planning")
        #expect(store.upcoming.map(\.id) == [created.id])
        #expect(service.requestedDates.count == 2)
    }

    @Test func conflictIsSurfacedAndNothingAdded() async throws {
        service.bookResult = .failure(APIError.conflict("That room is already booked for part of that time."))
        let store = SpacesStore(service: service)
        await store.load(day: Date(), staff: false)
        let room = try #require(store.availability?.rooms.first)

        await #expect(throws: APIError.conflict("That room is already booked for part of that time.")) {
            try await store.book(room, start: Date(), minutes: 60, attendees: 1, purpose: "", day: Date())
        }
        #expect(store.myBookings.isEmpty)
    }

    @Test func checkInAndCancelReplaceBooking() async throws {
        let booking = try roomBookingFixture()
        service.mine = [booking]
        let fixedNow = booking.start
        let store = SpacesStore(service: service, now: { fixedNow })
        await store.load(day: Date(), staff: false)

        service.updateResult = .success(copy(booking, checkedInAt: booking.start))
        try await store.checkIn(booking, day: Date())
        #expect(store.myBookings.first?.checkedInAt == booking.start)
        #expect(service.checkedIn == [booking.id])

        service.updateResult = .success(copy(booking, status: .cancelled))
        try await store.cancel(booking, day: Date())
        #expect(store.upcoming.isEmpty)
        #expect(store.busyBookingID == nil)
    }

    @Test func resetClearsEverything() async throws {
        service.mine = [try roomBookingFixture()]
        let store = SpacesStore(service: service)
        await store.load(day: Date(), staff: false)
        store.reset()
        #expect(store.availability == nil && store.myBookings.isEmpty && store.loadState == .idle)
    }
}
