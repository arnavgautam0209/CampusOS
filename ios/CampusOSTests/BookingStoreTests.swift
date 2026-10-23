import Foundation
import Testing
@testable import CampusOS

/// Records calls and returns canned results instead of talking to Django.
final class FakeBookingService: BookingService {
    var storedBookings: [LabBooking] = []
    var fetchError: Error?
    var createError: Error?
    var cancelError: Error?
    private(set) var createCalls: [(labID: String, start: Date, durationMinutes: Int)] = []
    private(set) var cancelledIDs: [UUID] = []

    func fetchBookings() async throws -> [LabBooking] {
        if let fetchError { throw fetchError }
        return storedBookings
    }

    func createBooking(labID: String, start: Date, durationMinutes: Int) async throws -> LabBooking {
        createCalls.append((labID, start, durationMinutes))
        if let createError { throw createError }
        return LabBooking(id: UUID(), labID: labID, labName: "Lab \(labID)", start: start,
                          end: start.addingTimeInterval(TimeInterval(durationMinutes * 60)), status: .active)
    }

    func cancelBooking(id: UUID) async throws -> LabBooking {
        cancelledIDs.append(id)
        if let cancelError { throw cancelError }
        let original = storedBookings.first { $0.id == id }!
        return LabBooking(id: id, labID: original.labID, labName: original.labName,
                          start: original.start, end: original.end, status: .cancelled)
    }
}

