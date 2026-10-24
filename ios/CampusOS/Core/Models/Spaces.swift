import Foundation
import Combine

/// GET /api/v1/spaces/?date=: every room with its busy slots between 08:00 and 20:00.
struct SpaceAvailability: Codable, Equatable {
    /// "YYYY-MM-DD"
    let date: String
    let dayStart: Date
    let dayEnd: Date
    let rooms: [CampusRoom]
}

enum RoomKind: String, Codable {
    case classroom, studyRoom = "study_room", meetingRoom = "meeting_room", other

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = RoomKind(rawValue: raw) ?? .other
    }

    var label: String {
        switch self {
        case .classroom: return "Classroom"
        case .studyRoom: return "Study room"
        case .meetingRoom: return "Meeting room"
        case .other: return "Room"
        }
    }

    var symbol: String {
        switch self {
        case .classroom: return "person.3.sequence"
        case .studyRoom: return "books.vertical"
        case .meetingRoom: return "person.2.wave.2"
        case .other: return "door.left.hand.closed"
        }
    }
}

struct CampusRoom: Codable, Identifiable, Equatable {
    struct BusySlot: Codable, Equatable {
        let start: Date
        let end: Date
        let mine: Bool
        /// Only sent to staff.
        let bookedBy: String?
        let checkedIn: Bool
    }

    let id: String
    let name: String
    let kind: RoomKind
    let capacity: Int
    let location: String
    let features: [String]
    /// Whether the signed-in user may book it (timetabled classrooms: staff only).
    let isBookable: Bool
    /// An attendance session is open in this room right now.
    let inClassNow: Bool
    let freeNow: Bool
    let busy: [BusySlot]

    /// Start times (every 30 min) where `minutes` fits between `dayStart` and `dayEnd`
    /// without overlapping a busy slot and not in the past. The server re-checks.
    func freeStarts(dayStart: Date, dayEnd: Date, minutes: Int, now: Date,
                    step: TimeInterval = 30 * 60) -> [Date] {
        let length = TimeInterval(minutes * 60)
        var starts: [Date] = []
        var slot = dayStart
        while slot.addingTimeInterval(length) <= dayEnd {
            let end = slot.addingTimeInterval(length)
            if slot > now, !busy.contains(where: { $0.start < end && slot < $0.end }) {
                starts.append(slot)
            }
            slot = slot.addingTimeInterval(step)
        }
        return starts
    }
}

/// A SpacePulse room reservation (GET/POST /api/v1/spaces/bookings/).
struct RoomBooking: Codable, Identifiable, Equatable {
    enum Status: String, Codable {
        case active, cancelled, expired, other

        init(from decoder: Decoder) throws {
            let raw = try decoder.singleValueContainer().decode(String.self)
            self = Status(rawValue: raw) ?? .other
        }
    }

    let id: UUID
    let roomId: String
    let roomName: String
    let start: Date
    let end: Date
    let purpose: String
    let attendees: Int
    let status: Status
    let checkedInAt: Date?
    let bookedBy: String
    let username: String

    /// Server rules (spaces/services.py): check-in opens 10 min before the start and
    /// closes 15 min after it, when an un-checked-in booking is released.
    static let checkInOpensBefore: TimeInterval = 10 * 60
    static let noShowAfter: TimeInterval = 15 * 60

    func canCheckIn(now: Date) -> Bool {
        status == .active && checkedInAt == nil
            && now >= start.addingTimeInterval(-Self.checkInOpensBefore)
            && now <= start.addingTimeInterval(Self.noShowAfter)
    }
}

/// Staff summary from GET /api/v1/spaces/utilization/.
struct RoomUsage: Codable, Identifiable, Equatable {
    let roomId: String
    let roomName: String
    let bookings: Int
    let noShows: Int
    let bookedHours: Double
    let utilizationPct: Int

    var id: String { roomId }
}

protocol SpacesService {
    func fetchAvailability(date: String) async throws -> SpaceAvailability
    func fetchMyBookings() async throws -> [RoomBooking]
    func fetchUtilization() async throws -> [RoomUsage]
    func book(roomId: String, start: Date, minutes: Int, attendees: Int, purpose: String) async throws -> RoomBooking
    func cancel(id: UUID) async throws -> RoomBooking
    func checkIn(id: UUID) async throws -> RoomBooking
}

