import Foundation
import Testing
@testable import CampusOS

@MainActor
@Suite("BookingStore")
final class BookingStoreTests {
    private let suiteName = "BookingStoreTests-\(UUID().uuidString)"
    private let defaults: UserDefaults
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    private let openLab = Lab(id: "LAB-OPEN", name: "Open Lab", location: "Test",
                              symbol: "cpu", capacity: 10, equipment: [], isOpenForBooking: true)
    private let otherLab = Lab(id: "LAB-OTHER", name: "Other Lab", location: "Test",
                               symbol: "bolt", capacity: 10, equipment: [], isOpenForBooking: true)
    private let closedLab = Lab(id: "LAB-CLOSED", name: "Closed Lab", location: "Test",
                                symbol: "printer", capacity: 10, equipment: [], isOpenForBooking: false)

    init() {
        defaults = UserDefaults(suiteName: suiteName)!
    }

    deinit {
        UserDefaults().removePersistentDomain(forName: suiteName)
    }

    private func makeStore() -> BookingStore {
        let fixedNow = now
        return BookingStore(defaults: defaults, now: { fixedNow })
    }

    private func hoursFromNow(_ hours: Double) -> Date {
        now.addingTimeInterval(hours * 3600)
    }

    @Test func reserveAddsBookingWithRequestedDuration() throws {
        let store = makeStore()
        let start = hoursFromNow(2)

        try store.reserve(lab: openLab, start: start, durationMinutes: 120)

        #expect(store.bookings.count == 1)
        let booking = try #require(store.bookings.first)
        #expect(booking.labID == openLab.id)
        #expect(booking.labName == openLab.name)
        #expect(booking.start == start)
        #expect(booking.end == start.addingTimeInterval(120 * 60))
    }

    @Test func defaultDurationIsOneHour() throws {
        let store = makeStore()
        try store.reserve(lab: openLab, start: hoursFromNow(1))
        let booking = try #require(store.bookings.first)
        #expect(booking.end.timeIntervalSince(booking.start) == 3600)
    }

    @Test func closedLabIsRejected() {
        let store = makeStore()
        #expect(throws: BookingFailure.closed) {
            try store.reserve(lab: closedLab, start: hoursFromNow(1))
        }
        #expect(store.bookings.isEmpty)
    }

    @Test(arguments: [0, -30])
    func nonPositiveDurationIsRejected(minutes: Int) {
        let store = makeStore()
        #expect(throws: BookingFailure.invalidDuration) {
            try store.reserve(lab: openLab, start: hoursFromNow(1), durationMinutes: minutes)
        }
        #expect(store.bookings.isEmpty)
    }

    @Test func pastStartIsRejected() {
        let store = makeStore()
        #expect(throws: BookingFailure.past) {
            try store.reserve(lab: openLab, start: hoursFromNow(-1))
        }
    }

    @Test func startExactlyNowIsRejected() {
        let store = makeStore()
        #expect(throws: BookingFailure.past) {
            try store.reserve(lab: openLab, start: now)
        }
    }

    @Test func overlappingBookingInSameLabIsRejected() throws {
        let store = makeStore()
        try store.reserve(lab: openLab, start: hoursFromNow(2), durationMinutes: 60)

        // Starts 30 minutes into the existing booking.
        #expect(throws: BookingFailure.conflict) {
            try store.reserve(lab: openLab, start: hoursFromNow(2.5), durationMinutes: 60)
        }
        // Fully contains the existing booking.
        #expect(throws: BookingFailure.conflict) {
            try store.reserve(lab: openLab, start: hoursFromNow(1.5), durationMinutes: 120)
        }
        #expect(store.bookings.count == 1)
    }

    @Test func backToBackBookingsAreAllowed() throws {
        let store = makeStore()
        try store.reserve(lab: openLab, start: hoursFromNow(2), durationMinutes: 60)
        try store.reserve(lab: openLab, start: hoursFromNow(3), durationMinutes: 60)
        try store.reserve(lab: openLab, start: hoursFromNow(1), durationMinutes: 60)
        #expect(store.bookings.count == 3)
    }

    @Test func sameTimeInDifferentLabIsAllowed() throws {
        let store = makeStore()
        try store.reserve(lab: openLab, start: hoursFromNow(2))
        try store.reserve(lab: otherLab, start: hoursFromNow(2))
        #expect(store.bookings.count == 2)
    }

    @Test func cancelRemovesOnlyThatBookingAndFreesTheSlot() throws {
        let store = makeStore()
        try store.reserve(lab: openLab, start: hoursFromNow(2))
        try store.reserve(lab: otherLab, start: hoursFromNow(2))
        let toCancel = try #require(store.bookings.first { $0.labID == openLab.id })

        store.cancel(toCancel)

        #expect(store.bookings.map(\.labID) == [otherLab.id])
        try store.reserve(lab: openLab, start: hoursFromNow(2))
        #expect(store.bookings.count == 2)
    }

    @Test func bookingsPersistAcrossStoreInstances() throws {
        let first = makeStore()
        try first.reserve(lab: openLab, start: hoursFromNow(2))
        let saved = try #require(first.bookings.first)

        let reloaded = makeStore()

        #expect(reloaded.bookings.count == 1)
        #expect(reloaded.bookings.first?.id == saved.id)
        // Overlap checking still applies to bookings loaded from storage.
        #expect(throws: BookingFailure.conflict) {
            try reloaded.reserve(lab: openLab, start: hoursFromNow(2))
        }
    }

    @Test func cancellationPersists() throws {
        let first = makeStore()
        try first.reserve(lab: openLab, start: hoursFromNow(2))
        first.cancel(try #require(first.bookings.first))

        #expect(makeStore().bookings.isEmpty)
    }
}