@MainActor
@Suite("BookingStore")
struct BookingStoreTests {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)
    private let service = FakeBookingService()

    private let openLab = Lab(id: "LAB-OPEN", name: "Open Lab", location: "Test",
                              symbol: "cpu", capacity: 10, equipment: [], isOpenForBooking: true)
    private let closedLab = Lab(id: "LAB-CLOSED", name: "Closed Lab", location: "Test",
                                symbol: "printer", capacity: 10, equipment: [], isOpenForBooking: false)

    private func makeStore() -> BookingStore {
        let fixedNow = now
        return BookingStore(service: service, now: { fixedNow })
    }

    private func hoursFromNow(_ hours: Double) -> Date {
        now.addingTimeInterval(hours * 3600)
    }

    private func booking(hours: Double, status: LabBooking.Status = .active) -> LabBooking {
        LabBooking(id: UUID(), labID: openLab.id, labName: openLab.name,
                   start: hoursFromNow(hours), end: hoursFromNow(hours + 1), status: status)
    }

    // Loading

    @Test func loadFetchesBookingsFromService() async {
        service.storedBookings = [booking(hours: 2)]
        let store = makeStore()

        await store.load()

        #expect(store.bookings == service.storedBookings)
        #expect(store.loadState == .loaded)
    }

    @Test func loadFailureIsReportedWithMessage() async {
        service.fetchError = APIError.unreachable
        let store = makeStore()

        await store.load()

        #expect(store.loadState == .failed(APIError.unreachable.localizedDescription))
        #expect(store.bookings.isEmpty)
    }

    @Test func upcomingHidesCancelledAndFinishedAndSortsByStart() async {
        let later = booking(hours: 5)
        let sooner = booking(hours: 1)
        service.storedBookings = [later, booking(hours: 3, status: .cancelled), booking(hours: -3), sooner]
        let store = makeStore()

        await store.load()

        #expect(store.upcoming.map(\.id) == [sooner.id, later.id])
    }

    @Test func resetClearsEverything() async {
        service.storedBookings = [booking(hours: 2)]
        let store = makeStore()
        await store.load()

        store.reset()

        #expect(store.bookings.isEmpty)
        #expect(store.loadState == .idle)
    }

    // Reserving

    @Test func reserveSendsRequestAndAddsServerBooking() async throws {
        let store = makeStore()
        let start = hoursFromNow(2)

        try await store.reserve(lab: openLab, start: start, durationMinutes: 120)

        #expect(service.createCalls.count == 1)
        #expect(service.createCalls.first?.labID == openLab.id)
        #expect(service.createCalls.first?.start == start)
        #expect(service.createCalls.first?.durationMinutes == 120)
        #expect(store.upcoming.count == 1)
        #expect(store.upcoming.first?.end == start.addingTimeInterval(120 * 60))
    }

    @Test func serverConflictIsSurfacedAndNothingIsAdded() async {
        service.createError = APIError.conflict("This lab already has an overlapping reservation.")
        let store = makeStore()

        await #expect(throws: APIError.conflict("This lab already has an overlapping reservation.")) {
            try await store.reserve(lab: openLab, start: hoursFromNow(2))
        }
        #expect(store.bookings.isEmpty)
    }

    @Test func closedLabIsRejectedWithoutCallingServer() async {
        let store = makeStore()
        await #expect(throws: BookingFailure.closed) {
            try await store.reserve(lab: closedLab, start: hoursFromNow(1))
        }
        #expect(service.createCalls.isEmpty)
    }

    @Test(arguments: [0, -30])
    func nonPositiveDurationIsRejectedWithoutCallingServer(minutes: Int) async {
        let store = makeStore()
        await #expect(throws: BookingFailure.invalidDuration) {
            try await store.reserve(lab: openLab, start: hoursFromNow(1), durationMinutes: minutes)
        }
        #expect(service.createCalls.isEmpty)
    }

    @Test(arguments: [-1.0, 0.0])
    func pastOrCurrentStartIsRejectedWithoutCallingServer(hours: Double) async {
        let store = makeStore()
        await #expect(throws: BookingFailure.past) {
            try await store.reserve(lab: openLab, start: hoursFromNow(hours))
        }
        #expect(service.createCalls.isEmpty)
    }

    // Cancelling

    @Test func cancelMarksBookingCancelledAndRemovesItFromUpcoming() async throws {
        let first = booking(hours: 2)
        let second = booking(hours: 4)
        service.storedBookings = [first, second]
        let store = makeStore()
        await store.load()

        try await store.cancel(first)

        #expect(service.cancelledIDs == [first.id])
        #expect(store.bookings.first { $0.id == first.id }?.status == .cancelled)
        #expect(store.upcoming.map(\.id) == [second.id])
    }

    @Test func refreshPicksUpCheckInWithoutLoadingState() async {
        let first = booking(hours: 0.1)
        service.storedBookings = [first]
        let store = makeStore()
        await store.load()

        var checkedIn = first
        checkedIn.checkedInAt = now
        service.storedBookings = [checkedIn]
        await store.refresh()

        #expect(store.bookings.first?.checkedInAt == now)
        #expect(store.loadState == .loaded)
    }

    @Test func failedRefreshKeepsBookings() async {
        service.storedBookings = [booking(hours: 2)]
        let store = makeStore()
        await store.load()
        service.fetchError = APIError.unreachable

        await store.refresh()

        #expect(store.bookings.count == 1)
        #expect(store.loadState.errorMessage != nil)
    }

    @Test func checkInStateFollowsTheServerWindow() {
        let upcoming = booking(hours: 1)
        #expect(upcoming.checkInState(now: now) == .upcoming)
        // Check-in opens 10 minutes before the start.
        #expect(upcoming.checkInState(now: upcoming.start.addingTimeInterval(-11 * 60)) == .upcoming)
        #expect(upcoming.checkInState(now: upcoming.start.addingTimeInterval(-10 * 60)) == .checkInOpen)
        #expect(upcoming.checkInState(now: upcoming.start.addingTimeInterval(30 * 60)) == .checkInOpen)

        var checkedIn = upcoming
        checkedIn.checkedInAt = upcoming.start
        #expect(checkedIn.checkInState(now: now) == .checkedIn(at: upcoming.start))
    }

    @Test func bookingDecodesCheckInFromServer() throws {
        let checkedIn = """
        {"id":"d808ae4a-b8e6-405b-9231-1ce929912a92","labID":"LAB001","labName":"Robotics Lab",
         "start":"2026-10-24T10:00:00+05:30","end":"2026-10-24T11:00:00+05:30","status":"active",
         "createdAt":"2026-10-23T23:11:17.747476+05:30","checkedInAt":"2026-10-24T09:58:12.120000+05:30"}
        """
        let notYet = checkedIn.replacingOccurrences(of: #""checkedInAt":"2026-10-24T09:58:12.120000+05:30""#,
                                                    with: #""checkedInAt":null"#)
        #expect(try JSONDecoder.campusOS.decode(LabBooking.self, from: Data(checkedIn.utf8)).checkedInAt != nil)
        #expect(try JSONDecoder.campusOS.decode(LabBooking.self, from: Data(notYet.utf8)).checkedInAt == nil)
    }

    @Test func failedCancelLeavesBookingActive() async {
        let first = booking(hours: 2)
        service.storedBookings = [first]
        service.cancelError = APIError.invalid("This booking has already ended.")
        let store = makeStore()
        await store.load()

        await #expect(throws: APIError.invalid("This booking has already ended.")) {
            try await store.cancel(first)
        }
        #expect(store.upcoming.map(\.id) == [first.id])
    }
}
