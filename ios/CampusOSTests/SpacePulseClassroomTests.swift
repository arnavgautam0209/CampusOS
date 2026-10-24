import Foundation
import Testing
@testable import CampusOS

// Captured from the backend during a rehearsal of the demo (seed_spacepulse_demo, Monday 11:00, group of 8).
private let searchJSON = #"""
{"date": "2026-10-26", "start": "2026-10-26T11:00:00+05:30", "end": "2026-10-26T12:00:00+05:30", "groupSize": 8, "mode": "shared", "timetable": {"id": 1, "version": 1, "name": "Timetable A — Regular Semester Schedule"}, "recommended": {"id": "ECE-101", "name": "Electronics Classroom 101", "kind": "classroom", "location": "ECE Block · Floor 1", "capacity": 30, "availableSeats": 30, "bookedSeats": 0, "seatsAfterBooking": 22, "reason": null}, "rooms": [{"id": "ECE-101", "name": "Electronics Classroom 101", "kind": "classroom", "location": "ECE Block · Floor 1", "capacity": 30, "availableSeats": 30, "bookedSeats": 0, "seatsAfterBooking": 22, "reason": null}, {"id": "ECE-102", "name": "Electronics Classroom 102", "kind": "classroom", "location": "ECE Block · Floor 1", "capacity": 45, "availableSeats": 45, "bookedSeats": 0, "seatsAfterBooking": 37, "reason": null}, {"id": "CSE-301", "name": "Computer Science Room 301", "kind": "classroom", "location": "CSE Block · Floor 3", "capacity": 75, "availableSeats": 75, "bookedSeats": 0, "seatsAfterBooking": 67, "reason": null}, {"id": "SEM-01", "name": "Seminar Room 01", "kind": "classroom", "location": "Admin Block · Ground floor", "capacity": 100, "availableSeats": 100, "bookedSeats": 0, "seatsAfterBooking": 92, "reason": null}, {"id": "HALL-01", "name": "Conference Hall 01", "kind": "classroom", "location": "Admin Block · Ground floor", "capacity": 150, "availableSeats": 150, "bookedSeats": 0, "seatsAfterBooking": 142, "reason": null}], "unavailable": [{"id": "IT-201", "name": "Information Technology Room 201", "kind": "classroom", "location": "IT Block · Floor 2", "capacity": 60, "availableSeats": 0, "bookedSeats": 0, "seatsAfterBooking": 0, "reason": "Timetabled: Python Programming 11:00–12:00"}], "message": "Best fit for 8 people — 22 seats would remain available."}
"""#

private let bookingJSON = #"""
{"id": "f8981ba9-ee49-4b6c-9c31-a7366f762d55", "roomId": "ECE-101", "roomName": "Electronics Classroom 101", "roomCapacity": 30, "start": "2026-10-26T11:00:00+05:30", "end": "2026-10-26T12:00:00+05:30", "purpose": "Robotics team", "attendees": 8, "mode": "shared", "status": "active", "note": "", "checkedInAt": null, "bookedBy": "Demo Student", "username": "demo_student"}
"""#

private let uploadJSON = #"""
{"id": 2, "version": 2, "name": "Timetable B Updated", "status": "draft", "sourceFilename": "Timetable_B_Updated.csv", "uploadedBy": "Demo Faculty", "createdAt": "2026-10-24T06:17:25.993856+00:00", "activatedAt": null, "classCount": 19, "entries": [{"weekday": 0, "day": "Monday", "start": "09:00", "end": "10:00", "roomId": "ECE-101", "activity": "Digital Electronics"}, {"weekday": 0, "day": "Monday", "start": "11:00", "end": "12:00", "roomId": "CSE-301", "activity": "AI Workshop"}], "preview": {"againstVersion": 1, "againstName": "Timetable A — Regular Semester Schedule", "changes": [{"day": "Monday", "weekday": 0, "start": "11:00", "end": "12:00", "roomId": "CSE-301", "change": "occupied", "before": null, "after": "AI Workshop"}, {"day": "Monday", "weekday": 0, "start": "11:00", "end": "12:00", "roomId": "ECE-101", "change": "occupied", "before": null, "after": "Microcontrollers"}, {"day": "Monday", "weekday": 0, "start": "15:00", "end": "16:00", "roomId": "ECE-102", "change": "freed", "before": "Signals and Systems", "after": null}, {"day": "Friday", "weekday": 4, "start": "11:00", "end": "12:00", "roomId": "IT-201", "change": "activity_changed", "before": "Machine Learning", "after": "Deep Learning"}]}, "conflicts": [{"bookingId": "f8981ba9-ee49-4b6c-9c31-a7366f762d55", "roomId": "ECE-101", "roomName": "Electronics Classroom 101", "start": "2026-10-26T05:30:00+00:00", "end": "2026-10-26T06:30:00+00:00", "attendees": 8, "mode": "shared", "bookedBy": "Demo Student", "username": "demo_student", "clashesWith": "Microcontrollers", "classStart": "2026-10-26T11:00:00+05:30", "classEnd": "2026-10-26T12:00:00+05:30", "suggestedRoomId": "ECE-102", "suggestedRoomName": "Electronics Classroom 102"}]}
"""#

private let uploadErrorJSON = #"""
{"detail": "The timetable has problems; nothing was saved.", "errors": [{"row": 2, "message": "Unknown day \"Funday\" (use Monday … Sunday)"}, {"row": 3, "message": "End must be after start; Unknown room \"LAB-9\""}]}
"""#

private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
    try JSONDecoder.campusOS.decode(T.self, from: Data(json.utf8))
}

final class FakeSpacePulseService: SpacePulseService {
    var searches: [Result<RoomSearchResult, Error>] = []
    var bookResult: Result<RoomBooking, Error> = .failure(APIError.badResponse)
    var uploadResult: Result<Timetable, Error> = .failure(APIError.badResponse)
    var conflictResponses: [[TimetableConflict]] = []
    var activateError: Error?
    private(set) var searchCalls: [RoomSearch] = []
    private(set) var bookCalls: [(roomId: String, start: Date, minutes: Int, group: Int, mode: BookingMode)] = []
    private(set) var resolved: [(bookingId: UUID, action: ConflictAction)] = []
    private(set) var activated: [Int] = []

    func findRooms(_ search: RoomSearch) async throws -> RoomSearchResult {
        searchCalls.append(search)
        return try (searches.count > 1 ? searches.removeFirst() : searches[0]).get()
    }

    func book(roomId: String, start: Date, minutes: Int, groupSize: Int, mode: BookingMode,
              purpose: String) async throws -> RoomBooking {
        bookCalls.append((roomId, start, minutes, groupSize, mode))
        return try bookResult.get()
    }

    func fetchActiveTimetable() async throws -> Timetable? { nil }
    func fetchTimetables() async throws -> [Timetable] { [] }
    func fetchTimetable(id: Int) async throws -> Timetable { try uploadResult.get() }
    func uploadTimetable(name: String, filename: String, csv: String) async throws -> Timetable { try uploadResult.get() }
    func fetchPreview(id: Int) async throws -> TimetablePreview { try uploadResult.get().preview! }

    func fetchConflicts(id: Int) async throws -> [TimetableConflict] {
        conflictResponses.count > 1 ? conflictResponses.removeFirst() : (conflictResponses.first ?? [])
    }

    func resolve(timetableId: Int, bookingId: UUID, action: ConflictAction, roomId: String?) async throws -> RoomBooking {
        resolved.append((bookingId, action))
        return try decode(RoomBooking.self, bookingJSON)
    }

    func activate(id: Int) async throws -> Timetable {
        activated.append(id)
        if let activateError { throw activateError }
        return try uploadResult.get()
    }

    func fetchHistory() async throws -> [TimetableEvent] { [] }
    func fetchAllBookings() async throws -> [RoomBooking] { [] }
}

@Suite("SpacePulse classrooms: decoding")
struct SpacePulseDecodingTests {
    @Test func decodesServerRecommendation() throws {
        let result = try decode(RoomSearchResult.self, searchJSON)
        #expect(result.recommended?.id == "ECE-101")
        #expect(result.message == "Best fit for 8 people — 22 seats would remain available.")
        #expect(result.rooms.map(\.seatsAfterBooking) == [22, 37, 67, 92, 142])
        #expect(result.alternatives.map(\.id) == ["ECE-102", "CSE-301", "SEM-01", "HALL-01"])
        #expect(result.unavailable.first?.reason == "Timetabled: Python Programming 11:00–12:00")
        #expect(result.timetable?.version == 1)
        // Capacity and seats free at that time are separate numbers.
        let best = try #require(result.recommended)
        #expect((best.capacity, best.availableSeats) == (30, 30))
    }

    @Test func decodesSharedBookingAndHidesEmptyNote() throws {
        let booking = try decode(RoomBooking.self, bookingJSON)
        #expect(booking.mode == .shared)
        #expect(booking.roomCapacity == 30)
        #expect(booking.note == nil)
        let moved = bookingJSON.replacingOccurrences(of: #""note": """#, with: #""note": "Moved from ECE-101 to ECE-102""#)
        #expect(try decode(RoomBooking.self, moved).note == "Moved from ECE-101 to ECE-102")
    }

    @Test func olderBookingJSONDefaultsToExclusive() throws {
        let older = bookingJSON
            .replacingOccurrences(of: #""mode": "shared", "#, with: "")
            .replacingOccurrences(of: #""roomCapacity": 30, "#, with: "")
            .replacingOccurrences(of: #""note": "", "#, with: "")
        let booking = try decode(RoomBooking.self, older)
        #expect(booking.mode == .exclusive)
        #expect(booking.roomCapacity == nil)
    }

    @Test func decodesUploadWithPreviewAndConflicts() throws {
        let timetable = try decode(Timetable.self, uploadJSON)
        #expect((timetable.version, timetable.status, timetable.classCount) == (2, .draft, 19))
        #expect(timetable.preview?.changes.map(\.change) == [.occupied, .occupied, .freed, .activityChanged])
        let conflict = try #require(timetable.conflicts?.first)
        #expect((conflict.roomId, conflict.clashesWith, conflict.suggestedRoomId) == ("ECE-101", "Microcontrollers", "ECE-102"))
    }

    @Test func uploadErrorsListEveryLine() {
        let message = APIError.serverMessage(from: Data(uploadErrorJSON.utf8))
        #expect(message == """
        The timetable has problems; nothing was saved.
        Line 2: Unknown day "Funday" (use Monday … Sunday)
        Line 3: End must be after start; Unknown room "LAB-9"
        """)
        #expect(APIError.from(status: 400, data: Data(uploadErrorJSON.utf8)).errorDescription?.contains("Line 3") == true)
    }

    @Test func roomsDecodeLecturesAndFreeStartsSkipThem() throws {
        let day = try spacesFixture()
        #expect(day.rooms.allSatisfy { $0.lectures.isEmpty })   // older servers: no lectures key
        let start = Date(timeIntervalSince1970: 1_800_000_000)
        let room = CampusRoom(id: "IT-201", name: "IT 201", kind: .classroom, capacity: 60, location: "", features: [],
                              isBookable: true, inClassNow: false, freeNow: true, busy: [],
                              lectures: [.init(start: start.addingTimeInterval(3600), end: start.addingTimeInterval(7200),
                                               activity: "Python Programming")])
        let starts = room.freeStarts(dayStart: start, dayEnd: start.addingTimeInterval(4 * 3600), minutes: 60,
                                     now: start.addingTimeInterval(-60))
        #expect(starts.map { $0.timeIntervalSince(start) / 60 } == [0, 120, 150, 180])
    }

    @Test func searchSendsLocalDateAndTime() {
        var calendar = Calendar.current
        calendar.timeZone = .current
        let day = calendar.date(from: DateComponents(year: 2026, month: 10, day: 26))!
        let time = calendar.date(from: DateComponents(year: 2000, month: 1, day: 1, hour: 11, minute: 5))!
        let search = RoomSearch(groupSize: 8, mode: .shared, day: day, startTime: time, minutes: 60)
        #expect(search.queryItems.map { "\($0.name)=\($0.value ?? "")" }
                == ["date=2026-10-26", "start=11:05", "duration=60", "group_size=8", "mode=shared"])
        #expect(calendar.dateComponents([.day, .hour, .minute], from: search.start) == DateComponents(day: 26, hour: 11, minute: 5))
    }

    @Test func readsTheCSVFileAsText() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("Timetable_B_Updated.csv")
        let csv = "day,start,end,room_id,activity\nMonday,11:00,12:00,ECE-101,Microcontrollers\n"
        try Data(csv.utf8).write(to: url)
        defer { try? FileManager.default.removeItem(at: url) }
        #expect(try ManageTimetablesView.readText(at: url) == csv)
    }
}

@MainActor
@Suite("SpacePulse classrooms: stores")
struct SpacePulseStoreTests {
    private let service = FakeSpacePulseService()

    @Test func findShowsTheServerRecommendation() async throws {
        service.searches = [.success(try decode(RoomSearchResult.self, searchJSON))]
        let store = RoomFinderStore(service: service)
        store.search.groupSize = 8
        await store.find()
        #expect(store.searchState == .loaded)
        #expect(store.result?.recommended?.id == "ECE-101")
        #expect(service.searchCalls.first?.groupSize == 8)
    }

    @Test func bookingSendsTheSearchAndRefreshesSeats() async throws {
        let before = try decode(RoomSearchResult.self, searchJSON)
        let after = try decode(RoomSearchResult.self, searchJSON.replacingOccurrences(
            of: #""availableSeats": 30, "bookedSeats": 0, "seatsAfterBooking": 22"#,
            with: #""availableSeats": 22, "bookedSeats": 8, "seatsAfterBooking": 14"#))
        service.searches = [.success(before), .success(after)]
        service.bookResult = .success(try decode(RoomBooking.self, bookingJSON))
        let store = RoomFinderStore(service: service)
        await store.find()
        let booking = try await store.book(try #require(store.result?.recommended))

        #expect(booking.mode == .shared)
        let call = try #require(service.bookCalls.first)
        #expect((call.roomId, call.group, call.mode, call.minutes) == ("ECE-101", store.search.groupSize, .shared, 60))
        #expect(call.start == store.search.start)
        #expect(store.result?.recommended?.availableSeats == 22)   // re-fetched from the server
        #expect(store.bookingRoomID == nil)
    }

    @Test func rejectedBookingIsSurfaced() async throws {
        service.searches = [.success(try decode(RoomSearchResult.self, searchJSON))]
        service.bookResult = .failure(APIError.conflict("Only 5 of 30 seats in Electronics Classroom 101 are free."))
        let store = RoomFinderStore(service: service)
        await store.find()
        await #expect(throws: APIError.conflict("Only 5 of 30 seats in Electronics Classroom 101 are free.")) {
            try await store.book(try #require(store.result?.recommended))
        }
    }

    @Test func failedSearchShowsTheMessage() async {
        service.searches = [.failure(APIError.invalid("Choose a future start time."))]
        let store = RoomFinderStore(service: service)
        await store.find()
        #expect(store.result == nil)
        #expect(store.searchState.errorMessage == "Choose a future start time.")
    }

    @Test func uploadShowsPreviewAndBlocksActivationWhileConflicts() async throws {
        service.uploadResult = .success(try decode(Timetable.self, uploadJSON))
        let store = TimetableStore(service: service)
        let uploaded = try await store.upload(filename: "Timetable_B_Updated.csv", csv: "…")
        #expect(uploaded.version == 2)
        #expect(store.preview?.changes.count == 4)
        #expect(store.conflicts.count == 1)
        #expect(!store.canActivate)
    }

    @Test func resolvingTheConflictAllowsActivation() async throws {
        let timetable = try decode(Timetable.self, uploadJSON)
        service.uploadResult = .success(timetable)
        service.conflictResponses = [[]]   // after the move, nothing clashes
        let store = TimetableStore(service: service)
        _ = try await store.upload(filename: "Timetable_B_Updated.csv", csv: "…")
        try await store.resolve(try #require(store.conflicts.first), action: .reassign)
        #expect(service.resolved.map(\.action) == [.reassign])
        #expect(store.conflicts.isEmpty)
        #expect(store.canActivate)
        try await store.activate()
        #expect(service.activated == [2])
    }

    @Test func refusedActivationReloadsConflicts() async throws {
        let timetable = try decode(Timetable.self, uploadJSON)
        service.uploadResult = .success(timetable)
        service.conflictResponses = [timetable.conflicts ?? []]
        service.activateError = APIError.conflict("1 upcoming booking(s) clash with this timetable.")
        let store = TimetableStore(service: service)
        _ = try await store.upload(filename: "x.csv", csv: "…")
        await #expect(throws: APIError.conflict("1 upcoming booking(s) clash with this timetable.")) {
            try await store.activate()
        }
        #expect(store.conflicts.count == 1)
    }
}
