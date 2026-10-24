import Foundation
import Combine

struct LabBooking: Identifiable, Codable, Equatable {
    enum Status: String, Codable {
        /// Confirmed (approved, or the lab doesn't need approval).
        case active
        /// Waiting for faculty approval; the slot is held.
        case pending
        case declined
        case cancelled
        /// Not approved before its start time.
        case expired
        case other

        init(from decoder: Decoder) throws {
            let raw = try decoder.singleValueContainer().decode(String.self)
            self = Status(rawValue: raw) ?? .other
        }
    }

    let id: UUID
    let labID: String
    let labName: String
    let start: Date
    let end: Date
    let status: Status
    /// When the student tapped their card at the lab door (actual session start).
    var checkedInAt: Date? = nil
    /// What the student plans to do; shown to faculty reviewing the request.
    var purpose: String? = nil
    /// Who made the booking (shown to faculty in the review queue).
    var student: String? = nil
    var username: String? = nil
    /// Faculty decision on a request.
    var decidedBy: String? = nil
    var decisionNote: String? = nil

    /// The server opens check-in this long before the start (bookings/services.py CHECK_IN_EARLY).
    static let checkInOpensBefore: TimeInterval = 10 * 60

    enum CheckInState: Equatable {
        case upcoming
        case checkInOpen
        case checkedIn(at: Date)
    }

    func checkInState(now: Date) -> CheckInState {
        if let checkedInAt { return .checkedIn(at: checkedInAt) }
        return now >= start.addingTimeInterval(-LabBooking.checkInOpensBefore) ? .checkInOpen : .upcoming
    }
}

enum BookingFailure: Error, LocalizedError {
    case closed, past, invalidDuration

    var errorDescription: String? {
        switch self {
        case .closed: return "This lab is not accepting bookings."
        case .past: return "Choose a future start time."
        case .invalidDuration: return "The booking duration must be positive."
        }
    }
}

/// The signed-in user's lab bookings and requests, plus (for faculty) the
/// approval queue. The Django API is the source of truth: it checks overlaps
/// against every student's bookings and decides whether approval is needed.
@MainActor
final class BookingStore: ObservableObject {
    @Published private(set) var bookings: [LabBooking] = []
    @Published private(set) var loadState: LoadState = .idle
    /// Faculty: requests waiting for approval.
    @Published private(set) var pendingReviews: [LabBooking] = []
    @Published private(set) var reviewState: LoadState = .idle
    @Published private(set) var reviewingID: UUID?

    private let service: BookingService
    private let now: () -> Date

    init(service: BookingService, now: @escaping () -> Date = Date.init) {
        self.service = service
        self.now = now
    }

    /// Confirmed bookings and pending requests that haven't finished, soonest first.
    var upcoming: [LabBooking] {
        let current = now()
        return bookings
            .filter { ($0.status == .active || $0.status == .pending) && $0.end > current }
            .sorted { $0.start < $1.start }
    }

    /// Requests faculty declined (or that expired) for times that haven't passed, so the student sees why.
    var notApproved: [LabBooking] {
        let current = now()
        return bookings
            .filter { ($0.status == .declined || $0.status == .expired) && $0.end > current }
            .sorted { $0.start < $1.start }
    }

    func load() async {
        loadState = .loading
        do {
            bookings = try await service.fetchBookings()
            loadState = .loaded
        } catch {
            loadState = .failed(error.localizedDescription)
        }
    }

    /// Re-fetches without showing a loading state, for live updates while the
    /// Bookings screen is open (e.g. after a check-in tap or a faculty decision).
    func refresh() async {
        do {
            bookings = try await service.fetchBookings()
            loadState = .loaded
        } catch {
            loadState = .failed(error.localizedDescription)
        }
    }

    /// Clears bookings after sign-out so the next user never sees them.
    func reset() {
        bookings = []
        loadState = .idle
        pendingReviews = []
        reviewState = .idle
    }

    /// Returns the server's booking: `.pending` when the lab needs faculty approval.
    @discardableResult
    func reserve(lab: Lab, start: Date, durationMinutes: Int = 60, purpose: String = "") async throws -> LabBooking {
        // Quick local checks for instant feedback; the server re-checks everything.
        guard lab.isOpenForBooking else { throw BookingFailure.closed }
        guard durationMinutes > 0 else { throw BookingFailure.invalidDuration }
        guard start > now() else { throw BookingFailure.past }

        let booking = try await service.createBooking(labID: lab.id, start: start, durationMinutes: durationMinutes,
                                                      purpose: purpose.trimmingCharacters(in: .whitespacesAndNewlines))
        bookings.append(booking)
        return booking
    }

    /// Cancels a confirmed booking or withdraws a pending request.
    func cancel(_ booking: LabBooking) async throws {
        let updated = try await service.cancelBooking(id: booking.id)
        if let index = bookings.firstIndex(where: { $0.id == updated.id }) {
            bookings[index] = updated
        }
    }

    // MARK: Faculty review

    func loadReviews() async {
        reviewState = .loading
        do {
            pendingReviews = try await service.fetchPendingReviews()
            reviewState = .loaded
        } catch {
            reviewState = .failed(error.localizedDescription)
        }
    }

    /// The server refuses self-approval and re-checks SkillPass before confirming.
    func approve(_ booking: LabBooking, note: String = "") async throws {
        try await review(booking) { try await self.service.approve(id: booking.id, note: note) }
    }

    func decline(_ booking: LabBooking, note: String) async throws {
        try await review(booking) { try await self.service.decline(id: booking.id, note: note) }
    }

    private func review(_ booking: LabBooking, _ action: () async throws -> LabBooking) async throws {
        reviewingID = booking.id
        defer { reviewingID = nil }
        _ = try await action()
        pendingReviews.removeAll { $0.id == booking.id }
    }
}
