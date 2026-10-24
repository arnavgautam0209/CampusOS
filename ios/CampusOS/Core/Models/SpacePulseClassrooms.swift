import Foundation
import Combine

// MARK: Room search (GET /api/v1/spaces/availability/)

/// A room that fits (or doesn't fit) a group over the requested time. All numbers come from the server.
struct RoomFit: Codable, Identifiable, Equatable {
    let id: String
    let name: String
    let kind: RoomKind
    let location: String
    /// The room's permanent number of seats.
    let capacity: Int
    /// Seats free for the whole requested time (0 when a class or exclusive booking takes the room).
    let availableSeats: Int
    /// Most seats other groups hold at any moment in that time.
    let bookedSeats: Int
    let seatsAfterBooking: Int
    /// Why the room doesn't work; nil for rooms that fit.
    let reason: String?
}

struct TimetableRef: Codable, Equatable {
    let id: Int
    let version: Int
    let name: String
}

struct RoomSearchResult: Codable, Equatable {
    let date: String
    let start: Date
    let end: Date
    let groupSize: Int
    let mode: BookingMode
    let timetable: TimetableRef?
    let recommended: RoomFit?
    /// Rooms that fit, best fit first (the recommended one is first).
    let rooms: [RoomFit]
    let unavailable: [RoomFit]
    let message: String

    var alternatives: [RoomFit] { Array(rooms.dropFirst()) }
}

/// What a student is looking for. Date and time are combined in the campus (device) calendar.
struct RoomSearch: Equatable {
    var groupSize = 8
    var mode: BookingMode = .shared
    var day: Date
    var startTime: Date
    var minutes = 60

    var start: Date {
        let calendar = Calendar.current
        let time = calendar.dateComponents([.hour, .minute], from: startTime)
        return calendar.date(bySettingHour: time.hour ?? 0, minute: time.minute ?? 0, second: 0, of: day) ?? day
    }

    var queryItems: [URLQueryItem] {
        let time = Calendar.current.dateComponents([.hour, .minute], from: startTime)
        return [
            URLQueryItem(name: "date", value: SpacesStore.dayString(day)),
            URLQueryItem(name: "start", value: String(format: "%02d:%02d", time.hour ?? 0, time.minute ?? 0)),
            URLQueryItem(name: "duration", value: String(minutes)),
            URLQueryItem(name: "group_size", value: String(groupSize)),
            URLQueryItem(name: "mode", value: mode.rawValue),
        ]
    }
}

// MARK: Timetables (/api/v1/spaces/timetables/)

struct TimetableClass: Codable, Equatable, Identifiable {
    let weekday: Int
    let day: String
    let start: String
    let end: String
    let roomId: String
    let activity: String

    var id: String { "\(weekday)-\(start)-\(roomId)" }
}

struct TimetableChange: Codable, Equatable, Identifiable {
    enum Kind: String, Codable {
        case occupied, freed, activityChanged = "activity_changed", other

        init(from decoder: Decoder) throws {
            let raw = try decoder.singleValueContainer().decode(String.self)
            self = Kind(rawValue: raw) ?? .other
        }
    }

    let day: String
    let weekday: Int
    let start: String
    let end: String
    let roomId: String
    let change: Kind
    let before: String?
    let after: String?

    var id: String { "\(weekday)-\(start)-\(roomId)" }
}

struct TimetablePreview: Codable, Equatable {
    let againstVersion: Int?
    let againstName: String?
    let changes: [TimetableChange]
}

struct TimetableConflict: Codable, Equatable, Identifiable {
    let bookingId: UUID
    let roomId: String
    let roomName: String
    let start: Date
    let end: Date
    let attendees: Int
    let mode: BookingMode
    let bookedBy: String
    let username: String
    let clashesWith: String
    let classStart: Date
    let classEnd: Date
    let suggestedRoomId: String?
    let suggestedRoomName: String?

    var id: UUID { bookingId }
}

struct Timetable: Codable, Equatable, Identifiable {
    enum Status: String, Codable {
        case draft, active, archived, other

        init(from decoder: Decoder) throws {
            let raw = try decoder.singleValueContainer().decode(String.self)
            self = Status(rawValue: raw) ?? .other
        }

        var label: String {
            switch self {
            case .draft: return "Not active"
            case .active: return "Active"
            case .archived: return "Previous"
            case .other: return "Unknown"
            }
        }
    }

    let id: Int
    let version: Int
    let name: String
    let status: Status
    let sourceFilename: String
    let uploadedBy: String?
    let createdAt: Date
    let activatedAt: Date?
    let classCount: Int
    /// Sent with a single timetable, the active one and upload results.
    var entries: [TimetableClass]?
    /// Sent with upload results only.
    var preview: TimetablePreview?
    var conflicts: [TimetableConflict]?
}

struct TimetableEvent: Codable, Equatable, Identifiable {
    let action: String
    let detail: String
    let createdAt: Date
    let timetableVersion: Int?
    let actor: String?

