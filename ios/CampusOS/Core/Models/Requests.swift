import Foundation
import Combine

/// A student request from LabOS (lab booking) or AssetX (equipment loan), from GET /api/v1/requests/.
struct CampusRequest: Codable, Identifiable, Equatable {
    enum Kind: String, Codable {
        case labBooking = "lab_booking", equipment, other

        init(from decoder: Decoder) throws {
            let raw = try decoder.singleValueContainer().decode(String.self)
            self = Kind(rawValue: raw) ?? .other
        }
    }

    enum Status: String, Codable {
        case pending, approved, rejected, cancelled, expired, returned, other

        init(from decoder: Decoder) throws {
            let raw = try decoder.singleValueContainer().decode(String.self)
            self = Status(rawValue: raw) ?? .other
        }
    }

    let type: Kind
    /// The booking UUID or loan number, as text.
    let rawId: String
    let status: Status
    let title: String
    let detail: String
    let purpose: String
    let requester: String
    let username: String
    let createdAt: Date
    let decidedBy: String?
    let decisionNote: String

    var id: String { "\(type.rawValue)-\(rawId)" }

    enum CodingKeys: String, CodingKey {
        case type, rawId = "id", status, title, detail, purpose, requester, username, createdAt, decidedBy, decisionNote
    }
}

protocol RequestsService {
    /// Admins: every pending request. Students: their own requests.
    func fetchRequests() async throws -> [CampusRequest]
    func approve(_ request: CampusRequest, note: String) async throws
    func reject(_ request: CampusRequest, note: String) async throws
}

struct APIRequestsService: RequestsService {
    let api: APIClient

    func fetchRequests() async throws -> [CampusRequest] {
        try await api.get("requests/", authenticated: true)
    }

    func approve(_ request: CampusRequest, note: String) async throws {
        try await decide(request, labAction: "approve", loanAction: "approve", note: note)
    }

    func reject(_ request: CampusRequest, note: String) async throws {
        try await decide(request, labAction: "decline", loanAction: "reject", note: note)
    }

    /// Each module's own endpoint applies its rules (slot clashes, stock, SkillPass, permissions).
    private func decide(_ request: CampusRequest, labAction: String, loanAction: String, note: String) async throws {
        struct Body: Encodable { let note: String }
        struct Ignored: Decodable {}
        let path: String
        switch request.type {
        case .labBooking: path = "bookings/\(request.rawId.lowercased())/\(labAction)/"
        case .equipment: path = "inventory/loans/\(request.rawId)/\(loanAction)/"
        case .other: throw APIError.invalid("This kind of request can't be decided in the app.")
        }
        let _: Ignored = try await api.post(path, body: Body(note: note), authenticated: true)
    }
}

@MainActor
final class RequestsStore: ObservableObject {
    @Published private(set) var requests: [CampusRequest] = []
    @Published private(set) var loadState: LoadState = .idle
    @Published private(set) var decidingID: String?

    private let service: RequestsService

    init(service: RequestsService) {
        self.service = service
    }

    func load() async {
        if requests.isEmpty { loadState = .loading }
        do {
            requests = try await service.fetchRequests()
            loadState = .loaded
        } catch {
            loadState = .failed(error.localizedDescription)
        }
    }

    func approve(_ request: CampusRequest, note: String = "") async throws {
        try await decide(request) { try await self.service.approve(request, note: note) }
    }

    func reject(_ request: CampusRequest, note: String = "") async throws {
        try await decide(request) { try await self.service.reject(request, note: note) }
    }

    /// The decided request leaves the admin's pending list; a refusal (e.g. no stock left) keeps it.
    private func decide(_ request: CampusRequest, _ action: () async throws -> Void) async throws {
        decidingID = request.id
        defer { decidingID = nil }
        try await action()
        requests.removeAll { $0.id == request.id }
        await load()
    }

    func reset() {
        requests = []
        loadState = .idle
    }
}
