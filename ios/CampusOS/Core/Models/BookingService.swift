import Foundation

/// The booking operations BookingStore needs. The live version calls Django;
/// tests and previews substitute their own.
protocol BookingService {
    func fetchBookings() async throws -> [LabBooking]
    func createBooking(labID: String, start: Date, durationMinutes: Int, purpose: String) async throws -> LabBooking
    func cancelBooking(id: UUID) async throws -> LabBooking
    // Faculty only (for students the server ignores the scope and returns their own bookings).
    func fetchPendingReviews() async throws -> [LabBooking]
    func approve(id: UUID, note: String) async throws -> LabBooking
    func decline(id: UUID, note: String) async throws -> LabBooking
}

struct APIBookingService: BookingService {
    let api: APIClient

    func fetchBookings() async throws -> [LabBooking] {
        try await api.get("bookings/", authenticated: true)
    }

    func createBooking(labID: String, start: Date, durationMinutes: Int, purpose: String) async throws -> LabBooking {
        struct Request: Encodable { let labID: String; let start: Date; let durationMinutes: Int; let purpose: String }
        return try await api.post("bookings/",
                                  body: Request(labID: labID, start: start, durationMinutes: durationMinutes,
                                                purpose: purpose),
                                  authenticated: true)
    }

    func cancelBooking(id: UUID) async throws -> LabBooking {
        try await api.post("bookings/\(id.uuidString.lowercased())/cancel/", authenticated: true)
    }

    func fetchPendingReviews() async throws -> [LabBooking] {
        try await api.get("bookings/?scope=pending", authenticated: true)
    }

    func approve(id: UUID, note: String) async throws -> LabBooking {
        try await decide(id, "approve", note)
    }

    func decline(id: UUID, note: String) async throws -> LabBooking {
        try await decide(id, "decline", note)
    }

    private func decide(_ id: UUID, _ action: String, _ note: String) async throws -> LabBooking {
        struct Request: Encodable { let note: String }
        return try await api.post("bookings/\(id.uuidString.lowercased())/\(action)/", body: Request(note: note),
                                  authenticated: true)
    }
}
