import Foundation
import Testing
@testable import CampusOS

// Captured from GET /api/v1/requests/ (admin: pending from both modules; student: after a rejection).
private let adminJSON = #"""
[{"type": "lab_booking", "id": "447dfdd5-6e0f-4d1a-81fa-8e7fa8606c25", "status": "pending", "title": "AI & Computing Lab", "detail": "Tue 27 Oct, 10:00–11:00", "purpose": "Train the model", "requester": "Demo Student", "username": "demo_student", "createdAt": "2026-10-24T07:03:54.470956+00:00", "decidedBy": null, "decisionNote": ""}, {"type": "equipment", "id": "1", "status": "pending", "title": "Arduino Uno Boards ×2", "detail": "Robotics Lab · 3 days", "purpose": "", "requester": "Demo Student", "username": "demo_student", "createdAt": "2026-10-24T07:03:54.473540+00:00", "decidedBy": null, "decisionNote": ""}]
"""#

private let studentJSON = #"""
[{"type": "equipment", "id": "1", "status": "rejected", "title": "Arduino Uno Boards ×2", "detail": "Robotics Lab · 3 days", "purpose": "", "requester": "Demo Student", "username": "demo_student", "createdAt": "2026-10-24T07:03:54.479913+00:00", "decidedBy": "Demo Admin", "decisionNote": "Out for repair"}]
"""#

private func requests(_ json: String) throws -> [CampusRequest] {
    try JSONDecoder.campusOS.decode([CampusRequest].self, from: Data(json.utf8))
}

final class FakeRequestsService: RequestsService {
    var responses: [[CampusRequest]] = []
    var decideError: Error?
    private(set) var decisions: [(id: String, action: String, note: String)] = []

    func fetchRequests() async throws -> [CampusRequest] {
        responses.count > 1 ? responses.removeFirst() : (responses.first ?? [])
    }

    func approve(_ request: CampusRequest, note: String) async throws {
        decisions.append((request.id, "approve", note))
        if let decideError { throw decideError }
    }

    func reject(_ request: CampusRequest, note: String) async throws {
        decisions.append((request.id, "reject", note))
        if let decideError { throw decideError }
    }
}

@Suite("Requests")
struct RequestsDecodingTests {
    @Test func decodesBothModules() throws {
        let items = try requests(adminJSON)
        #expect(items.map(\.type) == [.labBooking, .equipment])
        #expect(items.allSatisfy { $0.status == .pending })
        #expect(items[0].rawId == "447dfdd5-6e0f-4d1a-81fa-8e7fa8606c25")
        #expect(items[1].id == "equipment-1")
    }

    @Test func decodesDecision() throws {
        let rejected = try #require(try requests(studentJSON).first)
        #expect((rejected.status, rejected.decidedBy, rejected.decisionNote) == (.rejected, "Demo Admin", "Out for repair"))
    }

    @Test func unknownValuesStillDecode() throws {
        let odd = adminJSON.replacingOccurrences(of: #""type": "equipment""#, with: #""type": "room""#)
            .replacingOccurrences(of: #""status": "pending", "title": "Arduino"#, with: #""status": "on_hold", "title": "Arduino"#)
        let items = try requests(odd)
        #expect((items[1].type, items[1].status) == (.other, .other))
    }
}

@MainActor
@Suite("RequestsStore")
struct RequestsStoreTests {
    private let service = FakeRequestsService()

    @Test func approveRemovesFromPendingAndReloads() async throws {
        let pending = try requests(adminJSON)
        service.responses = [pending, [pending[1]]]
        let store = RequestsStore(service: service)
        await store.load()
        #expect(store.requests.count == 2)

        try await store.approve(pending[0])
        #expect(service.decisions.map(\.action) == ["approve"])
        #expect(store.requests.map(\.id) == [pending[1].id])
        #expect(store.decidingID == nil)
    }

    @Test func rejectSendsTheReason() async throws {
        let pending = try requests(adminJSON)
        service.responses = [pending, [pending[0]]]
        let store = RequestsStore(service: service)
        await store.load()
        try await store.reject(pending[1], note: "Out for repair")
        #expect(service.decisions.first?.note == "Out for repair")
        #expect(store.requests.count == 1)
    }

    @Test func refusedApprovalKeepsTheRequest() async throws {
        let pending = try requests(adminJSON)
        service.responses = [pending]
        service.decideError = APIError.conflict("Only 1 Arduino Uno Boards available now; this request needs 2.")
        let store = RequestsStore(service: service)
        await store.load()
        await #expect(throws: APIError.conflict("Only 1 Arduino Uno Boards available now; this request needs 2.")) {
            try await store.approve(pending[1])
        }
        #expect(store.requests.count == 2)
    }

    @Test func resetClears() async throws {
        service.responses = [try requests(studentJSON)]
        let store = RequestsStore(service: service)
        await store.load()
        store.reset()
        #expect(store.requests.isEmpty)
        #expect(store.loadState == .idle)
    }
}

// In NetworkTests (serialized) because it shares StubURLProtocol's static state with those tests.
extension NetworkTests {
    private func requestsClient() -> APIClient {
        APIClient(session: StubURLProtocol.makeSession(), tokenStore: InMemoryTokenStore(token: "abc"),
                  baseURL: { URL(string: "http://campus.test/api/v1/")! })
    }

    @Test func requestDecisionsUseEachModulesEndpoint() async throws {
        let items = try requests(adminJSON)
        let service = APIRequestsService(api: requestsClient())
        let cases: [(CampusRequest, Bool, String)] = [
            (items[0], true, "/bookings/447dfdd5-6e0f-4d1a-81fa-8e7fa8606c25/approve/"),
            (items[0], false, "/bookings/447dfdd5-6e0f-4d1a-81fa-8e7fa8606c25/decline/"),
            (items[1], true, "/inventory/loans/1/approve/"),
            (items[1], false, "/inventory/loans/1/reject/"),
        ]
        for (item, approve, path) in cases {
            StubURLProtocol.reset(.init(status: 200, json: "{}"))
            if approve { try await service.approve(item, note: "") } else { try await service.reject(item, note: "No") }
            let request = try #require(StubURLProtocol.requests.first)
            #expect(request.url?.absoluteString.hasSuffix(path) == true, "\(path)")
            #expect(request.httpMethod == "POST")
        }
    }
}
