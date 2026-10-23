import Foundation
import Combine

struct LabBooking: Identifiable, Codable, Equatable {
    enum Status: String, Codable {
        case active, cancelled
    }

    let id: UUID
    let labID: String
    let labName: String
    let start: Date
    let end: Date
    let status: Status
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

/// The signed-in user's lab bookings. The Django API is the source of truth:
/// it checks overlaps against every student's bookings, not just this device's.
@MainActor
final class BookingStore: ObservableObject {
    @Published private(set) var bookings: [LabBooking] = []
    @Published private(set) var loadState: LoadState = .idle

    private let service: BookingService
    private let now: () -> Date

    init(service: BookingService, now: @escaping () -> Date = Date.init) {
        self.service = service
        self.now = now
    }

    /// Active bookings that haven't finished, soonest first.
    var upcoming: [LabBooking] {
        let current = now()
        return bookings
            .filter { $0.status == .active && $0.end > current }
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

    /// Clears bookings after sign-out so the next user never sees them.
    func reset() {
        bookings = []
        loadState = .idle
    }

    func reserve(lab: Lab, start: Date, durationMinutes: Int = 60) async throws {
        // Quick local checks for instant feedback; the server re-checks everything.
        guard lab.isOpenForBooking else { throw BookingFailure.closed }
        guard durationMinutes > 0 else { throw BookingFailure.invalidDuration }
        guard start > now() else { throw BookingFailure.past }

        let booking = try await service.createBooking(labID: lab.id, start: start,
                                                      durationMinutes: durationMinutes)
        bookings.append(booking)
    }

    func cancel(_ booking: LabBooking) async throws {
        let updated = try await service.cancelBooking(id: booking.id)
        if let index = bookings.firstIndex(where: { $0.id == updated.id }) {
            bookings[index] = updated
        }
    }
}