    var id: String { "\(createdAt.timeIntervalSince1970)-\(action)-\(detail)" }

    var label: String {
        switch action {
        case "seeded": return "Loaded demo timetable"
        case "uploaded": return "Uploaded"
        case "activated": return "Activated"
        case "booking_cancelled": return "Booking cancelled"
        case "booking_reassigned": return "Booking moved"
        default: return action.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
}

enum ConflictAction: String {
    case reassign, cancel
}

protocol SpacePulseService {
    func findRooms(_ search: RoomSearch) async throws -> RoomSearchResult
    func book(roomId: String, start: Date, minutes: Int, groupSize: Int, mode: BookingMode,
              purpose: String) async throws -> RoomBooking
    // Faculty (the server refuses students, except reading the active timetable).
    func fetchActiveTimetable() async throws -> Timetable?
    func fetchTimetables() async throws -> [Timetable]
    func fetchTimetable(id: Int) async throws -> Timetable
    func uploadTimetable(name: String, filename: String, csv: String) async throws -> Timetable
    func fetchPreview(id: Int) async throws -> TimetablePreview
    func fetchConflicts(id: Int) async throws -> [TimetableConflict]
    func resolve(timetableId: Int, bookingId: UUID, action: ConflictAction, roomId: String?) async throws -> RoomBooking
    func activate(id: Int) async throws -> Timetable
    func fetchHistory() async throws -> [TimetableEvent]
    func fetchAllBookings() async throws -> [RoomBooking]
}

extension APISpacesService: SpacePulseService {
    func findRooms(_ search: RoomSearch) async throws -> RoomSearchResult {
        var components = URLComponents()
        components.queryItems = search.queryItems
        return try await api.get("spaces/availability/?\(components.percentEncodedQuery ?? "")", authenticated: true)
    }

    func book(roomId: String, start: Date, minutes: Int, groupSize: Int, mode: BookingMode,
              purpose: String) async throws -> RoomBooking {
        struct Request: Encodable {
            let roomId: String; let start: Date; let durationMinutes: Int; let attendees: Int; let mode: String
            let purpose: String
        }
        return try await api.post("spaces/bookings/", body: Request(roomId: roomId, start: start,
                                                                    durationMinutes: minutes, attendees: groupSize,
                                                                    mode: mode.rawValue, purpose: purpose),
                                  authenticated: true)
    }

    func fetchActiveTimetable() async throws -> Timetable? {
        do {
            return try await api.get("spaces/timetables/active/", authenticated: true)
        } catch APIError.notFound {
            return nil
        }
    }

    func fetchTimetables() async throws -> [Timetable] {
        try await api.get("spaces/timetables/", authenticated: true)
    }

    func fetchTimetable(id: Int) async throws -> Timetable {
        try await api.get("spaces/timetables/\(id)/", authenticated: true)
    }

    func uploadTimetable(name: String, filename: String, csv: String) async throws -> Timetable {
        struct Request: Encodable { let name: String; let filename: String; let csv: String }
        return try await api.post("spaces/timetables/upload/", body: Request(name: name, filename: filename, csv: csv),
                                  authenticated: true, timeout: 30)
    }

    func fetchPreview(id: Int) async throws -> TimetablePreview {
        try await api.get("spaces/timetables/\(id)/preview/", authenticated: true)
    }

    func fetchConflicts(id: Int) async throws -> [TimetableConflict] {
        try await api.get("spaces/timetables/\(id)/conflicts/", authenticated: true)
    }

    func resolve(timetableId: Int, bookingId: UUID, action: ConflictAction, roomId: String?) async throws -> RoomBooking {
        struct Request: Encodable { let bookingId: String; let action: String; let roomId: String? }
        return try await api.post("spaces/timetables/\(timetableId)/resolve/",
                                  body: Request(bookingId: bookingId.uuidString.lowercased(), action: action.rawValue,
                                                roomId: roomId),
                                  authenticated: true)
    }

    func activate(id: Int) async throws -> Timetable {
        try await api.post("spaces/timetables/\(id)/activate/", authenticated: true)
    }

    func fetchHistory() async throws -> [TimetableEvent] {
        try await api.get("spaces/timetables/history/", authenticated: true)
    }

    func fetchAllBookings() async throws -> [RoomBooking] {
        try await api.get("spaces/bookings/?scope=all", authenticated: true)
    }
}

// MARK: Student: find and book a room

@MainActor
final class RoomFinderStore: ObservableObject {
    @Published var search: RoomSearch
    @Published private(set) var result: RoomSearchResult?
    @Published private(set) var searchState: LoadState = .idle
    /// The room being booked, to show progress on its button.
    @Published private(set) var bookingRoomID: String?

    private let service: SpacePulseService

    init(service: SpacePulseService, now: Date = Date()) {
        self.service = service
        // Default: the next full hour today (or 09:00 tomorrow when it's late).
        let calendar = Calendar.current
        var start = calendar.nextDate(after: now, matching: DateComponents(minute: 0), matchingPolicy: .nextTime) ?? now
        if calendar.component(.hour, from: start) >= 19 || calendar.component(.hour, from: start) < 8 {
            let tomorrow = calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: now)) ?? now
            start = calendar.date(bySettingHour: 9, minute: 0, second: 0, of: tomorrow) ?? now
        }
        search = RoomSearch(day: calendar.startOfDay(for: start), startTime: start)
    }