struct APISpacesService: SpacesService {
    let api: APIClient

    func fetchAvailability(date: String) async throws -> SpaceAvailability {
        try await api.get("spaces/?date=\(date)", authenticated: true)
    }

    func fetchMyBookings() async throws -> [RoomBooking] {
        try await api.get("spaces/bookings/", authenticated: true)
    }

    func fetchUtilization() async throws -> [RoomUsage] {
        struct Response: Decodable { let rooms: [RoomUsage] }
        let response: Response = try await api.get("spaces/utilization/?days=7", authenticated: true)
        return response.rooms
    }

    func book(roomId: String, start: Date, minutes: Int, attendees: Int, purpose: String) async throws -> RoomBooking {
        struct Request: Encodable {
            let roomId: String; let start: Date; let durationMinutes: Int; let attendees: Int; let purpose: String
        }
        return try await api.post("spaces/bookings/", body: Request(roomId: roomId, start: start,
                                                                    durationMinutes: minutes, attendees: attendees,
                                                                    purpose: purpose), authenticated: true)
    }

    func cancel(id: UUID) async throws -> RoomBooking {
        try await api.post("spaces/bookings/\(id.uuidString.lowercased())/cancel/", authenticated: true)
    }

    func checkIn(id: UUID) async throws -> RoomBooking {
        try await api.post("spaces/bookings/\(id.uuidString.lowercased())/check-in/", authenticated: true)
    }
}

/// SpacePulse: room availability for a chosen day and the user's room bookings.
/// Conflicts, capacity and who may book are decided by the server.
@MainActor
final class SpacesStore: ObservableObject {
    @Published private(set) var availability: SpaceAvailability?
    @Published private(set) var myBookings: [RoomBooking] = []
    @Published private(set) var usage: [RoomUsage] = []
    @Published private(set) var loadState: LoadState = .idle
    @Published private(set) var busyBookingID: UUID?

    private let service: SpacesService
    private let now: () -> Date

    init(service: SpacesService, now: @escaping () -> Date = Date.init) {
        self.service = service
        self.now = now
    }

    var upcoming: [RoomBooking] {
        let current = now()
        return myBookings.filter { $0.status == .active && $0.end > current }.sorted { $0.start < $1.start }
    }

    nonisolated static func dayString(_ day: Date, calendar: Calendar = .current) -> String {
        let parts = calendar.dateComponents([.year, .month, .day], from: day)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    func load(day: Date, staff: Bool) async {
        loadState = .loading
        do {
            availability = try await service.fetchAvailability(date: Self.dayString(day))
            myBookings = try await service.fetchMyBookings()
            usage = staff ? (try? await service.fetchUtilization()) ?? [] : []
            loadState = .loaded
        } catch {
            loadState = .failed(error.localizedDescription)
        }
    }

    func book(_ room: CampusRoom, start: Date, minutes: Int, attendees: Int, purpose: String, day: Date) async throws {
        let booking = try await service.book(roomId: room.id, start: start, minutes: minutes, attendees: attendees,
                                             purpose: purpose.trimmingCharacters(in: .whitespacesAndNewlines))
        myBookings.append(booking)
        await reloadAvailability(day: day)
    }

    func cancel(_ booking: RoomBooking, day: Date) async throws {
        try await update(booking, day: day) { try await self.service.cancel(id: booking.id) }
    }

    func checkIn(_ booking: RoomBooking, day: Date) async throws {
        try await update(booking, day: day) { try await self.service.checkIn(id: booking.id) }
    }

    func reset() {
        availability = nil
        myBookings = []
        usage = []
        loadState = .idle
    }

    private func update(_ booking: RoomBooking, day: Date, _ action: () async throws -> RoomBooking) async throws {
        busyBookingID = booking.id
        defer { busyBookingID = nil }
        let updated = try await action()
        if let index = myBookings.firstIndex(where: { $0.id == updated.id }) {
            myBookings[index] = updated
        }
        await reloadAvailability(day: day)
    }

    private func reloadAvailability(day: Date) async {
        if let fresh = try? await service.fetchAvailability(date: Self.dayString(day)) {
            availability = fresh
        }
    }
}