    func find() async {
        searchState = .loading
        do {
            result = try await service.findRooms(search)
            searchState = .loaded
        } catch {
            result = nil
            searchState = .failed(error.localizedDescription)
        }
    }

    /// Books the room for the searched time, then searches again so the seats left are the server's.
    @discardableResult
    func book(_ room: RoomFit, purpose: String = "") async throws -> RoomBooking {
        bookingRoomID = room.id
        defer { bookingRoomID = nil }
        let booking = try await service.book(roomId: room.id, start: search.start, minutes: search.minutes,
                                             groupSize: search.groupSize, mode: search.mode,
                                             purpose: purpose.trimmingCharacters(in: .whitespacesAndNewlines))
        await find()
        return booking
    }

    func reset() {
        result = nil
        searchState = .idle
    }
}

// MARK: Faculty: timetables

@MainActor
final class TimetableStore: ObservableObject {
    @Published private(set) var active: Timetable?
    @Published private(set) var versions: [Timetable] = []
    @Published private(set) var history: [TimetableEvent] = []
    @Published private(set) var reservations: [RoomBooking] = []
    @Published private(set) var loadState: LoadState = .idle

    // The version being reviewed before activation.
    @Published private(set) var review: Timetable?
    @Published private(set) var preview: TimetablePreview?
    @Published private(set) var conflicts: [TimetableConflict] = []
    @Published private(set) var reviewState: LoadState = .idle
    @Published private(set) var isUploading = false
    @Published private(set) var isActivating = false
    @Published private(set) var resolvingID: UUID?

    private let service: SpacePulseService

    init(service: SpacePulseService) {
        self.service = service
    }

    func load(staff: Bool) async {
        if active == nil { loadState = .loading }
        do {
            active = try await service.fetchActiveTimetable()
            if staff {
                versions = try await service.fetchTimetables()
                history = try await service.fetchHistory()
                reservations = try await service.fetchAllBookings()
            }
            loadState = .loaded
        } catch {
            loadState = .failed(error.localizedDescription)
        }
    }

    /// Sends the CSV as read from the file. The server validates every row; nothing is stored if one is wrong.
    func upload(filename: String, csv: String) async throws -> Timetable {
        isUploading = true
        defer { isUploading = false }
        let name = (filename as NSString).deletingPathExtension.replacingOccurrences(of: "_", with: " ")
        let uploaded = try await service.uploadTimetable(name: name, filename: filename, csv: csv)
        review = uploaded
        preview = uploaded.preview
        conflicts = uploaded.conflicts ?? []
        reviewState = .loaded
        versions.insert(uploaded, at: 0)
        return uploaded
    }

    func loadReview(id: Int) async {
        if review?.id != id {
            review = nil
            preview = nil
            conflicts = []
            reviewState = .loading
        }
        do {
            let timetable = try await service.fetchTimetable(id: id)
            preview = try await service.fetchPreview(id: id)
            conflicts = timetable.status == .active ? [] : try await service.fetchConflicts(id: id)
            review = timetable
            reviewState = .loaded
        } catch {
            reviewState = .failed(error.localizedDescription)
        }
    }

    func fetchEntries(id: Int) async throws -> [TimetableClass] {
        try await service.fetchTimetable(id: id).entries ?? []
    }

    /// Faculty decision for one clashing booking; logged on the server and shown to the student.
    func resolve(_ conflict: TimetableConflict, action: ConflictAction, roomId: String? = nil) async throws {
        guard let review else { return }
        resolvingID = conflict.bookingId
        defer { resolvingID = nil }
        _ = try await service.resolve(timetableId: review.id, bookingId: conflict.bookingId, action: action,
                                      roomId: roomId)
        conflicts = try await service.fetchConflicts(id: review.id)
    }

    var canActivate: Bool {
        review != nil && review?.status != .active && conflicts.isEmpty && reviewState == .loaded
    }

    func activate() async throws {
        guard let review else { return }
        isActivating = true
        defer { isActivating = false }
        do {
            _ = try await service.activate(id: review.id)
        } catch {
            // Someone may have booked in the meantime: show the current conflicts.
            conflicts = (try? await service.fetchConflicts(id: review.id)) ?? conflicts
            throw error
        }
        await loadReview(id: review.id)
        await load(staff: true)
    }

    func reset() {
        active = nil
        versions = []
        history = []
        reservations = []
        review = nil
        preview = nil
        conflicts = []
        loadState = .idle
        reviewState = .idle
    }
}
